from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_main_chart_latest_values_are_always_rendered() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    style = (ROOT / "web" / "style.css").read_text(encoding="utf-8")

    assert "function latestDatasetPoint" in script
    assert 'if(raw===null||raw===undefined||raw==="")continue' in script
    for group in ("metal_prices", "market_indices", "fear_greed"):
        assert f"economicContext.{group}" in script
    assert "function renderLatestValues" in script
    assert script.count("renderLatestValues(") >= 13
    assert 'className="latest-values"' in script
    assert ".latest-value-chip" in style


def test_market_trends_identify_the_latest_value_without_hover() -> None:
    script = (ROOT / "web" / "market.js").read_text(encoding="utf-8")

    assert '<em>최신</em>' in script
    assert "${item.date} 최신값" in script


def test_economic_indicators_have_an_independent_daily_workflow() -> None:
    workflow = (ROOT / ".github" / "workflows" / "economic-indicators-daily.yml").read_text(encoding="utf-8")

    assert 'cron: "15 22 * * *"' in workflow
    assert "update_economic_context.py" in workflow
    assert "update_market_snapshot.py" in workflow
    assert "update_stock_briefing.py" not in workflow
