import json
from pathlib import Path

import pandas as pd

from realestate.collectors import trades
from scripts.publish_collection_status import public_status


def test_retry_runs_only_problem_pairs(tmp_path, monkeypatch) -> None:
    source = tmp_path / "initial.json"
    retry = tmp_path / "retry.json"
    source.write_text(json.dumps({"problems": [
        {"lawd_cd": "41135", "region_name": "성남분당구", "deal_ym": "202609"},
        {"lawd_cd": "48120", "region_name": "창원시", "deal_ym": "202608"},
    ]}), encoding="utf-8")
    seen = []

    def fake_run(_settings, tasks, _output, report):
        seen.extend(tasks)
        payload = {"request_count": len(tasks), "failed_request_count": 0}
        report.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    monkeypatch.setattr(trades, "_run_trade_tasks", fake_run)
    trades.retry_failed_trades(object(), source, tmp_path / "raw", retry)
    assert [(task[1], task[3]) for task in seen] == [("41135", "202609"), ("48120", "202608")]


def test_public_status_overrides_recovered_retry() -> None:
    initial = {
        "success_count": 1,
        "requests": [
            {"lawd_cd": "11110", "deal_ym": "202609", "status": "ok", "row_count": 2},
            {"lawd_cd": "41135", "deal_ym": "202609", "status": "failed", "row_count": None},
        ],
    }
    retry = {"request_count": 1, "requests": [
        {"lawd_cd": "41135", "deal_ym": "202609", "status": "ok", "row_count": 4},
    ]}
    result = public_status(initial, retry)
    assert result["status"] == "complete"
    assert result["recovered_count"] == 1
    assert result["unresolved_count"] == 0
