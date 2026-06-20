import numpy as np
from typing import Optional


def compute_risk_score(acoustic_features: dict, speech_statistics: dict) -> dict:
    """
    Compute cognitive risk score based on acoustic and speech features.
    Uses a weighted scoring model based on research-correlated markers:
    - Reduced pitch variability
    - Slower speech rate
    - Higher silence ratio
    - Lower prosody stability
    - Energy pattern changes
    - MFCC distribution anomalies
    """
    risk_indicators = []

    # 1. Pitch variability - reduced variability correlates with cognitive decline
    pitch_std = acoustic_features.get("pitch_std", 0)
    if pitch_std < 15:
        risk_indicators.append(("pitch_variability", 0.8, 0.15))
    elif pitch_std < 30:
        risk_indicators.append(("pitch_variability", 0.5, 0.15))
    elif pitch_std < 60:
        risk_indicators.append(("pitch_variability", 0.3, 0.15))
    else:
        risk_indicators.append(("pitch_variability", 0.1, 0.15))

    # 2. Speech rate - slower speech may indicate cognitive changes
    speech_rate = acoustic_features.get("speech_rate", 120)
    if speech_rate < 80:
        risk_indicators.append(("speech_rate", 0.8, 0.15))
    elif speech_rate < 100:
        risk_indicators.append(("speech_rate", 0.5, 0.15))
    elif speech_rate < 140:
        risk_indicators.append(("speech_rate", 0.2, 0.15))
    else:
        risk_indicators.append(("speech_rate", 0.1, 0.15))

    # 3. Silence ratio - more pauses may indicate cognitive processing delays
    silence_ratio = speech_statistics.get("silence_ratio", 0.5)
    if silence_ratio > 0.7:
        risk_indicators.append(("silence_pattern", 0.8, 0.12))
    elif silence_ratio > 0.5:
        risk_indicators.append(("silence_pattern", 0.5, 0.12))
    elif silence_ratio > 0.3:
        risk_indicators.append(("silence_pattern", 0.2, 0.12))
    else:
        risk_indicators.append(("silence_pattern", 0.1, 0.12))

    # 4. Prosody stability
    prosody = acoustic_features.get("prosody_stability", 0.5)
    if prosody < 0.3:
        risk_indicators.append(("prosody", 0.7, 0.12))
    elif prosody < 0.5:
        risk_indicators.append(("prosody", 0.4, 0.12))
    else:
        risk_indicators.append(("prosody", 0.15, 0.12))

    # 5. Energy variability
    energy_var = acoustic_features.get("energy_variability", 0.5)
    if energy_var > 2.0:
        risk_indicators.append(("energy_pattern", 0.7, 0.10))
    elif energy_var > 1.0:
        risk_indicators.append(("energy_pattern", 0.4, 0.10))
    else:
        risk_indicators.append(("energy_pattern", 0.15, 0.10))

    # 6. Mean utterance length - shorter utterances may indicate word-finding difficulty
    mean_utt = speech_statistics.get("mean_utterance_length", 1.0)
    if mean_utt < 0.5:
        risk_indicators.append(("utterance_length", 0.7, 0.10))
    elif mean_utt < 1.0:
        risk_indicators.append(("utterance_length", 0.4, 0.10))
    else:
        risk_indicators.append(("utterance_length", 0.15, 0.10))

    # 7. Speech density
    density = speech_statistics.get("speech_density", 0.5)
    if density < 0.3:
        risk_indicators.append(("speech_density", 0.7, 0.08))
    elif density < 0.5:
        risk_indicators.append(("speech_density", 0.4, 0.08))
    else:
        risk_indicators.append(("speech_density", 0.15, 0.08))

    # 8. Spectral features - changes in spectral distribution
    spectral_centroid = acoustic_features.get("spectral_centroid_mean", 2000)
    if spectral_centroid < 1000:
        risk_indicators.append(("spectral_pattern", 0.6, 0.08))
    elif spectral_centroid < 2000:
        risk_indicators.append(("spectral_pattern", 0.3, 0.08))
    else:
        risk_indicators.append(("spectral_pattern", 0.1, 0.08))

    # 9. MFCC distribution anomaly
    mfcc_std = acoustic_features.get("mfcc_std", [])
    if len(mfcc_std) > 0:
        avg_mfcc_std = np.mean(mfcc_std)
        if avg_mfcc_std < 5:
            risk_indicators.append(("mfcc_pattern", 0.6, 0.10))
        elif avg_mfcc_std < 10:
            risk_indicators.append(("mfcc_pattern", 0.3, 0.10))
        else:
            risk_indicators.append(("mfcc_pattern", 0.1, 0.10))
    else:
        risk_indicators.append(("mfcc_pattern", 0.5, 0.10))

    # Compute weighted risk score
    weighted_sum = sum(score * weight for _, score, weight in risk_indicators)
    total_weight = sum(weight for _, _, weight in risk_indicators)
    raw_risk = weighted_sum / total_weight if total_weight > 0 else 0.5

    # Scale to 0-100
    risk_score = float(np.clip(raw_risk * 100, 0, 100))

    # Compute probability (sigmoid-like transformation)
    risk_probability = float(1.0 / (1.0 + np.exp(-5 * (raw_risk - 0.5))))

    # Determine risk level
    if risk_score < 35:
        risk_level = "low"
    elif risk_score < 65:
        risk_level = "middle"
    else:
        risk_level = "high"

    # Model entropy (uncertainty)
    indicator_scores = [s for _, s, _ in risk_indicators]
    score_var = np.var(indicator_scores)
    model_entropy = float(np.clip(score_var * 4, 0, 1))

    return {
        "risk_score": round(risk_score, 2),
        "risk_level": risk_level,
        "risk_probability": round(risk_probability, 4),
        "model_entropy": round(model_entropy, 4),
        "indicators": {name: round(score, 4) for name, score, _ in risk_indicators},
    }


