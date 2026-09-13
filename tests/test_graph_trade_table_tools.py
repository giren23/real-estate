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
    assert "trend_fallback_used" in script
    assert "min:yMin,max:yMax" in script
    assert "data-area-trend-comparison" in script
    assert "Math.floor(Math.min(...finite)-10)" in script
    assert "usable.flatMap" in script
    assert "0%=최상위" in script
    assert "높은 전용 평단가일수록 0%에 가까우며 그래프 위쪽" in script
    assert "기간 내 거래" in script
    assert "area-benchmark-summary" in script
    assert "개발 호재·생활권 공식 확인" in script
    assert "https://www.eum.go.kr/" in script
    assert "https://www.gwanbo.go.kr/" in script
    assert "--trade-pastel" in script
    assert "--trade-pastel" in stylesheet
    assert "--filter-color" in stylesheet
    assert 'href="graph-trade-tools.css?v=2"' in html
    assert 'href="area-benchmark.css?v=4"' in html
    assert 'src="app.js?v=84"' in html
