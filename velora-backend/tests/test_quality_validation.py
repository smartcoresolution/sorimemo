import numpy as np

from app.services.audio_processor import TARGET_SR, compute_silence_ratio, compute_snr, get_quality_policy
from app.services.language_processor import extract_linguistic_features
from app.services.risk_model import compute_confidence_score


def test_quality_policy_exposes_operational_thresholds():
    policy = get_quality_policy()

    assert policy["target_sample_rate"] == TARGET_SR
    assert policy["min_duration_seconds"] > 0
    assert 0 < policy["max_silence_ratio"] <= 1
    assert policy["min_snr_db"] >= 0


def test_silence_ratio_detects_mostly_silent_audio():
    speech = np.full(TARGET_SR, 0.2, dtype=np.float32)
    silence = np.zeros(TARGET_SR * 4, dtype=np.float32)
    audio = np.concatenate([speech, silence])

    assert compute_silence_ratio(audio, TARGET_SR) > 0.70


def test_snr_improves_for_cleaner_signal():
    rng = np.random.default_rng(7)
    base = np.sin(2 * np.pi * 220 * np.linspace(0, 3, TARGET_SR * 3, endpoint=False))
    noisy = (base * 0.2) + rng.normal(0, 0.08, size=base.shape)
    cleaner = (base * 0.2) + rng.normal(0, 0.005, size=base.shape)

    assert compute_snr(cleaner.astype(np.float32)) >= compute_snr(noisy.astype(np.float32))


def test_confidence_score_penalizes_low_audio_quality():
    high_quality = compute_confidence_score(
        snr_db=24,
        silence_ratio=0.20,
        diarization_confidence=0.95,
        model_entropy=0.10,
        feature_quality=0.90,
    )
    low_quality = compute_confidence_score(
        snr_db=3,
        silence_ratio=0.90,
        diarization_confidence=0.95,
        model_entropy=0.10,
        feature_quality=0.90,
    )

    assert high_quality["overall"] > low_quality["overall"]
    assert high_quality["audio_quality_score"] > low_quality["audio_quality_score"]


def test_linguistic_features_surface_semantic_risk_markers():
    normal = extract_linguistic_features("오늘은 병원 예약을 확인하고 가족과 저녁을 먹을 계획이에요.")
    risky = extract_linguistic_features("오늘이 며칠인지 모르겠고, 너 이름이 생각이 안 나. 자꾸 같은 말을 물어본다.")

    assert risky["semantic_impairment_score"] > normal["semantic_impairment_score"]
    assert risky["transcript_available"] is True
