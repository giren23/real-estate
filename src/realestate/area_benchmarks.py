from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable


TARGET_AREA_MIN = 80.0
TARGET_AREA_MAX = 90.0
TARGET_AREA_M2 = 84.0
ASSUMED_EXCLUSIVE_RATIO = 0.75
PYEONG_M2 = 3.305785


def complex_key(lawd_cd: str, dong: str, apt_name: str) -> str:
    return "|".join((str(lawd_cd).zfill(5)[:5], str(dong), str(apt_name)))


def city_label(region_name: str) -> str:
    """Return a meaningful city/county comparator while keeping metro cities intact."""
    tokens = str(region_name or "").split()
    if not tokens:
        return "지역 미확인"
    if len(tokens) >= 2 and (tokens[1].endswith("시") or tokens[1].endswith("군")):
        return " ".join(tokens[:2])
    return tokens[0]


def estimated_supply_pyeong(area_m2: float) -> float:
    return float(area_m2) / ASSUMED_EXCLUSIVE_RATIO / PYEONG_M2


def price_per_estimated_supply_pyeong(price_eok: float, area_m2: float) -> float:
    supply_pyeong = estimated_supply_pyeong(area_m2)
    return float(price_eok) * 10_000 / supply_pyeong if supply_pyeong else 0.0


def _reference(values: Iterable[float]) -> dict:
    rows = [float(value) for value in values if float(value) > 0]
    count = len(rows)
    if not count:
        return {"count": 0, "mean_manwon": None, "stddev_manwon": None}
    mean = sum(rows) / count
    variance = sum((value - mean) ** 2 for value in rows) / count
    return {
        "count": count,
        "mean_manwon": round(mean, 1),
        "stddev_manwon": round(math.sqrt(variance), 1),
    }


def build_index(records: Iterable[dict]) -> dict:
    """Index one selected 84㎡-class row per complex for local comparisons."""
    complexes: dict[str, dict] = {}
    dong_values: dict[str, list[float]] = defaultdict(list)
    city_values: dict[str, list[float]] = defaultdict(list)
    province_values: dict[str, list[float]] = defaultdict(list)

    for source in records:
        area_m2 = float(source["area_m2"])
        price_eok = float(source["median_price_eok"])
        value = price_per_estimated_supply_pyeong(price_eok, area_m2)
        if value <= 0:
            continue
        row = {
            "lawd_cd": str(source["lawd_cd"]).zfill(5)[:5],
            "dong": str(source["dong"]),
            "apt_name": str(source["apt_name"]),
            "region_name": str(source.get("region_name") or ""),
            "area_m2": round(area_m2, 2),
            "month": str(source["month"]),
            "trade_count": int(source.get("trade_count") or 0),
            "price_per_supply_pyeong_manwon": round(value, 1),
        }
        key = complex_key(row["lawd_cd"], row["dong"], row["apt_name"])
        row["dong_key"] = "|".join((row["lawd_cd"], row["dong"]))
        row["city_label"] = city_label(row["region_name"])
        row["province_label"] = row["region_name"].split()[0] if row["region_name"] else "지역 미확인"
        complexes[key] = row
        dong_values[row["dong_key"]].append(value)
        city_values[row["city_label"]].append(value)
        province_values[row["province_label"]].append(value)

    return {
        "complexes": complexes,
        "dongs": {key: _reference(values) for key, values in dong_values.items()},
        "cities": {key: _reference(values) for key, values in city_values.items()},
        "provinces": {key: _reference(values) for key, values in province_values.items()},
    }


def _position(value: float, reference: dict) -> dict:
    count = int(reference.get("count") or 0)
    mean = reference.get("mean_manwon")
    stddev = reference.get("stddev_manwon")
    result = {**reference, "z_score": None, "top_percent": None}
    if count < 2 or mean is None or not stddev:
        return result
    z_score = (value - float(mean)) / float(stddev)
    result["z_score"] = round(z_score, 2)
    return result


