import json
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from scripts import public_trade_archive as archive


def trade(month="202609", day="01", **extra):
    return {"lawd_cd": "41135", "region_name": "경기도 성남분당구", "dong": "이매동",
            "apt_name": "이매촌한신", "area_m2": 84.9, "deal_ym": month,
            "trade_date": f"{month[:4]}-{month[4:]}-{day}", "jibun": "124",
            "price_manwon": 150000, "price_eok": 15.0, "floor": 10, "build_year": 1992,
            "apt_dong": "", "cancelled": False, **extra}


def history(month="2026-09", count=1, **extra):
    return {"lawd_cd": "41135", "region_name": "경기도 성남분당구", "dong": "이매동",
            "apt_name": "이매촌한신", "area_m2": 84.9, "month": month,
            "median_price_eok": 15.0, "trade_count": count, **extra}


def initial(tmp_path, histories=None, trades=None):
    public = tmp_path / "public"
    public.mkdir()
    item = archive.write_district(public / "shards", "41135", histories or [history()], trades or [trade()])
    archive.finish(public, [item], "test", 0)
    return public


def test_compressed_archive_preserves_all_records_and_counts(tmp_path):
    public = initial(tmp_path, [history(count=6001)], [trade()] * 6001)
    manifest = archive.read(public / "shards/manifest.json")
    h, t = archive.load_district(public / "shards", manifest["districts"][0])
    assert len(t) == 6001  # Not the former global 50,000/selected 5,000 export limit.
    assert h[0]["trade_count"] == 6001
    assert manifest["detail_trade_count"] == manifest["trade_count"] == 6001
    assert "source_no" not in t[0]
    assert archive.validate(public)["compressed_bytes"] < 100000


def test_hash_bucket_keeps_different_complexes_separate():
    import hashlib
    key = "이매동\0이매촌한신".encode()
    assert archive.bucket_number("이매동", "이매촌한신") == hashlib.sha256(key).digest()[0] % 16


def test_seed_replaces_whole_month_to_avoid_csv_api_precision_duplicates():
    old = [history("2010-01", 2, area_m2=84.97), history(count=1)]
    local = [history("2010-01", 2, area_m2=84.9735), history(count=2)]
    merged = archive.seed_history(old, local, "2026-09")
    assert sum(r["trade_count"] for r in merged) == 3
    assert len(merged) == 2
    assert archive.trade_key(trade(area_m2=84.9735)) == archive.trade_key(trade(area_m2=84.97))
    assert archive.trade_key(trade(apt_dong="-")) == archive.trade_key(trade(apt_dong=""))
    assert archive.trade_key(trade(apt_dong="101")) != archive.trade_key(trade(apt_dong="102"))


def test_daily_merge_preserves_old_history_and_replaces_refreshed_month(tmp_path):
    public = initial(tmp_path, [history("2010-01", 1), history(count=1)], [trade("201001"), trade()])
    raw = tmp_path / "raw"
    raw.mkdir()
    pd.DataFrame([trade(day="02"), trade(day="03")]).to_parquet(raw / "41135_202609.parquet", index=False)
    result = archive.update(public, raw)
    h, t = archive.load_district(public / "shards", result["districts"][0])
    assert result["trade_count"] == result["detail_trade_count"] == 3
    assert {r["month"]: r["trade_count"] for r in h} == {"2010-01": 1, "2026-09": 2}
    assert [r["trade_date"] for r in t] == ["2010-01-01", "2026-09-02", "2026-09-03"]
    assert archive.update(public, raw)["detail_trade_count"] == 3  # Idempotent rerun.


def test_failed_and_empty_months_do_not_erase_published_data(tmp_path):
    public = initial(tmp_path)
    raw = tmp_path / "raw"
    raw.mkdir()
    pd.DataFrame().to_parquet(raw / "41135_202609.parquet", index=False)
    result = archive.update(public, raw)
    assert result["trade_count"] == result["detail_trade_count"] == 1
    with pytest.raises(ValueError, match="No successfully"):
        archive.update(public, tmp_path / "absent")


def test_cancellation_is_reflected_when_a_nonempty_month_is_replaced(tmp_path):
    public = initial(tmp_path, [history("2010-01", 100), history(count=2)], [trade("201001")] * 100 + [trade(), trade(day="02")])
    raw = tmp_path / "raw"
    raw.mkdir()
    pd.DataFrame([trade(), trade(day="02", cancelled=True)]).to_parquet(raw / "41135_202609.parquet", index=False)
    assert archive.update(public, raw)["trade_count"] == 101


def test_same_price_floor_date_can_be_two_distinct_official_transactions(tmp_path):
    public = initial(tmp_path)
    raw = tmp_path / "raw"
    raw.mkdir()
    pd.DataFrame([trade(), trade()]).to_parquet(raw / "41135_202609.parquet", index=False)
    assert archive.update(public, raw)["detail_trade_count"] == 2


def test_validation_rejects_tampering_and_missing_parts(tmp_path):
    public = initial(tmp_path)
    manifest = archive.read(public / "shards/manifest.json")
    item = manifest["districts"][0]
    part = archive.read(public / "shards" / item["file"])["trade_buckets"][0]
    (public / "shards" / part["file"]).write_bytes(b"bad")
    with pytest.raises(ValueError, match="integrity"):
        archive.validate(public)


def test_loss_guard_and_path_traversal_rejected(tmp_path):
    public = initial(tmp_path)
    manifest = archive.read(public / "shards/manifest.json")
    with pytest.raises(ValueError, match="loss guard"):
        archive.finish(public, manifest["districts"], "bad", 1000)
    with pytest.raises(ValueError, match="escapes"):
        archive.safe_file(public / "shards", "../../private.db")


def test_partition_with_wrong_district_or_month_rejected(tmp_path):
    public = initial(tmp_path)
    raw = tmp_path / "raw"
    raw.mkdir()
    pd.DataFrame([trade(month="202608")]).to_parquet(raw / "41135_202609.parquet", index=False)
    with pytest.raises(ValueError, match="Mismatched"):
        archive.update(public, raw)


def test_pipeline_gates_data_on_trade_tests_not_unrelated_editorial_content():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/daily-update.yml").read_text(encoding="utf8")
    assert 'cron: "5 21 * * *"' in workflow
    assert "public_trade_archive.py update" in workflow
    assert "public_trade_archive.py validate" in workflow
    assert "tests/test_public_trade_archive.py" in workflow
    assert "python -m pytest -q 2>&1" not in workflow
    assert "web/content/news web/content/analysis" not in workflow


def test_browser_reads_manifest_paths_and_lazy_detail_buckets():
    source = (Path(__file__).resolve().parents[1] / "web/app.js").read_text(encoding="utf8")
    assert 'DecompressionStream("gzip")' in source
    assert "fetchPublicArchiveFile(descriptor)" in source
    assert "publicGroupTrades(group,payload)" in source
    assert 'digest[0]%16' in source
    assert 'fetchJson("data/shards/manifest.json?updated="+Date.now())' in source
    assert 'next.generated_at!==publicShardManifest.generated_at' in source
