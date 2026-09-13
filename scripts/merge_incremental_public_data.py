from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from realestate.analysis.metrics import apartment_metrics, monthly_metrics
from realestate.analysis.publish import compact_history, records


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "data" / "public"
RAW_TRADES = ROOT / "data" / "raw" / "trades"
PARTITION_PATTERN = re.compile(r"^(\d{5})_(\d{6})\.parquet$")


def read_json(name: str, default: object) -> object:
    path = PUBLIC / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def history_frame(payload: dict) -> pd.DataFrame:
    apartments = payload.get("apartments", [])
    output = []
    for row in payload.get("rows", []):
        apartment = apartments[int(row[0])]
        output.append({
            "lawd_cd": str(apartment[0]).zfill(5), "region_name": apartment[1],
            "dong": apartment[2], "apt_name": apartment[3], "area_m2": float(row[1]),
            "month": str(row[2]), "median_price_eok": float(row[3]), "trade_count": int(row[4]),
        })
    return pd.DataFrame(output)


def collected_partitions() -> tuple[set[tuple[str, str]], pd.DataFrame]:
    covered: set[tuple[str, str]] = set()
    frames: list[pd.DataFrame] = []
    for path in sorted(RAW_TRADES.glob("*.parquet")):
        match = PARTITION_PATTERN.match(path.name)
        if not match:
            continue
        lawd_cd, deal_ym = match.groups()
        covered.add((lawd_cd, f"{deal_ym[:4]}-{deal_ym[4:]}"))
        frame = pd.read_parquet(path)
        if not frame.empty:
            frames.append(frame)
    trades = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not trades.empty:
        trades["lawd_cd"] = trades["lawd_cd"].astype(str).str.zfill(5)
        trades = trades[~trades.get("cancelled", False).fillna(False)].copy()
    return covered, trades


def replace_covered(frame: pd.DataFrame, covered: set[tuple[str, str]], month_column: str = "month") -> pd.DataFrame:
    if frame.empty:
        return frame
    keep = [
        (str(code).zfill(5), str(month)) not in covered
        for code, month in zip(frame["lawd_cd"], frame[month_column])
    ]
    return frame.loc[keep].copy()


def merge_apartments(old_rows: list[dict], trades: pd.DataFrame, merged_history: pd.DataFrame) -> list[dict]:
    if trades.empty:
        return old_rows
    updated = apartment_metrics(trades)
    history_counts = merged_history.groupby(["lawd_cd", "region_name", "dong", "apt_name", "area_m2"], dropna=False)["trade_count"].sum()
    keys = ("lawd_cd", "region_name", "dong", "apt_name", "area_m2")

    def key(row: dict) -> tuple:
        return (str(row["lawd_cd"]).zfill(5), str(row["region_name"]), str(row["dong"]), str(row["apt_name"]), round(float(row["area_m2"]), 3))

    merged = {key(row): dict(row) for row in old_rows}
    for fresh in records(updated):
        item_key = key(fresh)
        previous = merged.get(item_key)
        if previous:
            fresh["first_trade_date"] = previous.get("first_trade_date") or fresh.get("first_trade_date")
            fresh["first_price_eok"] = previous.get("first_price_eok") if previous.get("first_price_eok") is not None else fresh.get("first_price_eok")
            fresh["min_price_eok"] = min(float(previous.get("min_price_eok", fresh["min_price_eok"])), float(fresh["min_price_eok"]))
            fresh["max_price_eok"] = max(float(previous.get("max_price_eok", fresh["max_price_eok"])), float(fresh["max_price_eok"]))
            fresh["median_price_eok"] = previous.get("median_price_eok", fresh.get("median_price_eok"))
            fresh["median_pyeong_price_manwon"] = previous.get("median_pyeong_price_manwon", fresh.get("median_pyeong_price_manwon"))
        count_key = (item_key[0], item_key[1], item_key[2], item_key[3], float(item_key[4]))
        fresh["trade_count"] = int(history_counts.get(count_key, fresh.get("trade_count") or 0))
        fresh["range_eok"] = float(fresh["max_price_eok"]) - float(fresh["min_price_eok"])
        first_price = float(fresh.get("first_price_eok") or 0)
        fresh["change_eok"] = float(fresh["latest_price_eok"]) - first_price
        fresh["change_pct"] = fresh["change_eok"] / first_price * 100 if first_price else None
        merged[item_key] = fresh
    return sorted(merged.values(), key=lambda row: str(row.get("latest_trade_date") or ""), reverse=True)


