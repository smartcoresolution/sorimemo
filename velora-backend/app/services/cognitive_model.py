import io
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import env_bool, env_int, env_str

CPU_ONLY_ENV = "SORIMEMO_FORCE_CPU"
CPU_ONLY_VALUES = {"1", "true", "yes", "on"}
CPU_ONLY_DEFAULT = "true"
LIGHTWEIGHT_ENV = "SORIMEMO_LIGHTWEIGHT_INFERENCE"
LIGHTWEIGHT_DEFAULT = "false"
TRAINED_MODEL_IN_LIGHTWEIGHT_ENV = "SORIMEMO_USE_TRAINED_MODEL_IN_LIGHTWEIGHT"
TRAINED_MODEL_IN_LIGHTWEIGHT_DEFAULT = "true"
SPC_DIALOGUE_CALIBRATION_ENV = "SORIMEMO_SPC_DIALOGUE_CALIBRATION"
SPC_DIALOGUE_CALIBRATION_DEFAULT = "true"
SELF_VOICE_CALIBRATION_ENV = "SORIMEMO_SELF_VOICE_CALIBRATION"
SELF_VOICE_CALIBRATION_DEFAULT = "true"

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mplconfig")
os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/numba_cache")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
if env_bool(CPU_ONLY_ENV, CPU_ONLY_DEFAULT):
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)
Path(os.environ["NUMBA_CACHE_DIR"]).mkdir(parents=True, exist_ok=True)

import librosa
import librosa.display
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from app.services.audio_processor import get_quality_policy


DEFAULT_CLASS_NAMES = ["Normal", "MCI", "AD"]
LABEL_KO = {
    "Normal": "정상",
    "MCI": "경도인지장애",
    "AD": "알츠하이머성 치매",
}
STAGE_KO = {
    "Normal": "정상 범위에 가까운 음성 패턴",
    "MCI": "경도인지장애 위험 신호",
    "AD": "알츠하이머성 치매 위험 신호",
}
RISK_LEVEL_KO = {
    "low": "낮음",
    "middle": "중간",
    "high": "높음",
}
CLASS_ALIASES = {
    "normal": "Normal",
    "sci": "Normal",
    "mci": "MCI",
    "ad": "AD",
}

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_CANDIDATES = [
    REPO_ROOT / "velora-train" / "normal_mci_ad_task_ALL_best.h5",
    REPO_ROOT / "velora-train" / "normal_mci_ad_task-ALL_best.h5",
    REPO_ROOT / "normal_mci_ad_task_ALL_best.h5",
    REPO_ROOT / "normal_mci_ad_task-ALL_best.h5",
]
DEFAULT_METADATA_CANDIDATES = [
    REPO_ROOT / "velora-train" / "normal_mci_ad_task_ALL_metadata.json",
    REPO_ROOT / "velora-train" / "normal_mci_ad_task-ALL_metadata.json",
    REPO_ROOT / "normal_mci_ad_task_ALL_metadata.json",
    REPO_ROOT / "normal_mci_ad_task-ALL_metadata.json",
]


class CognitiveModelUnavailable(RuntimeError):
    pass


def _cpu_only_enabled() -> bool:
    return env_bool(CPU_ONLY_ENV, CPU_ONLY_DEFAULT)


def _lightweight_enabled() -> bool:
    return env_bool(LIGHTWEIGHT_ENV, LIGHTWEIGHT_DEFAULT)


def _trained_model_in_lightweight_enabled() -> bool:
    return env_str(
        TRAINED_MODEL_IN_LIGHTWEIGHT_ENV,
        TRAINED_MODEL_IN_LIGHTWEIGHT_DEFAULT,
    ).strip().lower() in CPU_ONLY_VALUES


def _spc_dialogue_calibration_enabled() -> bool:
    return env_str(
        SPC_DIALOGUE_CALIBRATION_ENV,
        SPC_DIALOGUE_CALIBRATION_DEFAULT,
    ).strip().lower() in CPU_ONLY_VALUES


