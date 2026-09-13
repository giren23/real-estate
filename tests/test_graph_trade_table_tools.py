from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_trade_history_supports_sorting_filters_and_pastel_rows() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "web" / "graph-trade-tools.css").read_text(encoding="utf-8")
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

    for key in ("date", "apt", "area", "price", "floor"):
        assert f'data-trade-sort="{key}"' in script
    assert 'data-trade-filter="group"' in script
    assert 'data-trade-filter="area"' in script
    assert 'data-trade-filter-only="group"' in script
    assert 'data-trade-filter-only="area"' in script
    assert "tradeHistoryHiddenGroups" in script
    assert "tradeHistoryHiddenAreas" in script
    assert "--trade-pastel" in script
    assert "--trade-pastel" in stylesheet
    assert 'href="graph-trade-tools.css?v=1"' in html
    assert 'src="app.js?v=77"' in html
