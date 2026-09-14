from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_trade_history_supports_sorting_filters_and_pastel_rows() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "web" / "graph-trade-tools.css").read_text(encoding="utf-8")
    area_stylesheet = (ROOT / "web" / "area-benchmark.css").read_text(encoding="utf-8")
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
    assert "data-area-trend-level" in script
    assert "activeLevels.includes" in script
    assert "const scopeGroups=new Map()" in script
    assert 'charts.set("area-trend-comparison:"+group.scope.key,chart)' in script
    assert "같은 행정구역을 한 그래프로 묶음" in script
    assert "Math.max(0,Math.floor(Math.min(...group.finite)-10))" in script
    assert "reverse:true" in script
    assert "tradeCounts" in script
    assert "tablePeriods=periods.filter" in script
    assert "[1,3,6,12,36].includes" in script
    assert "AREA_TREND_WINDOWS" in script
    assert "addStaticAreaTrends" in script
    assert "staticAreaTrendDistrictCodes" in script
    assert "loadStaticAreaTrendRows" in script
    assert "rows.forEach(row=>consumeRow(row))" in script
    assert "84㎡급 거래 " in script
    assert 'districtToken===mappedCity?(tokens[2]||"")' in script
    assert 'value!==null&&value!==undefined&&value!==""' in script
    assert "population.filter(hasFiniteNumber)" in script
    assert "hasFiniteNumber(target.calculations.get(window)?.strength)" in script
    assert "average_exclusive_pyeong_manwon" in script
    assert "Number(right.months)-Number(left.months)" in script
    assert "오른쪽이 최근" in script
    assert "위쪽일수록 최상위에 가까움" in script
    assert "표시할 행정단계" in script
    assert "기간 내 거래" in script
    assert "area-benchmark-summary" in script
    assert "행정구역별 84㎡급 전용 평당가 위치" in script
    assert "administrative_price_positions" in script
    assert "administrative_trend_ranks" in script
    assert 'cache:"no-store"' in script
    assert "renderStaticAreaBenchmarks" in script
    assert "const loaded=await renderStaticAreaBenchmarks" in script
    assert "개발 호재·생활권 공식 요약" in script
    assert "include_development=true" in script
    assert "검증 본문" in script
    assert "--trade-pastel" in script
    assert "--trade-pastel" in stylesheet
    assert "--filter-color" in stylesheet
    assert ".area-trend-chart{height:320px" in area_stylesheet
    assert ".area-trend-chart{height:280px" in area_stylesheet
    assert 'href="graph-trade-tools.css?v=2"' in html
    assert 'href="area-benchmark.css?v=9"' in html
    assert 'href="reb-market-map.css?v=5"' in html
    assert 'src="app.js?v=105"' in html
    assert 'href="development-opportunities.css?v=1"' in html
    assert script.index("areaBenchmarkHtml(board)") < script.index("developmentOpportunityPanelHtml(board)")
    assert 'class="development-opportunity-panel foldable-card"' in script
    assert "distance_status" in script
    assert "[루머]" in script
    assert "공식 원문 우선" in script
    assert 'data-area-trend-level="locality"><span>' in script


def test_every_collapsible_heading_has_a_leading_state_shape() -> None:
    stylesheet = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
    pages = ("index.html", "market.html", "news.html", "analysis.html")

    assert "details>summary::before" in stylesheet
    assert "details[open]>summary::before" in stylesheet
    assert "rotate(-45deg)" in stylesheet
    assert "rotate(45deg)" in stylesheet
    assert ".reb-market-summary>i,.area-benchmark-summary>i{display:none!important}" in stylesheet
    assert ".development-opportunity>summary::after{content:none!important}" in stylesheet
    for page in pages:
        html = (ROOT / "web" / page).read_text(encoding="utf-8")
        assert 'href="style.css?v=41"' in html


def test_three_real_estate_foldable_panels_share_one_visual_contract() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    stylesheet = (ROOT / "web" / "foldable-panels.css").read_text(encoding="utf-8")

    assert 'reb-market-panel foldable-card' in html
    assert 'reb-market-summary foldable-summary' in html
    assert 'graph-trade-history foldable-card' in script
    assert 'area-benchmark-panel foldable-card' in script
    assert script.count('area-benchmark-summary foldable-summary') >= 2
    assert 'href="foldable-panels.css?v=2"' in html
    assert '.foldable-card>.foldable-summary' in stylesheet
    assert 'content:"펼치기"' in stylesheet
    assert 'content:"접기"' in stylesheet
