import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_market_snapshot_page_and_data_are_wired() -> None:
    html = (ROOT / "web" / "market.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "market.js").read_text(encoding="utf-8")
    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert "시장 한 컷" in html
    assert "data/market_snapshot.json" in script
    assert 'href="market.html"' in index
    assert "주식 아침 브리핑 · 기존 기능 보존" not in html
    assert html.index("시장·환율·원자재 핵심 요약") > html.index('id="trendCharts"')


def test_market_snapshot_has_required_sections_and_charts() -> None:
    payload = json.loads((ROOT / "data" / "public" / "market_snapshot.json").read_text(encoding="utf-8"))
    assert {category["id"] for category in payload["categories"]} >= {"global", "fx", "commodities", "rates"}
    assert len(payload["charts"]) >= 5
    commodity_keys = {item["key"] for category in payload["categories"] if category["id"] == "commodities" for item in category["items"]}
    assert "dubai" in commodity_keys
    dubai = next(item for category in payload["categories"] for item in category["items"] if item["key"] == "dubai")
    assert dubai["changes"]["day"] is None
    assert dubai["changes"]["week"] is None
    for category in payload["categories"]:
        for item in category["items"]:
            assert {"day", "week", "month", "quarter"} <= item["changes"].keys()
            assert item["history"]