def merge_latest(old_rows: list[dict], trades: pd.DataFrame, covered: set[tuple[str, str]]) -> list[dict]:
    retained = [row for row in old_rows if (str(row.get("lawd_cd", "")).zfill(5), str(row.get("trade_date", ""))[:7]) not in covered]
    incoming = records(trades) if not trades.empty else []
    unique: dict[tuple, dict] = {}
    for row in retained + incoming:
        identity = (
            str(row.get("lawd_cd", "")).zfill(5), str(row.get("trade_date", "")), str(row.get("dong", "")),
            str(row.get("apt_name", "")), float(row.get("area_m2") or 0), int(row.get("floor") or 0),
            int(row.get("price_manwon") or 0), str(row.get("apt_dong", "")),
        )
        unique[identity] = row
    return sorted(unique.values(), key=lambda row: str(row.get("trade_date") or ""), reverse=True)[:50000]


def write_json_atomic(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    old_meta = read_json("meta.json", {})
    old_history = history_frame(read_json("apartment_history.json", {}))
    covered, trades = collected_partitions()
    if not covered:
        raise SystemExit("병합할 최신 실거래 파티션이 없습니다.")

    retained_history = replace_covered(old_history, covered)
    if trades.empty:
        fresh_history = pd.DataFrame(columns=old_history.columns)
    else:
        fresh_history = (
            trades.assign(month=trades["trade_date"].str[:7])
            .groupby(["lawd_cd", "region_name", "dong", "apt_name", "area_m2", "month"], as_index=False)
            .agg(median_price_eok=("price_eok", "median"), trade_count=("price_eok", "size"))
        )
        fresh_history["median_price_eok"] = fresh_history["median_price_eok"].round(4)
    merged_history = pd.concat([retained_history, fresh_history], ignore_index=True).sort_values(["lawd_cd", "apt_name", "area_m2", "month"])

    old_count = int(old_meta.get("trade_count") or old_history.get("trade_count", pd.Series(dtype=int)).sum())
    new_count = int(merged_history["trade_count"].sum()) if not merged_history.empty else 0
    if old_count and new_count < old_count * 0.98:
        raise RuntimeError(f"안전장치 작동: 공개 이력 거래 수가 {old_count:,}건에서 {new_count:,}건으로 급감함")

    old_monthly = pd.DataFrame(read_json("monthly.json", []))
    merged_monthly = replace_covered(old_monthly, covered)
    if not trades.empty:
        merged_monthly = pd.concat([merged_monthly, monthly_metrics(trades)], ignore_index=True).sort_values(["lawd_cd", "month"])
    old_latest = read_json("latest_trades.json", [])
    latest = merge_latest(old_latest, trades, covered)
    apartments = merge_apartments(read_json("apartments.json", []), trades, merged_history)
    regions = pd.concat([
        pd.DataFrame(read_json("regions.json", [])),
        trades[["lawd_cd", "region_name"]].drop_duplicates() if not trades.empty else pd.DataFrame(columns=["lawd_cd", "region_name"]),
    ], ignore_index=True).drop_duplicates().sort_values("region_name")
    complexes_path = ROOT / "data" / "raw" / "complexes.csv"
    complexes = (
        records(pd.read_csv(complexes_path, dtype=str).fillna(""))
        if complexes_path.exists()
        else read_json("complexes.json", [])
    )

    meta = {
        **old_meta,
        "status": "ok",
        "trade_count": new_count,
        "region_count": int(merged_history["lawd_cd"].nunique()) if not merged_history.empty else 0,
        "apartment_count": len(complexes),
        "trade_apartment_count": int(merged_history[["lawd_cd", "dong", "apt_name"]].drop_duplicates().shape[0]) if not merged_history.empty else 0,
        "first_date": str(old_meta.get("first_date") or (merged_history["month"].min() + "-01")),
        "latest_date": max((str(row.get("trade_date") or "") for row in latest), default=str(old_meta.get("latest_date") or "")),
        "history_format": 2,
        "incremental_partition_count": len(covered),
    }
    payloads = {
        "meta.json": meta,
        "latest_trades.json": latest,
        "apartments.json": apartments,
        "apartment_history.json": compact_history(merged_history),
        "monthly.json": records(merged_monthly),
        "regions.json": records(regions),
    }
    for name, payload in payloads.items():
        write_json_atomic(PUBLIC / name, payload)
    print(f"증분 공개 데이터 병합 완료: {len(covered):,}개 지역·월, 전체 {new_count:,}건 보존")


if __name__ == "__main__":
    main()
