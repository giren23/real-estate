from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sqlite3
from pathlib import Path

from backup_real_estate_db import database_facts


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore a backup to a new candidate file; never overwrite the live database.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if not args.confirm:
        raise SystemExit("복구 후보 파일 생성을 위해 --confirm을 지정하세요. 운영 DB는 자동 교체되지 않습니다.")
    if args.output.exists():
        raise SystemExit(f"출력 파일이 이미 존재하므로 덮어쓰지 않음: {args.output}")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    compressed = args.manifest.parent / manifest["backup"]
    if hash_file(compressed) != manifest["sha256"]:
        raise SystemExit("백업 SHA-256이 일치하지 않아 복구를 중단함")
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with gzip.open(compressed, "rb") as source, temporary.open("wb") as target:
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
        facts = database_facts(temporary)
        expected = {key: int(manifest[key]) for key in ("transactions", "monthly_history", "completed_district_years")}
        if facts != expected:
            raise RuntimeError(f"복구 검증 행 수 불일치: expected={expected}, actual={facts}")
        os.replace(temporary, args.output)
        print(json.dumps({"status": "verified-candidate", "output": str(args.output), **facts}, ensure_ascii=False))
    finally:
        temporary.unlink(missing_ok=True)
        Path(str(temporary) + "-wal").unlink(missing_ok=True)
        Path(str(temporary) + "-shm").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
