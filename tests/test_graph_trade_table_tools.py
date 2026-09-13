from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_trade_history_supports_sorting_filters_and_pastel_rows() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "web" / "graph-trade-tools.css").read_text(encoding="utf-8")
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

    for key in ("date", "apt", "area", "price", "floor"):
        assert f'data-trade-sort="{key}"' in script
    assert 'data-trade-filter="series"' in script
    assert 'data-trade-filter-only="series"' in script
    assert "tradeHistoryHiddenSeries" in script
    assert "tradeHistoryMonths:1" in script
    assert '[[1,"최근 1개월"]' in script
    assert 'sort().at(-1)' in script
    assert "--filter-color" in script
    assert "benchmarkDong" in script
    assert "benchmarkCity" in script
    assert "include_history=true" in script
    assert "benchmarkOverlay:true" in script
    assert "borderDash:dash" in script
    assert "--trade-pastel" in script
    assert "--trade-pastel" in stylesheet
    assert "--filter-color" in stylesheet
    assert 'href="graph-trade-tools.css?v=2"' in html
    assert 'src="app.js?v=79"' in html
