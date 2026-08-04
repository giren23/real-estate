from __future__ import annotations
import time
import xml.etree.ElementTree as ET
from pathlib import Path
import pandas as pd

from realestate.core.http import get_text
from realestate.core.settings import Settings

ALIASES = {
    "apt_name": ["aptNm", "아파트"],
    "dong": ["umdNm", "법정동"],
    "jibun": ["jibun", "지번"],
    "deal_amount": ["dealAmount", "거래금액"],
    "area_m2": ["excluUseAr", "전용면적"],
    "floor": ["floor", "층"],
    "deal_year": ["dealYear", "년"],
    "deal_month": ["dealMonth", "월"],
    "deal_day": ["dealDay", "일"],
    "build_year": ["buildYear", "건축년도"],
    "deal_type": ["dealingGbn", "거래유형"],
    "cancel_date": ["cdealDay", "해제사유발생일"],
    "registration_date": ["rgstDate", "등기일자"],
    "apt_dong": ["aptDong", "동"],
}

def pick(row: dict, names: list[str], default: str = "") -> str:
    for name in names:
        if row.get(name) is not None:
            return str(row[name]).strip()
    return default

def num(value: str) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0

def parse_trade_xml(xml_text: str, lawd_cd: str, region_name: str, deal_ym: str) -> pd.DataFrame:
    root = ET.fromstring(xml_text)
    code = root.findtext(".//resultCode")
    msg = root.findtext(".//resultMsg")
    if code and code not in {"00", "000"}:
        raise RuntimeError(f"국토부 API 오류 {code}: {msg}")

    rows = []
    for item in root.findall(".//item"):
        raw = {child.tag: (child.text or "").strip() for child in item}
        year = int(num(pick(raw, ALIASES["deal_year"])))
        month = int(num(pick(raw, ALIASES["deal_month"])))
        day = int(num(pick(raw, ALIASES["deal_day"])))
        price_manwon = int(num(pick(raw, ALIASES["deal_amount"])))
        area_m2 = num(pick(raw, ALIASES["area_m2"]))
        cancel_date = pick(raw, ALIASES["cancel_date"])
        if not (year and month and day and price_manwon and area_m2):
            continue

        pyeong = area_m2 / 3.305785
        rows.append({
            "lawd_cd": lawd_cd,
            "region_name": region_name,
            "deal_ym": deal_ym,
            "trade_date": f"{year:04d}-{month:02d}-{day:02d}",
            "apt_name": pick(raw, ALIASES["apt_name"]),
            "dong": pick(raw, ALIASES["dong"]),
            "jibun": pick(raw, ALIASES["jibun"]),
            "apt_dong": pick(raw, ALIASES["apt_dong"]),
            "area_m2": round(area_m2, 2),
            "area_pyeong": round(pyeong, 2),
            "floor": int(num(pick(raw, ALIASES["floor"]))),
            "build_year": int(num(pick(raw, ALIASES["build_year"]))),
            "price_manwon": price_manwon,
            "price_eok": round(price_manwon / 10000, 4),
            "price_per_m2_manwon": round(price_manwon / area_m2, 2),
            "price_per_pyeong_manwon": round(price_manwon / pyeong, 2),
            "deal_type": pick(raw, ALIASES["deal_type"]),
            "registration_date": pick(raw, ALIASES["registration_date"]),
            "cancelled": bool(cancel_date),
        })
    return pd.DataFrame(rows)

def fetch_trade_month(settings: Settings, lawd_cd: str, region_name: str, deal_ym: str) -> pd.DataFrame:
    if not settings.service_key:
        raise RuntimeError("MOLIT_SERVICE_KEY가 필요합니다.")
    xml_text = get_text(settings.trade_endpoint, {
        "serviceKey": settings.service_key,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ym,
        "pageNo": 1,
        "numOfRows": 9999,
    })
    return parse_trade_xml(xml_text, lawd_cd, region_name, deal_ym)

def collect_trades(settings: Settings, regions: pd.DataFrame, months: list[str], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(regions) * len(months)
    completed = 0
    failures: list[str] = []

    for _, region in regions.iterrows():
        lawd_cd = str(region["lawd_cd"]).zfill(5)
        region_name = str(region["region_name"])
        for ym in months:
            completed += 1
            target = output_dir / f"{lawd_cd}_{ym}.parquet"
            label = f"{region_name} ({lawd_cd}) {ym}"
            print(f"[START] [{completed}/{total}] {label}", flush=True)
            try:
                df = fetch_trade_month(settings, lawd_cd, region_name, ym)
                if not df.empty:
                    df = df[~df["cancelled"]].copy()
                df.to_parquet(target, index=False)
                print(f"[OK] [{completed}/{total}] {label}: {len(df):,}건", flush=True)
            except Exception as exc:
                error = f"{label}: {type(exc).__name__}: {exc}"
                failures.append(error)
                print(f"[ERROR] [{completed}/{total}] {error}", flush=True)
            finally:
                time.sleep(settings.request_delay_seconds)

    if failures:
        details = "\n".join(f"  - {failure}" for failure in failures)
        raise RuntimeError(
            f"국토부 실거래 수집 실패: {len(failures)}/{total}개 요청\n{details}"
        )
