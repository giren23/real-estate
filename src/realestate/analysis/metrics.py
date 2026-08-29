from __future__ import annotations
import pandas as pd

def apartment_metrics(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    df = trades.sort_values("trade_date").copy()
    keys = ["lawd_cd", "region_name", "dong", "apt_name", "area_m2"]
    grouped = df.groupby(keys, dropna=False)
    out = grouped.agg(
        trade_count=("price_eok", "size"),
        first_trade_date=("trade_date", "first"),
        first_price_eok=("price_eok", "first"),
        latest_trade_date=("trade_date", "last"),
        latest_price_eok=("price_eok", "last"),
        min_price_eok=("price_eok", "min"),
        max_price_eok=("price_eok", "max"),
        median_price_eok=("price_eok", "median"),
        median_pyeong_price_manwon=("price_per_pyeong_manwon", "median"),
    ).reset_index()
    out["range_eok"] = out["max_price_eok"] - out["min_price_eok"]
    out["change_eok"] = out["latest_price_eok"] - out["first_price_eok"]
    out["change_pct"] = out["change_eok"] / out["first_price_eok"] * 100
    return out

def monthly_metrics(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    df = trades.copy()
    df["month"] = df["trade_date"].str[:7]
    return (
        df.groupby(["lawd_cd", "region_name", "month"])
        .agg(
            trade_count=("price_eok", "size"),
            median_price_eok=("price_eok", "median"),
            average_price_eok=("price_eok", "mean"),
            median_pyeong_price_manwon=("price_per_pyeong_manwon", "median"),
        )
        .reset_index()
    )
