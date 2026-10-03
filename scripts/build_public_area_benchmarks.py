"""Build the GitHub Pages 84㎡ benchmark snapshot from already-public history."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from realestate.analysis.publish import area_benchmark_snapshot
if __package__:
    from .public_trade_archive import read, history_rows
else:
    from public_trade_archive import read, history_rows


ROOT = Path(__file__).resolve().parents[1]


def expand_history(payload: dict) -> pd.DataFrame:
    apartments = payload.get("apartments", [])
    rows = []
    for item in payload.get("rows", []):
        if not isinstance(item, list) or len(item) < 5:
            continue
        apartment_id = int(item[0])
        if apartment_id < 0 or apartment_id >= len(apartments):
            continue
        apartment = apartments[apartment_id]
        if not isinstance(apartment, list) or len(apartment) < 4:
            continue
        rows.append({
            "lawd_cd": str(apartment[0]), "region_name": str(apartment[1]),
            "dong": str(apartment[2]), "apt_name": str(apartment[3]),
            "area_m2": float(item[1]), "month": str(item[2]),
            "median_price_eok": float(item[3]), "trade_count": int(item[4]),
        })
    return pd.DataFrame(rows)


def main() -> None:
    source = ROOT / "data" / "public" / "apartment_history.json"
    target = ROOT / "data" / "public" / "area_benchmarks.json"
    manifest_path = ROOT / "data/public/shards/manifest.json"
    if manifest_path.exists():
        # Reduce each district before concatenating: no multi-million-row
        # dataframe is needed to choose one representative 84sqm observation.
        candidates = []
        for item in read(manifest_path)["districts"]:
            best = {}
            for row in history_rows(read(manifest_path.parent / item["file"])["history"]):
                area = float(row["area_m2"])
                if not 80 <= area <= 90 or float(row["median_price_eok"]) <= 0:
                    continue
                key = (row["dong"], row["apt_name"])
                rank = (abs(area - 84), -int(row["month"].replace("-", "")), -int(row["trade_count"]))
                if key not in best or rank < best[key][0]:
                    best[key] = (rank, row)
            candidates.extend(value[1] for value in best.values())
        frame = pd.DataFrame(candidates)
    else:
        frame = expand_history(json.loads(source.read_text(encoding="utf-8")))
    result = area_benchmark_snapshot(frame)
    target.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"[PUBLISH] GitHub 84㎡ 비교 스냅샷: {len(result['items']):,}개 단지 · {target}")


if __name__ == "__main__":
    main()
