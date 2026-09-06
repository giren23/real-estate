from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "local" / "real_estate.sqlite3"
BACKUP_DIR = ROOT / "backups" / "real-estate"


def database_facts(path: Path) -> dict:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=120)) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite 무결성 검사 실패: {integrity}")
        return {
            "transactions": int(db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]),
            "monthly_history": int(db.execute("SELECT COUNT(*) FROM monthly_history").fetchone()[0]),
            "completed_district_years": int(db.execute("SELECT COUNT(*) FROM collection_status WHERE status='ok'").fetchone()[0]),
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(root: Path = ROOT, label: str = "daily") -> dict:
    source = root / "data" / "local" / "real_estate.sqlite3"
    backup_dir = root / "backups" / "real-estate"
    backup_dir.mkdir(parents=True, exist_ok=True)
    before = database_facts(source)
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S%z")
    stem = f"real-estate-{timestamp}-{label}"
    sqlite_temp = backup_dir / f".{stem}.sqlite3.tmp"
    gzip_temp = backup_dir / f".{stem}.sqlite3.gz.tmp"
    destination = backup_dir / f"{stem}.sqlite3.gz"
    manifest_path = backup_dir / f"{stem}.json"

    if sqlite_temp.exists() or gzip_temp.exists():
        raise RuntimeError("이전 임시 백업 파일이 남아 있어 새 백업을 중단함")
    try:
        with closing(sqlite3.connect(source, timeout=120)) as source_db, closing(sqlite3.connect(sqlite_temp)) as backup_db:
            source_db.backup(backup_db, pages=8192, sleep=0.05)
        after = database_facts(sqlite_temp)
        if after != before:
            raise RuntimeError(f"백업 전후 행 수가 다름: source={before}, backup={after}")
        with sqlite_temp.open("rb") as source_file, gzip.open(gzip_temp, "wb", compresslevel=6) as compressed:
            while chunk := source_file.read(1024 * 1024):
                compressed.write(chunk)
        os.replace(gzip_temp, destination)
        payload = {
            "status": "verified",
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "label": label,
            "source": str(source),
            "backup": destination.name,
            "compressed_bytes": destination.stat().st_size,
            "sha256": sha256_file(destination),
            **after,
        }
        manifest_temp = manifest_path.with_suffix(".json.tmp")
        manifest_temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(manifest_temp, manifest_path)
        latest_temp = backup_dir / "latest.json.tmp"
        latest_temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(latest_temp, backup_dir / "latest.json")
        return payload
    finally:
        sqlite_temp.unlink(missing_ok=True)
        Path(str(sqlite_temp) + "-wal").unlink(missing_ok=True)
        Path(str(sqlite_temp) + "-shm").unlink(missing_ok=True)
        gzip_temp.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a verified, consistent SQLite backup without replacing older backups.")
    parser.add_argument("--label", default="manual")
    args = parser.parse_args()
    payload = create_backup(label=args.label)
    print(json.dumps(payload, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
