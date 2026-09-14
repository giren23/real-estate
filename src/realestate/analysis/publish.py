from __future__ import annotations

import bisect
import json
import math
from collections import defaultdict
from pathlib import Path

import pandas as pd

from realestate.analysis.metrics import apartment_metrics, monthly_metrics
from realestate.collectors.population import load_population_csv
from realestate.area_benchmarks import (
    administrative_scopes,
    price_per_estimated_supply_pyeong,
)


HISTORY_VERSION = 2
HISTORY_APARTMENT_COLUMNS = [
    "lawd_cd",
    "region_name",
    "dong",
    "apt_name",
]


def load_parquets(folder: Path) -> pd.DataFrame:
    paths = sorted(folder.glob("*.parquet"))
    frames = [pd.read_parquet(path) for path in paths]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def records(frame: pd.DataFrame) -> list[dict]:
    if frame.empty:
        return []
    return frame.where(pd.notna(frame), None).to_dict(orient="records")


def compact_history(frame: pd.DataFrame) -> dict:
    """Store repeated apartment labels once instead of on every monthly point."""
    if frame.empty:
        return {
            "version": HISTORY_VERSION,
            "apartment_columns": HISTORY_APARTMENT_COLUMNS,
            "row_columns": [
                "apartment_id",
                "area_m2",
                "month",
                "median_price_eok",
                "trade_count",
            ],
            "apartments": [],
            "rows": [],
        }

    apartments = (
        frame[HISTORY_APARTMENT_COLUMNS]
        .drop_duplicates()
        .sort_values(HISTORY_APARTMENT_COLUMNS)
        .reset_index(drop=True)
    )
    apartments["apartment_id"] = range(len(apartments))
    encoded = frame.merge(
        apartments,
        on=HISTORY_APARTMENT_COLUMNS,
        how="left",
        validate="many_to_one",
    ).sort_values(["apartment_id", "area_m2", "month"])

    apartment_rows = [
        [
            str(row.lawd_cd),
            str(row.region_name),
            str(row.dong),
            str(row.apt_name),
        ]
        for row in apartments.itertuples(index=False)
    ]
    history_rows = [
        [
            int(row.apartment_id),
            float(row.area_m2),
            str(row.month),
            float(row.median_price_eok),
            int(row.trade_count),
        ]
        for row in encoded.itertuples(index=False)
    ]
    return {
        "version": HISTORY_VERSION,
        "apartment_columns": HISTORY_APARTMENT_COLUMNS,
        "row_columns": [
            "apartment_id",
            "area_m2",
            "month",
            "median_price_eok",
            "trade_count",
        ],
        "apartments": apartment_rows,
        "rows": history_rows,
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def area_benchmark_snapshot(history: pd.DataFrame) -> dict:
    """Precalculate the 84㎡ comparison cards for GitHub Pages.

    The browser receives only the selected-complex cards and their peer summaries,
    never the local server database.  This keeps the same calculation available
    when the PC and its API are offline.
    """
    columns = ["lawd_cd", "region_name", "dong", "apt_name", "area_m2", "month", "median_price_eok", "trade_count"]
    candidates = history.loc[
        history["area_m2"].between(80.0, 90.0) & (history["median_price_eok"] > 0), columns
    ].copy()
    if candidates.empty:
        return {"schema_version": 1, "basis": "전용 80~90㎡ 중 84㎡에 가장 가까운 최신 월별 중앙 실거래가", "items": {}}

    candidates["distance_to_84"] = (candidates["area_m2"] - 84.0).abs()
    candidates = candidates.sort_values(
        ["lawd_cd", "dong", "apt_name", "distance_to_84", "month", "trade_count"],
        ascending=[True, True, True, True, False, False],
    ).drop_duplicates(["lawd_cd", "dong", "apt_name"], keep="first")

    rows: list[dict] = []
    scope_values: dict[str, list[float]] = defaultdict(list)
    for source in candidates.to_dict(orient="records"):
        lawd_cd = str(source["lawd_cd"]).zfill(5)[:5]
        value = price_per_estimated_supply_pyeong(float(source["median_price_eok"]), float(source["area_m2"]))
        if value <= 0:
            continue
        scopes = administrative_scopes(str(source["region_name"]), lawd_cd, str(source["dong"]))
        row = {
            "lawd_cd": lawd_cd,
            "region_name": str(source["region_name"]),
            "dong": str(source["dong"]),
            "apt_name": str(source["apt_name"]),
            "area_m2": round(float(source["area_m2"]), 2),
            "month": str(source["month"]),
            "trade_count": int(source["trade_count"]),
            "price_per_supply_pyeong_manwon": round(value, 1),
            "administrative_scopes": scopes,
        }
        rows.append(row)
        for scope in scopes:
            scope_values[scope["key"]].append(value)

    summaries: dict[str, dict] = {}
    for key, values in scope_values.items():
        ordered = sorted(values)
        count = len(ordered)
        mean = sum(ordered) / count
        variance = sum((value - mean) ** 2 for value in ordered) / count
        summaries[key] = {"values": ordered, "count": count, "mean_manwon": mean, "stddev_manwon": math.sqrt(variance)}

    items: dict[str, dict] = {}
    for row in rows:
        value = row["price_per_supply_pyeong_manwon"]
        references = []
        for scope in reversed(row["administrative_scopes"]):
            summary = summaries[scope["key"]]
            count = summary["count"]
            stddev = summary["stddev_manwon"]
            z_score = (value - summary["mean_manwon"]) / stddev if count >= 2 and stddev else None
            references.append({
                **scope,
                "reference": {
                    "count": count,
                    "mean_manwon": round(summary["mean_manwon"], 1),
                    "stddev_manwon": round(stddev, 1),
                    "z_score": round(z_score, 2) if z_score is not None else None,
                    "top_percent": round((count - bisect.bisect_left(summary["values"], value)) / count * 100, 1) if count >= 2 else None,
                },
            })
        key = "|".join((row["lawd_cd"], row["dong"], row["apt_name"]))
        items[key] = {key: value for key, value in row.items() if key != "administrative_scopes"}
        items[key]["administrative_references"] = references
    return {
        "schema_version": 1,
        "basis": "전용 80~90㎡ 중 84㎡에 가장 가까운 최신 월별 중앙 실거래가 · 공급면적은 전용률 75% 가정으로 환산",
        "items": items,
    }


def build_public_data(root: Path) -> None:
    trades = load_parquets(root / "data/raw/trades")
    population = load_population_csv(
        root / "data/raw/population/population.csv"
    )
    complexes_path = root / "data/raw/complexes.csv"
    complexes = (
        pd.read_csv(complexes_path, dtype=str).fillna("")
        if complexes_path.exists()
        else pd.DataFrame()
    )
    out_dir = root / "data/public"
    out_dir.mkdir(parents=True, exist_ok=True)

    _write_json(out_dir / "complexes.json", records(complexes))

    if trades.empty:
        _write_json(
            out_dir / "apartment_history.json",
            compact_history(pd.DataFrame()),
        )
        _write_json(
            out_dir / "meta.json",
            {
                "status": "empty",
                "message": "아직 실거래 데이터가 없습니다.",
                "apartment_count": int(len(complexes)),
                "history_format": HISTORY_VERSION,
            },
        )
        return

    trades = trades.sort_values("trade_date")
    apartments = apartment_metrics(trades)
    monthly = monthly_metrics(trades)
    trade_history = (
        trades.assign(month=trades["trade_date"].str[:7])
        .groupby(
            [
                "lawd_cd",
                "region_name",
                "dong",
                "apt_name",
                "area_m2",
                "month",
            ],
            as_index=False,
        )
        .agg(
            median_price_eok=("price_eok", "median"),
            trade_count=("price_eok", "size"),
        )
        .sort_values(["lawd_cd", "apt_name", "area_m2", "month"])
    )
    trade_history["median_price_eok"] = (
        trade_history["median_price_eok"].round(4)
    )

    if not population.empty:
        pop = population.rename(columns={"region_code": "lawd_cd"})
        monthly = monthly.merge(pop, on=["lawd_cd", "month"], how="left")

    apartment_count = (
        int(len(complexes))
        if not complexes.empty
        else int(
            trades[["lawd_cd", "dong", "apt_name"]]
            .drop_duplicates()
            .shape[0]
        )
    )
    payloads = {
        "meta.json": {
            "status": "ok",
            "trade_count": int(len(trades)),
            "region_count": int(trades["lawd_cd"].nunique()),
            "apartment_count": apartment_count,
            "trade_apartment_count": int(
                trades[["lawd_cd", "dong", "apt_name"]]
                .drop_duplicates()
                .shape[0]
            ),
            "first_date": str(trades["trade_date"].min()),
            "latest_date": str(trades["trade_date"].max()),
            "history_format": HISTORY_VERSION,
        },
        "latest_trades.json": records(
            trades.sort_values("trade_date", ascending=False).head(50000)
        ),
        "apartments.json": records(
            apartments.sort_values("latest_trade_date", ascending=False)
        ),
        "apartment_history.json": compact_history(trade_history),
        "area_benchmarks.json": area_benchmark_snapshot(trade_history),
        "complexes.json": records(complexes),
        "monthly.json": records(monthly),
        "regions.json": records(
            trades[["lawd_cd", "region_name"]]
            .drop_duplicates()
            .sort_values("region_name")
        ),
    }
    for filename, payload in payloads.items():
        target = out_dir / filename
        _write_json(target, payload)
        if filename == "apartment_history.json":
            print(
                f"[PUBLISH] 압축 장기 이력: {target.stat().st_size / 1024 / 1024:.2f}MB",
                flush=True,
            )
