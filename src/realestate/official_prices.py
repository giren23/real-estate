from __future__ import annotations

import sqlite3
import unicodedata
from pathlib import Path
from statistics import median


def normalize(value: object) -> str:
    return "".join(character for character in unicodedata.normalize("NFKC", str(value or "")).lower() if character.isalnum())


def normalize_unit(value: object, suffix: str) -> str:
    normalized = normalize(value)
    return normalized[:-len(suffix)] if suffix and normalized.endswith(suffix) else normalized


class OfficialPriceStore:
    """Local-only index of the Ministry of Land unit-level apartment price file."""

    def __init__(self, path: Path):
        self.path = path

    @property
    def available(self) -> bool:
        return self.path.exists() and self.path.stat().st_size > 4096

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS official_prices (
                    year INTEGER NOT NULL,
                    address TEXT NOT NULL,
                    address_norm TEXT NOT NULL,
                    apt_name TEXT NOT NULL,
                    apt_norm TEXT NOT NULL,
                    building TEXT NOT NULL DEFAULT '',
                    unit TEXT NOT NULL DEFAULT '',
                    area_m2 REAL NOT NULL,
                    price_won INTEGER NOT NULL,
                    source_date TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(year,address_norm,apt_norm,building,unit,area_m2)
                );
                CREATE INDEX IF NOT EXISTS idx_official_lookup
                ON official_prices(year,apt_norm,area_m2,building,unit);
                """
            )

    def lookup(self, *, apt_name: str, area_m2: float, year: int, address: str = "", building: str = "", unit: str = "") -> dict:
        if not self.available:
            return {"available": False, "message": "PC의 공식 공동주택가격 색인이 아직 준비되지 않았습니다."}
        apt_norm, address_norm = normalize(apt_name), normalize(address)
        building_norm, unit_norm = normalize_unit(building, "동"), normalize_unit(unit, "호")
        where = ["year=?", "apt_norm=?", "ABS(area_m2-?)<=0.25"]
        params: list[object] = [year, apt_norm, float(area_m2)]
        if address_norm:
            where.append("address_norm LIKE ?")
            params.append(f"%{address_norm}%")
        if building_norm:
            where.append("building=?")
            params.append(building_norm)
        if unit_norm:
            where.append("unit=?")
            params.append(unit_norm)
        sql = "SELECT address,apt_name,building,unit,area_m2,price_won,source_date FROM official_prices WHERE " + " AND ".join(where) + " ORDER BY building,unit LIMIT 5000"
        with sqlite3.connect(self.path) as db:
            rows = db.execute(sql, params).fetchall()
        if not rows and address_norm:
            return self.lookup(apt_name=apt_name, area_m2=area_m2, year=year, building=building, unit=unit)
        if not rows:
            return {"available": True, "matched": False, "message": "선택한 단지·평형의 공식 공시가격을 찾지 못했습니다."}
        values = sorted(int(row[5]) for row in rows)
        exact = bool(building_norm and unit_norm and len(rows) == 1)
        return {
            "available": True,
            "matched": True,
            "exact": exact,
            "year": year,
            "count": len(values),
            "price_won": values[0] if exact else int(median(values)),
            "min_won": values[0],
            "max_won": values[-1],
            "area_m2": rows[0][4],
            "building": rows[0][2] if exact else "",
            "unit": rows[0][3] if exact else "",
            "source_date": rows[0][6],
            "method": "동·호 정확값" if exact else "같은 단지·전용면적의 중앙값",
            "message": "동·호의 정확한 공식 공시가격입니다." if exact else "동·호가 없어 같은 단지·평형의 중앙값을 자동 적용했습니다. 범위와 동·호를 확인하세요.",
        }
