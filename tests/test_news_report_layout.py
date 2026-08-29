from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_news_report_uses_structured_analysis_and_source_links() -> None:
    script = (ROOT / "web" / "report.js").read_text(encoding="utf-8")

    for heading in ("투자자가 먼저 볼 결론", "시간순 사실·발언 전체 기록", "수치·발언 원장", "세계 경제·투자 전문가 총평", "즉시 경고 조건", "다음 확인 일정·값"):
        assert heading in script
    assert "주요 경제·시장 뉴스 원문" in script
    assert "원문 보기 ↗" in script
    assert "쉽게 풀어쓰면" not in script
    assert "시장·실물 해석" not in script
    assert "sourceLedgerHtml(item.sources)}${references}" in script
    assert "coverageHtml(item)" in script
    assert "timelineHtml(legacyNewsTimeline(item))" in script
    assert "factLedgerHtml(legacyFactLedger(item))" in script


def test_collection_metrics_are_small_bottom_reference_information() -> None:
    style = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
    script = (ROOT / "web" / "report.js").read_text(encoding="utf-8")

    assert "참고 수집정보" in script
    assert ".report-reference .report-metrics" in style
    assert ".report-source-links" in style
