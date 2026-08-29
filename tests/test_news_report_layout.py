from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_news_report_uses_structured_analysis_and_source_links() -> None:
    script = (ROOT / "web" / "report.js").read_text(encoding="utf-8")

    for heading in ("기사 요약", "핵심 요약"):
        assert heading in script
    assert "주요 경제·시장 뉴스 원문" in script
    assert "원문 보기 ↗" in script
    assert "쉽게 풀어쓰면" not in script
    assert "시장·실물 해석" not in script
    assert "sourceLedgerHtml(item.sources)}${references}" in script
    assert 'if (options.kind === "news") return newsReportHtml(item)' in script
    assert "나무위키" not in script
    assert "https://namu.wiki/Search?q=" in script
    assert "news-keyword" in script


def test_news_page_does_not_render_duplicate_analysis_blocks() -> None:
    script = (ROOT / "web" / "report.js").read_text(encoding="utf-8")
    start = script.index("function newsReportHtml")
    end = script.index("function coverageHtml", start)
    rendered = script[start:end]
    for duplicate in ("요약의 확보 범위", "시간순 사실", "수치·발언 원장", "세계 경제·투자 전문가 총평", "투자자가 먼저 볼 결론"):
        assert duplicate not in rendered


def test_collection_metrics_are_small_bottom_reference_information() -> None:
    style = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
    script = (ROOT / "web" / "report.js").read_text(encoding="utf-8")

    assert "참고 수집정보" in script
    assert ".report-reference .report-metrics" in style
    assert ".report-source-links" in style
