import json

import pandas as pd

from realestate.analysis.publish import compact_history
from scripts import build_public_trade_shards as builder


def test_builds_one_independently_loadable_file_per_district(tmp_path, monkeypatch) -> None:
    public = tmp_path / "data/public"
    public.mkdir(parents=True)
    (public / "meta.json").write_text(json.dumps({"trade_count": 3, "latest_date": "2026-09-14"}), encoding="utf-8")
    trades = [
        {"lawd_cd": "41135", "trade_date": "2026-09-14", "dong": "서현동", "apt_name": "시범한신"},
        {"lawd_cd": "11110", "trade_date": "2026-09-13", "dong": "청운동", "apt_name": "테스트"},
    ]
    (public / "latest_trades.json").write_text(json.dumps(trades, ensure_ascii=False), encoding="utf-8")
    history = pd.DataFrame([
        {"lawd_cd": "41135", "region_name": "경기도 성남분당구", "dong": "서현동", "apt_name": "시범한신", "area_m2": 84.69, "month": "2026-09", "median_price_eok": 15.0, "trade_count": 2},
    ])
    (public / "apartment_history.json").write_text(json.dumps(compact_history(history), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(builder, "PUBLIC", public)
    monkeypatch.setattr(builder, "SHARDS", public / "shards")
    builder.main()
    manifest = json.loads((public / "shards/manifest.json").read_text(encoding="utf-8"))
    district = json.loads((public / "shards/41135.json").read_text(encoding="utf-8"))
    assert [row["lawd_cd"] for row in manifest["districts"]] == ["11110", "41135"]
    assert manifest["trade_apartment_count"] == 2
    assert manifest["districts"][1]["apartments"] == [["서현동", "시범한신"]]
    assert district["lawd_cd"] == "41135"
    assert district["trades"][0]["apt_name"] == "시범한신"
    assert district["history"]["rows"][0][4] == 2
