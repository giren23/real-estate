from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "web" / "content" / "reb_market_map.json"
LATEST_TRADES = ROOT / "data" / "public" / "latest_trades.json"
MAIN_URL = "https://www.reb.or.kr/r-one/portal/main/indexPage.do"
DATA_URL = "https://www.reb.or.kr/r-one/portal/main/searchRegionalStatusMap.do"
PRICE_PARAMS = {
    "statblId": "A_2024_00045",
    "dtacycleCd": "MM",
    "itmDatano": "100001",
    "clsDatano": "",
    "geoCd": "10",
    "dtadvsCd": "PR",
    "itmTag": "C",
}
VOLUME_PARAMS = {
    **PRICE_PARAMS,
    "statblId": "A_2024_00554",
    "dtadvsCd": "OD",
}


def normalize_metric(rows: list[dict], *, integer_values: bool = False) -> dict:
    if len(rows) < 100:
        raise ValueError(f"지역 수가 비정상적으로 적음: {len(rows)}")
    periods = {str(row.get("wrttimeIdtfrId") or "") for row in rows}
    periods = {period for period in periods if re.fullmatch(r"\d{6}", period)}
    if len(periods) != 1:
        raise ValueError(f"기준월이 하나가 아님: {sorted(periods)}")
    period = next(iter(periods))
    normalized = []
    for row in rows:
        name = str(row.get("viewItmNm") or "").strip()
        code = str(row.get("geoCd") or "").strip()
        raw_value = row.get("dtaVal")
        try:
            number = float(str(raw_value).replace(",", ""))
        except (TypeError, ValueError):
            continue
        if not name or not code:
            continue
        normalized.append({
            "data_no": int(row.get("clsDatano") or row.get("datano") or 0),
            "parent_data_no": int(row.get("parDatano") or 0),
            "code": code,
            "name": name,
            "value": int(round(number)) if integer_values else round(number, 4),
            "rank": int(row.get("odRnk") or 0),
        })
    country = next((row for row in normalized if row["code"] == "10" and row["parent_data_no"] == 0), None)
    provinces = [row for row in normalized if row["parent_data_no"] == 0 and row["code"] != "10"]
    children = [row for row in normalized if row["parent_data_no"] != 0]
    if not country or len(provinces) < 15 or len(children) < 80:
        raise ValueError(f"전국·시도·시군구 검증 실패: {bool(country)}/{len(provinces)}/{len(children)}")
    for province in provinces:
        prefixes = ("29", "46") if province["code"] == "12" else (province["code"],)
        province["cities"] = sorted(
            (row for row in children if len(row["code"]) > 2 and row["code"].startswith(prefixes)),
            key=lambda row: (row["value"], row["name"]), reverse=True,
        )
    grouped_city_count = sum(len(province["cities"]) for province in provinces)
    if grouped_city_count < 180:
        raise ValueError(f"시군구 묶음 수가 비정상적으로 적음: {grouped_city_count}")
    provinces.sort(key=lambda row: (row["value"], row["name"]), reverse=True)
    return {
        "period": f"{period[:4]}-{period[4:]}",
        "country": country,
        "provinces": provinces,
    }


def regional_rankings(metric: dict, limit: int = 20) -> dict:
    rows = []
    for province in metric["provinces"]:
        for city in province.get("cities", []):
            item = {
                "code": city["code"],
                "name": city["name"],
                "province": province["name"],
                "value": city["value"],
            }
            if city.get("area_84_price"):
                item["area_84_price"] = city["area_84_price"]
            rows.append(item)
    highest = sorted(rows, key=lambda row: (row["value"], row["province"], row["name"]), reverse=True)[:limit]
    lowest = sorted(rows, key=lambda row: (row["value"], row["province"], row["name"]))[:limit]
    return {"basis": "전국 시·군·구 공표지역", "top": highest, "bottom": lowest}