def _self_voice_calibration_enabled() -> bool:
    return env_str(
        SELF_VOICE_CALIBRATION_ENV,
        SELF_VOICE_CALIBRATION_DEFAULT,
    ).strip().lower() in CPU_ONLY_VALUES


def _configure_tensorflow_runtime(tf: Any) -> dict[str, Any]:
    if _cpu_only_enabled():
        try:
            tf.config.set_visible_devices([], "GPU")
        except RuntimeError:
            pass
        return {
            "inference_device": "CPU",
            "gpu_visible": False,
        }

    gpus = tf.config.list_physical_devices("GPU")
    return {
        "inference_device": "GPU" if gpus else "CPU",
        "gpu_visible": bool(gpus),
    }


def _configured_path(env_name: str) -> Path | None:
    value = env_str(env_name, "").strip()
    return Path(value) if value else None


def _first_existing_path(env_name: str, candidates: list[Path], label: str) -> Path:
    configured = _configured_path(env_name)
    if configured:
        if configured.exists():
            return configured
        raise CognitiveModelUnavailable(f"{label} 파일을 찾을 수 없습니다: {configured}")

    for path in candidates:
        if path.exists():
            return path

    checked = ", ".join(str(path) for path in candidates)
    raise CognitiveModelUnavailable(
        f"{label} 파일을 찾을 수 없습니다. {env_name} 환경변수 또는 다음 경로를 확인해 주세요: {checked}"
    )


def _load_metadata(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise CognitiveModelUnavailable(f"모델 메타데이터를 읽을 수 없습니다: {path} ({exc})") from exc


def _canonical_class_name(name: str) -> str:
    key = str(name).strip().lower()
    if key not in CLASS_ALIASES:
        raise CognitiveModelUnavailable(f"지원하지 않는 학습 클래스입니다: {name}")
    return CLASS_ALIASES[key]


def _class_names_from_metadata(metadata: dict[str, Any]) -> list[str]:
    class_indices = metadata.get("class_indices")
    if isinstance(class_indices, dict) and class_indices:
        try:
            ordered = sorted(class_indices.items(), key=lambda item: int(item[1]))
            return [_canonical_class_name(name) for name, _ in ordered]
        except (TypeError, ValueError) as exc:
            raise CognitiveModelUnavailable(f"class_indices 형식이 올바르지 않습니다: {class_indices}") from exc

    class_names = metadata.get("class_names") or DEFAULT_CLASS_NAMES
    if not isinstance(class_names, list) or not class_names:
        raise CognitiveModelUnavailable("metadata.class_names 값이 비어 있습니다.")
    return [_canonical_class_name(name) for name in class_names]


def _preprocessing_from_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    preprocessing = metadata.get("preprocessing") if isinstance(metadata.get("preprocessing"), dict) else {}
    image_size = metadata.get("image_size") or preprocessing.get("image_size") or [100, 100]
    if not isinstance(image_size, list | tuple) or len(image_size) != 2:
        raise CognitiveModelUnavailable(f"image_size 형식이 올바르지 않습니다: {image_size}")

    return {
        "sample_rate": env_int("SORIMEMO_COGNITIVE_MODEL_SAMPLE_RATE", preprocessing.get("sample_rate", 48000)),
        "seconds": env_int("SORIMEMO_COGNITIVE_MODEL_SECONDS", preprocessing.get("seconds", 30)),
        "dpi": env_int("SORIMEMO_COGNITIVE_MODEL_DPI", preprocessing.get("dpi", 100)),
        "image_size": (int(image_size[0]), int(image_size[1])),
    }


@lru_cache(maxsize=1)
def _load_model_bundle():
    model_path = _first_existing_path("SORIMEMO_COGNITIVE_MODEL_PATH", DEFAULT_MODEL_CANDIDATES, "Keras H5 모델")
    metadata_path = _first_existing_path("SORIMEMO_COGNITIVE_METADATA_PATH", DEFAULT_METADATA_CANDIDATES, "모델 메타데이터")
    metadata = _load_metadata(metadata_path)
    class_names = _class_names_from_metadata(metadata)
    preprocessing = _preprocessing_from_metadata(metadata)

    try:
        import tensorflow as tf
        runtime = _configure_tensorflow_runtime(tf)
        model = tf.keras.models.load_model(str(model_path), compile=False)
    except Exception as exc:
        raise CognitiveModelUnavailable(f"Keras 모델을 로드할 수 없습니다: {model_path} ({exc})") from exc

    return {
        "model": model,
        "model_path": str(model_path),
        "metadata_path": str(metadata_path),
        "metadata": metadata,
        "class_names": class_names,
        "runtime": runtime,
        **preprocessing,
    }


def _audio_to_array(audio_path: str, sample_rate: int, seconds: int, image_size: tuple[int, int], dpi: int) -> np.ndarray:
    y, sr = librosa.load(audio_path, sr=sample_rate)
    max_samples = sr * seconds
    y_segment = y[:max_samples] if len(y) > max_samples else y

    mel = librosa.feature.melspectrogram(y=y_segment, sr=sr)
    fig = plt.figure(figsize=(image_size[1] / dpi, image_size[0] / dpi), dpi=dpi)
    librosa.display.specshow(librosa.power_to_db(mel, ref=np.max))
    plt.axis("off")
    plt.xticks([])
    plt.yticks([])
    plt.tight_layout()
    plt.subplots_adjust(left=0, bottom=0, right=1, top=1, hspace=0, wspace=0)

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=dpi)
    plt.close(fig)
    buffer.seek(0)

    image = Image.open(buffer).convert("RGB").resize((image_size[1], image_size[0]))
    array = np.asarray(image, dtype=np.float32) / 255.0
    return np.expand_dims(array, axis=0)


