from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "local" / "real_estate.sqlite3"
CATALOG_PATH = ROOT / "data" / "local" / "catalog.json"


def main() -> int:
    catalog_payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    catalog = catalog_payload.get("catalog", [])
    by_region: dict[str, list[dict]] = {}
    for group in catalog:
        code = str(group.get("lawd_cd", ""))[:5]
        by_region.setdefault(code, []).append(group)

    with sqlite3.connect(DB_PATH) as db:
        rows = db.execute(
            """
            SELECT lawd_cd
              FROM collection_status
             WHERE year = (SELECT MAX(year) FROM collection_status)
               AND status = 'ok'
             ORDER BY lawd_cd
            """
        ).fetchall()

    completed = [str(row[0]) for row in rows]
    failures: list[dict] = []
    province_counts: Counter[str] = Counter()
    representative_counts: list[int] = []

    for code in completed:
        groups = by_region.get(code, [])
        if not groups:
            failures.append({"lawd_cd": code, "reason": "catalog groups missing"})
            continue
        usable = [
            group
            for group in groups
            if str(group.get("apt_name", "")).strip()
            and str(group.get("dong", "")).strip()
            and str(group.get("region_name", "")).strip()
        ]
        if not usable:
            failures.append({"lawd_cd": code, "reason": "no usable map candidates"})
            continue
        named = [group for group in usable if str(group.get("directory_name", "")).strip()]
        if not named:
            failures.append({"lawd_cd": code, "reason": "no directory-backed map candidate"})
            continue
        province = str(usable[0].get("region_name", "")).split()[0]
        province_counts[province] += 1
        representative_counts.append(min(10, len(named)))

    report = {
        "completed_regions": len(completed),
        "validated_regions": len(completed) - len(failures),
        "province_counts": dict(sorted(province_counts.items())),
        "representative_candidates": sum(representative_counts),
        "failures": failures,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
