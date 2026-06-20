import os
import base64
import hashlib
import hmac
import json
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from app.config import env_int, env_str
from app.database import execute, fetch_all, fetch_one, is_database_configured
from app.routers.analysis import analysis_job_store, analysis_store
from app.routers.auth import verify_password
from app.routers.upload import file_store, voice_sample_store
from app.services.cognitive_model import get_model_status
from app.services.retention_policy import (
    AUDIO_RETENTION_DAYS,
    DELETE_VOICE_SAMPLE_AFTER_ANALYSIS,
    RESULT_RETENTION_DAYS,
    VOICE_SAMPLE_RETENTION_DAYS,
    ensure_retention_schema,
    purge_expired_data,
)

router = APIRouter()

ADMIN_TOKEN_TTL_SECONDS = env_int("SORIMEMO_ADMIN_TOKEN_TTL_SECONDS", "28800")
_ADMIN_TOKEN_SECRET = env_str("SORIMEMO_ADMIN_SECRET_KEY") or base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


class AdminLoginRequest(BaseModel):
    admin_id: str = Field(min_length=1)
    password: str = Field(min_length=1)


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    admin_id: str
    role: str


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def _sign_token(unsigned_token: str) -> str:
    return _b64_encode(hmac.new(
        _ADMIN_TOKEN_SECRET.encode("utf-8"),
        unsigned_token.encode("ascii"),
        hashlib.sha256,
    ).digest())


def _create_admin_token(admin_id: str, role: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": admin_id,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + ADMIN_TOKEN_TTL_SECONDS,
    }
    unsigned = f"{_b64_encode(json.dumps(header, separators=(',', ':')).encode('utf-8'))}.{_b64_encode(json.dumps(payload, separators=(',', ':')).encode('utf-8'))}"
    return f"{unsigned}.{_sign_token(unsigned)}"


def _verify_admin_token(token: str) -> dict:
    try:
        header, payload, signature = token.split(".", 2)
        unsigned = f"{header}.{payload}"
        if not hmac.compare_digest(signature, _sign_token(unsigned)):
            raise ValueError("invalid signature")
        decoded = json.loads(_b64_decode(payload))
        if int(decoded.get("exp", 0)) < int(time.time()):
            raise ValueError("expired token")
        if decoded.get("role") not in {"admin", "operator"}:
            raise ValueError("invalid role")
        return decoded
    except Exception as exc:
        raise HTTPException(status_code=401, detail="관리자 인증이 필요합니다.") from exc


def require_admin(authorization: str | None = Header(default=None, alias="Authorization")) -> dict:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="관리자 인증이 필요합니다.")
    return _verify_admin_token(token)


def _env_admin_login(admin_id: str, password: str) -> tuple[str, str] | None:
    configured_id = env_str("SORIMEMO_ADMIN_USERNAME", "").strip()
    configured_password = env_str("SORIMEMO_ADMIN_PASSWORD", "")
    configured_hash = env_str("SORIMEMO_ADMIN_PASSWORD_HASH", "").strip()
    if not configured_id or configured_id != admin_id:
        return None
    if configured_hash and verify_password(password, configured_hash):
        return configured_id, "admin"
    if configured_password and hmac.compare_digest(configured_password, password):
        return configured_id, "admin"
    return None


def _db_admin_login(admin_id: str, password: str) -> tuple[str, str] | None:
    if not is_database_configured():
        return None
    row = fetch_one(
        """
        SELECT id, email, password_hash, role, status
        FROM users
        WHERE (lower(email) = lower(:admin_id) OR id::text = :admin_id)
          AND role IN ('admin', 'operator')
        """,
        {"admin_id": admin_id.strip()},
    )
    if not row or row.get("status") != "active" or not row.get("password_hash"):
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return row.get("email") or str(row["id"]), row["role"]


def _safe_execute(query: str, params: dict | None = None) -> None:
    try:
        execute(query, params)
    except SQLAlchemyError:
        return