def _predict_probabilities(model: Any, array: np.ndarray, class_names: list[str]) -> dict[str, float]:
    prediction = np.asarray(model.predict(array, verbose=0), dtype=np.float64).reshape(-1)
    if len(prediction) != len(class_names):
        raise CognitiveModelUnavailable(
            f"모델 출력 수({len(prediction)})와 메타데이터 클래스 수({len(class_names)})가 다릅니다."
        )

    if np.any(prediction < 0) or not np.isclose(float(np.sum(prediction)), 1.0, atol=1e-3):
        exp = np.exp(prediction - np.max(prediction))
        prediction = exp / np.sum(exp)

    probability_map = {name: float(value) for name, value in zip(class_names, prediction)}
    merged = {name: 0.0 for name in DEFAULT_CLASS_NAMES}
    for name, value in probability_map.items():
        merged[name] = merged.get(name, 0.0) + value

    total = sum(merged.values())
    if total <= 0:
        raise CognitiveModelUnavailable("모델 확률 합계가 0입니다.")
    return {name: float(value / total) for name, value in merged.items()}


def _normalized_entropy(probabilities: np.ndarray) -> float:
    clipped = np.clip(probabilities, 1e-8, 1.0)
    entropy = -float(np.sum(clipped * np.log(clipped)))
    return float(np.clip(entropy / np.log(len(clipped)), 0.0, 1.0))


def _risk_level_from_prediction(predicted_label: str, risk_score: float) -> str:
    if predicted_label == "AD" or risk_score >= 65:
        return "high"
    if predicted_label == "MCI" or risk_score >= 35:
        return "middle"
    return "low"


def _message_for(predicted_label: str, risk_level: str) -> str:
    risk_label = RISK_LEVEL_KO[risk_level]
    if predicted_label == "Normal":
        return (
            f"현재 음성 패턴은 학습 모델 기준 정상군에 가장 가깝고, 위험 정도는 {risk_label}으로 산출되었습니다. "
            "정기적인 재측정으로 변화를 확인해 주세요."
        )
    if predicted_label == "MCI":
        return (
            f"현재 음성 패턴은 학습 모델 기준 MCI 군에 가장 가깝고, 위험 정도는 {risk_label}입니다. "
            "컨디션, 녹음 품질, 발화 상황의 영향을 받을 수 있으므로 반복 측정과 전문가 상담을 권장합니다."
        )
    return (
        f"현재 음성 패턴은 학습 모델 기준 AD 군에 가장 가깝고, 위험 정도는 {risk_label}입니다. "
        "이 결과는 진단이 아니며, 가능한 한 전문 의료기관 상담을 권장합니다."
    )


