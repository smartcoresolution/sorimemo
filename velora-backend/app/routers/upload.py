import json
import os
import re
import time
import traceback
from difflib import SequenceMatcher
from fastapi import APIRouter, Depends, UploadFile, File, Header, HTTPException
import numpy as np
from app.config import env_bool, env_float, env_str
from app.database import execute, fetch_one, get_audio_file, get_consent_by_token, get_voice_sample
from app.models.schemas import UploadResponse, QualityReport, VoiceSampleResponse
from app.services.audio_processor import (
    MAX_DURATION as MAX_AUDIO_DURATION,
    MIN_SELF_VOICE_DURATION,
    save_uploaded_file,
    save_voice_sample,
    convert_to_standard_wav,
    quality_check,
    get_voice_sample_embedding,
    trim_wav_to_duration,
)
from app.services.retention_policy import (
    ensure_retention_schema,
    mark_audio_upload_retention,
    mark_voice_sample_retention,
    remove_file_if_exists,
)
from app.services.speaker_processor import perform_speaker_diarization
from app.services.stt_processor import transcribe_audio
from app.routers.auth import get_current_user
from app.routers.consent import consent_store

router = APIRouter()

# In-memory file store
file_store: dict[str, dict] = {}
voice_sample_store: dict[str, dict] = {}

ALLOWED_EXTENSIONS = {
    ".m4a",
    ".mp3",
    ".wav",
    ".flac",
    ".ogg",
    ".aac",
    ".wma",
    ".webm",
    ".mp4",
    ".3gp",
    ".3ga",
    ".amr",
}
ALLOWED_CONTENT_TYPE_PREFIXES = ("audio/",)
ALLOWED_CONTENT_TYPES = {
    "application/octet-stream",
    "video/mp4",
}
MIN_VOICE_SAMPLE_DURATION = env_float("SORIMEMO_MIN_VOICE_SAMPLE_DURATION", "20.0")
MAX_VOICE_SAMPLE_DURATION = env_float("SORIMEMO_MAX_VOICE_SAMPLE_DURATION", "30.0")
UPLOAD_DEBUG_LOG = env_str("SORIMEMO_UPLOAD_DEBUG_LOG", "/tmp/sorimemo_upload_debug.log")
MIN_CHILD_VOICE_DURATION = env_float("SORIMEMO_MIN_CHILD_VOICE_DURATION", "5.0")
MIN_PARENT_VOICE_DURATION = env_float("SORIMEMO_MIN_PARENT_VOICE_DURATION", "10.0")
PARENT_CALL_DIA_MAX_SECONDS = env_float("SORIMEMO_PARENT_CALL_DIA_MAX_SECONDS", "120.0")
MIN_CHILD_VOICE_SIMILARITY = env_float("SORIMEMO_MIN_CHILD_VOICE_SIMILARITY", "0.65")
STRONG_CHILD_VOICE_SIMILARITY = env_float("SORIMEMO_STRONG_CHILD_VOICE_SIMILARITY", "0.975")
MAX_CHILD_VOICE_DISTANCE = env_float("SORIMEMO_MAX_CHILD_VOICE_DISTANCE", "45.0")
MIN_PARENT_DURATION_FOR_DISTANCE_BYPASS = env_float("SORIMEMO_MIN_PARENT_DURATION_FOR_DISTANCE_BYPASS", "45.0")
SELF_VOICE_PROMPT_CHECK_ENABLED = env_bool("SORIMEMO_SELF_VOICE_PROMPT_CHECK_ENABLED", "true")
SELF_VOICE_PROMPT_MIN_SIMILARITY = env_float("SORIMEMO_SELF_VOICE_PROMPT_MIN_SIMILARITY", "0.42")
SELF_VOICE_PROMPT_MIN_KEYWORD_COVERAGE = env_float("SORIMEMO_SELF_VOICE_PROMPT_MIN_KEYWORD_COVERAGE", "0.35")
CHILD_VOICE_PROMPT_CHECK_ENABLED = env_bool("SORIMEMO_CHILD_VOICE_PROMPT_CHECK_ENABLED", "true")
CHILD_VOICE_PROMPT_MIN_SIMILARITY = env_float("SORIMEMO_CHILD_VOICE_PROMPT_MIN_SIMILARITY", "0.40")
CHILD_VOICE_PROMPT_MIN_KEYWORD_COVERAGE = env_float("SORIMEMO_CHILD_VOICE_PROMPT_MIN_KEYWORD_COVERAGE", "0.35")
SELF_VOICE_PROMPT_TEXT = (
    "오늘은 조용한 곳에서 제 목소리를 자연스럽게 녹음하고 있습니다. "
    "아침에는 물을 한 잔 마시고 창밖의 날씨를 살펴보았습니다. "
    "요즘은 가족과 친구들의 안부를 묻고, 하루 일정을 차분히 정리하려고 합니다. "
    "장을 볼 때는 필요한 물건을 미리 적어 두고, 천천히 확인하면서 고릅니다. "
    "가끔 단어가 바로 떠오르지 않을 때도 있지만, 서두르지 않고 다시 생각해 봅니다. "
    "이 녹음은 제 목소리의 말 속도와 멈춤, 발음의 변화를 참고하기 위한 것입니다."
)
SELF_VOICE_PROMPT_KEYWORDS = [
    "조용한곳",
    "제목소리",
    "자연스럽게",
    "아침",
    "물을한잔",
    "창밖",
    "날씨",
    "가족",
    "친구",
    "안부",
    "하루일정",
    "장을볼때",
    "필요한물건",
    "적어두고",
    "천천히",
    "단어",
    "떠오르지",
    "서두르지",
    "말속도",
    "멈춤",
    "발음",
    "변화",
]
CHILD_VOICE_PROMPT_TEXT = (
    "안녕하세요. 저는 부모님과의 통화 분석을 위해 제 목소리를 등록하고 있습니다. "
    "이 음성은 통화 녹음에서 제 목소리를 구분하기 위한 기준 샘플입니다. "
    "저는 평소 부모님과 전화할 때와 비슷한 속도와 크기로 말하고 있습니다. "
    "오늘 날씨와 최근에 있었던 일, 그리고 가족과 나눈 대화를 자연스럽게 떠올리며 말해 보겠습니다. "
    "이 녹음은 부모님 음성을 더 정확히 확인하기 위한 참고용으로 사용됩니다."
)
CHILD_VOICE_PROMPT_KEYWORDS = [
    "부모님과의통화",
    "분석",
    "제목소리",
    "등록",
    "통화녹음",
    "구분",
    "기준샘플",
    "부모님과전화",
    "비슷한속도",
    "크기",
    "오늘날씨",
    "최근",
    "가족",
    "대화",
    "자연스럽게",
    "부모님음성",
    "정확히",
    "참고용",
]


