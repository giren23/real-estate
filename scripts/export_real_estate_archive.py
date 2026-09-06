from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from realestate.local_store import LocalStore


ROOT = Path(__file__).resolve().parents[1]
EXPORT_ROOT = ROOT / "data" / "local" / "cloud-archive"


def json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def store_object(object_dir: Path, payload: object) -> dict:
    raw = json_bytes(payload)
    compressed = gzip.compress(raw, compresslevel=6, mtime=0)
    digest = hashlib.sha256(compressed).hexdigest()
    target = object_dir / f"{digest}.json.gz"
    if not target.exists():
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(compressed)
        os.replace(temporary, target)
    return {"key": f"objects/{target.name}", "sha256": digest, "bytes": len(compressed), "rows": len(payload.get("rows", [])) if isinstance(payload, dict) else 0}


def rows(db: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(row) for row in db.execute(sql, params)]


def export_archive(root: Path = ROOT) -> tuple[dict, Path]:
    store = LocalStore(root)
    store.initialize()
    catalog = store.build_catalog()
    export_root = root / "data" / "local" / "cloud-archive"
    object_dir = export_root / "objects"
    manifest_dir = export_root / "manifests"
    object_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    snapshot_id = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    manifest = {
        "version": 1,
        "snapshot_id": snapshot_id,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "meta": catalog["meta"],
        "catalog": store_object(object_dir, catalog),
        "history": {},
        "trades": {},
    }
    with store.connect() as db:
        district_codes = [str(row[0]) for row in db.execute(
            "SELECT lawd_cd FROM complexes UNION SELECT lawd_cd FROM monthly_history UNION SELECT lawd_cd FROM transactions ORDER BY lawd_cd"
        )]
        for index, lawd_cd in enumerate(district_codes, 1):
            history_rows = rows(db, """SELECT lawd_cd,region_name,dong,apt_name,area_m2,month,median_price_eok,trade_count
                FROM monthly_history WHERE lawd_cd=? ORDER BY dong,apt_name,area_m2,month""", (lawd_cd,))
            trade_rows = rows(db, """SELECT lawd_cd,region_name,dong,jibun,apt_name,area_m2,deal_ym,trade_date,apt_dong,
                floor,build_year,price_manwon,price_eok,price_per_m2_manwon,price_per_pyeong_manwon,deal_type,registration_date,source
                FROM transactions WHERE lawd_cd=? ORDER BY dong,apt_name,area_m2,trade_date""", (lawd_cd,))
            manifest["history"][lawd_cd] = store_object(object_dir, {"scope": "district", "lawd_cd": lawd_cd, "rows": history_rows})
            manifest["trades"][lawd_cd] = store_object(object_dir, {"scope": "district", "lawd_cd": lawd_cd, "rows": trade_rows})
            print(f"[{index}/{len(district_codes)}] {lawd_cd}: history {len(history_rows):,}, trades {len(trade_rows):,}", flush=True)
    manifest_path = manifest_dir / f"{snapshot_id}.json"
    temporary = manifest_path.with_suffix(".tmp")
    temporary.write_bytes(json_bytes(manifest))
    os.replace(temporary, manifest_path)
    current_temp = export_root / "current.json.tmp"
    current_temp.write_bytes(json_bytes({"version": 1, "snapshot_id": snapshot_id, "manifest_key": f"manifests/{manifest_path.name}"}))
    os.replace(current_temp, export_root / "current.json")
    return manifest, manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export content-addressed, district-partitioned public files for Cloudflare R2.")
    parser.parse_args()
    manifest, path = export_archive()
    total = sum(item["bytes"] for item in [manifest["catalog"], *manifest["history"].values(), *manifest["trades"].values()])
    print(json.dumps({"status": "exported", "manifest": str(path), "objects": 1 + len(manifest["history"]) + len(manifest["trades"]), "compressed_bytes": total}, ensure_ascii=False))


if __name__ == "__main__":
    main()
