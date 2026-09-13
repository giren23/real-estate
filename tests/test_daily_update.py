from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from realestate.local_collect import Region
from realestate.local_store import LocalStore
from scripts.daily_local_update import (
    load_rotation,
    one_day_priority_regions,
    save_rotation,
    select_stalest_regions,
)
from realestate.server import _finished_for_today


def test_rotation_state_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "latest_rotation.json"

    save_rotation(path, 15)

    assert load_rotation(path) == 15
    assert json.loads(path.read_text(encoding="utf-8"))["next"] == 15
    assert not path.with_suffix(".json.tmp").exists()


def test_invalid_rotation_state_recovers_from_first_region(tmp_path: Path) -> None:
    path = tmp_path / "latest_rotation.json"
    path.write_text("not-json", encoding="utf-8")

    assert load_rotation(path) == 0


def test_update_completion_distinguishes_delayed_quota_reset() -> None:
    assert _finished_for_today({"state": "completed"})
    assert _finished_for_today({"state": "quota", "phase": "history", "latest": {"completed_jobs": 15}})
    assert not _finished_for_today({"state": "quota", "phase": "latest", "latest": {"completed_jobs": 0}})
    assert not _finished_for_today({"state": "completed_with_failures"})


def test_select_stalest_regions_prefers_missing_then_oldest(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    store.initialize()
    regions = [
        Region("11110", "서울 종로구", "서울특별시", "종로구"),
        Region("11140", "서울 중구", "서울특별시", "중구"),
        Region("11170", "서울 용산구", "서울특별시", "용산구"),
    ]
    store.status("11110", 2026, "ok", 1, 1, "2026-08-24T01:00:00", "")
    store.status("11140", 2026, "ok", 1, 1, "2026-08-20T01:00:00", "")

    selected = select_stalest_regions(regions, 3, 2026, root=tmp_path)

    assert [region.lawd_cd for region in selected] == ["11170", "11140", "11110"]


def test_one_day_priority_regions_only_applies_on_2026_09_15() -> None:
    regions = [
        Region("41135", "경기 성남시 분당구", "경기도", "성남시 분당구"),
        Region("48121", "경남 창원시 의창구", "경상남도", "창원시 의창구"),
        Region("48123", "경남 창원시 성산구", "경상남도", "창원시 성산구"),
        Region("48125", "경남 창원시 마산합포구", "경상남도", "창원시 마산합포구"),
        Region("48127", "경남 창원시 마산회원구", "경상남도", "창원시 마산회원구"),
        Region("48129", "경남 창원시 진해구", "경상남도", "창원시 진해구"),
        Region("11110", "서울 종로구", "서울특별시", "종로구"),
    ]

    selected = one_day_priority_regions(regions, date(2026, 9, 15))

    assert [region.lawd_cd for region in selected] == [
        "41135",
        "48121",
        "48123",
        "48125",
        "48127",
        "48129",
    ]
    assert one_day_priority_regions(regions, date(2026, 9, 16)) == []
