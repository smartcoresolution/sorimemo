import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from app.database import execute, execute_many, fetch_one, get_consent_by_token, insert_returning
from app.models.schemas import ConsentRequest, ConsentResponse
from app.routers.auth import get_current_user

router = APIRouter()

# In-memory consent store
consent_store: dict[str, dict] = {}

POLICY_VERSION = "1.0.0"
RETENTION_PERIOD_DAYS = 90
TRAINING_RETENTION_PERIOD_DAYS = 1095


class ConsentSubjectRequest(BaseModel):
    subject_type: str = Field(default="parent")
    subject_relation: str | None = None
    subject_display_name: str = Field(min_length=1, max_length=80)
    subject_age_group: str = Field(default="other")
    subject_gender: str | None = None


def ensure_subject_schema() -> None:
    try:
        execute_many([
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name text",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS signup_purpose text NOT NULL DEFAULT 'parent_care'",
            """
            CREATE TABLE IF NOT EXISTS care_subjects (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                subject_type text NOT NULL DEFAULT 'parent',
                relation text,
                display_name text,
                age_group text,
                gender text,
                status text NOT NULL DEFAULT 'active',
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now()
            )
            """,
            "ALTER TABLE consents ADD COLUMN IF NOT EXISTS subject_id uuid REFERENCES care_subjects(id) ON DELETE SET NULL",
            "ALTER TABLE consents ADD COLUMN IF NOT EXISTS model_training_agreed boolean NOT NULL DEFAULT false",
            "ALTER TABLE consents ADD COLUMN IF NOT EXISTS model_training_retention_days integer",
            "CREATE INDEX IF NOT EXISTS idx_care_subjects_user ON care_subjects(user_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_consents_subject ON consents(subject_id)",
            "CREATE INDEX IF NOT EXISTS idx_consents_model_training ON consents(model_training_agreed)",
        ])
    except SQLAlchemyError:
        return