def resolve_requested(index: dict, requested: Iterable[dict]) -> list[dict]:
    """Attach percentile rank after comparing with each reference distribution."""
    result: list[dict] = []
    for requested_item in requested:
        key = complex_key(requested_item.get("lawd_cd", ""), requested_item.get("dong", ""), requested_item.get("apt_name", ""))
        row = index["complexes"].get(key)
        if not row:
            continue
        value = float(row["price_per_supply_pyeong_manwon"])
        dong_values = [item["price_per_supply_pyeong_manwon"] for item in index["complexes"].values() if item["dong_key"] == row["dong_key"]]
        city_values = [item["price_per_supply_pyeong_manwon"] for item in index["complexes"].values() if item["city_label"] == row["city_label"]]
        province_values = [item["price_per_supply_pyeong_manwon"] for item in index["complexes"].values() if item["province_label"] == row["province_label"]]
        dong = _position(value, index["dongs"].get(row["dong_key"], {}))
        city = _position(value, index["cities"].get(row["city_label"], {}))
        province = _position(value, index["provinces"].get(row["province_label"], {}))
        if dong["count"] >= 2:
            dong["top_percent"] = round(sum(other >= value for other in dong_values) / dong["count"] * 100, 1)
        if city["count"] >= 2:
            city["top_percent"] = round(sum(other >= value for other in city_values) / city["count"] * 100, 1)
        if province["count"] >= 2:
            province["top_percent"] = round(sum(other >= value for other in province_values) / province["count"] * 100, 1)
        result.append({
            **{key: value for key, value in row.items() if key not in {"dong_key"}},
            "dong_reference": dong,
            "city_reference": city,
            "province_reference": province,
        })
    return result


def price_per_exclusive_pyeong(price_eok: float, area_m2: float) -> float:
    exclusive_pyeong = float(area_m2) / PYEONG_M2
    return float(price_eok) * 10_000 / exclusive_pyeong if exclusive_pyeong else 0.0


def shift_month(month: str, delta: int) -> str:
    year, number = (int(value) for value in month.split("-", 1))
    serial = year * 12 + number - 1 + delta
    return f"{serial // 12:04d}-{serial % 12 + 1:02d}"


def _monthly_complex_values(rows: Iterable[dict]) -> tuple[dict[str, dict[str, float]], dict[str, dict], dict[str, dict[str, int]]]:
    buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    trade_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    metadata: dict[str, dict] = {}
    for row in rows:
        key = complex_key(row["lawd_cd"], row["dong"], row["apt_name"])
        value = price_per_exclusive_pyeong(row["median_price_eok"], row["area_m2"])
        if value <= 0:
            continue
        buckets[key][str(row["month"])].append(value)
        trade_counts[key][str(row["month"])] += max(0, int(row.get("trade_count") or 0))
        metadata[key] = {
            "lawd_cd": str(row["lawd_cd"]).zfill(5)[:5],
            "region_name": str(row.get("region_name") or ""),
            "dong": str(row["dong"]),
            "apt_name": str(row["apt_name"]),
        }
    monthly = {
        key: {month: sum(values) / len(values) for month, values in months.items()}
        for key, months in buckets.items()
    }
    return monthly, metadata, {key: dict(values) for key, values in trade_counts.items()}


def _average(values: Iterable[float]) -> float | None:
    rows = list(values)
    return sum(rows) / len(rows) if rows else None


def _rank(value: float | None, population: Iterable[float], *, descending: bool = True) -> dict:
    values = [float(item) for item in population if item is not None and math.isfinite(float(item))]
    if value is None or not values:
        return {"rank": None, "total": len(values), "top_percent": None}
    rank = 1 + sum(other > value for other in values) if descending else 1 + sum(other < value for other in values)
    return {"rank": rank, "total": len(values), "top_percent": round(rank / len(values) * 100, 1)}


def _trend_strength(month_values: dict[str, float]) -> float | None:
    ordered = sorted(month_values.items())
    if len(ordered) < 2:
        return None
    origin_year, origin_month = (int(value) for value in ordered[0][0].split("-"))
    xs = [(int(month[:4]) - origin_year) * 12 + int(month[5:7]) - origin_month for month, _ in ordered]
    ys = [value for _, value in ordered]
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    denominator = sum((value - mean_x) ** 2 for value in xs)
    if not denominator or not mean_y:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator
    return slope / mean_y * 100


