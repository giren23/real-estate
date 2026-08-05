from __future__ import annotations

import argparse
import csv
import io
import json
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from realestate.analysis.metrics import apartment_metrics


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "data/public"
RTMS_PAGE = "https://rt.molit.go.kr/pt/xls/xls.do"
RTMS_CSV = "https://rt.molit.go.kr/pt/xls/ptXlsCSVDown.do"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "Chrome/136.0.0.0 Safari/537.36"
)


def yearly_ranges(start: date, end: date) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        range_end = min(date(cursor.year, 12, 31), end)
        ranges.append((cursor, range_end))
        cursor = date(cursor.year + 1, 1, 1)
    return ranges


def download_csv(
    session: requests.Session,
    start: date,
    end: date,
    *,
    sido_code: str,
    lawd_cd: str,
    emd_code: str,
    sido_name: str,
    sgg_name: str,
    emd_name: str,
) -> str:
    payload = {
        "srhThingNo": "A",
        "srhDelngSecd": "1",
        "srhAddrGbn": "1",
        "srhLfstsSecd": "1",
        "srhFromDt": start.isoformat(),
        "srhToDt": end.isoformat(),
        "srhNewRonSecd": "",
        "srhSidoCd": sido_code,
        "srhSggCd": lawd_cd,
        "srhEmdCd": emd_code,
        "srhLoadCd": "",
        "srhHsmpCd": "",
        "srhArea": "",
        "srhLrArea": "",
        "srhFromAmount": "",
        "srhToAmount": "",
        "sidoNm": sido_name,
        "sggNm": sgg_name,
        "emdNm": emd_name,
        "loadNm": "전체",
        "areaNm": "전체",
        "hsmpNm": "전체",
    }
    response = session.post(RTMS_CSV, data=payload, timeout=60)
    response.raise_for_status()
    if response.content.lstrip().startswith(b"<"):
        raise RuntimeError(f"RTMS CSV download returned HTML for {start}..{end}")
    return response.content.decode("cp949")


def parse_trades(text: str, *, lawd_cd: str, region_name: str, emd_name: str) -> list[dict]:
    lines = text.splitlines()
    try:
        header_index = next(i for i, line in enumerate(lines) if "거래금액(만원)" in line)
    except StopIteration as exc:
        raise RuntimeError("RTMS CSV header was not found") from exc

    rows: list[dict] = []
    for row in csv.DictReader(io.StringIO("\n".join(lines[header_index:]))):
        if (row.get("해제사유발생일") or "").strip() not in {"", "-"}:
            continue
        deal_ym = (row.get("계약년월") or "").strip()
        apt_name = (row.get("단지명") or "").strip()
        if len(deal_ym) != 6 or not apt_name:
            continue
        day = int((row.get("계약일") or "0").strip())
        price_manwon = int((row.get("거래금액(만원)") or "0").replace(",", "").strip())
        area_m2 = float((row.get("전용면적(㎡)") or "0").strip())
        if day <= 0 or price_manwon <= 0 or area_m2 <= 0:
            continue
        area_pyeong = area_m2 / 3.3058
        floor_text = (row.get("층") or "").strip()
        year_text = (row.get("건축년도") or "").strip()
        rows.append(
            {
                "lawd_cd": lawd_cd,
                "region_name": region_name,
                "deal_ym": deal_ym,
                "trade_date": f"{deal_ym[:4]}-{deal_ym[4:]}-{day:02d}",
                "apt_name": apt_name,
                "dong": emd_name,
                "jibun": (row.get("번지") or "").strip(),
                "apt_dong": (row.get("동") or "").strip(),
                "area_m2": area_m2,
                "area_pyeong": round(area_pyeong, 1),
                "floor": int(floor_text) if floor_text else None,
                "build_year": int(year_text) if year_text else None,
                "price_manwon": price_manwon,
                "price_eok": price_manwon / 10000,
                "price_per_m2_manwon": round(price_manwon / area_m2, 2),
                "price_per_pyeong_manwon": round(price_manwon / area_pyeong, 2),
                "deal_type": (row.get("거래유형") or "").strip(),
                "registration_date": (row.get("등기일자") or "").strip(),
                "cancelled": False,
            }
        )
    return rows


def read_json(name: str, fallback):
    path = PUBLIC_DIR / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else fallback


def write_json(name: str, payload) -> None:
    (PUBLIC_DIR / name).write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def frame_records(frame: pd.DataFrame) -> list[dict]:
    return frame.where(pd.notna(frame), None).to_dict(orient="records")


