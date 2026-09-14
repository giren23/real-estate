from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from realestate.analysis.publish import records


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/complexes.csv"
PUBLIC = ROOT / "data/public"


def write_json_atomic(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> None:
    frame = pd.read_csv(RAW, dtype=str).fillna("")
    if len(frame) < 20_000:
        raise RuntimeError(f"안전장치 작동: 공동주택 단지 목록이 {len(frame):,}개뿐임")
    old_path = PUBLIC / "complexes.json"
    if old_path.exists():
        old_count = len(json.loads(old_path.read_text(encoding="utf-8")))
        if old_count and len(frame) < old_count * 0.95:
            raise RuntimeError(
                f"안전장치 작동: 단지 목록이 {old_count:,}개에서 {len(frame):,}개로 급감함"
            )
    write_json_atomic(old_path, records(frame))
    meta_path = PUBLIC / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta["apartment_count"] = len(frame)
    write_json_atomic(meta_path, meta)
    print(f"공동주택 단지 목록 {len(frame):,}개 게시 완료", flush=True)


if __name__ == "__main__":
    main()