def build_trend_analysis(rows: Iterable[dict], requested: dict, as_of_month: str) -> dict:
    """Rolling price location and trend-strength ranks for one selected complex."""
    monthly, metadata, monthly_trade_counts = _monthly_complex_values(rows)
    target_key = complex_key(requested.get("lawd_cd", ""), requested.get("dong", ""), requested.get("apt_name", ""))
    target_meta = metadata.get(target_key, {
        "lawd_cd": str(requested.get("lawd_cd") or ""), "dong": str(requested.get("dong") or ""),
        "apt_name": str(requested.get("apt_name") or ""), "region_name": str(requested.get("region_name") or ""),
    })
    target_city = city_label(target_meta.get("region_name", ""))
    province = str(target_meta.get("region_name") or "").split()[0] if target_meta.get("region_name") else "지역 미확인"
    definitions = ((1, "최근 1개월"), (3, "최근 3개월"), (6, "최근 6개월"), (12, "최근 1년"), (36, "최근 3년"))
    labels = {months: label for months, label in definitions}
    fallback_windows = {
        36: (36,),
        12: (12, 36),
        6: (6, 12, 36),
        3: (3, 6, 12, 36),
        1: (1, 3, 6, 12, 36),
    }
    scopes: dict[int, dict] = {}

    def scope_data(months: int) -> dict:
        if months in scopes:
            return scopes[months]
        cutoff = shift_month(as_of_month, -(months - 1))
        scoped = {
            key: {month: value for month, value in values.items() if cutoff <= month <= as_of_month}
            for key, values in monthly.items()
        }
        scoped = {key: values for key, values in scoped.items() if values}
        price_averages = {key: _average(values.values()) for key, values in scoped.items()}
        strengths = {key: _trend_strength(values) for key, values in scoped.items()}
        scopes[months] = {
            "cutoff": cutoff,
            "values": scoped,
            "price_averages": price_averages,
            "strengths": strengths,
            "dong_keys": [
                key for key, meta in metadata.items()
                if meta["lawd_cd"] == target_meta["lawd_cd"] and meta["dong"] == target_meta["dong"] and key in scoped
            ],
            "province_keys": list(scoped),
            "city_keys": [
                key for key, meta in metadata.items()
                if city_label(meta["region_name"]) == target_city and key in scoped
            ],
        }
        return scopes[months]

    periods: list[dict] = []

    for months, label in definitions:
        exact = scope_data(months)
        scoped = exact["values"]
        target_values = scoped.get(target_key, {})
        target_trade_counts = monthly_trade_counts.get(target_key, {})
        target_average = _average(target_values.values())
        trend_basis_months = next(
            (window for window in fallback_windows[months] if scope_data(window)["strengths"].get(target_key) is not None),
            None,
        )
        trend_scope = scope_data(trend_basis_months) if trend_basis_months is not None else exact
        strengths = trend_scope["strengths"]
        target_strength = strengths.get(target_key)
        periods.append({
            "months": months,
            "label": label,
            "status": "ok" if target_values else "no_trade",
            "cutoff_month": exact["cutoff"],
            "latest_observation_month": max(target_values) if target_values else None,
            "observation_months": len(target_values),
            "trade_count": sum(count for month, count in target_trade_counts.items() if exact["cutoff"] <= month <= as_of_month),
            "average_exclusive_pyeong_manwon": round(target_average, 1) if target_average is not None else None,
            "dong_price_position": _rank(target_average, (exact["price_averages"][key] for key in exact["dong_keys"])),
            "province_price_position": _rank(target_average, (exact["price_averages"][key] for key in exact["province_keys"])),
            "trend_pct_per_month": round(target_strength, 3) if target_strength is not None else None,
            "trend_basis_months": trend_basis_months,
            "trend_basis_label": labels.get(trend_basis_months) if trend_basis_months is not None else None,
            "trend_fallback_used": trend_basis_months is not None and trend_basis_months != months,
            "trend_observation_months": len(trend_scope["values"].get(target_key, {})),
            "dong_trend_rank": _rank(target_strength, (strengths[key] for key in trend_scope["dong_keys"] if strengths.get(key) is not None)),
            "city_trend_rank": _rank(target_strength, (strengths[key] for key in trend_scope["city_keys"] if strengths.get(key) is not None)),
        })

    return {
        "as_of_month": as_of_month,
        "province_label": province,
        "city_label": target_city,
        "dong_label": target_meta.get("dong", ""),
        "periods": periods,
    }