def _upload_debug(stage: str, **fields) -> None:
    payload = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "stage": stage,
        **fields,
    }
    try:
        with open(UPLOAD_DEBUG_LOG, "a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _safe_print(message: str) -> None:
    try:
        print(message, flush=True)
    except Exception:
        pass


def _to_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_quality_report(qc: dict) -> dict:
    return {
        "duration_seconds": _to_float(qc.get("duration_seconds")),
        "snr_db": _to_float(qc.get("snr_db")),
        "silence_ratio": _to_float(qc.get("silence_ratio")),
        "sample_rate": _to_int(qc.get("sample_rate")),
        "channels": _to_int(qc.get("channels")),
        "format_original": str(qc.get("format_original") or ""),
        "quality_pass": _to_bool(qc.get("quality_pass")),
        "rejection_reason": qc.get("rejection_reason") or None,
        "original_duration_seconds": (
            _to_float(qc.get("original_duration_seconds"))
            if qc.get("original_duration_seconds") is not None
            else None
        ),
        "trimmed_to_seconds": (
            _to_float(qc.get("trimmed_to_seconds"))
            if qc.get("trimmed_to_seconds") is not None
            else None
        ),
        "was_trimmed": _to_bool(qc.get("was_trimmed")),
        "speech_duration_seconds": (
            _to_float(qc.get("speech_duration_seconds"))
            if qc.get("speech_duration_seconds") is not None
            else None
        ),
        "rms_dbfs": (
            _to_float(qc.get("rms_dbfs"))
            if qc.get("rms_dbfs") is not None
            else None
        ),
        "child_voice_present": (
            _to_bool(qc.get("child_voice_present"))
            if qc.get("child_voice_present") is not None
            else None
        ),
        "child_voice_duration_seconds": (
            _to_float(qc.get("child_voice_duration_seconds"))
            if qc.get("child_voice_duration_seconds") is not None
            else None
        ),
        "parent_voice_duration_seconds": (
            _to_float(qc.get("parent_voice_duration_seconds"))
            if qc.get("parent_voice_duration_seconds") is not None
            else None
        ),
        "detected_speaker_count": (
            _to_int(qc.get("detected_speaker_count"))
            if qc.get("detected_speaker_count") is not None
            else None
        ),
        "diarization_confidence": (
            _to_float(qc.get("diarization_confidence"))
            if qc.get("diarization_confidence") is not None
            else None
        ),
        "voice_sample_distance": (
            _to_float(qc.get("voice_sample_distance"))
            if qc.get("voice_sample_distance") is not None
            else None
        ),
        "voice_sample_similarity": (
            _to_float(qc.get("voice_sample_similarity"))
            if qc.get("voice_sample_similarity") is not None
            else None
        ),
        "self_voice_prompt_checked": (
            _to_bool(qc.get("self_voice_prompt_checked"))
            if qc.get("self_voice_prompt_checked") is not None
            else None
        ),
        "self_voice_prompt_match_score": (
            _to_float(qc.get("self_voice_prompt_match_score"))
            if qc.get("self_voice_prompt_match_score") is not None
            else None
        ),
        "self_voice_prompt_keyword_coverage": (
            _to_float(qc.get("self_voice_prompt_keyword_coverage"))
            if qc.get("self_voice_prompt_keyword_coverage") is not None
            else None
        ),
        "self_voice_prompt_stt_confidence": (
            _to_float(qc.get("self_voice_prompt_stt_confidence"))
            if qc.get("self_voice_prompt_stt_confidence") is not None
            else None
        ),
        "self_voice_prompt_transcript_char_count": (
            _to_int(qc.get("self_voice_prompt_transcript_char_count"))
            if qc.get("self_voice_prompt_transcript_char_count") is not None
            else None
        ),
    }


def _normalize_korean_text(text: str | None) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", text or "").lower()


def _validate_read_prompt(
    wav_path: str,
    *,
    expected_text: str,
    keywords: list[str],
    enabled: bool,
    min_similarity: float,
    min_keyword_coverage: float,
    mismatch_message: str,
) -> dict:
    if not enabled:
        return {
            "quality_pass": True,
            "rejection_reason": None,
            "self_voice_prompt_checked": False,
            "self_voice_prompt_match_score": None,
            "self_voice_prompt_keyword_coverage": None,
        }

    stt_result = transcribe_audio(wav_path)
    transcript = stt_result.get("transcript_text")
    if not transcript:
        return {
            "quality_pass": False,
            "rejection_reason": "화면의 안내 문장을 읽은 음성인지 확인하지 못했습니다. 조용한 곳에서 안내 문장을 다시 읽어 주세요.",
            "self_voice_prompt_checked": True,
            "self_voice_prompt_match_score": 0.0,
            "self_voice_prompt_keyword_coverage": 0.0,
            "self_voice_prompt_stt_note": stt_result.get("stt_note"),
        }

    normalized_expected = _normalize_korean_text(expected_text)
    normalized_transcript = _normalize_korean_text(str(transcript))
    similarity = SequenceMatcher(None, normalized_expected, normalized_transcript).ratio()
    keyword_hits = sum(1 for keyword in keywords if keyword in normalized_transcript)
    keyword_coverage = keyword_hits / max(1, len(keywords))
    quality_pass = (
        similarity >= min_similarity
        and keyword_coverage >= min_keyword_coverage
    ) or similarity >= max(0.55, min_similarity)

    return {
        "quality_pass": quality_pass,
        "rejection_reason": None if quality_pass else mismatch_message,
        "self_voice_prompt_checked": True,
        "self_voice_prompt_match_score": round(float(similarity), 4),
        "self_voice_prompt_keyword_coverage": round(float(keyword_coverage), 4),
        "self_voice_prompt_stt_confidence": stt_result.get("stt_confidence"),
        "self_voice_prompt_transcript_char_count": stt_result.get("transcript_char_count"),
    }


def _validate_self_voice_prompt(wav_path: str) -> dict:
    return _validate_read_prompt(
        wav_path,
        expected_text=SELF_VOICE_PROMPT_TEXT,
        keywords=SELF_VOICE_PROMPT_KEYWORDS,
        enabled=SELF_VOICE_PROMPT_CHECK_ENABLED,
        min_similarity=SELF_VOICE_PROMPT_MIN_SIMILARITY,
        min_keyword_coverage=SELF_VOICE_PROMPT_MIN_KEYWORD_COVERAGE,
        mismatch_message="화면에 표시된 내 목소리 안내 문장과 다른 음성으로 확인되었습니다. 안내 문장을 다시 읽어 주세요.",
    )


def _validate_child_voice_prompt(wav_path: str) -> dict:
    return _validate_read_prompt(
        wav_path,
        expected_text=CHILD_VOICE_PROMPT_TEXT,
        keywords=CHILD_VOICE_PROMPT_KEYWORDS,
        enabled=CHILD_VOICE_PROMPT_CHECK_ENABLED,
        min_similarity=CHILD_VOICE_PROMPT_MIN_SIMILARITY,
        min_keyword_coverage=CHILD_VOICE_PROMPT_MIN_KEYWORD_COVERAGE,
        mismatch_message="화면에 표시된 자녀 목소리 안내 문장과 다른 음성으로 확인되었습니다. 안내 문장을 다시 읽어 주세요.",
    )


def _load_voice_sample_embedding(sample_id: str, current_user: dict) -> np.ndarray:
    if sample_id in voice_sample_store:
        sample = voice_sample_store[sample_id]
        if str(sample.get("user_id")) != current_user["user_id"]:
            raise HTTPException(status_code=403, detail="현재 사용자에게 속한 자녀 음성 샘플이 아닙니다.")
        embedding = sample.get("embedding")
        if embedding is None:
            raise HTTPException(status_code=400, detail="자녀 음성 샘플의 특징 정보가 없습니다. 자녀 음성을 다시 등록해 주세요.")
        return np.asarray(embedding, dtype=float)

    sample = get_voice_sample(sample_id)
    if not sample:
        raise HTTPException(status_code=400, detail="자녀 음성 샘플을 찾을 수 없습니다. 자녀 음성을 다시 등록해 주세요.")
    if str(sample["user_id"]) != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="현재 사용자에게 속한 자녀 음성 샘플이 아닙니다.")
    embedding = sample.get("embedding")
    if isinstance(embedding, str):
        embedding = json.loads(embedding)
    if embedding is None:
        raise HTTPException(status_code=400, detail="자녀 음성 샘플의 특징 정보가 없습니다. 자녀 음성을 다시 등록해 주세요.")
    return np.asarray(embedding, dtype=float)


