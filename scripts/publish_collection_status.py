from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_report(path: Path | None) -> dict:
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def public_status(initial: dict, retry: dict) -> dict:
    requests = {
        (str(item.get("lawd_cd", "")), str(item.get("deal_ym", ""))): dict(item)
        for item in initial.get("requests", [])
    }
    recovered = 0
    for item in retry.get("requests", []):
        key = (str(item.get("lawd_cd", "")), str(item.get("deal_ym", "")))
        if item.get("status") == "ok" and requests.get(key, {}).get("status") != "ok":
            recovered += 1
        requests[key] = dict(item)
    unresolved = [item for item in requests.values() if item.get("status") != "ok"]
    months = sorted({str(item.get("deal_ym", "")) for item in requests.values() if item.get("deal_ym")})
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "complete" if requests and not unresolved else "partial",
        "requested_months": months,
        "target_count": len(requests),
        "initial_success_count": int(initial.get("success_count", 0)),
        "retry_count": int(retry.get("request_count", 0)),
        "recovered_count": recovered,
        "unresolved_count": len(unresolved),
        "unresolved": unresolved,
        "region_months": sorted(
            requests.values(),
            key=lambda item: (str(item.get("lawd_cd", "")), str(item.get("deal_ym", ""))),
        ),
    }


def write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--initial", type=Path, required=True)
    parser.add_argument("--retry", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data/public/collection_status.json",
    )
    args = parser.parse_args()
    payload = public_status(load_report(args.initial), load_report(args.retry))
    write_json_atomic(args.output, payload)
    print(
        f"수집 상태 게시: {payload['target_count']:,}개 중 미해결 {payload['unresolved_count']:,}개",
        flush=True,
    )


if __name__ == "__main__":
    main()
