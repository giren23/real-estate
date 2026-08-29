from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

from realestate.official_prices import OfficialPriceStore, normalize, normalize_unit


ALIASES = {
    "year": ("공시기준", "기준년도", "공시년도", "year"),
    "address": ("소재지", "주소", "도로명주소", "법정동명", "address"),
    "apt_name": ("단지명", "공동주택명", "아파트명", "aphusNm"),
    "building": ("동명", "동", "building"),
    "unit": ("호명", "호", "unit"),
    "area_m2": ("전용면적(㎡)", "전용면적", "공동주택명전용면적(㎡)", "prvuseAr"),
    "price_won": ("공동주택가격(원)", "공동주택가격", "공시가격", "pblntfPc"),
    "source_date": ("데이터기준일자", "기준일", "source_date"),
}


def field(row: dict[str, str], name: str, default: str = "") -> str:
    normalized = {normalize(key): value for key, value in row.items()}
    for alias in ALIASES[name]:
        value = normalized.get(normalize(alias))
        if value not in (None, ""):
            return str(value).strip()
    return default


def number(value: str) -> float:
    return float(str(value).replace(",", "").replace("㎡", "").replace("원", "").strip())


def import_csv(source: Path, database: Path, default_year: int | None = None) -> int:
    store = OfficialPriceStore(database)
    store.initialize()
    inserted = 0
    with source.open("r", encoding="utf-8-sig", newline="") as handle, sqlite3.connect(database) as db:
        reader = csv.DictReader(handle)
        batch = []
        for row in reader:
            try:
                year_text = field(row, "year", str(default_year or ""))[:4]
                address, apt_name = field(row, "address"), field(row, "apt_name")
                area_m2, price_won = number(field(row, "area_m2")), int(number(field(row, "price_won")))
                if not year_text or not apt_name or area_m2 <= 0 or price_won <= 0:
                    continue
                building, unit = normalize_unit(field(row, "building"), "동"), normalize_unit(field(row, "unit"), "호")
                batch.append((int(year_text), address, normalize(address), apt_name, normalize(apt_name), building, unit, area_m2, price_won, field(row, "source_date")))
            except (ValueError, TypeError):
                continue
            if len(batch) >= 10000:
                db.executemany("INSERT OR REPLACE INTO official_prices VALUES (?,?,?,?,?,?,?,?,?,?)", batch)
                inserted += len(batch)
                batch.clear()
        if batch:
            db.executemany("INSERT OR REPLACE INTO official_prices VALUES (?,?,?,?,?,?,?,?,?,?)", batch)
            inserted += len(batch)
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="공식 공동주택가격 CSV를 PC 전용 SQLite 검색 색인으로 변환합니다.")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--year", type=int)
    parser.add_argument("--database", type=Path, default=Path("data/local/official_prices.sqlite3"))
    args = parser.parse_args()
    print(f"{import_csv(args.csv, args.database, args.year):,}건 색인 완료: {args.database}")


if __name__ == "__main__":
    main()