def _validate_parent_call_contains_child_voice(
    wav_path: str,
    voice_sample_id: str | None,
    current_user: dict,
) -> dict:
    if not voice_sample_id:
        return {
            "quality_pass": False,
            "rejection_reason": "부모통화검증에는 등록된 자녀 음성이 포함된 통화녹음이 필요합니다. 자녀 음성 등록 후 부모님과의 실제 통화녹음을 업로드해 주세요.",
        }

    embedding = _load_voice_sample_embedding(voice_sample_id, current_user)
    diarization = perform_speaker_diarization(
        wav_path,
        voice_sample_embedding=embedding,
        max_duration=PARENT_CALL_DIA_MAX_SECONDS,
    )
    child_duration = sum(float(segment.get("duration", 0.0) or 0.0) for segment in diarization.get("target_segments", []))
    parent_duration = sum(float(segment.get("duration", 0.0) or 0.0) for segment in diarization.get("excluded_segments", []))
    total_speakers = int(diarization.get("total_speakers", 0) or 0)
    result = {
        "total_speakers": total_speakers,
        "child_voice_duration_seconds": round(child_duration, 2),
        "parent_voice_duration_seconds": round(parent_duration, 2),
        "diarization_confidence": diarization.get("diarization_confidence"),
        "voice_sample_distance": diarization.get("voice_sample_distance"),
        "voice_sample_similarity": diarization.get("voice_sample_similarity"),
    }
    if total_speakers < 2:
        return {
            **result,
            "quality_pass": False,
            "rejection_reason": "통화 유형 오류: 한 명의 음성만 확인되었습니다. 부모님 단독 음성이 아니라 자녀와 부모님이 실제로 대화한 통화녹음을 업로드해 주세요.",
        }
    voice_sample_similarity = result.get("voice_sample_similarity")
    if voice_sample_similarity is not None and float(voice_sample_similarity) < MIN_CHILD_VOICE_SIMILARITY:
        return {
            **result,
            "quality_pass": False,
            "rejection_reason": "통화 유형 오류: 등록된 자녀 음성과 일치하는 발화가 확인되지 않았습니다. 부모님 단독 음성이 아니라 자녀와 부모님이 실제로 대화한 통화녹음을 업로드해 주세요.",
        }
    voice_sample_distance = result.get("voice_sample_distance")
    has_strong_similarity = (
        voice_sample_similarity is not None
        and float(voice_sample_similarity) >= STRONG_CHILD_VOICE_SIMILARITY
    )
    can_bypass_distance = has_strong_similarity and parent_duration >= MIN_PARENT_DURATION_FOR_DISTANCE_BYPASS
    if (
        not can_bypass_distance
        and voice_sample_distance is not None
        and float(voice_sample_distance) > MAX_CHILD_VOICE_DISTANCE
    ):
        return {
            **result,
            "quality_pass": False,
            "rejection_reason": "통화 유형 오류: 등록된 자녀 음성과 충분히 가까운 발화가 확인되지 않았습니다. 부모님 단독 음성이 아니라 자녀와 부모님이 실제로 대화한 통화녹음을 업로드해 주세요.",
        }
    if child_duration < MIN_CHILD_VOICE_DURATION:
        return {
            **result,
            "quality_pass": False,
            "rejection_reason": f"통화 유형 오류: 등록된 자녀 음성이 {child_duration:.1f}초만 확인되었습니다. 자녀 발화가 최소 {MIN_CHILD_VOICE_DURATION:.0f}초 이상 포함된 통화녹음을 업로드해 주세요.",
        }
    if parent_duration < MIN_PARENT_VOICE_DURATION:
        return {
            **result,
            "quality_pass": False,
            "rejection_reason": f"통화 유형 오류: 부모님으로 추정되는 발화가 {parent_duration:.1f}초로 부족합니다. 부모님 발화가 최소 {MIN_PARENT_VOICE_DURATION:.0f}초 이상 포함된 통화녹음을 업로드해 주세요.",
        }
    return {
        **result,
        "quality_pass": True,
        "rejection_reason": None,
    }


