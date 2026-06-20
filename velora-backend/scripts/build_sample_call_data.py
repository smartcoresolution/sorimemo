#!/usr/bin/env python3
"""Build synthetic parent-child call samples from local SoriMemo utterance data."""

from __future__ import annotations

import argparse
import json
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


def _load_audio(path: Path) -> np.ndarray:
    y, _ = librosa.load(path, sr=TARGET_SR, mono=True)
    return y.astype(np.float32)


def _child_variant(y: np.ndarray) -> np.ndarray:
    shifted = librosa.effects.pitch_shift(y, sr=TARGET_SR, n_steps=3.5)
    stretched = librosa.effects.time_stretch(shifted, rate=1.08)
    return (stretched * 0.82).astype(np.float32)


def _append_segment(
    audio_parts: list[np.ndarray],
    segments: list[dict[str, Any]],
    speaker: str,
    y: np.ndarray,
    transcript: str,
    source_case_id: str,
    cursor: float,
) -> float:
    audio_parts.append(y)
    duration = len(y) / TARGET_SR
    segments.append(
        {
            "speaker": speaker,
            "start_time": round(cursor, 2),
            "end_time": round(cursor + duration, 2),
            "duration": round(duration, 2),
            "transcript": transcript,
            "source_case_id": source_case_id,
        }
    )
    return cursor + duration


def build_sample_call(
    manifest_path: Path,
    output_dir: Path,
    target_seconds: float,
    parent_min_seconds: float,
    silence_seconds: float,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = manifest["cases"]

    output_source_dir = output_dir / "source_wav"
    output_label_dir = output_dir / "label_wav"
    output_source_dir.mkdir(parents=True, exist_ok=True)
    output_label_dir.mkdir(parents=True, exist_ok=True)

    audio_parts: list[np.ndarray] = []
    segments: list[dict[str, Any]] = []
    silence = np.zeros(int(TARGET_SR * silence_seconds), dtype=np.float32)
    cursor = 0.0
    parent_seconds = 0.0
    child_seconds = 0.0
    parent_texts: list[str] = []
    full_dialogue: list[str] = []

    parent_index = 0
    child_index = 80 if len(cases) > 90 else max(0, len(cases) // 2)

    while cursor < target_seconds or parent_seconds < parent_min_seconds:
        parent_case = cases[parent_index % len(cases)]
        parent_audio = _load_audio(_repo_path(parent_case["audio_path"]))
        parent_text = (parent_case.get("transcript_text") or "").strip()
        cursor = _append_segment(
            audio_parts,
            segments,
            "parent",
            parent_audio,
            parent_text,
            parent_case["case_id"],
            cursor,
        )
        parent_seconds += len(parent_audio) / TARGET_SR
        parent_texts.append(parent_text)
        full_dialogue.append(f"부모: {parent_text}")
        parent_index += 1

        audio_parts.append(silence)
        cursor += silence_seconds

        if cursor >= target_seconds and parent_seconds >= parent_min_seconds:
            break

        child_case = cases[child_index % len(cases)]
        child_audio = _child_variant(_load_audio(_repo_path(child_case["audio_path"])))
        child_text = (child_case.get("transcript_text") or "").strip()
        cursor = _append_segment(
            audio_parts,
            segments,
            "child_synthetic",
            child_audio,
            child_text,
            child_case["case_id"],
            cursor,
        )
        child_seconds += len(child_audio) / TARGET_SR
        full_dialogue.append(f"자녀(합성): {child_text}")
        child_index += 1

        audio_parts.append(silence)
        cursor += silence_seconds

    combined = np.concatenate(audio_parts).astype(np.float32)
    case_id = "sample_parent_child_call_0001"
    audio_path = output_source_dir / f"{case_id}.wav"
    label_path = output_label_dir / f"{case_id}.json"
    sf.write(audio_path, combined, TARGET_SR, subtype="PCM_16")

    label = {
        "case_id": case_id,
        "sample_type": "synthetic_parent_child_call",
        "audio_path": _relative(audio_path),
        "duration_seconds": round(len(combined) / TARGET_SR, 2),
        "parent_speech_seconds": round(parent_seconds, 2),
        "child_speech_seconds": round(child_seconds, 2),
        "target_speaker": "parent",
        "target_transcript_text": " ".join(parent_texts).strip(),
        "full_dialogue_text": "\n".join(full_dialogue),
        "segments": segments,
        "notes": [
            "This is not a real family call.",
            "Parent segments use local utterance wav files.",
            "Child segments are synthetic pitch/speed variants of other local utterances.",
            "Use this sample for pipeline testing, not clinical validation or model training.",
        ],
    }
    label_path.write_text(json.dumps(label, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest_out = {
        "schema_version": "1.0",
        "dataset_name": "sorimemo-sample-parent-child-call",
        "description": "Synthetic 1-minute parent-child call sample for SoriMemo service flow testing.",
        "case_count": 1,
        "cases": [
            {
                "case_id": case_id,
                "audio_path": _relative(audio_path),
                "label_path": _relative(label_path),
                "transcript_text": label["target_transcript_text"],
                "full_dialogue_text": label["full_dialogue_text"],
                "recording_seconds": label["duration_seconds"],
                "parent_speech_seconds": label["parent_speech_seconds"],
                "child_speech_seconds": label["child_speech_seconds"],
                "target_speaker": "parent",
            }
        ],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest_out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=REPO_ROOT / "test_data" / "manifest.json")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "test_data" / "sample_calls")
    parser.add_argument("--target-seconds", type=float, default=60.0)
    parser.add_argument("--parent-min-seconds", type=float, default=30.0)
    parser.add_argument("--silence-seconds", type=float, default=0.35)
    args = parser.parse_args()

    manifest = build_sample_call(
        args.manifest.resolve(),
        args.output_dir.resolve(),
        args.target_seconds,
        args.parent_min_seconds,
        args.silence_seconds,
    )
    case = manifest["cases"][0]
    print(
        f"wrote {args.output_dir / 'manifest.json'} "
        f"duration={case['recording_seconds']} "
        f"parent_speech={case['parent_speech_seconds']} "
        f"child_speech={case['child_speech_seconds']}"
    )


if __name__ == "__main__":
    main()
