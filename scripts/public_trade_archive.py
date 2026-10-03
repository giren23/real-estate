"""Durable PC-off trade archive: compressed districts and lazy apartment buckets.

Seed from a read-only SQLite snapshot once; GitHub Actions then replaces only
successfully collected district/months. No database, key or private source ID
is published. All counts are recomputed from the files the browser can read.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BUCKETS = 16
TRADE_FIELDS = (
    "lawd_cd", "region_name", "dong", "jibun", "apt_name", "area_m2",
    "deal_ym", "trade_date", "apt_dong", "floor", "build_year", "price_manwon",
    "price_eok", "price_per_m2_manwon", "price_per_pyeong_manwon", "deal_type",
    "registration_date",
)


def read(path: Path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)


def write(path: Path, payload) -> dict:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    data = gzip.compress(raw, compresslevel=6, mtime=0) if path.suffix == ".gz" else raw
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_bytes() != data:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_bytes(data)
        temp.replace(path)
    return {"file": path.name, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def safe_file(shards: Path, name: str) -> Path:
    path = (shards / name).resolve()
    if not path.is_relative_to(shards.resolve()):
        raise ValueError("Archive path escapes the public shard directory")
    return path


def bucket_number(dong: str, name: str) -> int:
    return hashlib.sha256((dong + "\0" + name).encode()).digest()[0] % BUCKETS


def history_rows(payload: dict) -> list[dict]:
    apartments = payload.get("apartments", [])
    return [dict(zip(("lawd_cd", "region_name", "dong", "apt_name", "area_m2", "month", "median_price_eok", "trade_count"),
                     [*apartments[int(row[0])], *row[1:5]])) for row in payload.get("rows", [])]


def compact_history(rows: list[dict]) -> dict:
    apartments, ids, encoded = [], {}, []
    for row in sorted(rows, key=lambda r: (r["dong"], r["apt_name"], float(r["area_m2"]), r["month"])):
        key = tuple(str(row[k]) for k in ("lawd_cd", "region_name", "dong", "apt_name"))
        if key not in ids:
            ids[key] = len(apartments)
            apartments.append(list(key))
        encoded.append([ids[key], float(row["area_m2"]), str(row["month"]), float(row["median_price_eok"]), int(row["trade_count"])])
    return {"version": 2, "apartments": apartments, "rows": encoded}


def load_district(shards: Path, item: dict) -> tuple[list[dict], list[dict]]:
    payload = read(safe_file(shards, item["file"]))
    trades = []
    if "trade_buckets" in payload:
        for part in payload["trade_buckets"]:
            trades.extend(read(safe_file(shards, part["file"]))["rows"])
    else:
        trades = payload.get("trades", [])
    return history_rows(payload.get("history", {})), trades


def write_district(shards: Path, code: str, history: list[dict], trades: list[dict]) -> dict:
    buckets = [[] for _ in range(BUCKETS)]
    apartments = {(r["dong"], r["apt_name"]) for r in history}
    for row in trades:
        if str(row["lawd_cd"]) != code or not row.get("apt_name"):
            raise ValueError(f"Wrong district or apartment in {code}")
        clean = {k: row.get(k, "") for k in TRADE_FIELDS}
        buckets[bucket_number(str(row["dong"]), str(row["apt_name"]))].append(clean)
        apartments.add((str(row["dong"]), str(row["apt_name"])))
    parts = []
    for index, rows in enumerate(buckets):
        rows.sort(key=lambda r: (r["dong"], r["apt_name"], r["trade_date"], float(r["area_m2"]), r.get("floor") or 0))
        name = f"details/{code}/{index:02x}.json.gz"
        descriptor = write(shards / name, {"lawd_cd": code, "rows": rows})
        parts.append({**descriptor, "file": name, "rows": len(rows)})
    recent = sorted(trades, key=lambda r: r["trade_date"], reverse=True)[:500]
    payload = {"schema_version": 2, "lawd_cd": code, "history": compact_history(history),
               "trades": [{k: r.get(k, "") for k in TRADE_FIELDS} for r in recent], "trade_buckets": parts}
    descriptor = write(shards / f"{code}.json.gz", payload)
    return {**descriptor, "lawd_cd": code, "trade_rows": len(trades), "history_rows": len(history),
            "represented_trades": sum(int(r["trade_count"]) for r in history),
            "region_name": next((str(r["region_name"]) for r in history or trades), ""),
            "latest_date": max((str(r["trade_date"]) for r in trades), default=""),
            "first_month": min((str(r["month"]) for r in history), default=""),
            "apartments": [list(k) for k in sorted(apartments)]}


def finish(public: Path, items: list[dict], source: str, old_count: int) -> dict:
    count = sum(int(i["represented_trades"]) for i in items)
    if old_count and count < old_count * .98:
        raise ValueError(f"Archive loss guard: {old_count:,} -> {count:,}")
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest = {"schema_version": 2, "generated_at": stamp, "source": source,
                "latest_date": max(i.get("latest_date", "") for i in items),
                "trade_count": count, "detail_trade_count": sum(i["trade_rows"] for i in items),
                "trade_apartment_count": sum(len(i["apartments"]) for i in items), "districts": items}
    write(public / "shards/manifest.json", manifest)
    old_meta = read(public / "meta.json") if (public / "meta.json").exists() else {}
    write(public / "meta.json", {**old_meta, "status": "ok", "trade_count": count,
          "detail_trade_count": manifest["detail_trade_count"], "trade_apartment_count": manifest["trade_apartment_count"],
          "region_count": len(items), "latest_date": manifest["latest_date"], "updated_at": stamp,
          "first_date": min(i["first_month"] for i in items if i.get("first_month")) + "-01", "source": source})
    validate(public)
    return manifest


def history_key(r: dict) -> tuple:
    return (r["dong"], r["apt_name"], float(r["area_m2"]), r["month"])


def trade_key(r: dict) -> tuple:
    def normalized(k):
        value = str(r.get(k) or "").strip()
        return "" if k in ("jibun", "apt_dong") and value == "-" else value
    return tuple(str(round(float(r.get(k) or 0), 2)) if k == "area_m2" else normalized(k)
                 for k in ("dong", "apt_name", "jibun", "trade_date", "area_m2", "floor", "price_manwon", "apt_dong"))


def seed(public: Path, database: Path, baseline_ref: str | None = None) -> dict:
    old = (json.loads(subprocess.check_output(["git", "show", f"{baseline_ref}:data/public/shards/manifest.json"], cwd=ROOT))
           if baseline_ref else read(public / "shards/manifest.json"))
    previous = {r["lawd_cd"]: r for r in old["districts"]}
    db = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute("BEGIN")  # Stable read snapshot; never alter the live database.
        codes = sorted(set(previous) | {r[0] for r in db.execute("SELECT DISTINCT lawd_cd FROM monthly_history")})
        items = []
        for n, code in enumerate(codes, 1):
            old_history, old_trades = load_district(public / "shards", previous[code]) if code in previous else ([], [])
            local = [dict(r) for r in db.execute("SELECT * FROM monthly_history WHERE lawd_cd=?", (code,))]
            history = seed_history(old_history, local, old.get("latest_date", "")[:7])
            trades = [dict(r) for r in db.execute("SELECT " + ",".join(TRADE_FIELDS) + " FROM transactions WHERE lawd_cd=? ORDER BY id", (code,))]
            available = Counter(trade_key(r) for r in trades)
            for row in old_trades:
                key = trade_key(row)
                if available[key]:
                    available[key] -= 1
                else:
                    trades.append(row)
            items.append(write_district(public / "shards", code, history, trades))
            print(f"[{n}/{len(codes)}] {code}: {items[-1]['represented_trades']:,} represented, {len(trades):,} detail rows", flush=True)
        return finish(public, items, "github-compressed-archive", int(old["trade_count"]))
    finally:
        db.close()


def seed_history(previous: list[dict], local: list[dict], public_latest_month: str) -> list[dict]:
    # Choose the entire district/month, not individual apartment/area rows.
    # CSV and API area precision/name variants otherwise double-count sales.
    public_months = {r["month"] for r in previous}
    local_months = {r["month"] for r in local if r["month"] < public_latest_month or r["month"] not in public_months}
    return [r for r in previous if r["month"] not in local_months] + [r for r in local if r["month"] in local_months]


def update(public: Path, raw: Path) -> dict:
    import pandas as pd
    manifest = read(public / "shards/manifest.json")
    if manifest.get("schema_version") != 2:
        raise ValueError("Seed the full compressed archive before enabling incremental updates")
    items = {i["lawd_cd"]: i for i in manifest["districts"]}
    files = defaultdict(list)
    for path in sorted(raw.glob("*.parquet")):
        match = re.fullmatch(r"(\d{5})_(\d{6})\.parquet", path.name)
        if match:
            files[match[1]].append((match[2], path))
    if not files:
        raise ValueError("No successfully collected district/month files")
    recent = []
    replaced, empty = 0, 0
    for code, partitions in files.items():
        history, trades = load_district(public / "shards", items[code]) if code in items else ([], [])
        changed = False
        for ym, path in partitions:
            frame = pd.read_parquet(path)
            if not frame.empty and "cancelled" in frame:
                frame = frame[~frame["cancelled"].fillna(False)].copy()
            if frame.empty:
                empty += 1  # Never erase existing history on an empty response.
                continue
            if not frame["lawd_cd"].astype(str).eq(code).all() or not frame["trade_date"].str[:7].eq(f"{ym[:4]}-{ym[4:]}").all():
                raise ValueError(f"Mismatched partition: {path.name}")
            # Replace, do not append/dedupe by price/date: identical-looking
            # official transactions can be distinct sales of different units.
            month = f"{ym[:4]}-{ym[4:]}"
            history = [r for r in history if r["month"] != month]
            trades = [r for r in trades if r["trade_date"][:7] != month]
            records = json.loads(frame.to_json(orient="records", force_ascii=False))
            trades.extend(records)
            fresh = frame.assign(month=month).groupby(["lawd_cd", "region_name", "dong", "apt_name", "area_m2", "month"], as_index=False).agg(median_price_eok=("price_eok", "median"), trade_count=("price_eok", "size"))
            history.extend(json.loads(fresh.to_json(orient="records", force_ascii=False)))
            recent.extend(records)
            replaced += 1
            changed = True
        if changed:
            items[code] = write_district(public / "shards", code, history, trades)
    # Compatibility input for the regional price map; not the durable archive.
    if recent:
        write(public / "latest_trades.json", sorted(recent, key=lambda r: r["trade_date"], reverse=True)[:50000])
    result = finish(public, [items[c] for c in sorted(items)], "github-daily-api", int(manifest["trade_count"]))
    print(f"Daily merge: {replaced} non-empty and {empty} empty partitions; {result['trade_count']:,} retained", flush=True)
    return result


def validate(public: Path) -> dict:
    shards = public / "shards"
    manifest = read(shards / "manifest.json")
    represented = details = history_count = total_bytes = 0
    for item in manifest["districts"]:
        path = safe_file(shards, item["file"])
        payload = read(path)
        rows = payload["history"]["rows"]
        count = sum(int(r[4]) for r in rows)
        if count != item["represented_trades"] or len(rows) != item["history_rows"]:
            raise ValueError(f"History count mismatch: {item['lawd_cd']}")
        detail_count = 0
        for descriptor in [item, *payload["trade_buckets"]]:
            data = safe_file(shards, descriptor["file"]).read_bytes()
            if len(data) != descriptor["size_bytes"] or hashlib.sha256(data).hexdigest() != descriptor["sha256"]:
                raise ValueError(f"Archive integrity mismatch: {descriptor['file']}")
            if len(data) >= 50 * 1024 * 1024:
                raise ValueError("Shard exceeds the safe GitHub file budget")
            total_bytes += len(data)
            if descriptor is not item:
                bucket = json.loads(gzip.decompress(data))
                if len(bucket["rows"]) != descriptor["rows"] or bucket["lawd_cd"] != item["lawd_cd"]:
                    raise ValueError("Trade bucket count/district mismatch")
                detail_count += len(bucket["rows"])
        if detail_count != item["trade_rows"]:
            raise ValueError("District detail total mismatch")
        represented += count
        details += detail_count
        history_count += len(rows)
    if represented != manifest["trade_count"] or details != manifest["detail_trade_count"]:
        raise ValueError("Manifest aggregate does not match downloadable records")
    site_bytes = sum(p.stat().st_size for p in public.rglob("*") if p.is_file())
    if site_bytes > 850 * 1024 * 1024:
        raise ValueError("Public data exceeds the reserved GitHub Pages budget")
    report = {"status": "verified", "trade_count": represented, "detail_trade_count": details,
              "history_rows": history_count, "districts": len(manifest["districts"]), "compressed_bytes": total_bytes,
              "public_bytes": site_bytes, "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    write(public / "archive_verification.json", report)
    print(json.dumps(report), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["seed", "update", "validate"])
    parser.add_argument("--public", type=Path, default=ROOT / "data/public")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--baseline-ref", help="Explicit git manifest revision when rebuilding an unpublished seed")
    parser.add_argument("--raw", type=Path, default=ROOT / "data/raw/trades")
    args = parser.parse_args()
    if args.command == "seed":
        if not args.database:
            parser.error("seed requires --database")
        seed(args.public, args.database, args.baseline_ref)
    elif args.command == "update":
        update(args.public, args.raw)
    else:
        validate(args.public)


if __name__ == "__main__":
    main()