def _validate_consent(consent_token: str, current_user: dict) -> dict:
    if not consent_token:
        raise HTTPException(
            status_code=403,
            detail="유효한 동의 토큰이 필요합니다. 먼저 동의 절차를 완료해 주세요.",
        )
    if consent_token in consent_store:
        consent = consent_store[consent_token]
        if str(consent.get("user_id")) != current_user["user_id"]:
            raise HTTPException(status_code=403, detail="현재 사용자에게 속한 동의 토큰이 아닙니다.")
        return consent
    consent = get_consent_by_token(consent_token)
    if not consent:
        raise HTTPException(
            status_code=403,
            detail="유효한 동의 토큰이 필요합니다. 먼저 동의 절차를 완료해 주세요.",
        )
    if str(consent["user_id"]) != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="현재 사용자에게 속한 동의 토큰이 아닙니다.")
    consent_store[consent_token] = {
        "db_id": str(consent["id"]),
        "user_id": str(consent["user_id"]),
        "user_name": consent["user_name"],
        "age_group": consent["age_group"],
        "agreed_at": consent["agreed_at"].isoformat(),
        "policy_version": consent["policy_version"],
    }
    return consent_store[consent_token]


def _validate_audio_file(filename: str, content_type: str | None) -> str:
    ext = os.path.splitext(filename)[1].lower()
    normalized_content_type = (content_type or "").split(";")[0].strip().lower()
    content_type_allowed = (
        normalized_content_type in ALLOWED_CONTENT_TYPES
        or any(normalized_content_type.startswith(prefix) for prefix in ALLOWED_CONTENT_TYPE_PREFIXES)
    )
    if ext in ALLOWED_EXTENSIONS:
        return ext
    if not ext and content_type_allowed:
        return ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식입니다. 지원 형식: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    return ext


