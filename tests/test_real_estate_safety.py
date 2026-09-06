from __future__ import annotations

import gzip
import json
import sqlite3
from pathlib import Path

import pytest

from realestate.local_store import LocalStore
from scripts.backup_real_estate_db import create_backup, database_facts
from scripts.export_real_estate_archive import export_archive


def trade(day: str, price: int = 100_000) -> dict:
    return {
        "lawd_cd": "11110", "region_name": "서울 종로구", "dong": "청운동", "jibun": "1",
        "apt_name": "안전아파트", "area_m2": 84.0, "deal_ym": day[:4] + day[5:7],
        "trade_date": day, "apt_dong": "101", "floor": 10, "build_year": 2020,
        "price_manwon": price, "price_eok": price / 10000, "deal_type": "중개거래", "registration_date": day,
    }


def test_empty_refresh_never_erases_existing_year(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    store.initialize()
    store.replace_region_year("11110", 2025, [trade("2025-01-01")])
    with pytest.raises(RuntimeError, match="빈 응답으로 교체하지 않음"):
        store.replace_region_year("11110", 2025, [])
    assert len(store.trades("11110", "청운동", "안전아파트")) == 1


def test_backup_is_verified_and_restore_source_is_immutable(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    store.initialize()
    store.replace_region_year("11110", 2025, [trade("2025-01-01")])
    payload = create_backup(tmp_path, "test")
    backup = tmp_path / "backups" / "real-estate" / payload["backup"]
    restored = tmp_path / "restored.sqlite3"
    with gzip.open(backup, "rb") as source, restored.open("wb") as target:
        target.write(source.read())
    assert payload["status"] == "verified"
    assert payload["transactions"] == 1
    assert database_facts(restored)["transactions"] == 1


def test_cloud_export_uses_content_hashes_and_district_partitions(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    store.initialize()
    store.replace_region_year("11110", 2025, [trade("2025-01-01")])
    manifest, path = export_archive(tmp_path)
    assert path.exists()
    assert manifest["trades"]["11110"]["rows"] == 1
    descriptor = manifest["trades"]["11110"]
    object_path = tmp_path / "data" / "local" / "cloud-archive" / descriptor["key"]
    with gzip.open(object_path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["scope"] == "district"
    assert payload["rows"][0]["apt_name"] == "안전아파트"
