from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_trade_chart_defaults_to_compact_mobile_height_and_is_resizable() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    style = (ROOT / "web" / "style.css").read_text(encoding="utf-8")

    assert 'id="graphWidth"' in script
    assert 'id="graphHeight"' in script
    assert 'id="alignEconomicCharts"' in script
    assert 'id="resetAllGraphScales"' in script
    assert 'id="graphHeight" type="range" min="260" max="720" step="10"' in script
    assert "chartWidth" in script and "chartHeight" in script
    assert "economicWidth" in script
    assert "function bindEconomicChartAlignment" in script
    assert "item.chartWidth=100;item.chartHeight=0;item.economicWidth=100" in script
    assert ".price-chart-scroll{overflow-x:auto" in style
    assert ".graph-chart-wrap{height:320px}" in style
    assert "width:var(--economic-chart-width,100%)" in style
    assert ".stack-chart{min-width:0" in style
    assert "grid-template-columns:minmax(0,1fr)" in style
