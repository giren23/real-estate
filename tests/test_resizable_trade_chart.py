from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_trade_chart_defaults_to_compact_mobile_height_and_is_resizable() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    style = (ROOT / "web" / "style.css").read_text(encoding="utf-8")

    assert 'id="graphWidth"' in script
    assert 'id="graphHeight"' in script
    assert 'id="resetGraphSize"' in script
    assert "chartWidth" in script and "chartHeight" in script
    assert ".price-chart-scroll{overflow-x:auto" in style
    assert ".graph-chart-wrap{height:320px}" in style
    assert ".stack-chart{min-width:0" in style
    assert "grid-template-columns:minmax(0,1fr)" in style
