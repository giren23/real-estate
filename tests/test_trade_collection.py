from __future__ import annotations

from types import SimpleNamespace
import threading
import time

import pandas as pd

from realestate.collectors import trades


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
    settings = SimpleNamespace(request_delay_seconds=0)
    regions = pd.DataFrame([{
        "lawd_cd": "11110",
        "region_name": "서울특별시 종로구",
    }])
    months = [f"2026{month:02d}" for month in range(1, 9)]

    trades.collect_trades(settings, regions, months, tmp_path)

    assert 1 < state["maximum"] <= 6
    assert len(list(tmp_path.glob("*.parquet"))) == len(months)