def compute_confidence_score(
    snr_db: float,
    silence_ratio: float,
    diarization_confidence: float,
    model_entropy: float,
    feature_quality: float,
) -> dict:
    """Compute overall confidence score from multiple quality indicators."""
    # Audio quality score
    if snr_db >= 20:
        audio_quality = 1.0
    elif snr_db >= 10:
        audio_quality = 0.5 + (snr_db - 10) / 20
    elif snr_db >= 5:
        audio_quality = 0.3 + (snr_db - 5) / 25
    else:
        audio_quality = max(0.1, snr_db / 16.67)

    audio_quality *= (1.0 - max(0, silence_ratio - 0.5))
    audio_quality = float(np.clip(audio_quality, 0, 1))

    # Diarization clarity
    diarization_clarity = float(np.clip(diarization_confidence, 0, 1))

    # Model certainty (inverse of entropy)
    model_certainty = float(np.clip(1.0 - model_entropy, 0, 1))

    # Overall confidence: weighted combination
    overall = (
        audio_quality * 0.35 +
        diarization_clarity * 0.30 +
        model_certainty * 0.25 +
        feature_quality * 0.10
    )
    overall = float(np.clip(overall, 0, 1))

    return {
        "overall": round(overall, 4),
        "audio_quality_score": round(audio_quality, 4),
        "diarization_clarity": round(diarization_clarity, 4),
        "model_certainty": round(model_certainty, 4),
    }