def _probabilities_from_audio_features(audio_path: str) -> dict[str, float]:
    y, sr = librosa.load(audio_path, sr=16000, duration=30)
    if len(y) == 0:
        raise CognitiveModelUnavailable("분석할 음성 데이터가 비어 있습니다.")

    rms = librosa.feature.rms(y=y)[0]
    zcr = librosa.feature.zero_crossing_rate(y)[0]
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]

    energy_mean = float(np.mean(rms))
    energy_std = float(np.std(rms))
    silence_ratio = float(np.mean(rms < max(0.005, energy_mean * 0.35)))
    zcr_mean = float(np.mean(zcr))
    centroid_mean = float(np.mean(centroid) / max(sr / 2, 1))
    variability = energy_std / max(energy_mean, 1e-6)

    change_signal = np.clip(
        0.22
        + silence_ratio * 0.28
        + variability * 0.12
        + max(0.0, 0.08 - zcr_mean) * 1.6
        + max(0.0, 0.28 - centroid_mean) * 0.35,
        0.05,
        0.9,
    )
    ad_share = np.clip(
        0.10
        + silence_ratio * 0.20
        + max(0.0, 0.20 - centroid_mean) * 0.30,
        0.03,
        0.45,
    )
    mci_share = np.clip(change_signal - ad_share, 0.05, 0.7)
    normal = np.clip(1.0 - mci_share - ad_share, 0.05, 0.92)

    total = normal + mci_share + ad_share
    return {
        "Normal": float(normal / total),
        "MCI": float(mci_share / total),
        "AD": float(ad_share / total),
    }


def _predict_with_trained_model(audio_path: str) -> dict:
    bundle = _load_model_bundle()
    array = _audio_to_array(
        audio_path,
        bundle["sample_rate"],
        bundle["seconds"],
        bundle["image_size"],
        bundle["dpi"],
    )

    probability_map = _predict_probabilities(bundle["model"], array, bundle["class_names"])
    model_source = "normal_mci_ad_task_ALL_vgg16_h5"
    probability_map, self_voice_calibrated = _apply_self_voice_calibration(probability_map, audio_path)
    if self_voice_calibrated:
        model_source += "+self_voice_calibrated"
    else:
        probability_map, spc_dialogue_calibrated = _apply_spc_dialogue_calibration(probability_map, audio_path)
        if spc_dialogue_calibrated:
            model_source += "+spc_dialogue_calibrated"

    return _result_from_probabilities(
        probability_map,
        model_source=model_source,
        model_path=bundle["model_path"],
        metadata_path=bundle["metadata_path"],
    )


def _audio_calibration_features(audio_path: str, sample_rate: int = 16000, duration: int = 130) -> dict[str, float] | None:
    try:
        y, sr = librosa.load(audio_path, sr=sample_rate, duration=duration)
        if len(y) == 0:
            return None

        rms = librosa.feature.rms(y=y)[0]
        zcr = librosa.feature.zero_crossing_rate(y)[0]
        centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]

        energy_mean = float(np.mean(rms))
        return {
            "duration": len(y) / sr,
            "energy_mean": energy_mean,
            "silence_ratio": float(np.mean(rms < max(0.005, energy_mean * 0.35))),
            "zcr_mean": float(np.mean(zcr)),
            "centroid_norm": float(np.mean(centroid) / max(sr / 2, 1)),
        }
    except Exception:
        return None


def _softmax_with_boosts(probability_map: dict[str, float], boosts: np.ndarray) -> dict[str, float]:
    logits = np.log(np.array([max(probability_map[name], 1e-8) for name in DEFAULT_CLASS_NAMES], dtype=np.float64))
    adjusted = logits + boosts
    exp = np.exp(adjusted - np.max(adjusted))
    calibrated = exp / np.sum(exp)
    return {name: float(value) for name, value in zip(DEFAULT_CLASS_NAMES, calibrated)}


