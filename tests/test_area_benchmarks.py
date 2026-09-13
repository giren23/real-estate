from realestate.area_benchmarks import administrative_scopes, build_index, build_trend_analysis, resolve_requested


def test_area_benchmark_reports_dong_and_city_percentile() -> None:
    records = [
        {"lawd_cd": "11110", "region_name": "서울특별시 종로구", "dong": "청운동", "apt_name": "가", "area_m2": 84, "month": "2026-08", "median_price_eok": 12, "trade_count": 2},
        {"lawd_cd": "11110", "region_name": "서울특별시 종로구", "dong": "청운동", "apt_name": "나", "area_m2": 84, "month": "2026-08", "median_price_eok": 8, "trade_count": 2},
        {"lawd_cd": "11140", "region_name": "서울특별시 중구", "dong": "소공동", "apt_name": "다", "area_m2": 84, "month": "2026-08", "median_price_eok": 10, "trade_count": 1},
    ]
    index = build_index(records)
    item = resolve_requested(index, [{"lawd_cd": "11110", "dong": "청운동", "apt_name": "가"}])[0]

    assert item["city_label"] == "종로구"
    assert item["dong_reference"]["count"] == 2
    assert item["dong_reference"]["z_score"] > 0
    assert item["dong_reference"]["top_percent"] == 50.0
    assert item["city_reference"]["count"] == 2
    assert item["province_reference"]["count"] == 3
    assert [scope["level"] for scope in item["administrative_references"]] == ["locality", "district", "province"]


def test_divided_city_hierarchy_restores_city_gu_and_dong_levels() -> None:
    scopes = administrative_scopes("경기도 성남분당구", "41135", "정자동")

    assert [(scope["level"], scope["label"]) for scope in scopes] == [
        ("province", "경기도"),
        ("municipality", "성남시"),
        ("district", "분당구"),
        ("locality", "정자동"),
    ]


def test_divided_city_reference_uses_each_administrative_population() -> None:
    records = [
        {"lawd_cd": "41135", "region_name": "경기도 성남분당구", "dong": "정자동", "apt_name": "가", "area_m2": 84, "month": "2026-08", "median_price_eok": 14, "trade_count": 1},
        {"lawd_cd": "41135", "region_name": "경기도 성남분당구", "dong": "정자동", "apt_name": "나", "area_m2": 84, "month": "2026-08", "median_price_eok": 12, "trade_count": 1},
        {"lawd_cd": "41135", "region_name": "경기도 성남분당구", "dong": "서현동", "apt_name": "다", "area_m2": 84, "month": "2026-08", "median_price_eok": 10, "trade_count": 1},
        {"lawd_cd": "41133", "region_name": "경기도 성남중원구", "dong": "성남동", "apt_name": "라", "area_m2": 84, "month": "2026-08", "median_price_eok": 8, "trade_count": 1},
        {"lawd_cd": "41210", "region_name": "경기도 광명시", "dong": "철산동", "apt_name": "마", "area_m2": 84, "month": "2026-08", "median_price_eok": 6, "trade_count": 1},
    ]

    item = resolve_requested(
        build_index(records), [{"lawd_cd": "41135", "dong": "정자동", "apt_name": "가"}]
    )[0]
    references = {scope["level"]: scope["reference"] for scope in item["administrative_references"]}

    assert references["locality"]["count"] == 2
    assert references["district"]["count"] == 3
    assert references["municipality"]["count"] == 4
    assert references["province"]["count"] == 5


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
    assert [period["months"] for period in trend["periods"]] == [1, 3, 6, 12, 36]
    assert three_months["status"] == "ok"
    assert three_months["trade_count"] == 2
    assert three_months["trend_pct_per_month"] > 0
    assert three_months["dong_trend_rank"]["rank"] == 1
    assert one_month["status"] == "no_trade"
    assert one_month["trade_count"] == 0
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
