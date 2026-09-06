from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from realestate.local_store import LocalStore


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_PATH = Path("data/public/local_meta.json")


def build_snapshot(root: Path = ROOT) -> dict:
    store = LocalStore(root)
    store.initialize()
    catalog = store.build_catalog()
    meta = catalog.get("meta", {})
    return {
        "status": "ok",
        "source": "local-main-server",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "trade_count": int(meta.get("represented_trades") or meta.get("transaction_rows") or 0),
        "transaction_rows": int(meta.get("transaction_rows") or 0),
        "represented_trades": int(meta.get("represented_trades") or 0),
        "apartment_count": int(meta.get("complex_count") or 0),
        "directory_count": int(meta.get("directory_count") or 0),
        "districts_complete": int(meta.get("districts_complete") or 0),
        "district_years_complete": int(meta.get("district_years_complete") or 0),
    }


def write_snapshot(payload: dict, root: Path = ROOT) -> Path:
    target = root / PUBLIC_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(target)
    return target


def run_git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=check, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def push_snapshot(payload: dict, root: Path = ROOT) -> bool:
    """Publish one tiny file from an isolated clone, preserving PC-only source files."""
    remote = run_git("remote", "get-url", "origin", cwd=root).stdout.strip()
    for attempt in range(2):
        with tempfile.TemporaryDirectory(prefix="real-estate-public-") as directory:
            worktree = Path(directory)
            run_git("clone", "--depth", "1", "--branch", "main", remote, str(worktree), cwd=root)
            write_snapshot(payload, worktree)
            run_git("config", "user.name", "real-estate-local-bot", cwd=worktree)
            run_git("config", "user.email", "actions@users.noreply.github.com", cwd=worktree)
            run_git("add", PUBLIC_PATH.as_posix(), cwd=worktree)
            changed = run_git("diff", "--cached", "--quiet", cwd=worktree, check=False).returncode != 0
            if not changed:
                return True
            run_git("commit", "-m", "Update local public real-estate snapshot", cwd=worktree)
            pushed = run_git("push", "origin", "HEAD:main", cwd=worktree, check=False)
            if pushed.returncode == 0:
                return True
        if attempt == 0:
            continue
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish the latest safe local real-estate aggregate.")
    parser.add_argument("--push", action="store_true", help="commit and push the snapshot to GitHub")
    args = parser.parse_args()
    payload = build_snapshot()
    target = write_snapshot(payload)
    print(f"공개 스냅샷 생성: {target} ({payload['trade_count']:,}건)", flush=True)
    if args.push and not push_snapshot(payload):
        raise SystemExit("GitHub 공개 스냅샷 push에 실패했습니다. 다음 실행에서 재시도합니다.")


if __name__ == "__main__":
    main()