@router.post("/agree", response_model=ConsentResponse)
async def submit_consent(request: ConsentRequest, current_user: dict = Depends(get_current_user)):
    if not all([
        request.data_collection_agreed,
        request.privacy_policy_agreed,
        request.non_medical_disclaimer_agreed,
        request.third_party_voice_agreed,
    ]):
        raise HTTPException(
            status_code=400,
            detail="모든 동의 항목에 동의해야 서비스를 이용할 수 있습니다."
        )

    ensure_subject_schema()
    normalized_name = (request.user_name or "").strip() or None
    subject_type = "self" if request.subject_type == "self" else "parent"
    subject_relation = (request.subject_relation or ("self" if subject_type == "self" else "mother")).strip()
    subject_display_name = (request.subject_display_name or ("본인" if subject_type == "self" else "부모님")).strip()
    subject_gender = (request.subject_gender or "").strip() or None

    consent_token = str(uuid.uuid4())
    consent_data = {
        "user_name": normalized_name,
        "age_group": request.age_group,
        "agreed_at": datetime.now(timezone.utc).isoformat(),
        "policy_version": POLICY_VERSION,
        "items": {
            "data_collection": request.data_collection_agreed,
            "privacy_policy": request.privacy_policy_agreed,
            "non_medical_disclaimer": request.non_medical_disclaimer_agreed,
            "third_party_voice": request.third_party_voice_agreed,
            "model_training": request.model_training_agreed,
        },
    }

    execute(
        """
        UPDATE users
        SET user_name = COALESCE(:user_name, user_name),
            display_name = COALESCE(:user_name, display_name),
            age_group = :age_group,
            updated_at = now()
        WHERE id = CAST(:user_id AS uuid)
        """,
        {
            "user_id": current_user["user_id"],
            "user_name": normalized_name,
            "age_group": request.age_group.value,
        },
    )
    subject_row = insert_returning(
        """
        INSERT INTO care_subjects (
            user_id, subject_type, relation, display_name, age_group, gender, updated_at
        )
        VALUES (
            CAST(:user_id AS uuid), :subject_type, :relation, :display_name, :age_group, :gender, now()
        )
        RETURNING id
        """,
        {
            "user_id": current_user["user_id"],
            "subject_type": subject_type,
            "relation": subject_relation,
            "display_name": subject_display_name,
            "age_group": request.subject_age_group.value,
            "gender": subject_gender,
        },
    )
    db_row = insert_returning(
        """
        INSERT INTO consents (
            user_id,
            subject_id,
            consent_token,
            policy_version,
            data_collection_agreed,
            privacy_policy_agreed,
            non_medical_disclaimer_agreed,
            third_party_voice_agreed,
            model_training_agreed,
            model_training_retention_days
        )
        VALUES (
            CAST(:user_id AS uuid),
            CAST(:subject_id AS uuid),
            CAST(:consent_token AS uuid),
            :policy_version,
            :data_collection_agreed,
            :privacy_policy_agreed,
            :non_medical_disclaimer_agreed,
            :third_party_voice_agreed,
            :model_training_agreed,
            :model_training_retention_days
        )
        RETURNING id, user_id
        """,
        {
            "user_id": current_user["user_id"],
            "subject_id": str(subject_row["id"]),
            "consent_token": consent_token,
            "policy_version": POLICY_VERSION,
            "data_collection_agreed": request.data_collection_agreed,
            "privacy_policy_agreed": request.privacy_policy_agreed,
            "non_medical_disclaimer_agreed": request.non_medical_disclaimer_agreed,
            "third_party_voice_agreed": request.third_party_voice_agreed,
            "model_training_agreed": request.model_training_agreed,
            "model_training_retention_days": TRAINING_RETENTION_PERIOD_DAYS if request.model_training_agreed else None,
        },
    )
    consent_data["db_id"] = str(db_row["id"])
    consent_data["user_id"] = str(db_row["user_id"])
    consent_data["subject_id"] = str(subject_row["id"])
    consent_store[consent_token] = consent_data

    return ConsentResponse(
        consent_token=consent_token,
        policy_version=POLICY_VERSION,
        retention_period_days=RETENTION_PERIOD_DAYS,
        message="동의가 완료되었습니다. 이 토큰을 사용하여 서비스를 이용하세요.",
    )


@router.post("/{consent_token}/subject")
async def upsert_consent_subject(
    consent_token: str,
    request: ConsentSubjectRequest,
    current_user: dict = Depends(get_current_user),
):
    ensure_subject_schema()
    row = get_consent_by_token(consent_token)
    if not row:
        raise HTTPException(status_code=404, detail="유효하지 않은 동의 토큰입니다.")
    if str(row["user_id"]) != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="현재 사용자에게 속한 동의 토큰이 아닙니다.")

    subject_type = "self" if request.subject_type == "self" else "parent"
    relation = (request.subject_relation or ("self" if subject_type == "self" else "mother")).strip()
    display_name = request.subject_display_name.strip()
    gender = (request.subject_gender or "").strip() or None
    subject_id = str(row["subject_id"]) if row.get("subject_id") else None

    if subject_id:
        execute(
            """
            UPDATE care_subjects
            SET subject_type = :subject_type,
                relation = :relation,
                display_name = :display_name,
                age_group = :age_group,
                gender = :gender,
                updated_at = now()
            WHERE id = CAST(:subject_id AS uuid)
              AND user_id = CAST(:user_id AS uuid)
            """,
            {
                "subject_id": subject_id,
                "user_id": current_user["user_id"],
                "subject_type": subject_type,
                "relation": relation,
                "display_name": display_name,
                "age_group": request.subject_age_group,
                "gender": gender,
            },
        )
    else:
        subject_row = insert_returning(
            """
            INSERT INTO care_subjects (
                user_id, subject_type, relation, display_name, age_group, gender, updated_at
            )
            VALUES (
                CAST(:user_id AS uuid), :subject_type, :relation, :display_name, :age_group, :gender, now()
            )
            RETURNING id
            """,
            {
                "user_id": current_user["user_id"],
                "subject_type": subject_type,
                "relation": relation,
                "display_name": display_name,
                "age_group": request.subject_age_group,
                "gender": gender,
            },
        )
        subject_id = str(subject_row["id"])
        execute(
            """
            UPDATE consents
            SET subject_id = CAST(:subject_id AS uuid)
            WHERE consent_token = CAST(:consent_token AS uuid)
              AND user_id = CAST(:user_id AS uuid)
            """,
            {
                "subject_id": subject_id,
                "consent_token": consent_token,
                "user_id": current_user["user_id"],
            },
        )

    return {
        "subject_id": subject_id,
        "subject_type": subject_type,
        "subject_relation": relation,
        "subject_display_name": display_name,
        "subject_age_group": request.subject_age_group,
        "subject_gender": gender,
        "message": "검증 대상자 정보가 저장되었습니다.",
    }