def generate_guidance(risk_level: str, risk_score: float, confidence_score: float) -> dict:
    """Generate non-medical guidance based on risk level."""
    disclaimer = (
        "본 분석 결과는 의료적 진단이나 치료 판단이 아닌, "
        "인지기능 변화와 연관될 수 있는 위험 신호를 참고용으로 제공하는 "
        "비의료적 정보입니다. 정확한 건강 상태 확인은 반드시 전문 의료기관을 방문하시기 바랍니다."
    )

    guidance_items = []
    next_steps = []

    if risk_level == "low":
        risk_explanation = (
            f"분석 결과, 현재 음성 패턴에서 인지기능 변화와 관련된 "
            f"특이 신호가 관찰되지 않았습니다. (위험 점수: {risk_score:.1f}/100)"
        )
        guidance_items = [
            {
                "category": "self_care",
                "title": "건강한 생활 습관 유지",
                "description": "규칙적인 운동, 충분한 수면, 균형 잡힌 식단을 유지하세요.",
                "priority": 1,
            },
            {
                "category": "monitoring",
                "title": "정기적 모니터링",
                "description": "3~6개월 간격으로 정기적으로 분석하여 변화를 추적하세요.",
                "priority": 2,
            },
            {
                "category": "activity",
                "title": "두뇌 활동 유지",
                "description": "독서, 퍼즐, 사회적 교류 등 인지 활동을 꾸준히 하세요.",
                "priority": 3,
            },
        ]
        next_steps = [
            "현재 상태를 유지하며 건강한 생활 습관을 지속하세요.",
            "3~6개월 후 다시 분석하여 변화를 추적하세요.",
            "궁금한 점이 있으면 의료 전문가와 상담하세요.",
        ]

    elif risk_level in {"middle", "caution"}:
        risk_explanation = (
            f"분석 결과, 일부 음성 패턴에서 주의가 필요한 변화가 감지되었습니다. "
            f"(위험 점수: {risk_score:.1f}/100) "
            f"이는 다양한 원인(피로, 스트레스, 환경 등)에 의한 것일 수 있으며, "
            f"반드시 인지기능 저하를 의미하지는 않습니다."
        )
        guidance_items = [
            {
                "category": "monitoring",
                "title": "주기적 모니터링 강화",
                "description": "1~3개월 간격으로 더 자주 분석하여 변화 추이를 확인하세요.",
                "priority": 1,
            },
            {
                "category": "consultation",
                "title": "전문가 상담 고려",
                "description": "걱정되시면 신경과 또는 정신건강의학과 전문의와 상담해 보세요.",
                "priority": 2,
            },
            {
                "category": "self_care",
                "title": "스트레스 관리",
                "description": "충분한 휴식과 스트레스 관리를 통해 전반적인 건강을 관리하세요.",
                "priority": 3,
            },
            {
                "category": "activity",
                "title": "인지 활동 강화",
                "description": "새로운 취미 활동이나 학습 활동을 시작하여 인지 기능을 자극하세요.",
                "priority": 4,
            },
        ]
        next_steps = [
            "결과에 대해 과도하게 걱정하지 마세요. 다양한 원인이 있을 수 있습니다.",
            "1~3개월 후 다시 분석하여 변화 추이를 확인하세요.",
            "필요시 전문 의료기관에서 정밀 검사를 받아보세요.",
            "건강한 생활 습관을 유지하세요.",
        ]

    else:  # high
        risk_explanation = (
            f"분석 결과, 음성 패턴에서 인지기능 변화와 연관될 수 있는 "
            f"신호가 여러 항목에서 감지되었습니다. (위험 점수: {risk_score:.1f}/100) "
            f"그러나 이 결과는 의료적 진단이 아니며, 다양한 요인에 의해 영향받을 수 있습니다."
        )
        guidance_items = [
            {
                "category": "consultation",
                "title": "전문가 상담 권장",
                "description": "가능한 빠른 시일 내에 신경과 또는 정신건강의학과 전문의와 상담하시기를 권장합니다.",
                "priority": 1,
            },
            {
                "category": "screening",
                "title": "정밀 검사 고려",
                "description": "전문 의료기관에서 인지기능 관련 정밀 검사를 받아보시기를 고려하세요.",
                "priority": 2,
            },
            {
                "category": "monitoring",
                "title": "빈번한 모니터링",
                "description": "2~4주 간격으로 재분석하여 변화를 면밀히 추적하세요.",
                "priority": 3,
            },
            {
                "category": "support",
                "title": "가족과 공유",
                "description": "가족이나 가까운 분에게 결과를 공유하고 함께 관리 계획을 세우세요.",
                "priority": 4,
            },
        ]
        next_steps = [
            "이 결과는 의료적 진단이 아닙니다. 과도한 걱정보다는 전문가 상담을 권장합니다.",
            "가능한 빠른 시일 내에 전문 의료기관을 방문하세요.",
            "가족이나 가까운 분과 결과를 공유하세요.",
            "2~4주 후 다시 분석하여 변화를 추적하세요.",
        ]

    if confidence_score < 0.5:
        guidance_items.append({
            "category": "quality",
            "title": "분석 신뢰도 개선",
            "description": (
                f"현재 분석 신뢰도가 {confidence_score*100:.0f}%로 낮습니다. "
                "더 조용한 환경에서 충분한 길이의 통화를 녹음하여 재분석하면 "
                "보다 정확한 결과를 얻을 수 있습니다."
            ),
            "priority": 0,
        })

    guidance_items.sort(key=lambda x: x["priority"])

    return {
        "guidance": guidance_items,
        "risk_explanation": risk_explanation,
        "next_steps": next_steps,
        "legal_notice": disclaimer,
    }
