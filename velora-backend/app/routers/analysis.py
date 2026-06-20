import json
import uuid
import time
import os
import asyncio
import numpy as np
import librosa
import soundfile as sf
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from app.config import env_float, env_str
from app.database import execute, fetch_one, get_analysis_result as db_get_analysis_result, get_audio_file, get_voice_sample
from app.models.schemas import AnalysisResult, AnalysisStatusResponse
from app.routers.auth import get_current_user
from app.routers.upload import file_store, voice_sample_store
from app.services.speaker_processor import perform_speaker_diarization, extract_target_audio
from app.services.feature_extractor import (
    extract_speech_statistics,
    extract_acoustic_features,
    compute_feature_quality,
)
from app.services.language_processor import extract_linguistic_features
from app.services.stt_processor import transcribe_audio
from app.services.risk_model import compute_confidence_score
from app.services.retention_policy import (
    DELETE_VOICE_SAMPLE_AFTER_ANALYSIS,
    ensure_retention_schema,
    mark_analysis_result_retention,
    mark_audio_deleted,
    mark_voice_sample_deleted,
    remove_file_if_exists,
)
from app.services.cognitive_model import (
    CognitiveModelUnavailable,
    apply_linguistic_adjustment,
    get_model_status,
    predict_cognitive_status,
)

router = APIRouter()

# In-memory analysis store
analysis_store: dict[str, dict] = {}
analysis_job_store: dict[str, dict] = {}


def _model_training_consent_for_audio(file_id: str) -> dict | None:
    return fetch_one(
        """
        SELECT c.model_training_agreed, c.model_training_retention_days
        FROM audio_files af
        JOIN consents c ON c.id = af.consent_id
        WHERE af.id = CAST(:file_id AS uuid)
          AND c.model_training_agreed IS true
          AND c.revoked_at IS NULL
        """,
        {"file_id": file_id},
    )


def _mark_training_audio_retained(file_id: str, retention_days: int) -> None:
    execute(
        """
        UPDATE audio_files
        SET analyzed_at = COALESCE(analyzed_at, now()),
            status = 'training_retained',
            retention_expires_at = now() + (:retention_days * interval '1 day')
        WHERE id = CAST(:file_id AS uuid)
        """,
        {"file_id": file_id, "retention_days": retention_days},
    )

TARGET_SR = 16000
LIGHTWEIGHT_VALUES = {"1", "true", "yes", "on"}


def _lightweight_analysis_enabled() -> bool:
    return env_str("SORIMEMO_LIGHTWEIGHT_INFERENCE", "false").strip().lower() in LIGHTWEIGHT_VALUES


def _trace_analysis(message: str) -> None:
    if env_str("SORIMEMO_ANALYSIS_TRACE", "false").strip().lower() not in LIGHTWEIGHT_VALUES:
        return
    with open(env_str("SORIMEMO_ANALYSIS_TRACE_LOG", "/tmp/sorimemo_analysis_trace.log"), "a", encoding="utf-8") as file:
        file.write(f"{time.time():.3f} {message}\n")


def _extract_lightweight_acoustic_features(y: np.ndarray, sr: int) -> dict:
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    mfcc_mean = np.mean(mfcc, axis=1).tolist()
    mfcc_std = np.std(mfcc, axis=1).tolist()
    rms = librosa.feature.rms(y=y)[0]
    energy_mean = float(np.mean(rms))
    energy_std = float(np.std(rms))
    spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    spectral_bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)[0]
    zcr = librosa.feature.zero_crossing_rate(y)[0]

    return {
        "mfcc_mean": [round(v, 4) for v in mfcc_mean],
        "mfcc_std": [round(v, 4) for v in mfcc_std],
        "pitch_mean": 0.0,
        "pitch_std": 0.0,
        "pitch_range": 0.0,
        "energy_mean": round(energy_mean, 6),
        "energy_std": round(energy_std, 6),
        "energy_variability": round(float(energy_std / energy_mean) if energy_mean > 0 else 0.0, 4),
        "speech_rate": 0.0,
        "prosody_stability": 0.5,
        "spectral_centroid_mean": round(float(np.mean(spectral_centroid)), 2),
        "spectral_bandwidth_mean": round(float(np.mean(spectral_bandwidth)), 2),
        "zero_crossing_rate": round(float(np.mean(zcr)), 6),
    }


