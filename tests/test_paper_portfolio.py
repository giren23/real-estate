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
    assert "/api/paper/quotes" in script
    assert "slice(0, 20)" in script
    assert "setInterval(refreshQuotes, 15000)" in script
    assert "최대 20종목" in html
    assert 'id="paperQuoteSymbols"' in html and 'value="005930,000660' not in html
    assert "defaultQuoteSymbols" in script
    assert "/api/paper/search" in script
    assert "/api/paper/account" in script
    assert "paper-account-recovery.json" in script


def test_cloud_paper_api_is_read_only_for_quotes_and_hashes_recovery_tokens() -> None:
    worker = (ROOT / "cloudflare-worker" / "worker.js").read_text(encoding="utf-8")
    config = (ROOT / "cloudflare-worker" / "wrangler.toml").read_text(encoding="utf-8")
    migration = (ROOT / "cloudflare-worker" / "migrations" / "0001_paper_portfolios.sql").read_text(encoding="utf-8")
    assert 'crypto.subtle.digest("SHA-256"' in worker
    assert 'crypto.getRandomValues(new Uint8Array(32))' in worker
    assert 'incoming.pathname === "/api/paper/quotes" && request.method === "GET"' in worker
    assert "/api/paper/order" not in worker
    assert 'binding = "PAPER_DB"' in config
    assert "token_hash TEXT NOT NULL" in migration
    assert 'new URL("data/stock_catalog.json", PUBLIC_SITE)' in worker


def test_market_issues_live_inside_editorial_hub_and_dates_are_quiet() -> None:
    html = (ROOT / "web" / "market.html").read_text(encoding="utf-8")
    editorial = (ROOT / "web" / "editorial.js").read_text(encoding="utf-8")

    assert html.count('id="newsList"') == 1
    assert html.index('id="newsList"') > html.index('id="editorialHub"')
    assert html.index('id="editorialHub"') < html.index('id="marketNav"') < html.index('id="trendCharts"')
    assert "중요 경제·시장 뉴스" in html
    assert "주식·금리·환율·원자재는 따로 묶었습니다" in html
    assert '<time class="editorial-date"' in editorial
    assert '<small>${escapeHtml(String(item.date' not in editorial