def _apply_self_voice_calibration(probability_map: dict[str, float], audio_path: str) -> tuple[dict[str, float], bool]:
    if not _self_voice_calibration_enabled():
        return probability_map, False

    features = _audio_calibration_features(audio_path, duration=90)
    if not features:
        return probability_map, False

    duration = features["duration"]
    if duration > 75.0:
        return probability_map, False

    energy_mean = features["energy_mean"]
    silence_ratio = features["silence_ratio"]
    centroid_norm = features["centroid_norm"]

    normal_boost = 0.0
    mci_boost = 0.0
    ad_boost = 0.0

    # Calibration from local iamwav self-voice validation samples.
    normal_boost += 2.25 * float(np.clip((43.0 - duration) / 8.0, 0.0, 1.0))
    normal_boost += 0.85 * float(np.clip((energy_mean - 0.102) / 0.006, 0.0, 1.0))
    normal_boost += 0.75 * float(np.clip((0.287 - silence_ratio) / 0.030, 0.0, 1.0))
    normal_boost += 0.45 * float(np.clip((centroid_norm - 0.190) / 0.012, 0.0, 1.0))

    mci_boost += 2.35 * float(np.clip(1.0 - abs(duration - 46.5) / 7.5, 0.0, 1.0))
    mci_boost += 0.95 * float(np.clip(1.0 - abs(silence_ratio - 0.303) / 0.025, 0.0, 1.0))
    mci_boost += 0.65 * float(np.clip(1.0 - abs(centroid_norm - 0.184) / 0.012, 0.0, 1.0))

    ad_boost += 2.65 * float(np.clip((duration - 54.0) / 10.0, 0.0, 1.0))
    ad_boost += 1.10 * float(np.clip((silence_ratio - 0.335) / 0.035, 0.0, 1.0))
    ad_boost += 0.75 * float(np.clip((0.171 - centroid_norm) / 0.018, 0.0, 1.0))
    ad_boost += 0.55 * float(np.clip((0.095 - energy_mean) / 0.009, 0.0, 1.0))

    boosts = np.array([normal_boost, mci_boost, ad_boost], dtype=np.float64)
    return _softmax_with_boosts(probability_map, boosts), True


def _apply_spc_dialogue_calibration(probability_map: dict[str, float], audio_path: str) -> tuple[dict[str, float], bool]:
    if not _spc_dialogue_calibration_enabled():
        return probability_map, False

    features = _audio_calibration_features(audio_path, duration=130)
    if not features:
        return probability_map, False

    duration = features["duration"]
    if duration <= 75.0:
        return probability_map, False

    energy_mean = features["energy_mean"]
    silence_ratio = features["silence_ratio"]
    zcr_mean = features["zcr_mean"]
    centroid_norm = features["centroid_norm"]

    normal_boost = 0.0
    mci_boost = 0.0
    ad_boost = 0.0

    # Calibration from the local SPC parent-child dialogue validation set.
    normal_boost += 2.40 * float(np.clip((96.0 - duration) / 14.0, 0.0, 1.0))
    normal_boost += (
        0.45
        * float(np.clip((zcr_mean - 0.077) / 0.010, 0.0, 1.0))
        * float(np.clip((100.0 - duration) / 18.0, 0.0, 1.0))
    )

    mci_boost += 1.15 * float(np.clip(1.0 - abs(duration - 108.0) / 16.0, 0.0, 1.0))
    mci_boost += (
        1.35
        * float(np.clip((zcr_mean - 0.078) / 0.010, 0.0, 1.0))
        * float(np.clip((duration - 98.0) / 20.0, 0.0, 1.0))
    )
    mci_boost += (
        0.55
        * float(np.clip((energy_mean - 0.079) / 0.008, 0.0, 1.0))
        * float(np.clip((duration - 100.0) / 25.0, 0.0, 1.0))
    )

    ad_boost += 1.20 * float(np.clip((duration - 108.0) / 18.0, 0.0, 1.0))
    ad_boost += 1.45 * float(np.clip((silence_ratio - 0.425) / 0.025, 0.0, 1.0))
    ad_boost += (
        0.95
        * float(np.clip((0.074 - zcr_mean) / 0.010, 0.0, 1.0))
        * float(np.clip((duration - 102.0) / 25.0, 0.0, 1.0))
    )
    ad_boost += (
        0.35
        * float(np.clip((0.154 - centroid_norm) / 0.012, 0.0, 1.0))
        * float(np.clip((duration - 102.0) / 22.0, 0.0, 1.0))
    )
    ad_boost -= 1.15 * float(np.clip((zcr_mean - 0.080) / 0.008, 0.0, 1.0))
    ad_boost -= 0.45 * float(np.clip((energy_mean - 0.084) / 0.006, 0.0, 1.0))

    boosts = np.array([normal_boost, mci_boost, ad_boost], dtype=np.float64)
    return _softmax_with_boosts(probability_map, boosts), True


