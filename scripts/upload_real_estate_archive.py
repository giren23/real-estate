from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = ROOT / "data" / "local" / "cloud-archive"
DEFAULT_BUCKET = "korean-real-estate-archive"
WRANGLER = ROOT / "cloudflare-worker" / "node_modules" / ".bin" / "wrangler.cmd"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wrangler(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        [str(WRANGLER), *args], cwd=ROOT / "cloudflare-worker", text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
    )
    if check and process.returncode:
        raise RuntimeError(process.stdout[-4000:])
    return process


def put(bucket: str, key: str, path: Path, *, encoded: bool = False) -> None:
    args = ["r2", "object", "put", f"{bucket}/{key}", "--remote", "--file", str(path),
            "--content-type", "application/json", "--cache-control", "public, max-age=31536000, immutable" if encoded else "no-cache"]
    if encoded:
        args.extend(["--content-encoding", "gzip"])
    wrangler(*args)


def verify_remote(bucket: str, key: str, expected_sha256: str) -> None:
    with tempfile.TemporaryDirectory(prefix="r2-verify-") as directory:
        downloaded = Path(directory) / "object"
        wrangler("r2", "object", "get", f"{bucket}/{key}", "--remote", "--file", str(downloaded))
        actual = sha256_file(downloaded)
        if actual != expected_sha256:
            raise RuntimeError(f"R2 검증 실패: {key}, expected={expected_sha256}, actual={actual}")


def upload(bucket: str = DEFAULT_BUCKET, root: Path = ROOT) -> dict:
    archive_root = root / "data" / "local" / "cloud-archive"
    current_path = archive_root / "current.json"
    current = json.loads(current_path.read_text(encoding="utf-8"))
    manifest_path = archive_root / current["manifest_key"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    state_path = archive_root / f"uploaded-{bucket}.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"verified": []}
    verified = set(state.get("verified", []))
    objects = [manifest["catalog"], *manifest["history"].values(), *manifest["trades"].values()]
    uploaded = 0
    for index, item in enumerate(objects, 1):
        if item["sha256"] in verified:
            continue
        local_path = archive_root / item["key"]
        if sha256_file(local_path) != item["sha256"]:
            raise RuntimeError(f"로컬 내보내기 해시 불일치: {local_path}")
        put(bucket, item["key"], local_path, encoded=True)
        verify_remote(bucket, item["key"], item["sha256"])
        verified.add(item["sha256"])
        uploaded += 1
        state_temp = state_path.with_suffix(".tmp")
        state_temp.write_text(json.dumps({"verified": sorted(verified)}, separators=(",", ":")), encoding="utf-8")
        os.replace(state_temp, state_path)
        print(f"[{index}/{len(objects)}] 검증 업로드: {item['key']}", flush=True)

    manifest_key = current["manifest_key"]
    manifest_sha = sha256_file(manifest_path)
    put(bucket, manifest_key, manifest_path)
    verify_remote(bucket, manifest_key, manifest_sha)
    current_sha = sha256_file(current_path)
    # The tiny pointer is intentionally written last. Readers therefore see either the
    # previous fully verified snapshot or this fully verified snapshot, never a partial one.
    put(bucket, "current.json", current_path)
    verify_remote(bucket, "current.json", current_sha)
    return {"status": "published", "bucket": bucket, "snapshot_id": manifest["snapshot_id"], "uploaded_objects": uploaded, "total_objects": len(objects)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload and read-back-verify a content-addressed R2 archive.")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    args = parser.parse_args()
    print(json.dumps(upload(args.bucket), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