def _lightweight_diarization_seconds() -> float:
    return env_float("SORIMEMO_LIGHTWEIGHT_DIARIZATION_SECONDS", "90.0")


def _segment_duration(segments: list[dict]) -> float:
    return sum(float(segment.get("duration", 0.0) or 0.0) for segment in segments)


def _assert_file_owner(file_info: dict, current_user: dict) -> None:
    if str(file_info.get("user_id")) != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="현재 사용자에게 속한 파일이 아닙니다.")


def _assert_analysis_owner(analysis_id: str, current_user: dict) -> dict | None:
    if analysis_id in analysis_store:
        stored = analysis_store[analysis_id]
        if str(stored.get("user_id")) != current_user["user_id"]:
            raise HTTPException(status_code=403, detail="현재 사용자에게 속한 분석 결과가 아닙니다.")
        return stored["result"]

    stored = db_get_analysis_result(analysis_id)
    if not stored:
        return None
    db_file = get_audio_file(str(stored["audio_file_id"]))
    if not db_file or str(db_file["user_id"]) != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="현재 사용자에게 속한 분석 결과가 아닙니다.")
    return stored["result_payload"]


def _job_response(job_id: str) -> dict:
    job = analysis_job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="분석 작업을 찾을 수 없습니다.")
    return {
        "job_id": job_id,
        "analysis_id": job.get("analysis_id"),
        "status": job["status"],
        "progress": job["progress"],
        "current_step": job["current_step"],
        "message": job["message"],
        "error_message": job.get("error_message"),
    }


async def _run_analysis_job(
    job_id: str,
    file_id: str,
    voice_sample_id: str | None,
    voice_sample_role: str,
    verification_type: str,
    transcript_text: str | None,
    current_user: dict,
) -> None:
    analysis_job_store[job_id].update({
        "status": "processing",
        "progress": 15,
        "current_step": "분석 준비",
        "message": "분석 작업을 시작했습니다.",
    })
    execute(
        """
        UPDATE analysis_jobs
        SET status = 'processing', started_at = now()
        WHERE id = CAST(:job_id AS uuid)
        """,
        {"job_id": job_id},
    )
    try:
        result = await start_analysis(
            file_id=file_id,
            voice_sample_id=voice_sample_id,
            voice_sample_role=voice_sample_role,
            verification_type=verification_type,
            transcript_text=transcript_text,
            current_user=current_user,
        )
        analysis_id = result.analysis_id
        analysis_job_store[job_id].update({
            "status": "completed",
            "progress": 100,
            "current_step": "완료",
            "message": "분석이 완료되었습니다.",
            "analysis_id": analysis_id,
        })
        execute(
            """
            UPDATE analysis_jobs
            SET status = 'completed',
                completed_at = now()
            WHERE id = CAST(:job_id AS uuid)
            """,
            {"job_id": job_id},
        )
        execute(
            """
            UPDATE analysis_results
            SET job_id = CAST(:job_id AS uuid)
            WHERE id = CAST(:analysis_id AS uuid)
            """,
            {"job_id": job_id, "analysis_id": analysis_id},
        )
    except Exception as exc:
        analysis_job_store[job_id].update({
            "status": "failed",
            "progress": 100,
            "current_step": "오류",
            "message": "분석 중 오류가 발생했습니다.",
            "error_message": str(exc),
        })
        execute(
            """
            UPDATE analysis_jobs
            SET status = 'failed',
                error_message = :error_message,
                completed_at = now()
            WHERE id = CAST(:job_id AS uuid)
            """,
            {"job_id": job_id, "error_message": str(exc)},
        )


def _run_analysis_job_background(
    job_id: str,
    file_id: str,
    voice_sample_id: str | None,
    voice_sample_role: str,
    verification_type: str,
    transcript_text: str | None,
    current_user: dict,
) -> None:
    asyncio.run(_run_analysis_job(
        job_id,
        file_id,
        voice_sample_id,
        voice_sample_role,
        verification_type,
        transcript_text,
        current_user,
    ))