@router.get("/latest")
async def latest_consent(current_user: dict = Depends(get_current_user)):
    ensure_subject_schema()
    row = fetch_one(
        """
        SELECT
            c.id,
            c.subject_id,
            c.consent_token,
            c.policy_version,
            c.agreed_at,
            c.model_training_agreed,
            c.model_training_retention_days,
            s.subject_type,
            s.relation AS subject_relation,
            s.display_name AS subject_display_name,
            s.age_group AS subject_age_group,
            s.gender AS subject_gender
        FROM consents c
        LEFT JOIN care_subjects s ON s.id = c.subject_id
        WHERE c.user_id = CAST(:user_id AS uuid)
          AND c.revoked_at IS NULL
          AND c.policy_version = :policy_version
          AND c.data_collection_agreed IS true
          AND c.privacy_policy_agreed IS true
          AND c.non_medical_disclaimer_agreed IS true
          AND c.third_party_voice_agreed IS true
        ORDER BY c.agreed_at DESC
        LIMIT 1
        """,
        {
            "user_id": current_user["user_id"],
            "policy_version": POLICY_VERSION,
        },
    )
    if not row:
        raise HTTPException(status_code=404, detail="현재 정책 버전에 대한 동의 기록이 없습니다.")
    return {
        "consent_token": str(row["consent_token"]),
        "policy_version": row["policy_version"],
        "agreed_at": row["agreed_at"].isoformat() if row.get("agreed_at") else None,
        "subject_id": str(row["subject_id"]) if row.get("subject_id") else None,
        "subject_type": row.get("subject_type"),
        "subject_relation": row.get("subject_relation"),
        "subject_display_name": row.get("subject_display_name"),
        "subject_age_group": row.get("subject_age_group"),
        "subject_gender": row.get("subject_gender"),
        "model_training_agreed": bool(row.get("model_training_agreed")),
        "model_training_retention_days": row.get("model_training_retention_days"),
    }


@router.get("/verify/{consent_token}")
async def verify_consent(consent_token: str, current_user: dict = Depends(get_current_user)):
    consent = consent_store.get(consent_token)
    if not consent:
        row = get_consent_by_token(consent_token)
        if row:
            consent = {
                "db_id": str(row["id"]),
                "user_id": str(row["user_id"]),
                "user_name": row["user_name"],
                "age_group": row["age_group"],
                "agreed_at": row["agreed_at"].isoformat(),
                "policy_version": row["policy_version"],
                "items": {
                    "data_collection": row["data_collection_agreed"],
                    "privacy_policy": row["privacy_policy_agreed"],
                    "non_medical_disclaimer": row["non_medical_disclaimer_agreed"],
                    "third_party_voice": row["third_party_voice_agreed"],
                    "model_training": bool(row.get("model_training_agreed")),
                },
            }
            consent_store[consent_token] = consent

    if not consent:
        raise HTTPException(status_code=404, detail="유효하지 않은 동의 토큰입니다.")
    if str(consent.get("user_id")) != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="현재 사용자에게 속한 동의 토큰이 아닙니다.")
    return {"valid": True, "consent": consent}


