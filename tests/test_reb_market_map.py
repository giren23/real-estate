from pathlib import Path

from scripts.update_reb_market_map import calculate_area_84_prices, enrich_area_84_prices, normalize_payload


ROOT = Path(__file__).resolve().parents[1]


def test_reb_map_normalization_groups_cities_under_provinces() -> None:
    rows = [{"viewItmNm": "전국", "geoCd": "10", "clsDatano": 1, "parDatano": 0, "dtaVal": 0.2, "wrttimeIdtfrId": "202607"}]
    for index in range(15):
        data_no = 100 + index
        rows.append({"viewItmNm": f"시도{index}", "geoCd": str(20 + index), "clsDatano": data_no, "parDatano": 0, "dtaVal": index / 100, "wrttimeIdtfrId": "202607"})
        for city in range(13):
            rows.append({"viewItmNm": f"지역{index}-{city}", "geoCd": f"{20 + index}{city:03d}", "clsDatano": data_no * 10 + city, "parDatano": data_no, "dtaVal": city / 10, "wrttimeIdtfrId": "202607"})
    payload = normalize_payload(rows, "2026-09-13T12:00:00+09:00")
    assert payload["period"] == "2026-07"
    assert len(payload["provinces"]) == 15
    assert sum(len(row["cities"]) for row in payload["provinces"]) == 195


def test_reb_map_adds_verified_transaction_volume_and_top20_rankings() -> None:
    price_rows = [{"viewItmNm": "전국", "geoCd": "10", "clsDatano": 1, "parDatano": 0, "dtaVal": 0.2, "wrttimeIdtfrId": "202607"}]
    volume_rows = [{"viewItmNm": "전국", "geoCd": "10", "clsDatano": 1, "parDatano": 0, "dtaVal": "50,129", "wrttimeIdtfrId": "202607"}]
    for index in range(15):
        data_no = 100 + index
        province = {"viewItmNm": f"시도{index}", "geoCd": str(20 + index), "clsDatano": data_no, "parDatano": 0, "wrttimeIdtfrId": "202607"}
        price_rows.append({**province, "dtaVal": index / 100})
        volume_rows.append({**province, "dtaVal": 1_000 + index})
        for city in range(13):
            region = {"viewItmNm": f"지역{index}-{city}", "geoCd": f"{20 + index}{city:03d}", "clsDatano": data_no * 10 + city, "parDatano": data_no, "wrttimeIdtfrId": "202607"}
            price_rows.append({**region, "dtaVal": city / 10})
            volume_rows.append({**region, "dtaVal": index * 100 + city})

    payload = normalize_payload(price_rows, "2026-09-14T12:00:00+09:00", volume_rows)

    assert payload["schema_version"] == 2
    assert payload["transaction_volume"]["period"] == "2026-07"
    assert payload["transaction_volume"]["country"]["value"] == 50_129
    assert payload["transaction_volume"]["source"]["stat_table_id"] == "A_2024_00554"
    assert len(payload["rankings"]["price_change"]["top"]) == 20
    assert len(payload["rankings"]["price_change"]["bottom"]) == 20
    assert len(payload["rankings"]["transaction_volume"]["top"]) == 20
    assert len(payload["rankings"]["transaction_volume"]["bottom"]) == 20
    assert payload["rankings"]["transaction_volume"]["top"][0]["value"] > payload["rankings"]["transaction_volume"]["bottom"][0]["value"]


def test_reb_frontend_renders_price_and_volume_top20() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    for element_id in ("rebNationalVolume", "rebPriceTop20", "rebPriceBottom20", "rebVolumeTop20", "rebVolumeBottom20"):
        assert f'id="{element_id}"' in html
    for sort_mode in ("price_high", "price_low", "volume_high", "volume_low"):
        assert f'value="{sort_mode}"' in html
    assert "renderRebTop20" in script
    assert "rebCombinedCities" in script
    assert "transaction_volume" in script
    assert "rebArea84" in script
    assert "84㎡급 평균" in script


def test_area_84_average_uses_only_valid_80_to_90_sqm_trades() -> None:
    rows = [
        {"lawd_cd": "11110", "area_m2": 84.9, "price_eok": 10, "trade_date": "2026-08-01", "cancelled": False},
        {"lawd_cd": "11110", "area_m2": 82.0, "price_eok": 12, "trade_date": "2026-09-01", "cancelled": False},
        {"lawd_cd": "11110", "area_m2": 59.9, "price_eok": 7, "trade_date": "2026-09-02", "cancelled": False},
        {"lawd_cd": "11110", "area_m2": 84.0, "price_eok": 30, "trade_date": "2026-09-03", "cancelled": True},
    ]
    result = calculate_area_84_prices(rows)
    assert result["11110"]["average_price_eok"] == 11
    assert result["11110"]["trade_count"] == 2
    assert result["11110"]["period_start"] == "2026-08-01"


def test_area_84_average_is_attached_by_official_district_code() -> None:
    payload = {
        "provinces": [{"code": "11", "name": "서울", "cities": [{"code": "11110", "name": "종로구", "value": 0.2}]}],
        "transaction_volume": {"provinces": []},
    }
    enrich_area_84_prices(payload, [
        {"lawd_cd": "11110", "area_m2": 84.0, "price_eok": 15.5, "trade_date": "2026-09-01", "cancelled": False}
    ])
    value = payload["provinces"][0]["cities"][0]["area_84_price"]
    assert value["average_price_eok"] == 15.5
    assert payload["area_84_prices"]["matched_region_count"] == 1


def test_area_84_average_is_also_added_to_volume_rankings() -> None:
    payload = {
        "provinces": [{"code": "11", "name": "서울", "cities": [{"code": "11110", "name": "종로구", "value": 0.2}]}],
        "transaction_volume": {
            "provinces": [{"code": "11", "name": "서울", "cities": [{"code": "11110", "name": "종로구", "value": 123}]}]
        },
    }
    enrich_area_84_prices(payload, [
        {"lawd_cd": "11110", "area_m2": 84.0, "price_eok": 15.5, "trade_date": "2026-09-01", "cancelled": False}
    ])
    ranking = payload["rankings"]["transaction_volume"]["top"][0]
    assert ranking["area_84_price"]["average_price_eok"] == 15.5
