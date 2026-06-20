from functools import lru_cache
from typing import Any

from app.config import env_int, env_str


STT_ENABLED_VALUES = {"1", "true", "yes", "on"}


class STTUnavailable(RuntimeError):
    pass


def stt_enabled() -> bool:
    return env_str("SORIMEMO_STT_ENABLED", "true").strip().lower() in STT_ENABLED_VALUES


@lru_cache(maxsize=1)
def _load_faster_whisper_model() -> Any:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise STTUnavailable("faster-whisper 패키지가 설치되어 있지 않습니다.") from exc

    model_size = env_str("SORIMEMO_STT_MODEL_SIZE", "small").strip() or "small"
    device = env_str("SORIMEMO_STT_DEVICE", "cpu").strip() or "cpu"
    compute_type = env_str("SORIMEMO_STT_COMPUTE_TYPE", "int8").strip() or "int8"
    try:
        return WhisperModel(model_size, device=device, compute_type=compute_type)
    except Exception as exc:
        raise STTUnavailable(f"STT 모델을 로드할 수 없습니다: {model_size} ({exc})") from exc


def transcribe_audio(audio_path: str) -> dict[str, Any]:
    if not stt_enabled():
        return {
            "transcript_text": None,
            "stt_available": False,
            "stt_engine": "disabled",
            "stt_confidence": 0.0,
            "transcript_char_count": 0,
            "stt_note": "STT가 비활성화되어 전사를 수행하지 않았습니다.",
        }

    try:
        model = _load_faster_whisper_model()
        language = env_str("SORIMEMO_STT_LANGUAGE", "ko").strip() or "ko"
        beam_size = env_int("SORIMEMO_STT_BEAM_SIZE", "1")
        segments, info = model.transcribe(
            audio_path,
            language=language,
            beam_size=beam_size,
            vad_filter=True,
        )
        segment_list = list(segments)
        transcript = " ".join(segment.text.strip() for segment in segment_list if segment.text.strip())
        avg_logprob_values = [
            float(segment.avg_logprob)
            for segment in segment_list
            if getattr(segment, "avg_logprob", None) is not None
        ]
        avg_logprob = sum(avg_logprob_values) / len(avg_logprob_values) if avg_logprob_values else -2.0
        confidence = max(0.0, min(1.0, (avg_logprob + 2.0) / 2.0))
        detected_language = getattr(info, "language", language)
        return {
            "transcript_text": transcript or None,
            "stt_available": bool(transcript),
            "stt_engine": f"faster-whisper:{env_str('SORIMEMO_STT_MODEL_SIZE', 'small')}",
            "stt_confidence": round(float(confidence), 4),
            "transcript_char_count": len(transcript),
            "stt_language": detected_language,
            "stt_note": "STT 전사를 완료했습니다." if transcript else "STT 결과가 비어 있습니다.",
        }
    except STTUnavailable as exc:
        return {
            "transcript_text": None,
            "stt_available": False,
            "stt_engine": "faster-whisper",
            "stt_confidence": 0.0,
            "transcript_char_count": 0,
            "stt_note": str(exc),
        }
    except Exception as exc:
        return {
            "transcript_text": None,
            "stt_available": False,
            "stt_engine": "faster-whisper",
            "stt_confidence": 0.0,
            "transcript_char_count": 0,
            "stt_note": f"STT 처리 중 오류가 발생했습니다: {exc}",
        }