@router.get("/policy")
async def get_policy():
    return {
        "version": POLICY_VERSION,
        "title": "안심소리 기억케어 데이터 처리 및 개인정보 보호 정책",
        "sections": [
            {
                "title": "서비스 목적",
                "content": (
                    "안심소리 기억케어는 통화 음성을 분석하여 인지기능 변화와 연관될 수 있는 "
                    "위험 신호를 비의료적으로 선별하는 참고용 서비스입니다. "
                    "본 서비스는 의료 진단을 목적으로 하지 않습니다."
                ),
            },
            {
                "title": "데이터 수집 범위",
                "content": (
                    "통화 녹음 파일, 연령대 정보를 수집합니다. "
                    "음성 내 개인식별정보(PII)는 자동으로 마스킹 처리됩니다."
                ),
            },
            {
                "title": "데이터 보관 및 삭제",
                "content": (
                    f"기본 서비스 목적의 원본 음성 파일은 분석 완료 후 정해진 기간 내 삭제되며, "
                    f"익명화된 특징 데이터는 최대 {RETENTION_PERIOD_DAYS}일간 보관 후 자동 삭제됩니다. "
                    "사용자는 언제든지 데이터 삭제를 요청할 수 있습니다."
                ),
            },
            {
                "title": "AI 모델 개선 및 연구 활용",
                "content": (
                    "선택 동의한 경우에만 업로드 음성, 분석 결과, 연령대, 성별, 검증 유형 정보가 "
                    "개인 식별정보 제거 또는 가명처리 후 SoriMemo AI 모델 개선과 품질 평가 목적으로 활용될 수 있습니다. "
                    f"학습 활용 데이터의 보관 기간은 최대 {TRAINING_RETENTION_PERIOD_DAYS}일이며, 동의하지 않아도 서비스 이용에는 제한이 없습니다."
                ),
            },
            {
                "title": "제3자 음성 안내",
                "content": (
                    "통화 녹음에는 상대방의 음성이 포함될 수 있습니다. "
                    "상대방 음성은 분석에서 자동으로 분리 및 제외되며, 별도로 저장되지 않습니다."
                ),
            },
            {
                "title": "비의료적 서비스 고지",
                "content": (
                    "본 서비스의 분석 결과는 의료적 진단이나 치료 판단이 아닌, "
                    "인지기능 변화와 연관될 수 있는 위험 신호를 참고용으로 제공하는 "
                    "비의료적 정보입니다. 건강 관련 결정은 반드시 전문 의료기관과 상담하시기 바랍니다."
                ),
            },
        ],
        "consent_items": [
            {"key": "data_collection", "label": "데이터 수집 및 분석에 동의합니다.", "required": True},
            {"key": "privacy_policy", "label": "개인정보 처리 방침에 동의합니다.", "required": True},
            {"key": "non_medical_disclaimer", "label": "비의료적 서비스임을 이해하고 동의합니다.", "required": True},
            {"key": "third_party_voice", "label": "제3자 음성 포함 가능성을 이해하고 동의합니다.", "required": True},
            {
                "key": "model_training",
                "label": (
                    "AI 모델 개선 및 연구 활용에 동의합니다. 업로드 음성, 분석 결과, 연령대, 성별, 검증 유형 정보가 "
                    "개인 식별정보 제거 또는 가명처리 후 SoriMemo AI 모델 개선과 품질 평가 목적으로 활용될 수 있습니다. "
                    "이 항목은 선택 사항이며 동의하지 않아도 서비스를 이용할 수 있습니다."
                ),
                "required": False,
            },
        ],
    }
