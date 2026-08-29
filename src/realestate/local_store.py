from __future__ import annotations

import json
import re
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Iterable


TARGET_CODE_PREFIXES = ("11", "41", "26", "4311", "4812")


def is_target_lawd(value: str) -> bool:
    code = str(value or "").replace(".0", "").zfill(5)[:5]
    return any(code.startswith(prefix) for prefix in TARGET_CODE_PREFIXES)


def normalize_name(value: str) -> str:
    text = re.sub(r"\s+", "", str(value or "").lower())
    text = re.sub(r"[()（）\[\]{}·.,\-_/]", "", text)
    return re.sub(r"(아파트|apt)$", "", text)


def name_score(left: str, right: str) -> int:
    a, b = normalize_name(left), normalize_name(right)
    if not a or not b:
        return 0
    if a == b:
        return 1000
    shorter, longer = sorted((a, b), key=len)
    if len(shorter) >= 4 and shorter in longer:
        return 800 + len(shorter)
    left_core = re.sub(r"\d+(차|단지)?$", "", a)
    right_core = re.sub(r"\d+(차|단지)?$", "", b)
    if len(left_core) >= 4 and left_core == right_core:
        return 700 + len(left_core)
    return 0


class LocalStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.local_dir = self.root / "data" / "local"
        self.local_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.local_dir / "real_estate.sqlite3"
        self.catalog_path = self.local_dir / "catalog.json"
        self.status_path = self.local_dir / "status.json"

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=60)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=60000")
        return connection

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS complexes (
                    complex_code TEXT PRIMARY KEY,
                    apt_name TEXT NOT NULL,
                    sido TEXT NOT NULL DEFAULT '',
                    sigungu TEXT NOT NULL DEFAULT '',
                    dong TEXT NOT NULL DEFAULT '',
                    bjd_code TEXT NOT NULL DEFAULT '',
                    lawd_cd TEXT NOT NULL,
                    region_name TEXT NOT NULL DEFAULT '',
                    address TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_complexes_place
                    ON complexes(lawd_cd, dong, apt_name);

                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY,
                    lawd_cd TEXT NOT NULL,
                    region_name TEXT NOT NULL,
                    dong TEXT NOT NULL,
                    jibun TEXT NOT NULL DEFAULT '',
                    apt_name TEXT NOT NULL,
                    area_m2 REAL NOT NULL,
                    deal_ym TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    apt_dong TEXT NOT NULL DEFAULT '',
                    floor INTEGER,
                    build_year INTEGER,
                    price_manwon INTEGER NOT NULL,
                    price_eok REAL NOT NULL,
                    price_per_m2_manwon REAL,
                    price_per_pyeong_manwon REAL,
                    deal_type TEXT NOT NULL DEFAULT '',
                    registration_date TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'official_rtms_csv',
                    source_no TEXT NOT NULL DEFAULT '',
                    UNIQUE(lawd_cd, dong, jibun, apt_name, area_m2, trade_date,
                           price_manwon, floor, apt_dong, source_no)
                );
                CREATE INDEX IF NOT EXISTS idx_transactions_group
                    ON transactions(lawd_cd, dong, apt_name, area_m2, trade_date);
                CREATE INDEX IF NOT EXISTS idx_transactions_year
                    ON transactions(lawd_cd, deal_ym);

                CREATE TABLE IF NOT EXISTS monthly_history (
                    lawd_cd TEXT NOT NULL,
                    region_name TEXT NOT NULL,
                    dong TEXT NOT NULL,
                    apt_name TEXT NOT NULL,
                    area_m2 REAL NOT NULL,
                    month TEXT NOT NULL,
                    median_price_eok REAL NOT NULL,
                    trade_count INTEGER NOT NULL,
                    PRIMARY KEY(lawd_cd, dong, apt_name, area_m2, month)
                );
                CREATE INDEX IF NOT EXISTS idx_history_group
                    ON monthly_history(lawd_cd, dong, apt_name, area_m2, month);

                CREATE TABLE IF NOT EXISTS collection_status (
                    lawd_cd TEXT NOT NULL,
                    year INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    row_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    message TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(lawd_cd, year)
                );
                """
            )

    def import_complexes(self, csv_path: Path) -> int:
        import csv

        rows: list[tuple] = []
        with Path(csv_path).open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                bjd_code = str(row.get("bjd_code", "")).replace(".0", "").zfill(10)
                lawd_cd = bjd_code[:5]
                if not is_target_lawd(lawd_cd):
                    continue
                rows.append(
                    (
                        row.get("complex_code") or f"dir-{bjd_code}-{normalize_name(row.get('apt_name', ''))}",
                        row.get("apt_name", "").strip(),
                        row.get("sido", "").strip(),
                        row.get("sigungu", "").strip(),
                        row.get("dong", "").strip(),
                        bjd_code,
                        lawd_cd,
                        row.get("region_name", "").strip(),
                        row.get("address", "").strip(),
                    )
                )
        with self.connect() as db:
            db.executemany(
                """INSERT INTO complexes
                   (complex_code, apt_name, sido, sigungu, dong, bjd_code, lawd_cd, region_name, address)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(complex_code) DO UPDATE SET
                     apt_name=excluded.apt_name, sido=excluded.sido, sigungu=excluded.sigungu,
                     dong=excluded.dong, bjd_code=excluded.bjd_code, lawd_cd=excluded.lawd_cd,
                     region_name=excluded.region_name, address=excluded.address""",
                rows,
            )
        return len(rows)

    def import_seed_public_data(self, public_dir: Path) -> dict[str, int]:
        history_path = Path(public_dir) / "apartment_history.json"
        latest_path = Path(public_dir) / "latest_trades.json"
        history_count = trade_count = 0
        with self.connect() as db:
            if history_path.exists() and not db.execute("SELECT 1 FROM monthly_history LIMIT 1").fetchone():
                payload = json.loads(history_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict) and payload.get("version") == 2:
                    apartments = payload.get("apartments", [])
                    records = (
                        (
                            str(apartments[int(row[0])][0]).zfill(5),
                            apartments[int(row[0])][1],
                            apartments[int(row[0])][2],
                            apartments[int(row[0])][3],
                            float(row[1]),
                            str(row[2]),
                            float(row[3]),
                            int(row[4]),
                        )
                        for row in payload.get("rows", [])
                        if is_target_lawd(str(apartments[int(row[0])][0]))
                    )
                else:
                    records = (
                        (
                            str(row.get("lawd_cd", "")).zfill(5), row.get("region_name", ""),
                            row.get("dong", ""), row.get("apt_name", ""), float(row.get("area_m2", 0)),
                            row.get("month", ""), float(row.get("median_price_eok", 0)), int(row.get("trade_count", 0)),
                        )
                        for row in (payload if isinstance(payload, list) else [])
                        if is_target_lawd(str(row.get("lawd_cd", "")))
                    )
                cursor = db.executemany(
                    """INSERT OR IGNORE INTO monthly_history
                       (lawd_cd, region_name, dong, apt_name, area_m2, month, median_price_eok, trade_count)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    records,
                )
                history_count = max(0, cursor.rowcount)

            if latest_path.exists() and not db.execute("SELECT 1 FROM transactions LIMIT 1").fetchone():
                rows = json.loads(latest_path.read_text(encoding="utf-8"))
                records = [self._trade_tuple(row, source="github_seed") for row in rows if not row.get("cancelled") and is_target_lawd(str(row.get("lawd_cd", "")))]
                cursor = db.executemany(
                    """INSERT OR IGNORE INTO transactions
                       (lawd_cd, region_name, dong, jibun, apt_name, area_m2, deal_ym, trade_date,
                        apt_dong, floor, build_year, price_manwon, price_eok, price_per_m2_manwon,
                        price_per_pyeong_manwon, deal_type, registration_date, source)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    records,
                )
                trade_count = max(0, cursor.rowcount)
        return {"history": history_count, "trades": trade_count}

    @staticmethod
    def _trade_tuple(row: dict, source: str = "official_rtms_csv") -> tuple:
        area = float(row.get("area_m2") or 0)
        price = int(row.get("price_manwon") or round(float(row.get("price_eok") or 0) * 10000))
        pyeong = area / 3.3058 if area else 0
        return (
            str(row.get("lawd_cd", "")).zfill(5)[:5], row.get("region_name", ""), row.get("dong", ""),
            row.get("jibun", ""), row.get("apt_name", ""), area, row.get("deal_ym") or str(row.get("trade_date", ""))[:7].replace("-", ""),
            row.get("trade_date", ""), row.get("apt_dong", ""), row.get("floor"), row.get("build_year"), price,
            price / 10000, round(price / area, 2) if area else None, round(price / pyeong, 2) if pyeong else None,
            row.get("deal_type", ""), row.get("registration_date", ""), source,
        )

    def replace_region_year(self, lawd_cd: str, year: int, trades: Iterable[dict]) -> int:
        rows = list(trades)
        prefix = str(year)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM transactions WHERE lawd_cd=? AND deal_ym LIKE ?", (lawd_cd, f"{prefix}%"))
            db.executemany(
                """INSERT OR IGNORE INTO transactions
                   (lawd_cd, region_name, dong, jibun, apt_name, area_m2, deal_ym, trade_date,
                    apt_dong, floor, build_year, price_manwon, price_eok, price_per_m2_manwon,
                    price_per_pyeong_manwon, deal_type, registration_date, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [self._trade_tuple(row) for row in rows],
            )
            db.execute("DELETE FROM monthly_history WHERE lawd_cd=? AND month LIKE ?", (lawd_cd, f"{prefix}-%"))
            grouped: dict[tuple, list[float]] = defaultdict(list)
            for row in rows:
                key = (lawd_cd, row["region_name"], row["dong"], row["apt_name"], float(row["area_m2"]), row["trade_date"][:7])
                grouped[key].append(float(row["price_eok"]))
            db.executemany(
                """INSERT INTO monthly_history
                   (lawd_cd, region_name, dong, apt_name, area_m2, month, median_price_eok, trade_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [(*key, round(statistics.median(values), 4), len(values)) for key, values in grouped.items()],
            )
        return len(rows)

    def status(self, lawd_cd: str, year: int, status: str, attempts: int, row_count: int, updated_at: str, message: str = "") -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO collection_status(lawd_cd, year, status, attempts, row_count, updated_at, message)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(lawd_cd, year) DO UPDATE SET status=excluded.status,
                     attempts=excluded.attempts, row_count=excluded.row_count,
                     updated_at=excluded.updated_at, message=excluded.message""",
                (lawd_cd, year, status, attempts, row_count, updated_at, message[:1000]),
            )

    def completed(self, lawd_cd: str, year: int) -> bool:
        with self.connect() as db:
            row = db.execute(
                "SELECT status FROM collection_status WHERE lawd_cd=? AND year=?", (lawd_cd, year)
            ).fetchone()
        return bool(row and row["status"] == "ok")

    def build_catalog(self) -> dict:
        with self.connect() as db:
            directories = [dict(row) for row in db.execute("SELECT * FROM complexes ORDER BY region_name, dong, apt_name")]
            trade_groups = [dict(row) for row in db.execute(
                """SELECT h.lawd_cd, h.region_name, h.dong, h.apt_name,
                          GROUP_CONCAT(DISTINCT h.area_m2) AS areas,
                          MAX(h.month) AS latest_month,
                          (SELECT h2.median_price_eok FROM monthly_history h2
                           WHERE h2.lawd_cd=h.lawd_cd AND h2.dong=h.dong AND h2.apt_name=h.apt_name
                           ORDER BY h2.month DESC, h2.trade_count DESC, h2.area_m2 LIMIT 1) AS latest_price,
                          (SELECT h2.area_m2 FROM monthly_history h2
                           WHERE h2.lawd_cd=h.lawd_cd AND h2.dong=h.dong AND h2.apt_name=h.apt_name
                           ORDER BY h2.month DESC, h2.trade_count DESC, h2.area_m2 LIMIT 1) AS latest_area,
                          (SELECT t.build_year FROM transactions t
                           WHERE t.lawd_cd=h.lawd_cd AND t.dong=h.dong AND t.apt_name=h.apt_name
                             AND t.build_year IS NOT NULL AND t.build_year > 0
                           ORDER BY t.trade_date DESC LIMIT 1) AS build_year
                   FROM monthly_history h
                   GROUP BY h.lawd_cd, h.dong, h.apt_name"""
            )]
            completed_rows = [dict(row) for row in db.execute(
                "SELECT lawd_cd, COUNT(*) years FROM collection_status WHERE status='ok' GROUP BY lawd_cd"
            )]
            trade_count = int(db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])
            history_trade_count = int(db.execute("SELECT COALESCE(SUM(trade_count),0) FROM monthly_history").fetchone()[0])

        completed = {row["lawd_cd"]: int(row["years"]) for row in completed_rows}
        by_place: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for item in directories:
            by_place[(item["lawd_cd"], normalize_name(item["dong"]))].append(item)
        used: set[str] = set()
        catalog: list[dict] = []
        for row in trade_groups:
            candidates = by_place.get((row["lawd_cd"], normalize_name(row["dong"])), [])
            match = max(candidates, key=lambda item: name_score(row["apt_name"], item["apt_name"]), default=None)
            if match and name_score(row["apt_name"], match["apt_name"]) < 700:
                match = None
            if match:
                used.add(match["complex_code"])
            areas = sorted({round(float(value), 4) for value in str(row.get("areas") or "").split(",") if value})
            catalog.append({
                "key": f"trade|{row['lawd_cd']}|{row['dong']}|{row['apt_name']}",
                "lawd_cd": row["lawd_cd"], "region_name": row["region_name"], "dong": row["dong"],
                "apt_name": row["apt_name"], "directory_name": match["apt_name"] if match else "",
                "search_names": list(dict.fromkeys(filter(None, [row["apt_name"], match["apt_name"] if match else ""]))),
                "jibun": "", "address": match["address"] if match else f"{row['region_name']} {row['dong']}",
                "areas": areas, "latest": {
                    "trade_date": row["latest_month"], "price_eok": row["latest_price"],
                    "area_m2": row["latest_area"],
                },
                "data_apt_name": row["apt_name"], "coverage_years": completed.get(row["lawd_cd"], 0),
                "build_year": row.get("build_year"),
            })
        for row in directories:
            if row["complex_code"] in used:
                continue
            catalog.append({
                "key": f"complex|{row['complex_code']}", "lawd_cd": row["lawd_cd"], "region_name": row["region_name"],
                "dong": row["dong"], "apt_name": row["apt_name"], "directory_name": row["apt_name"],
                "search_names": [row["apt_name"]], "jibun": "", "address": row["address"], "areas": [], "latest": None,
                "data_apt_name": "", "coverage_years": completed.get(row["lawd_cd"], 0),
                "build_year": None,
            })
        catalog.sort(key=lambda row: (row.get("latest") or {}).get("trade_date", ""), reverse=True)
        payload = {
            "version": 1,
            "catalog": catalog,
            "meta": {
                "transaction_rows": trade_count,
                "represented_trades": max(trade_count, history_trade_count),
                "complex_count": len(catalog),
                "directory_count": len(directories),
                "districts_complete": sum(1 for count in completed.values() if count >= 20),
                "district_years_complete": sum(completed.values()),
            },
        }
        temporary = self.catalog_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temporary.replace(self.catalog_path)
        return payload

    def history(self, lawd_cd: str, dong: str, apt_name: str) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                """SELECT lawd_cd, region_name, dong, apt_name, area_m2, month, median_price_eok, trade_count
                   FROM monthly_history WHERE lawd_cd=? AND dong=? AND apt_name=?
                   ORDER BY area_m2, month""", (lawd_cd, dong, apt_name)
            )]

    def trades(self, lawd_cd: str, dong: str, apt_name: str, area_m2: float | None = None, limit: int = 1000) -> list[dict]:
        sql = "SELECT * FROM transactions WHERE lawd_cd=? AND dong=? AND apt_name=?"
        params: list = [lawd_cd, dong, apt_name]
        if area_m2 is not None:
            sql += " AND ABS(area_m2-?) < 0.001"
            params.append(area_m2)
        sql += " ORDER BY trade_date DESC LIMIT ?"
        params.append(min(max(limit, 1), 5000))
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, params)]