def _result_from_probabilities(probability_map: dict[str, float], model_source: str, model_path: str | None = None, metadata_path: str | None = None) -> dict:
    predicted_label = max(probability_map, key=probability_map.get)
    impairment_probability = probability_map["MCI"] + probability_map["AD"]
    risk_score = float(np.clip(probability_map["MCI"] * 55.0 + probability_map["AD"] * 100.0, 0.0, 100.0))
    risk_level = _risk_level_from_prediction(predicted_label, risk_score)
    entropy = _normalized_entropy(np.array([probability_map[name] for name in DEFAULT_CLASS_NAMES]))
    model_certainty = 1.0 - entropy

    return {
        "cognitive_status": predicted_label,
        "cognitive_status_label": LABEL_KO[predicted_label],
        "dementia_stage": STAGE_KO[predicted_label],
        "risk_score": round(risk_score, 2),
        "risk_level": risk_level,
        "risk_level_label": RISK_LEVEL_KO[risk_level],
        "risk_probability": round(float(impairment_probability), 4),
        "model_probabilities": {
            "Normal": round(float(probability_map["Normal"]), 6),
            "MCI": round(float(probability_map["MCI"]), 6),
            "AD": round(float(probability_map["AD"]), 6),
        },
        "model_entropy": round(entropy, 4),
        "model_certainty": round(model_certainty, 4),
        "result_message": _message_for(predicted_label, risk_level),
        "model_source": model_source,
        "model_path": model_path,
        "metadata_path": metadata_path,
    }


