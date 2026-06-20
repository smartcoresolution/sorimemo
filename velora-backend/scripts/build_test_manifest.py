#!/usr/bin/env python3
"""Build a SoriMemo inference test manifest from paired wav/json files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def _load_label(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def build_manifest(test_data_dir: Path) -> dict[str, Any]:
    source_dir = test_data_dir / "source_wav"
    label_dir = test_data_dir / "label_wav"

    if not source_dir.is_dir():
        raise SystemExit(f"source_wav 디렉터리를 찾을 수 없습니다: {source_dir}")
    if not label_dir.is_dir():
        raise SystemExit(f"label_wav 디렉터리를 찾을 수 없습니다: {label_dir}")

    wav_files = sorted(source_dir.glob("*.wav"))
    cases: list[dict[str, Any]] = []
    missing_labels: list[str] = []

    for wav_path in wav_files:
        label_path = label_dir / f"{wav_path.stem}.json"
        if not label_path.exists():
            missing_labels.append(wav_path.name)
            continue

        label = _load_label(label_path)
        speech_info = label.get("발화정보", {})
        conversation_info = label.get("대화정보", {})
        recorder_info = label.get("녹음자정보", {})

        cases.append(
            {
                "case_id": wav_path.stem,
                "audio_path": _relative(wav_path),
                "label_path": _relative(label_path),
                "transcript_text": speech_info.get("stt", ""),
                "recording_seconds": _to_float(speech_info.get("recrdTime")),
                "script_id": speech_info.get("scriptId"),
                "script_set_no": speech_info.get("scriptSetNo"),
                "recording_quality": speech_info.get("recrdQuality"),
                "recorded_at": speech_info.get("recrdDt"),
                "speaker": {
                    "gender": recorder_info.get("gender"),
                    "age": recorder_info.get("age"),
                    "recorder_id": recorder_info.get("recorderId"),
                },
                "conversation": {
                    "environment": conversation_info.get("recrdEnvrn"),
                    "city": conversation_info.get("cityCode"),
                    "theme": _clean_text(conversation_info.get("convrsThema")),
                    "collection_unit": conversation_info.get("colctUnitCode"),
                    "recording_unit": conversation_info.get("recrdUnit"),
                },
            }
        )

    label_stems = {path.stem for path in label_dir.glob("*.json")}
    wav_stems = {path.stem for path in wav_files}
    missing_audio = sorted(f"{stem}.json" for stem in label_stems - wav_stems)

    return {
        "schema_version": "1.0",
        "dataset_name": "sorimemo-local-inference-validation",
        "description": (
            "Paired local wav/transcript cases for validating the SoriMemo upload "
            "and inference pipeline. These labels provide transcripts and recording "
            "metadata, not Normal/MCI/AD ground truth."
        ),
        "test_data_dir": _relative(test_data_dir),
        "source_dir": _relative(source_dir),
        "label_dir": _relative(label_dir),
        "case_count": len(cases),
        "missing_label_count": len(missing_labels),
        "missing_audio_count": len(missing_audio),
        "missing_labels": missing_labels,
        "missing_audio": missing_audio,
        "cases": cases,
    }


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip()


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--test-data-dir",
        type=Path,
        default=REPO_ROOT / "test_data",
        help="Directory containing source_wav/ and label_wav/.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "test_data" / "manifest.json",
        help="Manifest JSON output path.",
    )
    args = parser.parse_args()

    manifest = build_manifest(args.test_data_dir.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as file:
        json.dump(manifest, file, ensure_ascii=False, indent=2)
        file.write("\n")

    print(
        f"wrote {args.output} "
        f"cases={manifest['case_count']} "
        f"missing_labels={manifest['missing_label_count']} "
        f"missing_audio={manifest['missing_audio_count']}"
    )


if __name__ == "__main__":
    main()