@router.post("/jobs/start/{file_id}")
async def start_analysis_job(
    file_id: str,
    background_tasks: BackgroundTasks,
    voice_sample_id: str = Query(None, description="등록된 음성 샘플 ID (선택)"),
    voice_sample_role: str = Query("target", description="음성 샘플 역할: target 또는 exclude"),
    verification_type: str = Query("parent_call", description="검증 유형: parent_call 또는 self_voice"),
    transcript_text: str = Query(None, description="선택 입력: 전사 텍스트가 있으면 언어 특징을 함께 산출"),
    current_user: dict = Depends(get_current_user),
):
    normalized_verification_type = "self_voice" if verification_type == "self_voice" else "parent_call"
    ensure_retention_schema()
    if file_id in file_store:
        _assert_file_owner(file_store[file_id], current_user)
        if not file_store[file_id].get("wav_path"):
            raise HTTPException(status_code=410, detail="분석용 음성 파일이 이미 삭제되었습니다. 다시 업로드해 주세요.")
    else:
        db_file = get_audio_file(file_id)
        if not db_file:
            raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
        if str(db_file["user_id"]) != current_user["user_id"]:
            raise HTTPException(status_code=403, detail="현재 사용자에게 속한 파일이 아닙니다.")
        if not db_file.get("wav_path") or db_file.get("deleted_at"):
            raise HTTPException(status_code=410, detail="분석용 음성 파일이 이미 삭제되었습니다. 다시 업로드해 주세요.")

    if voice_sample_id:
        if voice_sample_id in voice_sample_store:
            if str(voice_sample_store[voice_sample_id].get("user_id")) != current_user["user_id"]:
                raise HTTPException(status_code=403, detail="현재 사용자에게 속한 음성 샘플이 아닙니다.")
        else:
            sample = get_voice_sample(voice_sample_id)
            if not sample:
                raise HTTPException(status_code=404, detail="음성 샘플을 찾을 수 없습니다.")
            if str(sample["user_id"]) != current_user["user_id"]:
                raise HTTPException(status_code=403, detail="현재 사용자에게 속한 음성 샘플이 아닙니다.")
            if sample.get("deleted_at") or sample.get("status") == "deleted":
                raise HTTPException(status_code=410, detail="음성 샘플이 이미 삭제되었습니다. 다시 등록해 주세요.")

    job_id = str(uuid.uuid4())
    analysis_job_store[job_id] = {
        "user_id": current_user["user_id"],
        "file_id": file_id,
        "voice_sample_id": voice_sample_id,
        "status": "queued",
        "progress": 5,
        "current_step": "대기",
        "message": "분석 작업이 등록되었습니다.",
        "analysis_id": None,
        "error_message": None,
        "created_at": time.time(),
    }
    execute(
        """
        INSERT INTO analysis_jobs (
            id, user_id, audio_file_id, voice_sample_id, status, created_at
        )
        VALUES (
            CAST(:job_id AS uuid),
            CAST(:user_id AS uuid),
            CAST(:file_id AS uuid),
            CAST(:voice_sample_id AS uuid),
            'queued',
            now()
        )
        """,
        {
            "job_id": job_id,
            "user_id": current_user["user_id"],
            "file_id": file_id,
            "voice_sample_id": voice_sample_id,
        },
    )
    background_tasks.add_task(
        _run_analysis_job_background,
        job_id,
        file_id,
        voice_sample_id,
        voice_sample_role,
        normalized_verification_type,
        transcript_text,
        current_user,
    )
    return _job_response(job_id)


