from realestate.area_benchmarks import build_index, resolve_requested


def test_area_benchmark_reports_dong_and_city_percentile() -> None:
    records = [
        {"lawd_cd": "11110", "region_name": "서울특별시 종로구", "dong": "청운동", "apt_name": "가", "area_m2": 84, "month": "2026-08", "median_price_eok": 12, "trade_count": 2},
        {"lawd_cd": "11110", "region_name": "서울특별시 종로구", "dong": "청운동", "apt_name": "나", "area_m2": 84, "month": "2026-08", "median_price_eok": 8, "trade_count": 2},
        {"lawd_cd": "11140", "region_name": "서울특별시 중구", "dong": "소공동", "apt_name": "다", "area_m2": 84, "month": "2026-08", "median_price_eok": 10, "trade_count": 1},
    ]
    index = build_index(records)
    item = resolve_requested(index, [{"lawd_cd": "11110", "dong": "청운동", "apt_name": "가"}])[0]

    assert item["city_label"] == "서울특별시"
    assert item["dong_reference"]["count"] == 2
    assert item["dong_reference"]["z_score"] > 0
    assert item["dong_reference"]["top_percent"] == 50.0
    assert item["city_reference"]["count"] == 3


def test_area_benchmark_uses_84_square_meter_class_only() -> None:
    records = [
        {"lawd_cd": "41110", "region_name": "경기도 수원시", "dong": "매산동", "apt_name": "가", "area_m2": 84.8, "month": "2026-08", "median_price_eok": 7, "trade_count": 1},
    ]
    index = build_index(records)
    item = resolve_requested(index, [{"lawd_cd": "41110", "dong": "매산동", "apt_name": "가"}])[0]

    assert item["area_m2"] == 84.8
    assert item["price_per_supply_pyeong_manwon"] > 0
