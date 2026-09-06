from __future__ import annotations

import json
from pathlib import Path

from realestate.local_store import LocalStore
from scripts.publish_local_snapshot import build_snapshot, write_snapshot


def test_local_snapshot_uses_represented_trade_count(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    store.initialize()
    with store.connect() as db:
        db.execute(
            "INSERT INTO monthly_history VALUES (?,?,?,?,?,?,?,?)",
            ("11110", "서울 종로구", "청운동", "테스트", 84.0, "2026-08", 10.0, 7),
        )

    payload = build_snapshot(tmp_path)
    target = write_snapshot(payload, tmp_path)

    assert payload["trade_count"] == 7
    assert payload["represented_trades"] == 7
    assert payload["source"] == "local-main-server"
    assert json.loads(target.read_text(encoding="utf-8"))["trade_count"] == 7
