#!/usr/bin/env python3
"""Run local SoriMemo quality and scoring validation without starting the API."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

REPO_ROOT = Path(__file__).resolve().parents[2]

import sys

sys.path.insert(0, str(REPO_ROOT / "velora-backend"))

from app.services.audio_processor import TARGET_SR, get_quality_policy, quality_check
from app.services.cognitive_model import get_model_status
from app.services.language_processor import extract_linguistic_features
from app.services.risk_model import compute_confidence_score


DEFAULT_TRANSCRIPT = (
    "오늘은 가족과 통화하면서 저녁 약속과 병원 예약 시간을 다시 확인했습니다. "
    "조금 깜빡한 부분은 메모를 보고 차분히 확인했고, 특별히 이상한 건 없었습니다."
)


def _synthetic_voice(seconds: float, sample_rate: int) -> np.ndarray:
    time_axis = np.linspace(0, seconds, int(seconds * sample_rate), endpoint=False)
    carrier = 0.22 * np.sin(2 * np.pi * 180 * time_axis)
    harmonic = 0.07 * np.sin(2 * np.pi * 360 * time_axis)
    envelope = 0.65 + 0.35 * np.sin(2 * np.pi * 3 * time_axis)
    noise = np.random.default_rng(42).normal(0, 0.003, size=time_axis.shape)
    return ((carrier + harmonic) * envelope + noise).astype(np.float32)


def run(args: argparse.Namespace) -> dict[str, Any]:
    policy = get_quality_policy()
    duration = args.duration or max(float(policy["min_duration_seconds"]) + 1.0, 3.0)

    with tempfile.TemporaryDirectory(prefix="sorimemo-quality-") as temp_dir:
        wav_path = Path(temp_dir) / "synthetic_voice.wav"
        sf.write(wav_path, _synthetic_voice(duration, TARGET_SR), TARGET_SR, subtype="PCM_16")

        quality_report = quality_check(str(wav_path))

    language_features = extract_linguistic_features(args.transcript)
    confidence = compute_confidence_score(
        snr_db=float(quality_report["snr_db"]),
        silence_ratio=float(quality_report["silence_ratio"]),
        diarization_confidence=args.diarization_confidence,
        model_entropy=args.model_entropy,
        feature_quality=args.feature_quality,
    )
    model_status = get_model_status()

    validation = {
        "ok": bool(quality_report["quality_pass"] and confidence["overall"] >= args.min_confidence),
        "quality_report": quality_report,
        "confidence_score": confidence,
        "language_features": {
            "transcript_available": language_features["transcript_available"],
            "token_count": language_features["token_count"],
            "language_quality_score": language_features["language_quality_score"],
            "semantic_impairment_score": language_features["semantic_impairment_score"],
        },
        "model_status": {
            "available": model_status["available"],
            "model_source": model_status.get("model_source"),
            "message": model_status.get("message"),
            "inference_config": model_status.get("inference_config"),
            "quality_policy": model_status.get("quality_policy"),
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as file:
        json.dump(validation, file, ensure_ascii=False, indent=2)
        file.write("\n")
    return validation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "test_data" / "quality_validation_results.json",
    )
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--transcript", default=DEFAULT_TRANSCRIPT)
    parser.add_argument("--diarization-confidence", type=float, default=0.92)
    parser.add_argument("--model-entropy", type=float, default=0.18)
    parser.add_argument("--feature-quality", type=float, default=0.88)
    parser.add_argument("--min-confidence", type=float, default=0.70)
    args = parser.parse_args()

    validation = run(args)
    status = "OK" if validation["ok"] else "FAIL"
    print(f"{status} wrote {args.output}")
    print(
        "quality_pass={quality_pass} confidence={confidence}".format(
            quality_pass=validation["quality_report"]["quality_pass"],
            confidence=validation["confidence_score"]["overall"],
        )
    )


if __name__ == "__main__":
    main()
