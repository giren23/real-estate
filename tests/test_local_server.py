from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi import HTTPException

from realestate.local_collect import DailyQuotaError, OfficialCsvCollector, Region, _year_batches, parse_rtms_csv, region_priority
from realestate.local_store import LocalStore, is_target_lawd, name_score
from realestate.official_prices import OfficialPriceStore, normalize
from realestate import server


ROOT = Path(__file__).resolve().parents[1]


def test_parse_official_csv_and_skip_cancelled() -> None:
    text = """공식 자료\nNO,시군구,번지,본번,부번,단지명,전용면적(㎡),계약년월,계약일,거래금액(만원),동,층,건축년도,해제사유발생일,거래유형,등기일자
1,서울특별시 성동구 옥수동,1-1,1,1,극동그린,84.32,202501,3,"120,000",101,10,1997,,중개거래,2025-02-01
2,서울특별시 성동구 옥수동,1-1,1,1,극동그린,114.32,202501,4,"150,000",102,11,1997,2025-02-02,중개거래,
"""
    rows = parse_rtms_csv(text, Region("11200", "서울특별시 성동구", "서울특별시", "성동구"))
    assert len(rows) == 1
    assert rows[0]["dong"] == "옥수동"
    assert rows[0]["apt_name"] == "극동그린"
    assert rows[0]["area_m2"] == 84.32
    assert rows[0]["price_manwon"] == 120000


def test_year_batches_keep_completed_gaps_separate() -> None:
    assert _year_batches([2006, 2007, 2009, 2010, 2011], 2) == [
        [2006, 2007], [2009, 2010], [2011]
    ]


def test_bulk_download_is_validated_and_saved_by_year(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = LocalStore(tmp_path)
    store.initialize()
    collector = OfficialCsvCollector(store, delay=0)
    region = Region("11200", "서울특별시 성동구", "서울특별시", "성동구")
    content = """공식 자료
NO,시군구,번지,본번,부번,단지명,전용면적(㎡),계약년월,계약일,거래금액(만원),동,층,건축년도,해제사유발생일,거래유형,등기일자
1,서울특별시 성동구 옥수동,1-1,1,1,극동그린,84.32,202401,3,"110,000",101,10,1997,,중개거래,2024-02-01
2,서울특별시 성동구 옥수동,1-1,1,1,극동그린,84.32,202501,3,"120,000",101,10,1997,,중개거래,2025-02-01
""".encode("utf-8")
    monkeypatch.setattr(collector, "_download", lambda *_: content)

    assert collector.collect_year_span(region, [2024, 2025]) == {2024: 1, 2025: 1}
    assert store.completed("11200", 2024)
    assert store.completed("11200", 2025)
    assert len(store.trades("11200", "옥수동", "극동그린")) == 2
    assert (store.local_dir / "raw" / "bulk" / "11200" / "2024-2025.csv.gz").exists()
    collector.close()


def test_failed_forced_refresh_keeps_previous_completed_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = LocalStore(tmp_path)
    store.initialize()
    store.status("11200", 2026, "ok", 1, 7, "2026-08-24T12:00:00")
    collector = OfficialCsvCollector(store, delay=0)
    monkeypatch.setattr(
        collector,
        "_download_twice",
        lambda *_: (_ for _ in ()).throw(DailyQuotaError("일일 다운로드 한도")),
    )

    with pytest.raises(DailyQuotaError):
        collector.collect_year(Region("11200", "서울특별시 성동구", "서울특별시", "성동구"), 2026, force=True)
    assert store.completed("11200", 2026)
    collector.close()


def test_directory_name_matches_official_name() -> None:
    assert name_score("옥수극동그린아파트", "극동그린") >= 700


def test_collection_priority_is_explicit() -> None:
    regions = [
        Region("50110", "제주", "제주", "제주"),
        Region("28110", "인천", "인천", "중구"),
        Region("26110", "부산", "부산", "중구"),
        Region("48120", "창원", "경남", "창원"),
        Region("43110", "청주", "충북", "청주"),
        Region("41135", "분당", "경기", "분당"),
        Region("11110", "종로", "서울", "종로"),
        Region("11200", "성동", "서울", "성동"),
    ]

    assert [item.lawd_cd for item in sorted(regions, key=region_priority)] == [
        "11200", "11110", "41135", "43110", "48120", "26110", "28110", "50110"
    ]


def test_nationwide_province_order_starts_with_requested_five() -> None:
    from realestate.local_collect import COLLECTION_PROVINCE_ORDER
    from realestate.local_store import TARGET_CODE_PREFIXES

    assert COLLECTION_PROVINCE_ORDER[:5] == ("11", "41", "43", "48", "26")
    assert set(COLLECTION_PROVINCE_ORDER) == set(TARGET_CODE_PREFIXES)
    assert all(is_target_lawd(f"{prefix}110") for prefix in COLLECTION_PROVINCE_ORDER)


def test_store_keeps_all_areas_and_dynamic_history(tmp_path: Path) -> None:
    root = tmp_path
    (root / "data" / "local").mkdir(parents=True)
    store = LocalStore(root)
    store.initialize()
    with store.connect() as db:
        db.execute(
            "INSERT INTO complexes VALUES (?,?,?,?,?,?,?,?,?)",
            ("A1", "옥수극동그린아파트", "서울특별시", "성동구", "옥수동", "1120011300", "11200", "서울특별시 성동구", "서울특별시 성동구 옥수동"),
        )
    rows = []
    for area, price in ((59.9, 100000), (84.32, 120000), (114.32, 150000)):
        rows.append(
            {
                "lawd_cd": "11200", "region_name": "서울특별시 성동구", "dong": "옥수동", "jibun": "1-1",
                "apt_name": "극동그린", "area_m2": area, "deal_ym": "202501", "trade_date": "2025-01-03",
                "apt_dong": str(area), "floor": 10, "build_year": 1997, "price_manwon": price,
                "price_eok": price / 10000, "deal_type": "중개거래", "registration_date": "",
            }
        )
    store.replace_region_year("11200", 2025, rows)
    payload = store.build_catalog()
    matched = next(item for item in payload["catalog"] if item.get("data_apt_name") == "극동그린")
    assert matched["directory_name"] == "옥수극동그린아파트"
    assert matched["areas"] == [59.9, 84.32, 114.32]
    assert matched["latest"]["area_m2"] == 59.9
    assert matched["build_year"] == 1997
    assert len(store.history("11200", "옥수동", "극동그린")) == 3
    assert len(store.trades("11200", "옥수동", "극동그린", 84.32)) == 1
    assert json.loads(store.catalog_path.read_text(encoding="utf-8"))["meta"]["directory_count"] == 1


def test_map_complexes_uses_named_complexes_and_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"elements": [{"id": 1, "tags": {"name": "테스트아파트"}}]}

    calls: list[dict] = []

    def fake_post(*args, **kwargs):
        calls.append(kwargs)
        return FakeResponse()

    server._map_cache.clear()
    monkeypatch.setattr(server.requests, "post", fake_post)
    first = server.map_complexes(37.4, 126.9, 37.5, 127.0)
    second = server.map_complexes(37.4, 126.9, 37.5, 127.0)

    assert first == {"elements": [{"id": 1, "tags": {"name": "테스트아파트"}}], "cached": False}
    assert second["cached"] is True
    assert len(calls) == 1
    query = calls[0]["data"]["data"]
    assert 'way["building"="apartments"]["name"]' in query
    assert 'relation["building"="apartments"]["name"]' in query