@router.post("/audio", response_model=UploadResponse)
async def upload_audio(
    file: UploadFile = File(...),
    x_consent_token: str = Header(..., alias="X-Consent-Token"),
    x_voice_sample_id: str | None = Header(default=None, alias="X-Voice-Sample-Id"),
    x_upload_context: str | None = Header(default=None, alias="X-Upload-Context"),
    current_user: dict = Depends(get_current_user),
):
    started_at = time.perf_counter()
    _upload_debug(
        "upload_audio:start",
        filename=file.filename,
        content_type=file.content_type,
        user_id=current_user.get("user_id"),
        consent_token_prefix=(x_consent_token or "")[:8],
        voice_sample_id=x_voice_sample_id,
        upload_context=x_upload_context,
    )
    ensure_retention_schema()
    _validate_consent(x_consent_token, current_user)
    ext = _validate_audio_file(file.filename or "audio", file.content_type)
    _upload_debug("upload_audio:validated", filename=file.filename, content_type=file.content_type, ext=ext)

    file_bytes = await file.read()
    read_at = time.perf_counter()
    _upload_debug("upload_audio:read", byte_size=len(file_bytes), elapsed=round(read_at - started_at, 3))
    if len(file_bytes) > 100 * 1024 * 1024:  # 100MB limit
        _upload_debug("upload_audio:reject_size", byte_size=len(file_bytes))
        raise HTTPException(status_code=400, detail="파일 크기가 100MB를 초과합니다.")

    file_id, raw_path = save_uploaded_file(file_bytes, file.filename or "audio.wav")
    saved_at = time.perf_counter()
    _upload_debug(
        "upload_audio:saved",
        file_id=file_id,
        raw_path=raw_path,
        byte_size=len(file_bytes),
        elapsed=round(saved_at - read_at, 3),
    )

    try:
        _upload_debug("upload_audio:convert_start", file_id=file_id, raw_path=raw_path)
        wav_path = convert_to_standard_wav(raw_path, file_id)
    except Exception as e:
        os.remove(raw_path)
        _upload_debug(
            "upload_audio:convert_error",
            file_id=file_id,
            raw_path=raw_path,
            error=str(e),
            traceback=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=400,
            detail=f"오디오 변환 중 오류가 발생했습니다: {str(e)}",
        )
    converted_at = time.perf_counter()
    _upload_debug(
        "upload_audio:converted",
        file_id=file_id,
        wav_path=wav_path,
        elapsed=round(converted_at - saved_at, 3),
    )

    try:
        _upload_debug("upload_audio:trim_start", file_id=file_id, wav_path=wav_path)
        original_duration, was_trimmed = trim_wav_to_duration(wav_path, MAX_AUDIO_DURATION)
        _upload_debug(
            "upload_audio:trimmed",
            file_id=file_id,
            original_duration=round(original_duration, 3),
            was_trimmed=was_trimmed,
        )

        parent_call_type_failure = None
        if x_upload_context == "parent_call" or x_voice_sample_id:
            _upload_debug("upload_audio:child_voice_check_start", file_id=file_id, voice_sample_id=x_voice_sample_id)
            parent_call_type_failure = _validate_parent_call_contains_child_voice(
                wav_path,
                x_voice_sample_id,
                current_user,
            )
            _upload_debug(
                "upload_audio:child_voice_check_done",
                file_id=file_id,
                quality_pass=parent_call_type_failure["quality_pass"],
                rejection_reason=parent_call_type_failure.get("rejection_reason"),
                child_voice_duration_seconds=parent_call_type_failure.get("child_voice_duration_seconds"),
                parent_voice_duration_seconds=parent_call_type_failure.get("parent_voice_duration_seconds"),
                detected_speaker_count=parent_call_type_failure.get("total_speakers"),
                voice_sample_similarity=parent_call_type_failure.get("voice_sample_similarity"),
                voice_sample_distance=parent_call_type_failure.get("voice_sample_distance"),
            )

        _upload_debug("upload_audio:quality_start", file_id=file_id, wav_path=wav_path)
        if x_upload_context == "self_voice":
            qc = quality_check(
                wav_path,
                min_duration_seconds=MIN_SELF_VOICE_DURATION,
                min_speech_duration_seconds=min(25.0, MIN_SELF_VOICE_DURATION),
            )
            if qc.get("quality_pass"):
                _upload_debug("upload_audio:self_voice_prompt_check_start", file_id=file_id, wav_path=wav_path)
                prompt_check = _validate_self_voice_prompt(wav_path)
                qc.update({
                    key: value
                    for key, value in prompt_check.items()
                    if key not in {"quality_pass", "rejection_reason"}
                })
                if not prompt_check["quality_pass"]:
                    qc["quality_pass"] = False
                    qc["rejection_reason"] = prompt_check["rejection_reason"]
                _upload_debug(
                    "upload_audio:self_voice_prompt_check_done",
                    file_id=file_id,
                    quality_pass=prompt_check["quality_pass"],
                    rejection_reason=prompt_check.get("rejection_reason"),
                    match_score=prompt_check.get("self_voice_prompt_match_score"),
                    keyword_coverage=prompt_check.get("self_voice_prompt_keyword_coverage"),
                    transcript_char_count=prompt_check.get("self_voice_prompt_transcript_char_count"),
                )
        else:
            qc = quality_check(wav_path)
        if parent_call_type_failure is not None:
            child_voice_check = parent_call_type_failure
            qc["child_voice_present"] = child_voice_check["quality_pass"]
            qc["child_voice_duration_seconds"] = child_voice_check.get("child_voice_duration_seconds", 0.0)
            qc["parent_voice_duration_seconds"] = child_voice_check.get("parent_voice_duration_seconds", 0.0)
            qc["detected_speaker_count"] = child_voice_check.get("total_speakers", 0)
            qc["diarization_confidence"] = child_voice_check.get("diarization_confidence")
            qc["voice_sample_distance"] = child_voice_check.get("voice_sample_distance")
            qc["voice_sample_similarity"] = child_voice_check.get("voice_sample_similarity")
            if not child_voice_check["quality_pass"]:
                qc["quality_pass"] = False
                qc["rejection_reason"] = child_voice_check["rejection_reason"]
    except Exception as e:
        _upload_debug(
            "upload_audio:quality_error",
            file_id=file_id,
            wav_path=wav_path,
            error=str(e),
            traceback=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=400,
            detail=f"오디오 품질검사 중 오류가 발생했습니다: {str(e)}",
        )
    checked_at = time.perf_counter()
    _upload_debug(
        "upload_audio:quality_done",
        file_id=file_id,
        quality_pass=qc.get("quality_pass"),
        rejection_reason=qc.get("rejection_reason"),
        duration_seconds=qc.get("duration_seconds"),
        snr_db=qc.get("snr_db"),
        silence_ratio=qc.get("silence_ratio"),
        elapsed=round(checked_at - converted_at, 3),
    )

    original_ext = os.path.splitext(file.filename or "audio.wav")[1].lower()
    qc["format_original"] = original_ext.lstrip(".")
    qc["original_duration_seconds"] = round(original_duration, 2)
    qc["trimmed_to_seconds"] = round(MAX_AUDIO_DURATION, 2) if was_trimmed else None
    qc["was_trimmed"] = was_trimmed

    file_store[file_id] = {
        "raw_path": raw_path,
        "wav_path": wav_path,
        "consent_token": x_consent_token,
        "user_id": current_user["user_id"],
        "quality": qc,
    }
    consent = get_consent_by_token(x_consent_token)
    try:
        _upload_debug("upload_audio:db_insert_start", file_id=file_id)
        execute(
            """
            INSERT INTO audio_files (
                id, user_id, consent_id, original_filename, original_format,
                storage_path, wav_path, file_size_bytes, duration_seconds,
                snr_db, silence_ratio, sample_rate, channels, quality_pass, rejection_reason
            )
            VALUES (
                CAST(:id AS uuid), CAST(:user_id AS uuid), CAST(:consent_id AS uuid),
                :original_filename, :original_format, :storage_path, :wav_path,
                :file_size_bytes, :duration_seconds, :snr_db, :silence_ratio,
                :sample_rate, :channels, :quality_pass, :rejection_reason
            )
            """,
            {
                "id": file_id,
                "user_id": str(consent["user_id"]) if consent else None,
                "consent_id": str(consent["id"]) if consent else None,
                "original_filename": file.filename or "audio.wav",
                "original_format": qc["format_original"],
                "storage_path": raw_path,
                "wav_path": wav_path,
                "file_size_bytes": len(file_bytes),
                "duration_seconds": qc["duration_seconds"],
                "snr_db": qc["snr_db"],
                "silence_ratio": qc["silence_ratio"],
                "sample_rate": qc["sample_rate"],
                "channels": qc["channels"],
                "quality_pass": qc["quality_pass"],
                "rejection_reason": qc["rejection_reason"],
            },
        )
        _upload_debug("upload_audio:db_insert_done", file_id=file_id)
    except Exception as e:
        _upload_debug(
            "upload_audio:db_insert_error",
            file_id=file_id,
            error=str(e),
            traceback=traceback.format_exc(),
        )
        _safe_print(f"[upload_audio] audio_files insert skipped: {e}")
    try:
        _upload_debug("upload_audio:retention_start", file_id=file_id)
        mark_audio_upload_retention(file_id, "rejected" if not qc["quality_pass"] else "converted")
        _upload_debug("upload_audio:retention_done", file_id=file_id)
    except Exception as e:
        _upload_debug(
            "upload_audio:retention_error",
            file_id=file_id,
            error=str(e),
            traceback=traceback.format_exc(),
        )
        _safe_print(f"[upload_audio] retention mark skipped: {e}")
    finished_at = time.perf_counter()
    _safe_print(
        "[upload_audio] "
        f"file={file.filename or 'audio.wav'} content_type={file.content_type or '-'} bytes={len(file_bytes)} "
        f"read={read_at - started_at:.2f}s save={saved_at - read_at:.2f}s "
        f"convert={converted_at - saved_at:.2f}s quality={checked_at - converted_at:.2f}s "
        f"db={finished_at - checked_at:.2f}s total={finished_at - started_at:.2f}s"
    )

    try:
        _upload_debug("upload_audio:response_build_start", file_id=file_id)
        normalized_qc = _normalize_quality_report(qc)
        quality_report = QualityReport(**normalized_qc)

        if not normalized_qc["quality_pass"]:
            msg = f"품질 검증 실패: {normalized_qc['rejection_reason']}"
        elif was_trimmed:
            msg = f"업로드 및 품질 검증이 완료되었습니다. 긴 통화 파일은 분석용으로 앞부분 {MAX_AUDIO_DURATION:.0f}초만 사용합니다."
        else:
            msg = "업로드 및 품질 검증이 완료되었습니다. 분석을 시작할 수 있습니다."

        response = UploadResponse(
            file_id=str(file_id),
            quality_report=quality_report,
            message=msg,
            file_name=file.filename or "audio.wav",
            file_size_mb=f"{len(file_bytes) / 1024 / 1024:.1f}",
        )
        _upload_debug(
            "upload_audio:response_ready",
            file_id=file_id,
            quality_pass=normalized_qc["quality_pass"],
            duration_seconds=normalized_qc["duration_seconds"],
            sample_rate=normalized_qc["sample_rate"],
            channels=normalized_qc["channels"],
        )
        return response
    except Exception as e:
        _upload_debug(
            "upload_audio:response_error",
            file_id=file_id,
            error=str(e),
            qc=qc,
            traceback=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail=f"업로드 처리 결과 생성 중 오류가 발생했습니다: {str(e)}",
        )


