#!/usr/bin/env python3
"""Run SoriMemo API inference validation cases from test_data/manifest.json."""

from __future__ import annotations

import argparse
import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]


def _request_json(
    method: str,
    url: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 600,
) -> dict[str, Any]:
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code} {detail}") from exc


def _create_consent(base_url: str) -> str:
    payload = {
        "user_name": "SoriMemo 테스트",
        "age_group": "other",
        "data_collection_agreed": True,
        "privacy_policy_agreed": True,
        "non_medical_disclaimer_agreed": True,
        "third_party_voice_agreed": True,
    }
    response = _request_json(
        "POST",
        f"{base_url}/api/consent/agree",
        json.dumps(payload).encode("utf-8"),
        {"Content-Type": "application/json"},
    )
    return str(response["consent_token"])


def _multipart_file(field_name: str, file_path: Path) -> tuple[bytes, str]:
    boundary = f"----sorimemo-{uuid.uuid4().hex}"
    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    file_bytes = file_path.read_bytes()
    parts = [
        f"--{boundary}\r\n".encode("utf-8"),
        (
            f'Content-Disposition: form-data; name="{field_name}"; '
            f'filename="{file_path.name}"\r\n'
        ).encode("utf-8"),
        f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"),
        file_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    return b"".join(parts), boundary


def _upload_audio(base_url: str, consent_token: str, audio_path: Path) -> dict[str, Any]:
    body, boundary = _multipart_file("file", audio_path)
    return _request_json(
        "POST",
        f"{base_url}/api/upload/audio",
        body,
        {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-Consent-Token": consent_token,
        },
    )


def _start_analysis(base_url: str, file_id: str, transcript_text: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({"transcript_text": transcript_text})
    return _request_json("POST", f"{base_url}/api/analysis/start/{file_id}?{query}")


def _load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def run(args: argparse.Namespace) -> dict[str, Any]:
    manifest = _load_manifest(args.manifest)
    base_url = args.base_url.rstrip("/")
    consent_token = args.consent_token or _create_consent(base_url)
    cases = manifest["cases"][: args.limit] if args.limit else manifest["cases"]
    results: list[dict[str, Any]] = []

    for index, case in enumerate(cases, start=1):
        started_at = time.time()
        audio_path = _resolve_repo_path(case["audio_path"])
        row: dict[str, Any] = {
            "case_id": case["case_id"],
            "audio_path": case["audio_path"],
            "transcript_text": case.get("transcript_text", ""),
            "ok": False,
        }

        try:
            upload = _upload_audio(base_url, consent_token, audio_path)
            row["file_id"] = upload["file_id"]
            row["quality_pass"] = upload["quality_report"]["quality_pass"]
            row["quality_report"] = upload["quality_report"]

            if not row["quality_pass"]:
                row["error"] = upload.get("message", "quality check failed")
            else:
                analysis = _start_analysis(
                    base_url,
                    upload["file_id"],
                    case.get("transcript_text", ""),
                )
                row["ok"] = True
                row["analysis_id"] = analysis["analysis_id"]
                row["cognitive_status"] = analysis["cognitive_status"]
                row["risk_level"] = analysis["risk_level"]
                row["risk_score"] = analysis["risk_score"]
                row["confidence_score"] = analysis["confidence_score"]
                row["model_probabilities"] = analysis["model_probabilities"]
        except Exception as exc:
            row["error"] = str(exc)

        row["elapsed_seconds"] = round(time.time() - started_at, 2)
        results.append(row)
        status = "OK" if row["ok"] else "FAIL"
        print(f"[{index}/{len(cases)}] {status} {case['case_id']} {row.get('error', '')}".rstrip())

        if args.stop_on_failure and not row["ok"]:
            break

    summary = {
        "manifest": str(args.manifest),
        "base_url": base_url,
        "case_count": len(results),
        "success_count": sum(1 for row in results if row["ok"]),
        "failure_count": sum(1 for row in results if not row["ok"]),
        "results": results,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)
        file.write("\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "test_data" / "manifest.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "test_data" / "inference_validation_results.json",
    )
    parser.add_argument("--consent-token", help="Reuse an existing consent token.")
    parser.add_argument("--limit", type=int, default=5, help="Number of cases to run. Use 0 for all.")
    parser.add_argument("--stop-on-failure", action="store_true")
    args = parser.parse_args()

    summary = run(args)
    print(
        f"wrote {args.output} "
        f"success={summary['success_count']} "
        f"failure={summary['failure_count']}"
    )


if __name__ == "__main__":
    main()
