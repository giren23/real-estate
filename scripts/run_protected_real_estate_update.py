from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from backup_real_estate_db import create_backup


ROOT = Path(__file__).resolve().parents[1]


def run(script: str, *arguments: str) -> None:
    process = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *arguments], cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")}, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if process.returncode:
        raise RuntimeError(f"{script} 실패(exit {process.returncode})")


def collection_is_publishable() -> bool:
    path = ROOT / "data" / "local" / "collection_state.json"
    if not path.exists():
        return False
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("state") == "completed":
        return True
    if state.get("state") == "quota":
        latest = state.get("latest") or {}
        return state.get("phase") == "history" or int(latest.get("completed_jobs") or 0) > 0
    return False


def main() -> None:
    create_backup(ROOT, "pre-collection")
    run("daily_local_update.py")
    if not collection_is_publishable():
        raise SystemExit("수집 상태가 완료 또는 정상 한도 소진이 아니므로 새 스냅샷을 게시하지 않음")
    create_backup(ROOT, "post-collection")
    run("publish_local_snapshot.py", "--push")
    if (ROOT / "data" / "local" / "r2-enabled.flag").exists():
        run("export_real_estate_archive.py")
        run("upload_real_estate_archive.py")


if __name__ == "__main__":
    main()
