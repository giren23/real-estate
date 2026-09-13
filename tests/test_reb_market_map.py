from scripts.update_reb_market_map import normalize_payload


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
