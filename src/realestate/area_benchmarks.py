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
        complexes[key] = row
        dong_values[row["dong_key"]].append(value)
        city_values[row["city_label"]].append(value)

    return {
        "complexes": complexes,
        "dongs": {key: _reference(values) for key, values in dong_values.items()},
        "cities": {key: _reference(values) for key, values in city_values.items()},
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
        dong = _position(value, index["dongs"].get(row["dong_key"], {}))
        city = _position(value, index["cities"].get(row["city_label"], {}))
        if dong["count"] >= 2:
            dong["top_percent"] = round(sum(other >= value for other in dong_values) / dong["count"] * 100, 1)
        if city["count"] >= 2:
            city["top_percent"] = round(sum(other >= value for other in city_values) / city["count"] * 100, 1)
        result.append({
            **{key: value for key, value in row.items() if key not in {"dong_key"}},
            "dong_reference": dong,
            "city_reference": city,
        })
    return result
