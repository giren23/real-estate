import json
from pathlib import Path

import pandas as pd

from realestate.analysis.publish import compact_history
from scripts import merge_incremental_public_data as merger


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_incremental_merge_replaces_only_collected_month_and_preserves_history(tmp_path, monkeypatch) -> None:
    public = tmp_path / "data" / "public"
    raw = tmp_path / "data" / "raw" / "trades"
    public.mkdir(parents=True)
    raw.mkdir(parents=True)
    old_history = pd.DataFrame([
        {"lawd_cd": "41135", "region_name": "경기도 성남분당구", "dong": "서현동", "apt_name": "시범한신", "area_m2": 84.69, "month": "2020-01", "median_price_eok": 8.0, "trade_count": 2},
        {"lawd_cd": "41135", "region_name": "경기도 성남분당구", "dong": "서현동", "apt_name": "시범한신", "area_m2": 84.69, "month": "2026-09", "median_price_eok": 15.0, "trade_count": 1},
    ])
    old_trade = {
        "lawd_cd": "41135", "region_name": "경기도 성남분당구", "deal_ym": "202609", "trade_date": "2026-09-01",
        "apt_name": "시범한신", "dong": "서현동", "jibun": "1", "apt_dong": "", "area_m2": 84.69,
        "area_pyeong": 25.62, "floor": 1, "build_year": 1991, "price_manwon": 150000, "price_eok": 15.0,
        "price_per_m2_manwon": 1771.17, "price_per_pyeong_manwon": 5854.8, "deal_type": "중개거래",
        "registration_date": "", "cancelled": False,
    }
    write_json(public / "apartment_history.json", compact_history(old_history))
    write_json(public / "meta.json", {"status": "ok", "trade_count": 3, "first_date": "2020-01-02", "latest_date": "2026-09-01"})
    write_json(public / "latest_trades.json", [old_trade])
    write_json(public / "apartments.json", [])
    write_json(public / "monthly.json", [{"lawd_cd": "41135", "region_name": "경기도 성남분당구", "month": "2026-09", "trade_count": 1}])
    write_json(public / "regions.json", [{"lawd_cd": "41135", "region_name": "경기도 성남분당구"}])
    write_json(public / "complexes.json", [])

    fresh = pd.DataFrame([
        {**old_trade, "trade_date": "2026-09-12", "floor": 7, "price_manwon": 160000, "price_eok": 16.0, "price_per_m2_manwon": 1889.24, "price_per_pyeong_manwon": 6245.1},
        {**old_trade, "trade_date": "2026-09-13", "floor": 8, "price_manwon": 170000, "price_eok": 17.0, "price_per_m2_manwon": 2007.32, "price_per_pyeong_manwon": 6635.4},
    ])
    fresh.to_parquet(raw / "41135_202609.parquet", index=False)

    monkeypatch.setattr(merger, "ROOT", tmp_path)
    monkeypatch.setattr(merger, "PUBLIC", public)
    monkeypatch.setattr(merger, "RAW_TRADES", raw)
    merger.main()

    result = merger.history_frame(json.loads((public / "apartment_history.json").read_text(encoding="utf-8")))
    old_month = result[result["month"] == "2020-01"].iloc[0]
    new_month = result[result["month"] == "2026-09"].iloc[0]
    meta = json.loads((public / "meta.json").read_text(encoding="utf-8"))

    assert old_month["trade_count"] == 2
    assert new_month["trade_count"] == 2
    assert new_month["median_price_eok"] == 16.5
    assert meta["trade_count"] == 4
    assert meta["first_date"] == "2020-01-02"
