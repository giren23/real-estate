from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_sentiment_reference_labels_are_outside_the_plot() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    style = (ROOT / "web" / "style.css").read_text(encoding="utf-8")

    assert 'class="sentiment-reference-guide"' in script
    assert 'sentimentOptions.scales.y.title={display:false}' in script
    assert 'sentimentOptions.scales.y1={position:"right",min:0,max:100,title:{display:false}' in script
    assert '{axis:"y",value:40,color:' in script
    assert '{axis:"y",value:40,label:' not in script
    assert ".sentiment-reference-guide" in style


def test_manual_paper_portfolio_is_local_and_requires_confirmation() -> None:
    html = (ROOT / "web" / "market.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "paper.js").read_text(encoding="utf-8")

    assert html.index('id="paperTrading"') > html.index('id="trendCharts"')
    assert "모의 투자" in html
    assert "initialCash" in script and "positions" in script and "orders" in script
    assert "localStorage" in script
    assert "window.confirm" in script
    assert 'id="paperSubmit"' in html and "disabled" in html
    assert "/api/paper-quotes" in script
    assert "slice(0, 10)" in script
    assert "setInterval(refreshQuotes, 15000)" in script
    assert "최대 10종목" in html


def test_market_issues_live_inside_editorial_hub_and_dates_are_quiet() -> None:
    html = (ROOT / "web" / "market.html").read_text(encoding="utf-8")
    editorial = (ROOT / "web" / "editorial.js").read_text(encoding="utf-8")

    assert html.count('id="newsList"') == 1
    assert html.index('id="newsList"') > html.index('id="editorialHub"')
    assert "중요 경제·시장 뉴스" in html
    assert "주식·금리·환율·원자재는 따로 묶었습니다" in html
    assert '<time class="editorial-date"' in editorial
    assert '<small>${escapeHtml(String(item.date' not in editorial
