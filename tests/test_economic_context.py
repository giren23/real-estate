from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def series_fields(rows: list[dict]) -> set[str]:
    return {key for row in rows for key in row}


def test_economic_context_contains_dashboard_series() -> None:
    data = json.loads((ROOT / "data" / "public" / "economic_context.json").read_text(encoding="utf-8"))
    required = {"exchange_rates", "money_supply", "metal_prices", "oil_prices", "bond_yields", "market_indices", "fear_greed"}
    assert required <= data.keys()
    assert {"gold_usd_oz", "silver_usd_oz", "copper_usd_ton"} <= series_fields(data["metal_prices"])
    assert {"brent_usd_barrel", "wti_usd_barrel", "dubai_usd_barrel"} <= series_fields(data["oil_prices"])
    assert {"kospi", "kosdaq", "sp500", "nasdaq", "dow", "bitcoin", "sox", "vix"} <= data["market_indices"][-1].keys()
    assert 0 <= data["fear_greed"][-1]["score"] <= 100


def test_news_archive_has_historical_days_and_articles() -> None:
    data = json.loads((ROOT / "web" / "content" / "news" / "index.json").read_text(encoding="utf-8"))
    assert data["archive_days"] >= 20
    assert data["total_articles"] >= 400
    assert data["latest_items"]
    assert all(item["sources"] and item["sources"][0]["url"].startswith("https://") for item in data["latest_items"])


def test_automatic_analysis_has_source_diversity_and_longform_structure() -> None:
    data = json.loads((ROOT / "web" / "content" / "analysis" / "index.json").read_text(encoding="utf-8"))
    assert len(data["company_items"]) >= 2
    assert len(data["analysis_items"]) >= 5
    for item in data["company_items"] + data["analysis_items"]:
        assert item["longform"] is True
        assert len(item["sections"]) >= 5
        assert len({source["publisher"] for source in item["sources"] if source["publisher"] != "금융감독원 DART"}) >= 2