def _audit_admin_action(
    request: Request | None,
    claims: dict | None,
    action: str,
    target_type: str,
    target_id: str | None = None,
) -> None:
    actor = (claims or {}).get("sub") or "admin"
    role = (claims or {}).get("role") or "admin"
    _safe_execute(
        """
        INSERT INTO audit_logs (actor, actor_role, action, target_type, target_id, ip_address, user_agent)
        VALUES (:actor, :actor_role, :action, :target_type, CAST(:target_id AS uuid), CAST(:ip_address AS inet), :user_agent)
        """,
        {
            "actor": actor,
            "actor_role": role,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "ip_address": request.client.host if request and request.client else None,
            "user_agent": request.headers.get("user-agent") if request else None,
        },
    )


@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(payload: AdminLoginRequest, request: Request):
    admin_id = payload.admin_id.strip()
    login_result = _db_admin_login(admin_id, payload.password) or _env_admin_login(admin_id, payload.password)
    if not login_result:
        _audit_admin_action(request, {"sub": admin_id, "role": "admin"}, "admin_login_failed", "admin_session")
        raise HTTPException(status_code=401, detail="관리자 ID 또는 비밀번호를 확인해 주세요.")

    resolved_id, role = login_result
    _audit_admin_action(request, {"sub": resolved_id, "role": role}, "admin_login_success", "admin_session")
    return AdminLoginResponse(
        access_token=_create_admin_token(resolved_id, role),
        expires_in=ADMIN_TOKEN_TTL_SECONDS,
        admin_id=resolved_id,
        role=role,
    )


def _dir_size(path: str) -> int:
    total = 0
    root = Path(path)
    if not root.exists():
        return 0
    for item in root.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def _safe_fetch_one(query: str, fallback: dict | None = None) -> dict:
    try:
        return fetch_one(query) or fallback or {}
    except SQLAlchemyError:
        return fallback or {}


def _safe_fetch_all(query: str) -> list[dict]:
    try:
        return fetch_all(query)
    except SQLAlchemyError:
        return []


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _risk_label(cognitive_status: str | None, risk_level: str | None) -> str:
    status = (cognitive_status or "").upper()
    level = (risk_level or "").lower()
    if "AD" in status or level in {"high", "critical"}:
        return "AD 의심"
    if "MCI" in status or level in {"moderate", "medium"}:
        return "MCI 의심"
    return "Normal"


def _quality_label(quality_pass, rejection_reason: str | None) -> str:
    if quality_pass is True:
        return "좋음"
    if quality_pass is False:
        return "부족"
    return "부족" if rejection_reason else "보통"


