from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd

from realestate.analysis.publish import compact_history


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "data/public"
SHARDS = PUBLIC / "shards"


def read_json(name: str, default: object) -> object:
    path = PUBLIC / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def history_frame(payload: dict) -> pd.DataFrame:
    output = []
    apartments = payload.get("apartments", [])
    for row in payload.get("rows", []):
        apartment = apartments[int(row[0])]
        output.append({
            "lawd_cd": str(apartment[0]).zfill(5),
            "region_name": apartment[1],
            "dong": apartment[2],
            "apt_name": apartment[3],
            "area_m2": float(row[1]),
            "month": str(row[2]),
            "median_price_eok": float(row[3]),
            "trade_count": int(row[4]),
        })
    return pd.DataFrame(output, columns=[
        "lawd_cd", "region_name", "dong", "apt_name", "area_m2",
        "month", "median_price_eok", "trade_count",
    ])


def write_json_atomic(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> None:
    SHARDS.mkdir(parents=True, exist_ok=True)
    trades = read_json("latest_trades.json", [])
    history = history_frame(read_json("apartment_history.json", {}))
    codes = sorted(
        {str(row.get("lawd_cd", "")).zfill(5) for row in trades if row.get("lawd_cd")}
        | set(history["lawd_cd"].astype(str).str.zfill(5))
    )
    manifest_rows = []
    for code in codes:
        district_trades = [row for row in trades if str(row.get("lawd_cd", "")).zfill(5) == code]
        district_history = history[history["lawd_cd"].astype(str).str.zfill(5) == code]
        catalog: dict[tuple[str, str], str] = {}
        for row in district_history.to_dict(orient="records"):
            catalog[(str(row.get("dong", "")), str(row.get("apt_name", "")))] = str(row.get("region_name", ""))
        for row in district_trades:
            catalog[(str(row.get("dong", "")), str(row.get("apt_name", "")))] = str(row.get("region_name", ""))
        payload = {
            "schema_version": 1,
            "lawd_cd": code,
            "trades": district_trades,
            "history": compact_history(district_history),
        }
        target = SHARDS / f"{code}.json"
        write_json_atomic(target, payload)
        content = target.read_bytes()
        manifest_rows.append({
            "lawd_cd": code,
            "file": f"{code}.json",
            "trade_rows": len(district_trades),
            "history_rows": len(district_history),
            "size_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "region_name": next(iter(catalog.values()), ""),
            "apartments": [[dong, name] for dong, name in sorted(catalog) if name],
        })
    meta = read_json("meta.json", {})
    write_json_atomic(SHARDS / "manifest.json", {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latest_date": meta.get("latest_date", ""),
        "trade_count": meta.get("trade_count", 0),
        "trade_apartment_count": sum(len(item["apartments"]) for item in manifest_rows),
        "districts": manifest_rows,
    })
    print(f"정적 모바일용 지역 데이터 {len(manifest_rows):,}개 생성 완료", flush=True)


if __name__ == "__main__":
    main()