@router.post("/voice-sample", response_model=VoiceSampleResponse)
async def upload_voice_sample(
    file: UploadFile = File(...),
    x_consent_token: str = Header(..., alias="X-Consent-Token"),
    current_user: dict = Depends(get_current_user),
):
    ensure_retention_schema()
    _validate_consent(x_consent_token, current_user)
    _validate_audio_file(file.filename or "sample", file.content_type)

    file_bytes = await file.read()
    if len(file_bytes) > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(status_code=400, detail="음성 샘플 파일 크기가 50MB를 초과합니다.")

    sample_id, sample_path = save_voice_sample(file_bytes, file.filename or "sample.wav")

    try:
        sample_wav_path = convert_to_standard_wav(sample_path, sample_id)
    except Exception as e:
        os.remove(sample_path)
        raise HTTPException(
            status_code=400,
            detail=f"자녀 음성 변환 중 오류가 발생했습니다: {str(e)}",
        )
    if sample_wav_path != sample_path:
        remove_file_if_exists(sample_path)

    original_duration, was_trimmed = trim_wav_to_duration(sample_wav_path, MAX_VOICE_SAMPLE_DURATION)

    if original_duration < MIN_VOICE_SAMPLE_DURATION:
        remove_file_if_exists(sample_wav_path)
        raise HTTPException(status_code=400, detail=f"음성 샘플은 최소 {MIN_VOICE_SAMPLE_DURATION:.0f}초 이상이어야 합니다.")

    duration = min(original_duration, MAX_VOICE_SAMPLE_DURATION)

    prompt_check = _validate_child_voice_prompt(sample_wav_path)
    if not prompt_check["quality_pass"]:
        remove_file_if_exists(sample_wav_path)
        raise HTTPException(
            status_code=400,
            detail=prompt_check["rejection_reason"] or "화면의 안내 문장을 읽은 음성인지 확인하지 못했습니다.",
        )

    try:
        embedding = get_voice_sample_embedding(sample_wav_path)
    except Exception:
        embedding = None

    voice_sample_store[sample_id] = {
        "path": sample_wav_path,
        "consent_token": x_consent_token,
        "user_id": current_user["user_id"],
        "duration": duration,
        "embedding": embedding.tolist() if embedding is not None else None,
    }
    consent = get_consent_by_token(x_consent_token)
    execute(
        """
        INSERT INTO voice_samples (
            id, user_id, consent_id, original_filename, storage_path, duration_seconds, embedding
        )
        VALUES (
            CAST(:id AS uuid), CAST(:user_id AS uuid), CAST(:consent_id AS uuid),
            :original_filename, :storage_path, :duration_seconds, CAST(:embedding AS jsonb)
        )
        """,
        {
            "id": sample_id,
            "user_id": str(consent["user_id"]) if consent else None,
            "consent_id": str(consent["id"]) if consent else None,
            "original_filename": file.filename or "sample.wav",
            "storage_path": sample_wav_path,
            "duration_seconds": round(duration, 2),
            "embedding": json.dumps(embedding.tolist() if embedding is not None else None),
        },
    )
    mark_voice_sample_retention(sample_id)

    if was_trimmed:
        message = f"음성 샘플이 등록되었습니다. 긴 녹음은 앞부분 {MAX_VOICE_SAMPLE_DURATION:.0f}초만 사용합니다."
    else:
        message = f"음성 샘플이 등록되었습니다. ({duration:.1f}초)"

    return VoiceSampleResponse(
        sample_id=sample_id,
        duration_seconds=round(duration, 2),
        original_duration_seconds=round(original_duration, 2),
        trimmed_to_seconds=round(MAX_VOICE_SAMPLE_DURATION, 2) if was_trimmed else None,
        was_trimmed=was_trimmed,
        message=message,
    )