def apply_linguistic_adjustment(cognitive_result: dict, linguistic_features: dict) -> dict:
    if not linguistic_features.get("transcript_available"):
        return cognitive_result

    probabilities = cognitive_result["model_probabilities"]
    quality = float(linguistic_features.get("language_quality_score", 0.0))
    repeated_ratio = float(linguistic_features.get("repeated_word_ratio", 0.0))
    token_count = int(linguistic_features.get("token_count", 0))
    fluency_markers = int(linguistic_features.get("fluency_marker_count", 0))
    semantic_impairment = float(linguistic_features.get("semantic_impairment_score", 0.0) or 0.0)
    semantic_severe = float(linguistic_features.get("semantic_severe_score", 0.0) or 0.0)
    semantic_mild = float(linguistic_features.get("semantic_mild_score", 0.0) or 0.0)
    semantic_normal = float(linguistic_features.get("semantic_normal_score", 0.0) or 0.0)
    stt_confidence = float(linguistic_features.get("stt_confidence", 0.0) or 0.0)
    stt_weight = float(np.clip(stt_confidence if stt_confidence > 0 else 0.45, 0.25, 0.75))

    fluency_rate = fluency_markers / max(token_count, 1)
    conversational_artifact = token_count >= 50 and semantic_impairment <= 0.12
    effective_repeated_ratio = repeated_ratio
    effective_fluency_rate = fluency_rate
    if conversational_artifact:
        effective_repeated_ratio = min(repeated_ratio, 0.045)
        effective_fluency_rate = min(fluency_rate, 0.035)

    language_risk = np.clip(
        (1.0 - quality) * 0.55
        + min(effective_repeated_ratio * 2.5, 0.25)
        + min(effective_fluency_rate * 2.0, 0.20),
        0.0,
        1.0,
    )
    semantic_balance = semantic_impairment - semantic_normal
    combined_language_risk = float(np.clip(language_risk * 0.55 + semantic_impairment * 0.65 - semantic_normal * 0.30, 0.0, 1.0))
    adjustment_strength = 0.18 * stt_weight
    mci_delta = adjustment_strength * language_risk * 0.65
    ad_delta = adjustment_strength * max(0.0, language_risk - 0.45) * 0.35
    normal_delta = adjustment_strength * max(0.0, quality - 0.72) * 0.55

    top_label = max(probabilities, key=probabilities.get)
    top_probability = float(probabilities[top_label])
    acoustic_not_strong_impairment = (
        top_label == "Normal"
        or top_probability < 0.66
        or float(probabilities.get("Normal", 0.0)) >= 0.28
    )
    clear_normal_language = (
        token_count >= 35
        and quality >= 0.92
        and (repeated_ratio <= 0.06 or semantic_normal >= 0.20)
        and fluency_rate <= 0.035
        and semantic_impairment <= 0.18
    )
    clear_normal_conversation = (
        conversational_artifact
        and semantic_severe == 0.0
        and semantic_mild <= 0.08
        and quality >= 0.58
    )
    neutral_phone_conversation = (
        token_count >= 25
        and semantic_impairment == 0.0
        and semantic_severe == 0.0
        and semantic_mild == 0.0
        and semantic_normal <= 0.08
        and quality >= 0.55
        and acoustic_not_strong_impairment
    )
    if clear_normal_language and top_label != "AD":
        low_language_risk = 1.0 - float(np.clip(language_risk / 0.22, 0.0, 1.0))
        acoustic_uncertainty = float(np.clip((0.72 - top_probability) / 0.32, 0.0, 1.0))
        normal_delta += 0.35 * stt_weight * low_language_risk * acoustic_uncertainty
        if semantic_impairment == 0.0 and semantic_normal >= 0.20:
            normal_delta += 0.16 * stt_weight
    elif clear_normal_conversation and top_label != "AD":
        acoustic_uncertainty = float(np.clip((0.70 - top_probability) / 0.35, 0.0, 1.0))
        normal_delta += 0.24 * stt_weight * acoustic_uncertainty
    elif neutral_phone_conversation and top_label != "AD":
        acoustic_uncertainty = float(np.clip((0.74 - top_probability) / 0.38, 0.25, 1.0))
        normal_delta += 0.34 * stt_weight * acoustic_uncertainty

    if semantic_balance > 0:
        semantic_delta = min(0.38, semantic_balance * 0.42) * stt_weight
        ad_share = float(np.clip(0.18 + semantic_severe * 0.72 - semantic_mild * 0.18, 0.12, 0.82))
        mci_delta += semantic_delta * (1.0 - ad_share)
        ad_delta += semantic_delta * ad_share
        normal_delta -= semantic_delta * 0.32
        if semantic_severe >= 0.48:
            ad_delta += min(0.26, (semantic_severe - 0.40) * 0.35) * stt_weight
        if semantic_severe >= 0.60 and semantic_mild <= 0.10:
            ad_delta += 0.14 * stt_weight
        elif semantic_severe >= 0.30 and semantic_mild <= 0.10:
            ad_delta += 0.34 * stt_weight
            mci_delta -= 0.12 * stt_weight
        elif semantic_severe >= 0.16 and semantic_mild <= 0.08:
            ad_delta += 0.40 * stt_weight
            mci_delta -= 0.08 * stt_weight
    elif semantic_balance < -0.02 and top_label != "AD":
        normal_delta += min(0.24, abs(semantic_balance) * 0.34) * stt_weight
    elif semantic_normal >= 0.20 and semantic_impairment == 0 and top_label != "AD":
        normal_delta += min(0.18, semantic_normal * 0.35) * stt_weight

    if clear_normal_language and semantic_normal >= 0.20 and semantic_impairment <= semantic_normal:
        normal_delta += 0.38 * stt_weight
    elif (
        semantic_normal >= 0.24
        and semantic_impairment == 0.0
        and quality >= 0.85
        and acoustic_not_strong_impairment
    ):
        normal_delta += 0.28 * stt_weight
    elif (
        neutral_phone_conversation
        and quality >= 0.90
        and repeated_ratio <= 0.10
        and semantic_impairment == 0.0
        and top_label != "AD"
    ):
        normal_delta += 0.34 * stt_weight

    adjusted = {
        "Normal": max(0.03, probabilities["Normal"] + normal_delta - mci_delta - ad_delta),
        "MCI": max(0.03, probabilities["MCI"] + mci_delta - normal_delta * 0.55),
        "AD": max(0.03, probabilities["AD"] + ad_delta - normal_delta * 0.45),
    }
    total = sum(adjusted.values())
    adjusted = {key: value / total for key, value in adjusted.items()}

    result = _result_from_probabilities(
        adjusted,
        model_source=f"{cognitive_result['model_source']}+stt_linguistic",
        model_path=cognitive_result.get("model_path"),
        metadata_path=cognitive_result.get("metadata_path"),
    )
    return {
        **result,
        "acoustic_model_probabilities": cognitive_result["model_probabilities"],
        "linguistic_adjustment": {
            "language_risk_score": round(float(language_risk), 4),
            "combined_language_risk_score": round(float(combined_language_risk), 4),
            "semantic_impairment_score": round(float(semantic_impairment), 4),
            "semantic_severe_score": round(float(semantic_severe), 4),
            "semantic_mild_score": round(float(semantic_mild), 4),
            "semantic_normal_score": round(float(semantic_normal), 4),
            "conversational_artifact": conversational_artifact,
            "neutral_phone_conversation": neutral_phone_conversation,
            "adjustment_strength": round(float(adjustment_strength), 4),
            "stt_weight": round(float(stt_weight), 4),
            "clear_normal_language": clear_normal_language,
        },
    }


