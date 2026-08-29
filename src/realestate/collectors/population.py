from __future__ import annotations
from pathlib import Path
import pandas as pd

REQUIRED = {"region_code", "region_name", "month", "population", "households"}

def load_population_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=sorted(REQUIRED))
    df = pd.read_csv(path, dtype={"region_code": str, "month": str})
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"인구 CSV 필수 컬럼 누락: {sorted(missing)}")
    for col in ["population", "households", "move_in", "move_out"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values(["region_code", "month"])
    df["population_change"] = df.groupby("region_code")["population"].diff()
    df["population_change_pct"] = df.groupby("region_code")["population"].pct_change(fill_method=None) * 100
    df["household_change"] = df.groupby("region_code")["households"].diff()
    if {"move_in", "move_out"}.issubset(df.columns):
        df["net_migration"] = df["move_in"] - df["move_out"]
    return df