def merge_public_data(trades: list[dict], *, lawd_cd: str, region_name: str, emd_name: str) -> None:
    frame = pd.DataFrame(trades).sort_values("trade_date")
    apartments = apartment_metrics(frame).sort_values("latest_trade_date", ascending=False)
    history = (
        frame.assign(month=frame["trade_date"].str[:7])
        .groupby(["lawd_cd", "region_name", "dong", "apt_name", "area_m2", "month"], as_index=False)
        .agg(median_price_eok=("price_eok", "median"), trade_count=("price_eok", "size"))
        .sort_values(["lawd_cd", "apt_name", "area_m2", "month"])
    )
    history["median_price_eok"] = history["median_price_eok"].round(4)

    def outside_target(row: dict) -> bool:
        return not (str(row.get("lawd_cd")) == lawd_cd and row.get("dong") == emd_name)

    merged_latest = [row for row in read_json("latest_trades.json", []) if outside_target(row)]
    merged_latest.extend(trades)
    merged_latest.sort(key=lambda row: row.get("trade_date", ""), reverse=True)
    write_json("latest_trades.json", merged_latest[:50000])

    merged_apartments = [row for row in read_json("apartments.json", []) if outside_target(row)]
    merged_apartments.extend(frame_records(apartments))
    merged_apartments.sort(key=lambda row: row.get("latest_trade_date", ""), reverse=True)
    write_json("apartments.json", merged_apartments)

    merged_history = [row for row in read_json("apartment_history.json", []) if outside_target(row)]
    merged_history.extend(frame_records(history))
    merged_history.sort(
        key=lambda row: (
            str(row.get("lawd_cd", "")),
            row.get("apt_name", ""),
            float(row.get("area_m2", 0)),
            row.get("month", ""),
        )
    )
    write_json("apartment_history.json", merged_history)

    regions = read_json("regions.json", [])
    regions = [row for row in regions if str(row.get("lawd_cd")) != lawd_cd]
    regions.append({"lawd_cd": lawd_cd, "region_name": region_name})
    regions.sort(key=lambda row: row.get("region_name", ""))
    write_json("regions.json", regions)

    meta = read_json("meta.json", {})
    source_key = f"{lawd_cd}:{emd_name}"
    supplemental = meta.setdefault("supplemental_trade_counts", {})
    previous_count = int(supplemental.get(source_key, 0))
    previous_apartments = int(meta.setdefault("supplemental_apartment_counts", {}).get(source_key, 0))
    apartment_count = int(frame[["lawd_cd", "dong", "apt_name"]].drop_duplicates().shape[0])
    meta["trade_count"] = int(meta.get("trade_count", 0)) - previous_count + len(frame)
    meta["trade_apartment_count"] = int(meta.get("trade_apartment_count", 0)) - previous_apartments + apartment_count
    meta["region_count"] = len(regions)
    meta["latest_date"] = max(str(meta.get("latest_date", "")), str(frame["trade_date"].max()))
    supplemental[source_key] = len(frame)
    meta["supplemental_apartment_counts"][source_key] = apartment_count
    meta["supplemental_source"] = RTMS_PAGE
    write_json("meta.json", meta)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import RTMS condition-search CSV history into public dashboard data")
    parser.add_argument("--lawd-cd", default="48123")
    parser.add_argument("--sido-code", default="48000")
    parser.add_argument("--sido-name", default="경상남도")
    parser.add_argument("--sgg-name", default="창원시 성산구")
    parser.add_argument("--emd-code", default="13600")
    parser.add_argument("--emd-name", default="신월동")
    parser.add_argument("--start", default="2006-01-01")
    parser.add_argument("--end", default=date.today().isoformat())
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Referer": RTMS_PAGE})
    session.get(RTMS_PAGE, timeout=30).raise_for_status()

    trades: list[dict] = []
    ranges = yearly_ranges(start, end)
    for index, (range_start, range_end) in enumerate(ranges, start=1):
        print(f"[DOWNLOAD] [{index}/{len(ranges)}] {args.emd_name} {range_start}..{range_end}", flush=True)
        text = download_csv(
            session,
            range_start,
            range_end,
            sido_code=args.sido_code,
            lawd_cd=args.lawd_cd,
            emd_code=args.emd_code,
            sido_name=args.sido_name,
            sgg_name=args.sgg_name,
            emd_name=args.emd_name,
        )
        batch = parse_trades(text, lawd_cd=args.lawd_cd, region_name=f"{args.sido_name} {args.sgg_name}", emd_name=args.emd_name)
        trades.extend(batch)
        print(f"[DONE] [{index}/{len(ranges)}] {len(batch)}건", flush=True)

    if not trades:
        raise RuntimeError(f"No official RTMS trades found for {args.sgg_name} {args.emd_name}")
    merge_public_data(trades, lawd_cd=args.lawd_cd, region_name=f"{args.sido_name} {args.sgg_name}", emd_name=args.emd_name)
    print(f"[COMPLETE] {args.sgg_name} {args.emd_name}: {len(trades)}건", flush=True)


if __name__ == "__main__":
    main()