def calculate_area_84_prices(rows: list[dict]) -> dict[str, dict]:
    """전용 80~90㎡의 공개 최신 실거래 표본으로 시군구별 평균가격을 계산합니다."""
    candidates = []
    for row in rows:
        try:
            code = str(row.get("lawd_cd") or "").zfill(5)
            area = float(row.get("area_m2") or 0)
            price = float(row.get("price_eok") or 0)
            trade_date = str(row.get("trade_date") or "")
        except (TypeError, ValueError):
            continue
        if not re.fullmatch(r"\d{5}", code) or not (80 <= area <= 90) or price <= 0:
            continue
        if row.get("cancelled") or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", trade_date):
            continue
        candidates.append((code, trade_date, price))
    if not candidates:
        return {}
    latest = max(datetime.strptime(row[1], "%Y-%m-%d") for row in candidates)
    cutoff = latest - timedelta(days=365)
    grouped: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for code, trade_date, price in candidates:
        if datetime.strptime(trade_date, "%Y-%m-%d") >= cutoff:
            grouped[code].append((trade_date, price))
    return {
        code: {
            "average_price_eok": round(sum(price for _, price in values) / len(values), 2),
            "trade_count": len(values),
            "period_start": min(date for date, _ in values),
            "period_end": max(date for date, _ in values),
        }
        for code, values in grouped.items()
    }


def aggregate_area_84_prices(values: list[dict]) -> dict | None:
    """거래 건수를 가중치로 사용해 하위 지역 실거래 평균을 상위 지역으로 합칩니다."""
    sample_count = sum(int(value.get("trade_count") or 0) for value in values)
    if not sample_count:
        return None
    return {
        "average_price_eok": round(
            sum(float(value["average_price_eok"]) * int(value["trade_count"]) for value in values) / sample_count,
            2,
        ),
        "trade_count": sample_count,
        "period_start": min(str(value["period_start"]) for value in values),
        "period_end": max(str(value["period_end"]) for value in values),
    }


def enrich_area_84_prices(payload: dict, rows: list[dict]) -> dict:
    prices = calculate_area_84_prices(rows)
    matched = 0
    country_samples = []
    for province in payload.get("provinces", []):
        province_samples = []
        for city in province.get("cities", []):
            value = prices.get(str(city.get("code") or "").zfill(5))
            city.pop("area_84_price", None)
            if value:
                city["area_84_price"] = value
                province_samples.append(value)
                matched += 1
        province.pop("area_84_price", None)
        province_average = aggregate_area_84_prices(province_samples)
        if province_average:
            province["area_84_price"] = province_average
            country_samples.append(province_average)
    payload.setdefault("country", {}).pop("area_84_price", None)
    country_average = aggregate_area_84_prices(country_samples)
    if country_average:
        payload["country"]["area_84_price"] = country_average
    for province in payload.get("transaction_volume", {}).get("provinces", []):
        province_samples = []
        for city in province.get("cities", []):
            value = prices.get(str(city.get("code") or "").zfill(5))
            city.pop("area_84_price", None)
            if value:
                city["area_84_price"] = value
                province_samples.append(value)
        province.pop("area_84_price", None)
        province_average = aggregate_area_84_prices(province_samples)
        if province_average:
            province["area_84_price"] = province_average
    payload["area_84_prices"] = {
        "label": "84㎡급 평균 실거래가격",
        "area_basis": "전용 80~90㎡",
        "calculation": "공개 최신 실거래 표본의 단순 평균",
        "window": "최신 거래일 기준 최근 1년",
        "matched_region_count": matched,
        "source": {"publisher": "국토교통부 실거래가 공개시스템", "url": "https://rt.molit.go.kr/"},
    }
    if payload.get("transaction_volume"):
        payload["rankings"] = {
            "price_change": regional_rankings(payload),
            "transaction_volume": regional_rankings(payload["transaction_volume"]),
        }
    return payload


