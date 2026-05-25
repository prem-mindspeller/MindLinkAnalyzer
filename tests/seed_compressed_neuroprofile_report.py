"""
Seed a neuroprofile JSON report to the staging API using the compressed
report contract.

Default target:
  https://stg-en.mindspell.be/api/cas/eeg-reports/seed

Default source report:
  M:\\CODEBASE\\MindLinkAnalyzer\\reports\\neuroprofile_session1_opposite_20260519_103852.json

Usage:
  python tests/seed_compressed_neuroprofile_report.py
  python tests/seed_compressed_neuroprofile_report.py --email user@example.com --partner-id PARTNER_000001 --protocol-type initial --jwt-token <token>
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import ssl
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request


DEFAULT_REPORT = Path(
    r"M:\CODEBASE\MindLinkAnalyzer\reports\neuroprofile_session1_opposite_20260519_103852.json"
)
DEFAULT_API_BASE = "https://stg-en.mindspell.be/api/cas"
DEFAULT_ENDPOINT = f"{DEFAULT_API_BASE}/eeg-reports/seed"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a compressed neuroprofile JSON report to the staging seeding endpoint."
    )
    parser.add_argument("--report-file", default=str(DEFAULT_REPORT))
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--email")
    parser.add_argument("--partner-id")
    parser.add_argument("--protocol-type", default="initial")
    parser.add_argument("--jwt-token")
    parser.add_argument("--session-id")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--insecure", action="store_true", help="Disable TLS verification for debugging.")
    return parser.parse_args()


def prompt_if_missing(value: str | None, prompt: str) -> str:
    if value:
        return value
    return input(prompt).strip()


def load_report_text(report_file: Path) -> str:
    return report_file.read_text(encoding="utf-8")


def compress_report_text(report_text: str) -> dict:
    report_bytes = report_text.encode("utf-8")
    compressed_bytes = gzip.compress(report_bytes)
    round_trip = gzip.decompress(compressed_bytes)
    report_sha = hashlib.sha256(report_bytes).hexdigest()
    round_trip_sha = hashlib.sha256(round_trip).hexdigest()

    if round_trip != report_bytes:
        raise ValueError("Local gzip round-trip mismatch.")
    if round_trip_sha != report_sha:
        raise ValueError("SHA-256 mismatch after local gzip round-trip.")

    report_blob = base64.b64encode(compressed_bytes).decode("ascii")
    return {
        "report_blob": report_blob,
        "original_size_bytes": len(report_bytes),
        "compressed_size_bytes": len(compressed_bytes),
        "report_sha256": report_sha,
        "gzip_prefix_hex": compressed_bytes[:4].hex(),
    }


def build_payload(
    report_text: str,
    email: str,
    partner_id: str,
    protocol_type: str,
    session_id: str,
) -> dict:
    packed = compress_report_text(report_text)
    generated_at = datetime.now(timezone.utc).isoformat()

    payload = {
        "email": email,
        "report_text": packed["report_blob"],
        "is_base64": True,
        "is_compressed": True,
        "compression": "gzip",
        "storage_format": "gzip+base64+utf8",
        "content_type": "application/json",
        "encoding": "utf-8",
        "original_size_bytes": packed["original_size_bytes"],
        "compressed_size_bytes": packed["compressed_size_bytes"],
        "report_sha256": packed["report_sha256"],
        "protocol_type": protocol_type,
        "partner_id": partner_id,
        "session_id": session_id,
        "generation_meta": {
            "generated_at": generated_at,
            "analyzer_version": "1.0",
            "workflow": "compressed_neuroprofile_test_script",
            "task_count": 4,
            "report_contract": "neuroprofile_feature_export",
            "report_storage": {
                "storage_format": "gzip+base64+utf8",
                "compression": "gzip",
                "original_size_bytes": packed["original_size_bytes"],
                "compressed_size_bytes": packed["compressed_size_bytes"],
                "sha256": packed["report_sha256"],
                "gzip_prefix_hex": packed["gzip_prefix_hex"],
            },
        },
    }
    return payload


def send_payload(endpoint: str, jwt_token: str, payload: dict, timeout: int, insecure: bool):
    headers = {
        "X-Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(endpoint, data=data, headers=headers, method="POST")
    context = None
    if insecure:
        context = ssl._create_unverified_context()
    return request.urlopen(req, timeout=timeout, context=context)


def main() -> int:
    args = parse_args()

    report_file = Path(args.report_file)
    if not report_file.exists():
        print(f"Report file not found: {report_file}")
        return 1

    email = prompt_if_missing(args.email, "Enter user email: ")
    partner_id = prompt_if_missing(args.partner_id, "Enter partner ID: ")
    jwt_token = prompt_if_missing(args.jwt_token, "Enter JWT token: ")
    protocol_type = (args.protocol_type or "initial").strip() or "initial"
    session_id = args.session_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    report_text = load_report_text(report_file)
    payload = build_payload(
        report_text=report_text,
        email=email,
        partner_id=partner_id,
        protocol_type=protocol_type,
        session_id=session_id,
    )

    print("=" * 72)
    print("COMPRESSED NEUROPROFILE SEED TEST")
    print("=" * 72)
    print(f"Endpoint             : {args.endpoint}")
    print(f"Report file          : {report_file}")
    print(f"Session ID           : {session_id}")
    print(f"Protocol type        : {protocol_type}")
    print(f"Original bytes       : {payload['original_size_bytes']}")
    print(f"Compressed bytes     : {payload['compressed_size_bytes']}")
    print(f"Compression ratio    : {payload['compressed_size_bytes'] / max(payload['original_size_bytes'], 1):.3f}")
    print(f"is_compressed        : {payload['is_compressed']}")
    print(f"storage_format       : {payload['storage_format']}")
    print(f"content_type         : {payload['content_type']}")
    print(f"gzip_prefix_hex      : {payload['generation_meta']['report_storage']['gzip_prefix_hex']}")
    print(f"report_sha256        : {payload['report_sha256']}")
    print(f"Base64 payload chars : {len(payload['report_text'])}")
    print("=" * 72)

    try:
        response = send_payload(
            endpoint=args.endpoint,
            jwt_token=jwt_token,
            payload=payload,
            timeout=args.timeout,
            insecure=args.insecure,
        )
    except error.URLError as exc:
        print(f"Request failed: {exc}")
        return 1

    status_code = getattr(response, "status", None) or response.getcode()
    response_headers = dict(response.headers.items())
    response_text = response.read().decode("utf-8", errors="replace")

    print(f"HTTP status          : {status_code}")
    print("Response headers     :", response_headers)
    print("-" * 72)
    try:
        parsed = json.loads(response_text)
        print(json.dumps(parsed, indent=2))
    except Exception:
        print(response_text)
    print("-" * 72)

    if 200 <= int(status_code) < 300:
        print("Seed request completed.")
        return 0

    print("Seed request failed.")
    return 1


if __name__ == "__main__":
    main()
