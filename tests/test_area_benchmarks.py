from realestate.area_benchmarks import build_index, build_trend_analysis, resolve_requested


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


def test_trend_analysis_marks_no_trade_and_ranks_available_windows() -> None:
    rows = []
    for apt_name, prices in {"가": [("2026-01", 8), ("2026-02", 10)], "나": [("2026-01", 9), ("2026-02", 9)], "다": [("2026-01", 7), ("2026-03", 8)]}.items():
        for month, price in prices:
            rows.append({"lawd_cd": "41110", "region_name": "경기도 수원시", "dong": "매산동", "apt_name": apt_name, "area_m2": 84, "month": month, "median_price_eok": price, "trade_count": 1})

    trend = build_trend_analysis(rows, {"lawd_cd": "41110", "dong": "매산동", "apt_name": "가"}, "2026-03")
    three_months = next(period for period in trend["periods"] if period["months"] == 3)
    one_month = next(period for period in trend["periods"] if period["months"] == 1)

    assert trend["province_label"] == "경기도"
    assert three_months["status"] == "ok"
    assert three_months["trend_pct_per_month"] > 0
    assert three_months["dong_trend_rank"]["rank"] == 1
    assert one_month["status"] == "no_trade"
    assert one_month["trend_basis_months"] == 3
    assert one_month["trend_fallback_used"] is True
    assert one_month["trend_pct_per_month"] > 0
    assert one_month["dong_trend_rank"]["rank"] == 1


def test_trend_analysis_expands_three_month_window_until_rank_is_available() -> None:
    rows = []
    for apt_name, prices in {
        "가": [("2025-11", 8), ("2026-02", 10)],
        "나": [("2025-11", 9), ("2026-02", 9)],
    }.items():
        for month, price in prices:
            rows.append({"lawd_cd": "41110", "region_name": "경기도 수원시", "dong": "매산동", "apt_name": apt_name, "area_m2": 84, "month": month, "median_price_eok": price, "trade_count": 1})

    trend = build_trend_analysis(rows, {"lawd_cd": "41110", "dong": "매산동", "apt_name": "가"}, "2026-03")
    three_months = next(period for period in trend["periods"] if period["months"] == 3)

    assert three_months["observation_months"] == 1
    assert three_months["trend_basis_months"] == 6
    assert three_months["trend_fallback_used"] is True
    assert three_months["trend_observation_months"] == 2
    assert three_months["dong_trend_rank"]["rank"] == 1