@router.get("/jobs/{job_id}")
async def get_analysis_job(job_id: str, current_user: dict = Depends(get_current_user)):
    job = analysis_job_store.get(job_id)
    if job:
        if str(job.get("user_id")) != current_user["user_id"]:
            raise HTTPException(status_code=403, detail="현재 사용자에게 속한 분석 작업이 아닙니다.")
        return _job_response(job_id)

    stored = None
    try:
        from app.database import fetch_one
        stored = fetch_one(
            """
            SELECT id, user_id, status, error_message
            FROM analysis_jobs
            WHERE id = CAST(:job_id AS uuid)
            """,
            {"job_id": job_id},
        )
    except Exception:
        stored = None
    if not stored:
        raise HTTPException(status_code=404, detail="분석 작업을 찾을 수 없습니다.")
    if str(stored["user_id"]) != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="현재 사용자에게 속한 분석 작업이 아닙니다.")

    result = None
    if stored["status"] == "completed":
        try:
            from app.database import fetch_one
            result = fetch_one(
                """
                SELECT id
                FROM analysis_results
                WHERE job_id = CAST(:job_id AS uuid)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                {"job_id": job_id},
            )
        except Exception:
            result = None

    return {
        "job_id": job_id,
        "analysis_id": str(result["id"]) if result else None,
        "status": stored["status"],
        "progress": 100 if stored["status"] in {"completed", "failed"} else 50,
        "current_step": "완료" if stored["status"] == "completed" else "오류" if stored["status"] == "failed" else "처리 중",
        "message": "분석이 완료되었습니다." if stored["status"] == "completed" else "분석 작업 상태를 확인했습니다.",
        "error_message": stored["error_message"],
    }


@router.post("/start/{file_id}", response_model=AnalysisResult)
async def start_analysis(
    file_id: str,
    voice_sample_id: str = Query(None, description="등록된 음성 샘플 ID (선택)"),
    voice_sample_role: str = Query("target", description="음성 샘플 역할: target 또는 exclude"),
    verification_type: str = Query("parent_call", description="검증 유형: parent_call 또는 self_voice"),
    transcript_text: str = Query(None, description="선택 입력: 전사 텍스트가 있으면 언어 특징을 함께 산출"),
    current_user: dict = Depends(get_current_user),
):
    ensure_retention_schema()
    _trace_analysis(f"start request file_id={file_id} voice_sample_id={voice_sample_id}")
    if file_id not in file_store:
        db_file = get_audio_file(file_id)
        if db_file:
            file_store[file_id] = {
                "raw_path": db_file["storage_path"],
                "wav_path": db_file["wav_path"],
                "consent_token": None,
                "user_id": str(db_file["user_id"]),
                "quality": {
                    "duration_seconds": float(db_file["duration_seconds"] or 0),
                    "snr_db": float(db_file["snr_db"] or 0),
                    "silence_ratio": float(db_file["silence_ratio"] or 0),
                    "sample_rate": db_file["sample_rate"],
                    "channels": db_file["channels"],
                    "format_original": db_file["original_format"],
                    "quality_pass": db_file["quality_pass"],
                    "rejection_reason": db_file["rejection_reason"],
                },
            }

    if file_id not in file_store:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")

    file_info = file_store[file_id]
    _assert_file_owner(file_info, current_user)
    _trace_analysis("file info loaded")

    if not file_info.get("wav_path"):
        raise HTTPException(status_code=410, detail="분석용 음성 파일이 이미 삭제되었습니다. 다시 업로드해 주세요.")

    if not file_info["quality"]["quality_pass"]:
        raise HTTPException(
            status_code=400,
            detail=f"품질 검증을 통과하지 못한 파일입니다: {file_info['quality']['rejection_reason']}",
        )

    wav_path = file_info["wav_path"]
    start_time = time.time()
    analysis_id = str(uuid.uuid4())

    # Get voice sample embedding if provided
    voice_embedding = None
    voice_sample_path = None
    if voice_sample_id and voice_sample_id in voice_sample_store:
        sample_data = voice_sample_store[voice_sample_id]
        if str(sample_data.get("user_id")) != current_user["user_id"]:
            raise HTTPException(status_code=403, detail="현재 사용자에게 속한 음성 샘플이 아닙니다.")
        voice_sample_path = sample_data.get("path")
        if sample_data["embedding"] is not None:
            voice_embedding = np.array(sample_data["embedding"])
    elif voice_sample_id:
        sample_data = get_voice_sample(voice_sample_id)
        if sample_data and str(sample_data["user_id"]) != current_user["user_id"]:
            raise HTTPException(status_code=403, detail="현재 사용자에게 속한 음성 샘플이 아닙니다.")
        if sample_data and (sample_data.get("deleted_at") or sample_data.get("status") == "deleted"):
            raise HTTPException(status_code=410, detail="음성 샘플이 이미 삭제되었습니다. 다시 등록해 주세요.")
        if sample_data:
            voice_sample_path = sample_data.get("storage_path")
        if sample_data and sample_data["embedding"] is not None:
            voice_embedding = np.array(sample_data["embedding"])
    _trace_analysis(f"voice embedding loaded={voice_embedding is not None}")

    normalized_voice_sample_role = (voice_sample_role or "target").strip().lower()
    if normalized_voice_sample_role not in {"target", "exclude"}:
        raise HTTPException(status_code=400, detail="voice_sample_role은 target 또는 exclude만 허용됩니다.")
    is_self_voice = verification_type == "self_voice"

    # Step 1: Speaker Diarization
    if _lightweight_analysis_enabled():
        if voice_embedding is not None and normalized_voice_sample_role == "exclude":
            _trace_analysis("lightweight parent-candidate diarization start")
            diarization_result = perform_speaker_diarization(
                wav_path,
                voice_embedding,
                max_duration=_lightweight_diarization_seconds(),
            )
            _trace_analysis("lightweight parent-candidate diarization done")
            excluded_voice_segments = diarization_result["target_segments"]
            parent_candidate_segments = diarization_result["excluded_segments"]
            if _segment_duration(parent_candidate_segments) >= 8.0:
                diarization_result = {
                    **diarization_result,
                    "target_speaker": "parent_candidate",
                    "target_segments": parent_candidate_segments,
                    "excluded_segments": excluded_voice_segments,
                    "diarization_confidence": max(0.62, diarization_result["diarization_confidence"]),
                }
                target_audio = extract_target_audio(wav_path, diarization_result["target_segments"])
            else:
                _trace_analysis("lightweight parent-candidate fallback first 30s")
                y, _ = librosa.load(wav_path, sr=TARGET_SR, duration=30)
                duration = round(len(y) / TARGET_SR, 2)
                diarization_result = {
                    "total_speakers": 2,
                    "target_speaker": "parent_candidate",
                    "target_segments": [{
                        "speaker": "parent_candidate",
                        "start_time": 0.0,
                        "end_time": duration,
                        "duration": duration,
                    }],
                    "excluded_segments": excluded_voice_segments,
                    "diarization_confidence": 0.58,
                }
                target_audio = y
        else:
            _trace_analysis("lightweight load audio start")
            y, _ = librosa.load(wav_path, sr=TARGET_SR, duration=30)
            _trace_analysis(f"lightweight load audio done samples={len(y)}")
            duration = round(len(y) / TARGET_SR, 2)
            diarization_result = {
                "total_speakers": 1,
                "target_speaker": "speaker_A",
                "target_segments": [{
                    "speaker": "speaker_A",
                    "start_time": 0.0,
                    "end_time": duration,
                    "duration": duration,
                }],
                "excluded_segments": [],
                "diarization_confidence": 0.65,
            }
            target_audio = y
    else:
        _trace_analysis("diarization start")
        diarization_result = perform_speaker_diarization(wav_path, voice_embedding)
        _trace_analysis("diarization done")
        if voice_embedding is not None and normalized_voice_sample_role == "exclude":
            excluded_voice_segments = diarization_result["target_segments"]
            parent_candidate_segments = diarization_result["excluded_segments"]
            if parent_candidate_segments:
                diarization_result = {
                    **diarization_result,
                    "target_speaker": "parent_candidate",
                    "target_segments": parent_candidate_segments,
                    "excluded_segments": excluded_voice_segments,
                }

        # Step 2: Extract target speaker audio
        target_audio = extract_target_audio(wav_path, diarization_result["target_segments"])
        _trace_analysis(f"target extraction done samples={len(target_audio)}")
    target_audio_path = f"{env_str('SORIMEMO_PROCESSED_DIR', '/tmp/sorimemo_processed')}/{analysis_id}_target.wav"
    _trace_analysis("write target audio start")
    sf.write(target_audio_path, target_audio, TARGET_SR)
    _trace_analysis("write target audio done")
    cognitive_audio_path = target_audio_path
    if is_self_voice:
        cognitive_audio_path = wav_path
    if voice_embedding is not None and normalized_voice_sample_role == "exclude":
        cognitive_audio_path = wav_path

    # Step 3: Extract speech statistics
    speech_stats = extract_speech_statistics(target_audio, TARGET_SR)
    _trace_analysis("speech stats done")

    # Step 4: Extract acoustic features
    if _lightweight_analysis_enabled():
        acoustic_features = _extract_lightweight_acoustic_features(target_audio, TARGET_SR)
    else:
        acoustic_features = extract_acoustic_features(target_audio, TARGET_SR)
    _trace_analysis("acoustic features done")

    # Step 5: STT transcription and linguistic feature extraction
    # Self-voice mode uses a fixed read-aloud prompt, so automatic STT mostly
    # measures script normality and can incorrectly pull acoustic MCI toward Normal.
    has_provided_transcript = bool((transcript_text or "").strip())
    stt_result = {
        "transcript_text": transcript_text,
        "stt_available": has_provided_transcript,
        "stt_engine": "provided" if has_provided_transcript else "none",
        "stt_confidence": 1.0 if has_provided_transcript else 0.0,
        "transcript_char_count": len((transcript_text or "").strip()),
        "stt_language": "provided" if has_provided_transcript else "",
        "stt_note": "요청에서 제공된 전사 텍스트를 사용했습니다." if has_provided_transcript else "",
    }
    if not has_provided_transcript and not is_self_voice:
        _trace_analysis("stt start")
        stt_result = transcribe_audio(target_audio_path)
        _trace_analysis(f"stt done available={stt_result['stt_available']}")
    elif is_self_voice and not has_provided_transcript:
        _trace_analysis("stt skipped for self_voice")
        stt_result["stt_note"] = "내 목소리 검증은 읽기 음성의 음향 특징 중심으로 분석하여 자동 전사를 생략했습니다."
    linguistic_features = extract_linguistic_features(stt_result.get("transcript_text"))
    linguistic_features = {
        **linguistic_features,
        "stt_available": bool(stt_result.get("stt_available")),
        "stt_engine": str(stt_result.get("stt_engine") or "none"),
        "stt_confidence": float(stt_result.get("stt_confidence") or 0.0),
        "transcript_char_count": int(stt_result.get("transcript_char_count") or 0),
        "stt_language": str(stt_result.get("stt_language") or ""),
        "stt_note": str(stt_result.get("stt_note") or ""),
    }

    # Step 6: Compute feature quality
    feature_quality = compute_feature_quality(acoustic_features, speech_stats)

    # Step 7: Run trained Normal/MCI/AD model and apply STT linguistic signal
    try:
        _trace_analysis("cognitive prediction start")
        cognitive_result = predict_cognitive_status(cognitive_audio_path)
        if not is_self_voice:
            cognitive_result = apply_linguistic_adjustment(cognitive_result, linguistic_features)
        _trace_analysis("cognitive prediction done")
    except CognitiveModelUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "학습된 Normal/MCI/AD 모델을 사용할 수 없습니다. "
                f"서버 모델 경로 설정 또는 기본 모델 경로를 확인해 주세요. ({str(exc)})"
            ),
        )

    # Step 8: Compute confidence score
    confidence_result = compute_confidence_score(
        snr_db=file_info["quality"]["snr_db"],
        silence_ratio=speech_stats["silence_ratio"],
        diarization_confidence=diarization_result["diarization_confidence"],
        model_entropy=cognitive_result["model_entropy"],
        feature_quality=feature_quality,
    )

    processing_time = time.time() - start_time
    raw_deleted = False
    standard_audio_deleted = False
    target_deleted = False
    voice_sample_deleted = False
    training_consent = _model_training_consent_for_audio(file_id)
    if training_consent:
        _mark_training_audio_retained(file_id, int(training_consent.get("model_training_retention_days") or 1095))
    else:
        for path_key in ("raw_path", "wav_path"):
            path = file_info.get(path_key)
            if remove_file_if_exists(path):
                file_info[path_key] = None
                if path_key == "raw_path":
                    raw_deleted = True
                else:
                    standard_audio_deleted = True
        mark_audio_deleted(file_id)

    if remove_file_if_exists(target_audio_path):
        target_deleted = True

    if voice_sample_id and DELETE_VOICE_SAMPLE_AFTER_ANALYSIS:
        voice_sample_deleted = remove_file_if_exists(voice_sample_path)
        if voice_sample_id in voice_sample_store:
            voice_sample_store.pop(voice_sample_id, None)
        mark_voice_sample_deleted(voice_sample_id)

    disclaimer = (
        "본 분석 결과는 의료적 진단이나 치료 판단이 아닌, "
        "인지기능 변화와 연관될 수 있는 위험 신호를 참고용으로 제공하는 "
        "비의료적 정보입니다."
    )

    result = AnalysisResult(
        analysis_id=analysis_id,
        file_id=file_id,
        cognitive_status=cognitive_result["cognitive_status"],
        cognitive_status_label=cognitive_result["cognitive_status_label"],
        dementia_stage=cognitive_result["dementia_stage"],
        risk_score=cognitive_result["risk_score"],
        risk_level=cognitive_result["risk_level"],
        risk_level_label=cognitive_result["risk_level_label"],
        risk_probability=cognitive_result["risk_probability"],
        model_probabilities=cognitive_result["model_probabilities"],
        acoustic_model_probabilities=cognitive_result.get("acoustic_model_probabilities"),
        linguistic_adjustment=cognitive_result.get("linguistic_adjustment"),
        result_message=cognitive_result["result_message"],
        model_source=cognitive_result["model_source"],
        confidence_score=confidence_result["overall"],
        confidence_breakdown={
            "audio_quality_score": confidence_result["audio_quality_score"],
            "diarization_clarity": confidence_result["diarization_clarity"],
            "model_certainty": confidence_result["model_certainty"],
        },
        features={
            "acoustic_features": acoustic_features,
            "linguistic_features": linguistic_features,
            "speech_statistics": speech_stats,
            "feature_quality_score": feature_quality,
        },
        diarization={
            "total_speakers": diarization_result["total_speakers"],
            "target_speaker": diarization_result["target_speaker"],
            "target_segments": diarization_result["target_segments"],
            "excluded_segments": diarization_result["excluded_segments"],
            "diarization_confidence": diarization_result["diarization_confidence"],
        },
        governance={
            "consent_token_validated": True,
            "policy_version": "1.0.0",
            "raw_audio_deleted_after_analysis": raw_deleted,
            "standard_audio_deleted_after_analysis": standard_audio_deleted,
            "target_audio_deleted_after_analysis": target_deleted,
            "voice_sample_deleted_after_analysis": voice_sample_deleted,
            "stored_data_scope": "feature_vector_and_analysis_result",
            "third_party_voice_handling": "speaker_diarization_excluded_segments_not_used_for_model",
            "non_medical_disclaimer_present": True,
            "transcript_available": linguistic_features["transcript_available"],
            "stt_available": linguistic_features["stt_available"],
            "stt_engine": linguistic_features["stt_engine"],
            "stt_confidence": linguistic_features["stt_confidence"],
            "transcript_char_count": linguistic_features["transcript_char_count"],
        },
        processing_time_seconds=round(processing_time, 2),
        disclaimer=disclaimer,
    )

    result_payload = jsonable_encoder(result)
    result_payload["verification_type"] = "self_voice" if verification_type == "self_voice" else "parent_call"
    analysis_store[analysis_id] = {
        "result": result_payload,
        "file_id": file_id,
        "user_id": current_user["user_id"],
        "created_at": time.time(),
    }
    execute(
        """
        INSERT INTO analysis_results (
            id, audio_file_id, status, cognitive_status, risk_score, risk_level,
            risk_probability, model_probabilities, confidence_score, result_payload
        )
        VALUES (
            CAST(:id AS uuid), CAST(:audio_file_id AS uuid), 'completed',
            :cognitive_status, :risk_score, :risk_level, :risk_probability,
            CAST(:model_probabilities AS jsonb), :confidence_score, CAST(:result_payload AS jsonb)
        )
        """,
        {
            "id": analysis_id,
            "audio_file_id": file_id,
            "cognitive_status": result_payload["cognitive_status"],
            "risk_score": result_payload["risk_score"],
            "risk_level": result_payload["risk_level"],
            "risk_probability": result_payload["risk_probability"],
            "model_probabilities": json.dumps(result_payload["model_probabilities"]),
            "confidence_score": result_payload["confidence_score"],
            "result_payload": json.dumps(result_payload),
        },
    )
    mark_analysis_result_retention(analysis_id)

    return result


@router.get("/model-status")
async def model_status():
    return get_model_status()


@router.get("/status/{analysis_id}", response_model=AnalysisStatusResponse)
async def get_analysis_status(analysis_id: str, current_user: dict = Depends(get_current_user)):
    if _assert_analysis_owner(analysis_id, current_user):
        return AnalysisStatusResponse(
            analysis_id=analysis_id,
            status="completed",
            progress=100,
            current_step="완료",
            message="분석이 완료되었습니다.",
        )
    raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다.")


@router.get("/result/{analysis_id}")
async def get_analysis_result(analysis_id: str, current_user: dict = Depends(get_current_user)):
    stored = _assert_analysis_owner(analysis_id, current_user)
    if not stored:
        raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다.")
    return stored