def read_latest_trades() -> list[dict]:
    if not LATEST_TRADES.exists():
        return []
    payload = json.loads(LATEST_TRADES.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else []


def write_payload(payload: dict) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(OUTPUT)


def normalize_payload(price_rows: list[dict], collected_at: str, volume_rows: list[dict] | None = None) -> dict:
    price = normalize_metric(price_rows)
    payload = {
        "schema_version": 2 if volume_rows is not None else 1,
        "source": {
            "publisher": "한국부동산원 부동산통계정보시스템 R-ONE",
            "url": MAIN_URL,
            "stat_table_id": PRICE_PARAMS["statblId"],
            "statistic": "전국주택가격동향조사 아파트 매매가격지수 전월 대비 변동률",
        },
        "period": price["period"],
        "unit": "%",
        "collected_at": collected_at,
        "country": price["country"],
        "provinces": price["provinces"],
    }
    if volume_rows is not None:
        volume = normalize_metric(volume_rows, integer_values=True)
        payload["transaction_volume"] = {
            "source": {
                "publisher": "한국부동산원 부동산통계정보시스템 R-ONE",
                "url": MAIN_URL,
                "stat_table_id": VOLUME_PARAMS["statblId"],
                "statistic": "부동산거래현황 아파트 매매거래호수",
            },
            "period": volume["period"],
            "unit": "호",
            "country": volume["country"],
            "provinces": volume["provinces"],
        }
        payload["rankings"] = {
            "price_change": regional_rankings(price),
            "transaction_volume": regional_rankings(volume),
        }
    return payload


def fetch_rows(session: requests.Session, params: dict[str, str], label: str, headers: dict[str, str]) -> list[dict]:
    response = session.post(DATA_URL, data=params, timeout=25, headers={**headers, "Accept": "application/json"})
    response.raise_for_status()
    payload = json.loads(response.content.decode("utf-8"))
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError(f"R-ONE {label} 응답에 data 배열이 없음")
    return rows


def fetch_payload() -> dict:
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 KoreanRealEstatePublicStatistics/1.0", "Accept-Language": "ko-KR,ko;q=0.9"}
    session.get(MAIN_URL, timeout=25, headers=headers).raise_for_status()
    price_rows = fetch_rows(session, PRICE_PARAMS, "가격상승률", headers)
    volume_rows = fetch_rows(session, VOLUME_PARAMS, "아파트 매매거래호수", headers)
    return normalize_payload(price_rows, datetime.now().astimezone().isoformat(timespec="seconds"), volume_rows)


def snapshot_is_fresh(max_age_hours: int = 18) -> bool:
    if not OUTPUT.exists():
        return False
    try:
        payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
        collected_at = datetime.fromisoformat(str(payload["collected_at"]))
        has_volume = payload.get("schema_version", 0) >= 2 and bool(payload.get("transaction_volume"))
        return has_volume and datetime.now().astimezone() - collected_at < timedelta(hours=max_age_hours)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="한국부동산원 R-ONE 지역별 월간 가격상승률·매매량을 안전하게 갱신합니다.")
    parser.add_argument("--force", action="store_true", help="18시간 이내에 갱신했더라도 다시 확인")
    parser.add_argument("--local-prices-only", action="store_true", help="기존 R-ONE 파일의 84㎡급 실거래 평균만 다시 계산")
    args = parser.parse_args()
    if args.local_prices_only or (not args.force and snapshot_is_fresh()):
        if not OUTPUT.exists():
            raise SystemExit("84㎡급 가격을 결합할 R-ONE 스냅샷이 없습니다.")
        payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
    else:
        payload = fetch_payload()
    payload = enrich_area_84_prices(payload, read_latest_trades())
    write_payload(payload)
    price_city_count = sum(len(row["cities"]) for row in payload["provinces"])
    volume = payload["transaction_volume"]
    volume_city_count = sum(len(row["cities"]) for row in volume["provinces"])
    print(
        f"R-ONE 가격상승률·매매량 저장 완료: 가격 {payload['period']} 시군구 {price_city_count}곳, "
        f"매매량 {volume['period']} 시군구 {volume_city_count}곳, "
        f"84㎡급 평균가격 {payload['area_84_prices']['matched_region_count']}곳"
    )


if __name__ == "__main__":
    main()