@router.get("/dashboard")
async def get_admin_dashboard(request: Request, admin_claims: dict = Depends(require_admin)):
    _audit_admin_action(request, admin_claims, "admin_dashboard_view", "admin_dashboard")
    ensure_retention_schema()
    model_status = get_model_status()
    stats = _safe_fetch_one(
        """
        SELECT
          (SELECT count(*) FROM analysis_results) AS completed,
          (SELECT count(*) FROM audio_files) AS uploaded,
          (SELECT count(*) FROM audio_files WHERE quality_pass IS true) AS quality_passed,
          (SELECT count(*) FROM audio_files WHERE raw_deleted_at IS NULL) AS raw_retained,
          (SELECT count(*) FROM voice_samples) AS voice_sample_count,
          (SELECT extract(epoch FROM max(created_at)) FROM analysis_results) AS latest_analysis
        """
    )
    completed = int(stats.get("completed") or len(analysis_store))
    uploaded = int(stats.get("uploaded") or len(file_store))
    quality_passed = int(
        stats.get("quality_passed")
        or sum(1 for item in file_store.values() if item["quality"].get("quality_pass"))
    )
    raw_retained = int(stats.get("raw_retained") or sum(1 for item in file_store.values() if item.get("raw_path")))
    latest_analysis = stats.get("latest_analysis") or max((item["created_at"] for item in analysis_store.values()), default=None)
    recent_jobs = _safe_fetch_all(
        """
        SELECT id, status, error_message, created_at, started_at, completed_at
        FROM analysis_jobs
        ORDER BY created_at DESC
        LIMIT 5
        """
    )
    recent_results = _safe_fetch_all(
        """
        SELECT ar.id, ar.cognitive_status, ar.risk_level, ar.risk_score, ar.confidence_score, ar.model_probabilities, ar.created_at
        FROM analysis_results ar
        ORDER BY ar.created_at DESC
        LIMIT 5
        """
    )
    user_rows = _safe_fetch_all(
        """
        SELECT
          u.id,
          u.email,
          COALESCE(u.display_name, u.user_name) AS user_name,
          u.signup_purpose,
          u.age_group,
          u.role,
          u.status,
          u.created_at,
          u.last_login_at,
          latest.id AS latest_analysis_id,
          latest.cognitive_status,
          latest.risk_level,
          latest.confidence_score,
          latest.created_at AS latest_analysis_at,
          subject.subject_type,
          subject.relation AS subject_relation,
          subject.display_name AS subject_name,
          subject.age_group AS subject_age_group,
          subject.gender AS subject_gender
        FROM users u
        LEFT JOIN LATERAL (
          SELECT subject_type, relation, display_name, age_group, gender
          FROM care_subjects
          WHERE user_id = u.id
          ORDER BY created_at DESC
          LIMIT 1
        ) subject ON true
        LEFT JOIN LATERAL (
          SELECT ar.id, ar.cognitive_status, ar.risk_level, ar.confidence_score, ar.created_at
          FROM analysis_results ar
          LEFT JOIN analysis_jobs aj ON aj.id = ar.job_id
          WHERE aj.user_id = u.id
          ORDER BY ar.created_at DESC
          LIMIT 1
        ) latest ON true
        WHERE u.role = 'user'
        ORDER BY COALESCE(latest.created_at, u.created_at) DESC
        LIMIT 30
        """
    )
    audio_rows = _safe_fetch_all(
        """
        SELECT
          af.id,
          af.user_id,
          COALESCE(cs.display_name, u.display_name, u.user_name) AS subject_name,
          cs.subject_type,
          cs.relation AS subject_relation,
          cs.age_group AS subject_age_group,
          cs.gender AS subject_gender,
          af.original_filename,
          af.duration_seconds,
          af.quality_pass,
          af.rejection_reason,
          af.status,
          af.uploaded_at,
          aj.id AS job_id,
          aj.status AS job_status,
          aj.error_message,
          ar.id AS analysis_id,
          u.email
        FROM audio_files af
        LEFT JOIN users u ON u.id = af.user_id
        LEFT JOIN consents c ON c.id = af.consent_id
        LEFT JOIN care_subjects cs ON cs.id = c.subject_id
        LEFT JOIN LATERAL (
          SELECT id, status, error_message
          FROM analysis_jobs
          WHERE audio_file_id = af.id
          ORDER BY created_at DESC
          LIMIT 1
        ) aj ON true
        LEFT JOIN LATERAL (
          SELECT id
          FROM analysis_results
          WHERE audio_file_id = af.id
          ORDER BY created_at DESC
          LIMIT 1
        ) ar ON true
        ORDER BY af.uploaded_at DESC
        LIMIT 30
        """
    )
    result_rows = _safe_fetch_all(
        """
        SELECT
          ar.id,
          ar.audio_file_id,
          ar.cognitive_status,
          ar.risk_level,
          ar.risk_score,
          ar.confidence_score,
          ar.model_probabilities,
          ar.result_payload,
          ar.created_at,
          af.quality_pass,
          af.rejection_reason,
          af.duration_seconds,
          COALESCE(cs.display_name, u.display_name, u.user_name) AS subject_name,
          cs.subject_type,
          cs.relation AS subject_relation,
          cs.age_group AS subject_age_group,
          cs.gender AS subject_gender,
          u.email
        FROM analysis_results ar
        LEFT JOIN audio_files af ON af.id = ar.audio_file_id
        LEFT JOIN analysis_jobs aj ON aj.id = ar.job_id
        LEFT JOIN users u ON u.id = COALESCE(aj.user_id, af.user_id)
        LEFT JOIN consents c ON c.id = af.consent_id
        LEFT JOIN care_subjects cs ON cs.id = c.subject_id
        ORDER BY ar.created_at DESC
        LIMIT 30
        """
    )
    training_rows = _safe_fetch_all(
        """
        SELECT
          c.id AS consent_id,
          c.agreed_at,
          c.model_training_retention_days,
          u.email,
          COALESCE(u.display_name, u.user_name) AS user_name,
          COALESCE(cs.display_name, u.display_name, u.user_name) AS subject_name,
          cs.subject_type,
          cs.relation AS subject_relation,
          cs.age_group AS subject_age_group,
          af.id AS audio_file_id,
          af.original_filename,
          af.status AS audio_status,
          af.storage_path,
          af.wav_path,
          af.raw_deleted_at,
          af.uploaded_at
        FROM consents c
        LEFT JOIN users u ON u.id = c.user_id
        LEFT JOIN care_subjects cs ON cs.id = c.subject_id
        LEFT JOIN LATERAL (
          SELECT id, original_filename, status, storage_path, wav_path, raw_deleted_at, uploaded_at
          FROM audio_files
          WHERE consent_id = c.id
          ORDER BY uploaded_at DESC
          LIMIT 1
        ) af ON true
        WHERE c.model_training_agreed IS true
          AND c.revoked_at IS NULL
        ORDER BY COALESCE(af.uploaded_at, c.agreed_at) DESC
        LIMIT 30
        """
    )
    audit_rows = _safe_fetch_all(
        """
        SELECT id, actor, actor_role, action, target_type, target_id, created_at
        FROM audit_logs
        ORDER BY created_at DESC
        LIMIT 30
        """
    )
    deleted_stats = _safe_fetch_one(
        """
        SELECT
          (SELECT count(*) FROM audio_files WHERE deleted_at IS NOT NULL) AS audio_deleted,
          (SELECT count(*) FROM voice_samples WHERE deleted_at IS NOT NULL) AS voice_samples_deleted,
          (SELECT count(*) FROM consents WHERE revoked_at IS NOT NULL) AS consents_revoked,
          (SELECT count(*) FROM consents WHERE model_training_agreed IS true AND revoked_at IS NULL) AS model_training_consents,
          (SELECT COALESCE(max(model_training_retention_days), 0) FROM consents WHERE model_training_agreed IS true AND revoked_at IS NULL) AS model_training_retention_days,
          (
            SELECT count(DISTINCT af.id)
            FROM audio_files af
            JOIN consents c ON c.id = af.consent_id
            WHERE c.model_training_agreed IS true
              AND c.revoked_at IS NULL
              AND af.raw_deleted_at IS NULL
          ) AS training_audio_retained
        """
    )

    try:
        load_1m, load_5m, load_15m = os.getloadavg()
    except OSError:
        load_1m, load_5m, load_15m = 0.0, 0.0, 0.0

    return {
        "system": {
            "status": "stable",
            "cpu_load_1m": round(load_1m, 2),
            "cpu_load_5m": round(load_5m, 2),
            "cpu_load_15m": round(load_15m, 2),
            "active_ai_nodes": 1 if model_status.get("available") else 0,
            "max_ai_nodes": 1,
            "requests_completed": completed,
        },
        "pipeline": {
            "mobile_capture": {"status": "live", "queue": uploaded},
            "data_processing": {"status": "ready", "quality_passed": quality_passed},
            "feature_engine": {"status": "ready", "feature_vectors": completed},
            "model_layer": {
                "status": "ready" if model_status.get("available") else "unavailable",
                "model_source": model_status.get("model_source"),
                "classes": model_status.get("class_names", []),
                "accuracy": model_status.get("test_metrics", {}).get("accuracy"),
                "epochs_trained": model_status.get("epochs_trained"),
                "model_path": model_status.get("model_path"),
                "runtime": model_status.get("runtime", {}),
            },
        },
        "storage": {
            "raw_audio_retained_count": raw_retained,
            "feature_result_count": completed,
            "upload_temp_bytes": _dir_size(env_str("SORIMEMO_UPLOAD_DIR", "/tmp/sorimemo_uploads")),
            "processed_temp_bytes": _dir_size(env_str("SORIMEMO_PROCESSED_DIR", "/tmp/sorimemo_processed")),
            "voice_sample_count": int(stats.get("voice_sample_count") or len(voice_sample_store)),
            "audio_deleted_count": int(deleted_stats.get("audio_deleted") or 0),
            "voice_samples_deleted_count": int(deleted_stats.get("voice_samples_deleted") or 0),
        },
        "governance": {
            "consent_required": True,
            "non_medical_notice_enabled": True,
            "original_audio_cleanup_enabled": True,
            "feature_vector_storage_only_after_analysis": True,
            "consents_revoked_count": int(deleted_stats.get("consents_revoked") or 0),
            "model_training": {
                "enabled": True,
                "retention_days": int(deleted_stats.get("model_training_retention_days") or 1095),
                "consent_count": int(deleted_stats.get("model_training_consents") or 0),
                "audio_retained_count": int(deleted_stats.get("training_audio_retained") or 0),
                "upload_dir": env_str("SORIMEMO_UPLOAD_DIR", "/tmp/sorimemo_uploads"),
                "voice_samples_dir": env_str("SORIMEMO_VOICE_SAMPLES_DIR", "/tmp/sorimemo_voice_samples"),
            },
            "retention": {
                "result_retention_days": RESULT_RETENTION_DAYS,
                "audio_retention_days": AUDIO_RETENTION_DAYS,
                "voice_sample_retention_days": VOICE_SAMPLE_RETENTION_DAYS,
                "delete_voice_sample_after_analysis": DELETE_VOICE_SAMPLE_AFTER_ANALYSIS,
            },
        },
        "operations": {
            "recent_jobs": [
                {
                    "job_id": str(row["id"]),
                    "status": row["status"],
                    "error_message": row["error_message"],
                    "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
                    "started_at": row["started_at"].isoformat() if row.get("started_at") else None,
                    "completed_at": row["completed_at"].isoformat() if row.get("completed_at") else None,
                }
                for row in recent_jobs
            ],
            "recent_results": [
                {
                    "analysis_id": str(row["id"]),
                    "cognitive_status": row["cognitive_status"],
                    "risk_level": row["risk_level"],
                    "risk_score": float(row["risk_score"] or 0),
                    "confidence_score": float(row["confidence_score"] or 0),
                    "model_probabilities": row.get("model_probabilities") or {},
                    "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
                }
                for row in recent_results
            ],
            "memory_jobs": len(analysis_job_store),
        },
        "management": {
            "users": [
                {
                    "id": str(row["id"]),
                    "email": row.get("email"),
                    "user_name": row.get("user_name") or row.get("email") or "사용자",
                    "signup_purpose": row.get("signup_purpose"),
                    "subject_type": row.get("subject_type"),
                    "subject_relation": row.get("subject_relation"),
                    "subject_name": row.get("subject_name"),
                    "subject_age_group": row.get("subject_age_group"),
                    "subject_gender": row.get("subject_gender"),
                    "age_group": row.get("age_group") or "-",
                    "role": row.get("role"),
                    "status": row.get("status"),
                    "created_at": _iso(row.get("created_at")),
                    "last_login_at": _iso(row.get("last_login_at")),
                    "latest_analysis_id": str(row["latest_analysis_id"]) if row.get("latest_analysis_id") else None,
                    "latest_analysis_at": _iso(row.get("latest_analysis_at")),
                    "latest_result": _risk_label(row.get("cognitive_status"), row.get("risk_level")),
                    "confidence_score": float(row.get("confidence_score") or 0),
                }
                for row in user_rows
            ],
            "audio_files": [
                {
                    "id": str(row["id"]),
                    "user_id": str(row["user_id"]) if row.get("user_id") else None,
                    "user_name": row.get("subject_name") or "사용자",
                    "login_id": row.get("email"),
                    "subject_type": row.get("subject_type"),
                    "subject_relation": row.get("subject_relation"),
                    "subject_age_group": row.get("subject_age_group"),
                    "subject_gender": row.get("subject_gender"),
                    "original_filename": row.get("original_filename"),
                    "duration_seconds": float(row.get("duration_seconds") or 0),
                    "quality": _quality_label(row.get("quality_pass"), row.get("rejection_reason")),
                    "separation_status": "실패" if row.get("job_status") == "failed" else "완료" if row.get("job_id") else "대기",
                    "analysis_status": "분석 완료" if row.get("analysis_id") else "재처리 필요" if row.get("job_status") == "failed" else "대기",
                    "status": row.get("status"),
                    "error_message": row.get("error_message"),
                    "uploaded_at": _iso(row.get("uploaded_at")),
                }
                for row in audio_rows
            ],
            "analysis_results": [
                {
                    "id": str(row["id"]),
                    "audio_file_id": str(row["audio_file_id"]) if row.get("audio_file_id") else None,
                    "user_name": row.get("subject_name") or "사용자",
                    "login_id": row.get("email"),
                    "subject_type": row.get("subject_type"),
                    "subject_relation": row.get("subject_relation"),
                    "subject_age_group": row.get("subject_age_group"),
                    "subject_gender": row.get("subject_gender"),
                    "result": _risk_label(row.get("cognitive_status"), row.get("risk_level")),
                    "cognitive_status": row.get("cognitive_status"),
                    "risk_level": row.get("risk_level"),
                    "risk_score": float(row.get("risk_score") or 0),
                    "confidence_score": float(row.get("confidence_score") or 0),
                    "model_probabilities": row.get("model_probabilities") or {},
                    "quality": _quality_label(row.get("quality_pass"), row.get("rejection_reason")),
                    "duration_seconds": float(row.get("duration_seconds") or 0),
                    "recommendation": (row.get("result_payload") or {}).get("recommendation")
                    if isinstance(row.get("result_payload"), dict)
                    else None,
                    "created_at": _iso(row.get("created_at")),
                }
                for row in result_rows
            ],
            "training_consents": [
                {
                    "consent_id": str(row["consent_id"]),
                    "login_id": row.get("email"),
                    "account_name": row.get("user_name") or row.get("email") or "사용자",
                    "subject_name": row.get("subject_name") or "-",
                    "subject_type": row.get("subject_type"),
                    "subject_relation": row.get("subject_relation"),
                    "subject_age_group": row.get("subject_age_group"),
                    "retention_days": int(row.get("model_training_retention_days") or 1095),
                    "audio_file_id": str(row["audio_file_id"]) if row.get("audio_file_id") else None,
                    "original_filename": row.get("original_filename"),
                    "audio_status": row.get("audio_status"),
                    "storage_path": row.get("storage_path"),
                    "wav_path": row.get("wav_path"),
                    "raw_deleted_at": _iso(row.get("raw_deleted_at")),
                    "uploaded_at": _iso(row.get("uploaded_at")),
                    "agreed_at": _iso(row.get("agreed_at")),
                }
                for row in training_rows
            ],
            "audit_logs": [
                {
                    "id": str(row["id"]),
                    "actor": row.get("actor") or "system",
                    "actor_role": row.get("actor_role"),
                    "action": row.get("action"),
                    "target_type": row.get("target_type"),
                    "target_id": str(row["target_id"]) if row.get("target_id") else None,
                    "created_at": _iso(row.get("created_at")),
                }
                for row in audit_rows
            ],
        },
        "alerts": [
            {
                "level": "warning",
                "message": "학습 모델을 사용할 수 없습니다. 모델 경로를 확인해 주세요.",
                "created_at": time.time(),
            }
        ] if not model_status.get("available") else [],
        "latest_analysis_at": latest_analysis,
    }


@router.post("/retention/cleanup")
async def cleanup_expired_retention(request: Request, admin_claims: dict = Depends(require_admin)):
    _audit_admin_action(request, admin_claims, "admin_retention_cleanup", "retention_policy")
    return {
        "message": "만료된 보관 데이터 정리를 완료했습니다.",
        "cleanup": purge_expired_data(),
    }