def test_map_complexes_reuses_cache_for_nearby_pan(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"elements": [{"id": 1}]}

    calls = 0

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        return FakeResponse()

    server._map_cache.clear()
    monkeypatch.setattr(server.requests, "post", fake_post)
    server.map_complexes(37.50, 127.00, 37.52, 127.02)
    nearby = server.map_complexes(37.505, 127.005, 37.525, 127.025)

    assert nearby["cached"] is True
    assert calls == 1


def test_map_complexes_rejects_oversized_bounds() -> None:
    with pytest.raises(HTTPException) as error:
        server.map_complexes(37.0, 126.0, 37.3, 126.1)
    assert error.value.status_code == 400


def test_official_price_lookup_returns_area_median_then_exact_unit(tmp_path: Path) -> None:
    store = OfficialPriceStore(tmp_path / "official.sqlite3")
    store.initialize()
    with sqlite3.connect(store.path) as db:
        for building, unit, price in (("101", "101", 600_000_000), ("101", "201", 620_000_000), ("102", "301", 700_000_000)):
            db.execute(
                "INSERT INTO official_prices VALUES (?,?,?,?,?,?,?,?,?,?)",
                (2026, "경기도 성남시 분당구", normalize("경기도 성남시 분당구"), "테스트단지", normalize("테스트단지"), building, unit, 84.9, price, "2026-01-01"),
            )
    summary = store.lookup(apt_name="테스트단지", area_m2=84.9, year=2026)
    assert summary["exact"] is False
    assert summary["price_won"] == 620_000_000
    assert summary["min_won"] == 600_000_000
    exact = store.lookup(apt_name="테스트단지", area_m2=84.9, year=2026, building="102동", unit="301호")
    assert exact["exact"] is True
    assert exact["price_won"] == 700_000_000


def test_tax_ui_requests_official_price_after_complex_and_area_selection() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert "/api/official-price?" in script
    assert "같은 전용면적 전체의 중앙값" in script


def test_homepage_shows_local_server_availability_and_limitations() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert 'id="mainServerStatus"' in html
    assert "모의투자의 실시간 종목 시세 API" in html
    assert "KIS 모의투자 API 연결" in html
    assert "일부 지도·주소 검색·공시가격 즉시 조회" in html
    assert "공개 데이터에 아직 저장되지 않은 실거래 상세 조회" in html
    assert 'response.headers.get("x-real-estate-source")==="local-pc"' in script
    assert "꺼짐 · 연결 불가" in script
    assert "localMeta.trade_count" in script
    assert "style.css?v=33" in html
