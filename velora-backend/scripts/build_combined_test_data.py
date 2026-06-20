#!/usr/bin/env python3
"""Combine short SoriMemo test wav files into 30+ second validation cases."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import soundfile as sf


REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET_SR = 16000


def _repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def _speaker_key(case: dict[str, Any]) -> tuple[Any, ...]:
    speaker = case.get("speaker") or {}
    conversation = case.get("conversation") or {}
    return (
        speaker.get("recorder_id"),
        speaker.get("gender"),
        speaker.get("age"),
        conversation.get("city"),
        conversation.get("environment"),
    )


def _flush_group(
    group: list[dict[str, Any]],
    group_index: int,
    output_source_dir: Path,
    output_label_dir: Path,
    silence_seconds: float,
) -> dict[str, Any]:
    audio_parts: list[np.ndarray] = []
    actual_seconds = 0.0
    silence = np.zeros(int(TARGET_SR * silence_seconds), dtype=np.float32)

    for index, case in enumerate(group):
        y, _ = librosa.load(_repo_path(case["audio_path"]), sr=TARGET_SR, mono=True)
        audio_parts.append(y.astype(np.float32))
        actual_seconds += len(y) / TARGET_SR
        if index < len(group) - 1 and len(silence):
            audio_parts.append(silence)

    combined = np.concatenate(audio_parts) if audio_parts else np.array([], dtype=np.float32)
    combined_seconds = len(combined) / TARGET_SR
    case_id = f"combined_30s_{group_index:04d}"
    audio_path = output_source_dir / f"{case_id}.wav"
    label_path = output_label_dir / f"{case_id}.json"
    transcript = " ".join((case.get("transcript_text") or "").strip() for case in group).strip()

    sf.write(audio_path, combined, TARGET_SR, subtype="PCM_16")

    first = group[0]
    label = {
        "case_id": case_id,
        "source_case_count": len(group),
        "source_case_ids": [case["case_id"] for case in group],
        "source_audio_paths": [case["audio_path"] for case in group],
        "transcript_text": transcript,
        "combined_seconds": round(combined_seconds, 2),
        "source_recording_seconds_sum": round(actual_seconds, 2),
        "inserted_silence_seconds": round(max(0, len(group) - 1) * silence_seconds, 2),
        "speaker": first.get("speaker"),
        "conversation": first.get("conversation"),
    }
    with label_path.open("w", encoding="utf-8") as file:
        json.dump(label, file, ensure_ascii=False, indent=2)
        file.write("\n")

    return {
        "case_id": case_id,
        "audio_path": _relative(audio_path),
        "label_path": _relative(label_path),
        "transcript_text": transcript,
        "recording_seconds": round(combined_seconds, 2),
        "source_case_count": len(group),
        "source_case_ids": [case["case_id"] for case in group],
        "source_recording_seconds_sum": round(actual_seconds, 2),
        "inserted_silence_seconds": round(max(0, len(group) - 1) * silence_seconds, 2),
        "speaker": first.get("speaker"),
        "conversation": first.get("conversation"),
    }


def build_combined_manifest(
    manifest_path: Path,
    output_dir: Path,
    target_seconds: float,
    silence_seconds: float,
    max_cases: int | None,
) -> dict[str, Any]:
    with manifest_path.open("r", encoding="utf-8") as file:
        manifest = json.load(file)

    output_source_dir = output_dir / "source_wav"
    output_label_dir = output_dir / "label_wav"
    output_source_dir.mkdir(parents=True, exist_ok=True)
    output_label_dir.mkdir(parents=True, exist_ok=True)

    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for case in manifest["cases"]:
        grouped[_speaker_key(case)].append(case)

    combined_cases: list[dict[str, Any]] = []
    group_index = 1
    for cases in grouped.values():
        pending: list[dict[str, Any]] = []
        pending_seconds = 0.0
        for case in cases:
            pending.append(case)
            pending_seconds += float(case.get("recording_seconds") or 0.0)
            pending_with_silence = pending_seconds + max(0, len(pending) - 1) * silence_seconds
            if pending_with_silence >= target_seconds:
                combined_cases.append(
                    _flush_group(pending, group_index, output_source_dir, output_label_dir, silence_seconds)
                )
                group_index += 1
                pending = []
                pending_seconds = 0.0
                if max_cases and len(combined_cases) >= max_cases:
                    break
        if max_cases and len(combined_cases) >= max_cases:
            break

    combined_manifest = {
        "schema_version": "1.0",
        "dataset_name": "sorimemo-combined-30s-inference-validation",
        "description": (
            "Generated 30+ second validation wav files made by concatenating short "
            "same-speaker local test wav files and joining their transcripts."
        ),
        "target_seconds": target_seconds,
        "silence_seconds_between_clips": silence_seconds,
        "source_manifest": _relative(manifest_path),
        "test_data_dir": _relative(output_dir),
        "source_dir": _relative(output_source_dir),
        "label_dir": _relative(output_label_dir),
        "case_count": len(combined_cases),
        "cases": combined_cases,
    }

    with (output_dir / "manifest.json").open("w", encoding="utf-8") as file:
        json.dump(combined_manifest, file, ensure_ascii=False, indent=2)
        file.write("\n")
    return combined_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=REPO_ROOT / "test_data" / "manifest.json")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "test_data" / "combined_30s")
    parser.add_argument("--target-seconds", type=float, default=30.0)
    parser.add_argument("--silence-seconds", type=float, default=0.25)
    parser.add_argument("--max-cases", type=int, help="Limit generated combined cases.")
    args = parser.parse_args()

    combined = build_combined_manifest(
        args.manifest.resolve(),
        args.output_dir.resolve(),
        args.target_seconds,
        args.silence_seconds,
        args.max_cases,
    )
    print(f"wrote {args.output_dir / 'manifest.json'} cases={combined['case_count']}")


if __name__ == "__main__":
    main()