@router.get("/files/{file_id}")
async def get_file_info(file_id: str, current_user: dict = Depends(get_current_user)):
    if file_id in file_store:
        info = file_store[file_id]
        if str(info.get("user_id")) != current_user["user_id"]:
            raise HTTPException(status_code=403, detail="현재 사용자에게 속한 파일이 아닙니다.")
        return {
            "file_id": file_id,
            "quality": info["quality"],
        }
    db_file = get_audio_file(file_id)
    if not db_file:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    if str(db_file["user_id"]) != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="현재 사용자에게 속한 파일이 아닙니다.")
    return {
        "file_id": file_id,
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


@router.get("/audio/latest")
async def get_latest_audio_upload(
    x_consent_token: str = Header(..., alias="X-Consent-Token"),
    x_upload_started_at: str | None = Header(default=None, alias="X-Upload-Started-At"),
    current_user: dict = Depends(get_current_user),
):
    consent = _validate_consent(x_consent_token, current_user)
    started_filter = ""
    params = {
        "user_id": current_user["user_id"],
        "consent_id": str(consent["db_id"]),
    }
    if x_upload_started_at:
        started_filter = "AND created_at >= CAST(:started_at AS timestamptz) - INTERVAL '30 seconds'"
        params["started_at"] = x_upload_started_at
    db_file = fetch_one(
        f"""
        SELECT *
        FROM audio_files
        WHERE user_id = CAST(:user_id AS uuid)
          AND consent_id = CAST(:consent_id AS uuid)
          AND deleted_at IS NULL
          AND wav_path IS NOT NULL
          {started_filter}
        ORDER BY created_at DESC
        LIMIT 1
        """,
        params,
    )
    if not db_file:
        raise HTTPException(status_code=404, detail="최근 통화녹음 업로드 결과가 없습니다.")
    return {
        "file_id": str(db_file["id"]),
        "file_name": db_file["original_filename"] or "선택한 통화녹음 파일",
        "file_size_mb": f"{float(db_file['file_size_bytes'] or 0) / 1024 / 1024:.1f}",
        "quality_report": QualityReport(**_normalize_quality_report({
            "duration_seconds": db_file["duration_seconds"],
            "snr_db": db_file["snr_db"],
            "silence_ratio": db_file["silence_ratio"],
            "sample_rate": db_file["sample_rate"],
            "channels": db_file["channels"],
            "format_original": db_file["original_format"],
            "quality_pass": db_file["quality_pass"],
            "rejection_reason": db_file["rejection_reason"],
        })),
    }
