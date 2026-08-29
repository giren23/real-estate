from __future__ import annotations

import json
from types import SimpleNamespace
import threading
import time

import pandas as pd
import pytest

from realestate.collectors import trades


def settings(**overrides):
    values = {
        "request_delay_seconds": 0,
        "trade_endpoint": "primary",
        "trade_fallback_endpoint": "",
        "service_key": "test-key",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_collect_trades_uses_bounded_parallel_requests(monkeypatch, tmp_path):
    state = {"active": 0, "maximum": 0}
    lock = threading.Lock()

    def fake_fetch(settings, lawd_cd, region_name, deal_ym):
        with lock:
            state["active"] += 1
            state["maximum"] = max(state["maximum"], state["active"])
        time.sleep(0.03)
        with lock:
            state["active"] -= 1
        return pd.DataFrame([{"cancelled": False, "value": 1}])

    monkeypatch.setattr(trades, "fetch_trade_month", fake_fetch)
    regions = pd.DataFrame(
        [{"lawd_cd": "11110", "region_name": "서울특별시 종로구"}]
    )
    months = [f"2026{month:02d}" for month in range(1, 9)]

    trades.collect_trades(settings(), regions, months, tmp_path)

    assert 1 < state["maximum"] <= 3
    assert len(list(tmp_path.glob("*.parquet"))) == len(months)


def test_collect_trades_uses_alternative_endpoint(monkeypatch, tmp_path):
    def failed_primary(settings, lawd_cd, region_name, deal_ym):
        raise RuntimeError("primary unavailable")

    def working_fallback(settings, lawd_cd, region_name, deal_ym, endpoint):
        assert endpoint == "fallback"
        return pd.DataFrame([{"cancelled": False, "value": 7}])

    monkeypatch.setattr(trades, "fetch_trade_month", failed_primary)
    monkeypatch.setattr(
        trades,
        "fetch_trade_month_from_endpoint",
        working_fallback,
    )
    regions = pd.DataFrame(
        [{"lawd_cd": "11110", "region_name": "서울특별시 종로구"}]
    )
    report_path = tmp_path / "report.json"

    trades.collect_trades(
        settings(trade_fallback_endpoint="fallback"),
        regions,
        ["202608"],
        tmp_path,
        report_path,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "ok"
    assert report["success_count"] == 1
    assert pd.read_parquet(tmp_path / "11110_202608.parquet")["value"].tolist() == [7]


def test_collect_trades_continues_and_reports_all_failures(monkeypatch, tmp_path):
    existing = tmp_path / "11110_202608.parquet"
    pd.DataFrame([{"cancelled": False, "value": 3}]).to_parquet(
        existing,
        index=False,
    )

    def failed_primary(settings, lawd_cd, region_name, deal_ym):
        raise RuntimeError("primary unavailable")

    def failed_fallback(settings, lawd_cd, region_name, deal_ym, endpoint):
        raise RuntimeError("fallback unavailable")

    monkeypatch.setattr(trades, "fetch_trade_month", failed_primary)
    monkeypatch.setattr(
        trades,
        "fetch_trade_month_from_endpoint",
        failed_fallback,
    )
    regions = pd.DataFrame(
        [
            {"lawd_cd": "11110", "region_name": "서울특별시 종로구"},
            {"lawd_cd": "41135", "region_name": "경기도 성남시 분당구"},
        ]
    )
    report_path = tmp_path / "report.json"

    with pytest.raises(RuntimeError, match="2/2개 요청"):
        trades.collect_trades(
            settings(trade_fallback_endpoint="fallback"),
            regions,
            ["202608"],
            tmp_path,
            report_path,
        )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "partial_failure"
    assert report["cached_fallback_count"] == 1
    assert report["failure_count"] == 1
    assert report["failed_request_count"] == 2
    assert [item["lawd_cd"] for item in report["failed_regions"]] == [
        "11110",
        "41135",
    ]
    assert pd.read_parquet(existing)["value"].tolist() == [3]
