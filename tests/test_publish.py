from __future__ import annotations

import json

import pandas as pd

from realestate.analysis.publish import compact_history


def test_compact_history_deduplicates_apartment_labels():
    history = pd.DataFrame(
        [
            {
                "lawd_cd": "41135",
                "region_name": "경기도 성남시 분당구",
                "dong": "이매동",
                "apt_name": "이매촌(한신)",
                "area_m2": 84.9,
                "month": "2026-07",
                "median_price_eok": 15.2,
                "trade_count": 2,
            },
            {
                "lawd_cd": "41135",
                "region_name": "경기도 성남시 분당구",
                "dong": "이매동",
                "apt_name": "이매촌(한신)",
                "area_m2": 84.9,
                "month": "2026-08",
                "median_price_eok": 15.5,
                "trade_count": 1,
            },
            {
                "lawd_cd": "48123",
                "region_name": "경상남도 창원시 성산구",
                "dong": "신월동",
                "apt_name": "은아",
                "area_m2": 59.98,
                "month": "2026-08",
                "median_price_eok": 3.4,
                "trade_count": 1,
            },
        ]
    )

    payload = compact_history(history)

    assert payload["version"] == 2
    assert len(payload["apartments"]) == 2
    assert len(payload["rows"]) == 3
    assert payload["rows"][0][0] == payload["rows"][1][0]
    assert json.loads(json.dumps(payload, ensure_ascii=False)) == payload
