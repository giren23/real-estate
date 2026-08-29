from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET

import pandas as pd

from realestate.core.http import HTTP_ATTEMPTS, get_text
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


def parse_trade_xml(
    xml_text: str,
    lawd_cd: str,
    region_name: str,
    deal_ym: str,
) -> pd.DataFrame:
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
        rows.append(
            {
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
            }
        )
    return pd.DataFrame(rows)


def fetch_trade_month_from_endpoint(
    settings: Settings,
    lawd_cd: str,
    region_name: str,
    deal_ym: str,
    endpoint: str,
) -> pd.DataFrame:
    if not settings.service_key:
        raise RuntimeError("MOLIT_SERVICE_KEY가 필요합니다.")
    xml_text = get_text(
        endpoint,
        {
            "serviceKey": settings.service_key,
            "LAWD_CD": lawd_cd,
            "DEAL_YMD": deal_ym,
            "pageNo": 1,
            "numOfRows": 9999,
        },
    )
    return parse_trade_xml(xml_text, lawd_cd, region_name, deal_ym)


def fetch_trade_month(
    settings: Settings,
    lawd_cd: str,
    region_name: str,
    deal_ym: str,
) -> pd.DataFrame:
    return fetch_trade_month_from_endpoint(
        settings,
        lawd_cd,
        region_name,
        deal_ym,
        settings.trade_endpoint,
    )


def _trade_methods(settings: Settings) -> list[tuple[str, str]]:
    methods = [("일반 실거래 API", settings.trade_endpoint)]
    fallback = str(getattr(settings, "trade_fallback_endpoint", "") or "").strip()
    if fallback and fallback != settings.trade_endpoint:
        methods.append(("상세 실거래 API", fallback))
    return methods


def _write_parquet_safely(frame: pd.DataFrame, target: Path) -> None:
    temporary = target.with_suffix(target.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(target)


def _collect_one(
    settings: Settings,
    index: int,
    total: int,
    lawd_cd: str,
    region_name: str,
    ym: str,
    output_dir: Path,
) -> dict:
    target = output_dir / f"{lawd_cd}_{ym}.parquet"
    label = f"{region_name} ({lawd_cd}) {ym}"
    errors: list[dict] = []
    print(f"[START] [{index}/{total}] {label}", flush=True)

    for method_name, endpoint in _trade_methods(settings):
        print(
            f"[TRY] [{index}/{total}] {label}: {method_name}, HTTP 최대 {HTTP_ATTEMPTS}회",
            flush=True,
        )
        try:
            if endpoint == settings.trade_endpoint:
                frame = fetch_trade_month(settings, lawd_cd, region_name, ym)
            else:
                frame = fetch_trade_month_from_endpoint(
                    settings,
                    lawd_cd,
                    region_name,
                    ym,
                    endpoint,
                )
            if not frame.empty:
                frame = frame[~frame["cancelled"]].copy()
            _write_parquet_safely(frame, target)
            print(
                f"[OK] [{index}/{total}] {label}: {len(frame):,}건 ({method_name})",
                flush=True,
            )
            return {
                "index": index,
                "status": "ok",
                "lawd_cd": lawd_cd,
                "region_name": region_name,
                "deal_ym": ym,
                "row_count": int(len(frame)),
                "method": method_name,
                "errors": errors,
            }
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            errors.append(
                {
                    "method": method_name,
                    "http_attempts": HTTP_ATTEMPTS,
                    "error": message[:1000],
                }
            )
            print(
                f"[WARN] [{index}/{total}] {label}: {method_name} 실패 - {message}",
                flush=True,
            )
            time.sleep(settings.request_delay_seconds)

    result = {
        "index": index,
        "lawd_cd": lawd_cd,
        "region_name": region_name,
        "deal_ym": ym,
        "row_count": None,
        "method": None,
        "errors": errors,
    }
    if target.exists():
        result["status"] = "cached_fallback"
        print(
            f"[CACHED] [{index}/{total}] {label}: 새 수집 실패, 기존 파일을 유지합니다.",
            flush=True,
        )
    else:
        result["status"] = "failed"
        print(
            f"[ERROR] [{index}/{total}] {label}: 사용 가능한 기존 파일도 없습니다.",
            flush=True,
        )
    return result


def _write_failure_report(
    report_path: Path | None,
    total: int,
    results: list[dict],
) -> dict:
    problems = [result for result in results if result["status"] != "ok"]
    failed_regions = sorted(
        {
            (result["lawd_cd"], result["region_name"])
            for result in problems
        }
    )
    report = {
        "status": "ok" if not problems else "partial_failure",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "request_count": total,
        "success_count": sum(result["status"] == "ok" for result in results),
        "cached_fallback_count": sum(
            result["status"] == "cached_fallback" for result in results
        ),
        "failure_count": sum(result["status"] == "failed" for result in results),
        "failed_request_count": len(problems),
        "failed_regions": [
            {"lawd_cd": code, "region_name": name}
            for code, name in failed_regions
        ],
        "problems": problems,
    }
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[REPORT] 수집 결과 보고서: {report_path}", flush=True)
    return report


def collect_trades(
    settings: Settings,
    regions: pd.DataFrame,
    months: list[str],
    output_dir: Path,
    failure_report: Path | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(regions) * len(months)
    tasks: list[tuple[int, str, str, str]] = []
    for _, region in regions.iterrows():
        lawd_cd = str(region["lawd_cd"]).zfill(5)
        region_name = str(region["region_name"])
        for ym in months:
            tasks.append((len(tasks) + 1, lawd_cd, region_name, ym))

    if not tasks:
        _write_failure_report(failure_report, 0, [])
        raise RuntimeError("수집할 지역 또는 월이 없습니다.")

    worker_count = min(3, total)
    results: list[dict] = []
    print(
        f"[COLLECT] 총 {total:,}개 요청, {len(regions):,}개 지역, "
        f"{len(months):,}개월, 동시 요청 {worker_count}개",
        flush=True,
    )
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(
                _collect_one,
                settings,
                index,
                total,
                lawd_cd,
                region_name,
                ym,
                output_dir,
            )
            for index, lawd_cd, region_name, ym in tasks
        ]
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda result: result["index"])
    report = _write_failure_report(failure_report, total, results)
    if report["failed_request_count"]:
        details = "\n".join(
            f"  - {item['region_name']} ({item['lawd_cd']}) {item['deal_ym']}: "
            f"{item['status']}"
            for item in report["problems"]
        )
        raise RuntimeError(
            "국토부 실거래 갱신 일부 실패: "
            f"{report['failed_request_count']}/{total}개 요청\n{details}"
        )

    print(f"[DONE] 실거래 갱신 {total:,}개 요청 모두 완료", flush=True)