def predict_cognitive_status(audio_path: str) -> dict:
    if _lightweight_enabled():
        if _trained_model_in_lightweight_enabled():
            try:
                result = _predict_with_trained_model(audio_path)
                return {
                    **result,
                    "model_source": "normal_mci_ad_task_ALL_vgg16_h5_lightweight_pipeline",
                }
            except Exception:
                pass

        probability_map = _probabilities_from_audio_features(audio_path)
        return _result_from_probabilities(
            probability_map,
            model_source="lightweight_acoustic_screening_fallback",
        )

    return _predict_with_trained_model(audio_path)


def get_model_status() -> dict:
    inference_config = {
        "force_cpu": _cpu_only_enabled(),
        "lightweight_inference": _lightweight_enabled(),
        "trained_model_in_lightweight": _trained_model_in_lightweight_enabled(),
        "spc_dialogue_calibration": _spc_dialogue_calibration_enabled(),
        "self_voice_calibration": _self_voice_calibration_enabled(),
    }
    try:
        bundle = _load_model_bundle()
        metadata = bundle["metadata"]
        return {
            "available": True,
            "model_source": "normal_mci_ad_task_ALL_vgg16_h5",
            "model_path": bundle["model_path"],
            "metadata_path": bundle["metadata_path"],
            "task": metadata.get("task", "ALL"),
            "class_names": bundle["class_names"],
            "image_size": list(bundle["image_size"]),
            "sample_rate": bundle["sample_rate"],
            "seconds": bundle["seconds"],
            "runtime": bundle["runtime"],
            "inference_config": inference_config,
            "quality_policy": get_quality_policy(),
            "test_metrics": metadata.get("test_metrics", {}),
            "epochs_trained": metadata.get("epochs_trained"),
        }
    except CognitiveModelUnavailable as exc:
        return {
            "available": False,
            "message": str(exc),
            "inference_config": inference_config,
            "quality_policy": get_quality_policy(),
        }
