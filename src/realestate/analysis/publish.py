from __future__ import annotations
from pathlib import Path
import json
import pandas as pd

from realestate.analysis.metrics import apartment_metrics, monthly_metrics
from realestate.collectors.population import load_population_csv

def load_parquets(folder: Path) -> pd.DataFrame:
    paths = sorted(folder.glob("*.parquet"))
    frames = [pd.read_parquet(p) for p in paths]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

def records(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    return df.where(pd.notna(df), None).to_dict(orient="records")

def build_public_data(root: Path) -> None:
    trades = load_parquets(root / "data/raw/trades")
    population = load_population_csv(root / "data/raw/population/population.csv")
    complexes_path = root / "data/raw/complexes.csv"
    complexes = pd.read_csv(complexes_path, dtype=str).fillna("") if complexes_path.exists() else pd.DataFrame()
    out_dir = root / "data/public"
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "complexes.json").write_text(json.dumps(records(complexes), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    if trades.empty:
        (out_dir / "apartment_history.json").write_text("[]", encoding="utf-8")
        (out_dir / "meta.json").write_text(
            json.dumps({"status": "empty", "message": "아직 실거래 데이터가 없습니다.", "apartment_count": int(len(complexes))}, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8"
        )
        return

    trades = trades.sort_values("trade_date")
    apartments = apartment_metrics(trades)
    monthly = monthly_metrics(trades)
    trade_history = trades.assign(month=trades["trade_date"].str[:7]).groupby(
        ["lawd_cd", "region_name", "dong", "apt_name", "area_m2", "month"],
        as_index=False,
    ).agg(
        median_price_eok=("price_eok", "median"),
        average_price_eok=("price_eok", "mean"),
        trade_count=("price_eok", "size"),
    ).sort_values(["lawd_cd", "apt_name", "area_m2", "month"])
    price_columns = ["median_price_eok", "average_price_eok"]
    trade_history[price_columns] = trade_history[price_columns].round(4)

    if not population.empty:
        pop = population.rename(columns={"region_code": "lawd_cd"})
        monthly = monthly.merge(pop, on=["lawd_cd", "month"], how="left")

    payloads = {
        "meta.json": {
            "status": "ok",
            "trade_count": int(len(trades)),
            "region_count": int(trades["lawd_cd"].nunique()),
            "apartment_count": int(len(complexes)) if not complexes.empty else int(trades[["lawd_cd", "dong", "apt_name"]].drop_duplicates().shape[0]),
            "trade_apartment_count": int(trades[["lawd_cd", "dong", "apt_name"]].drop_duplicates().shape[0]),
            "first_date": str(trades["trade_date"].min()),
            "latest_date": str(trades["trade_date"].max()),
        },
        "latest_trades.json": records(trades.sort_values("trade_date", ascending=False).head(50000)),
        "apartments.json": records(apartments.sort_values("latest_trade_date", ascending=False)),
        "apartment_history.json": records(trade_history),
        "complexes.json": records(complexes),
        "monthly.json": records(monthly),
        "regions.json": records(trades[["lawd_cd", "region_name"]].drop_duplicates().sort_values("region_name")),
    }
    for filename, payload in payloads.items():
        (out_dir / filename).write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
