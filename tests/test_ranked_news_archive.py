from __future__ import annotations

import json
from pathlib import Path

from scripts.update_economic_news import (
    DIRECT_RSS_FEEDS,
    GLOBAL_FEEDS,
    classify_region,
    classify_topic_region,
    enrich_video_news,
    article_sentences,
    importance_details,
    item_from_feed,
    mark_important,
    representative_score,
    select_caption_excerpts,
    sixw_summary_from_sentences,
    fetch_article_sentences,
    youtube_video_id,
)


ROOT = Path(__file__).resolve().parents[1]


def sample(title: str, category: str, reports: int = 2, sources: int = 2) -> dict:
    return {
        "title": title,
        "date": "2026-08-29",
        "tags": [category, "연합뉴스"],
        "category": category,
        "related_reports": reports,
        "source_count": sources,
        "sources": [{"publisher": "연합뉴스"}],
        "metrics": [],
    }


def test_market_news_scores_above_accident_noise() -> None:
    market = importance_details(sample("연준 기준금리와 국채 시장 전망", "금리·채권"))
    accident = importance_details(sample("아파트 화재로 주민 대피", "부동산"))
    assert market["score"] > accident["score"]
    assert market["views_available"] is False


def test_important_news_is_diversified_by_category() -> None:
    rows = [sample(f"연준 기준금리 전망 {index}", "금리·채권", 4, 3) for index in range(7)]
    rows += [sample("코스피 수출 실적 개선", "증시", 3, 2), sample("국제유가 물가 영향", "원자재", 3, 2)]
    marked = mark_important(rows)
    selected = [row for row in marked if row["important"]]
    assert sum(row["category"] == "금리·채권" for row in selected) == 3
    assert {row["category"] for row in selected} >= {"증시", "원자재"}


def test_stock_quote_pages_are_not_selected_as_important_news() -> None:
    quote = sample("Check out the latest ETF stock price and quote", "증시", 5, 4)
    marked = mark_important([quote])
    assert marked[0]["important"] is False
    assert marked[0]["importance"]["investment_relevant"] is False


def test_personal_housing_scandals_are_not_selected_as_important_news() -> None:
    scandal = sample("고위직 위장전입 아파트 부정청약 의혹", "부동산", 4, 3)
    marked = mark_important([scandal])
    assert marked[0]["important"] is False


def test_rate_decision_is_always_ranked_as_important_market_news() -> None:
    rows = [sample(f"경제 일반 기사 {index}", "거시경제", 5, 4) for index in range(8)]
    decision = sample("한국은행 기준금리 0.25%p 인상 결정", "금리·채권", 1, 1)
    marked = mark_important([*rows, decision])

    selected = next(row for row in marked if row["title"] == decision["title"])
    assert selected["important"] is True
    assert selected["importance"]["rate_decision"] is True


def test_representative_article_prefers_trusted_source_and_complete_context() -> None:
    trusted = {"publisher": "연합뉴스", "title": "기준금리 0.25%p 인상", "description": "한국은행 금융통화위원회 결정과 배경을 설명한 기사입니다."}
    unknown = {"publisher": "개인블로그", "title": "금리 올랐다", "description": "짧은 설명"}
    assert representative_score(trusted) > representative_score(unknown)


def test_news_archive_has_two_paginations_and_clickable_filters() -> None:
    html = (ROOT / "web" / "news.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "news.js").read_text(encoding="utf-8")
    editorial = (ROOT / "web" / "editorial.js").read_text(encoding="utf-8")
    index = json.loads((ROOT / "web" / "content" / "news" / "index.json").read_text(encoding="utf-8"))

    assert 'id="newsPaginationTop"' in html
    assert 'id="newsPaginationBottom"' in html
    assert "Math.min(5,total)" in script
    assert 'class="news-page-ellipsis"' in script
    assert 'class="news-page-jump"' in script
    assert 'aria-label="이동할 페이지 번호"' in script
    assert "data-filter-category" in script
    assert "data-source" in script
    assert "[중요]" in script
    assert "isRateDecision" in script
    assert "important_items" in editorial
    assert index["important_items"]
    assert index["importance_method"]


def test_latest_policy_is_the_default_selection() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert ".sort((a,b)=>b.date.localeCompare(a.date))" in script


def test_news_regions_and_real_engagement_are_explicit() -> None:
    assert classify_region("The New York Times", "global") == "us"
    assert classify_region("연합뉴스", "us") == "domestic"
    ranked = sample("연준 금리 결정", "금리·채권", 1, 1)
    ranked["engagement"] = {"rank": 1, "metric": "NYT most viewed"}
    detail = importance_details(ranked)
    assert detail["engagement_score"] > 0
    assert detail["views_available"] is False
    assert "공식 인기기사 순위" in detail["response_proxy"]


def test_news_ui_groups_regions_and_shows_verified_translation_below_link() -> None:
    editorial = (ROOT / "web" / "editorial.js").read_text(encoding="utf-8")
    report = (ROOT / "web" / "report.js").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "economic-indicators-daily.yml").read_text(encoding="utf-8")
    assert all(label in editorial for label in ("국내 뉴스", "미국 뉴스", "기타 글로벌 뉴스"))
    assert "summary_ko" in report and "한국어 번역 요약" in report
    assert "NYT_API_KEY" in workflow and "DEEPL_API_KEY" in workflow


def test_international_important_news_is_rendered_before_domestic() -> None:
    editorial = (ROOT / "web" / "editorial.js").read_text(encoding="utf-8")
    assert '["us","global","domestic"]' in editorial


def test_feed_item_preserves_every_number_with_context_and_time() -> None:
    rows = [{
        "title": "연준이 금리를 0.25%p 올려 5.50%로 결정",
        "description": "2026년 8월 30일 결정이다. 기관은 성장률 2.1%와 물가 3.2%를 제시했다.",
        "publisher": "Reuters",
        "url": "https://example.com/a",
        "published_at": "2026-08-30",
        "published_time": "2026-08-30T08:30+09:00",
        "region": "global",
    }]
    item = item_from_feed(rows[0], rows)
    values = [metric["value"] for metric in item["metrics"] if str(metric["label"]).startswith("기사 수치")]
    assert all(value in values for value in ("0.25%p", "5.50%", "2026년", "8월", "30일", "2.1%", "3.2%"))
    assert "timeline" not in item and "coverage_note" not in item and "sections" not in item
    assert item["narrative_paragraphs"]
    assert item["core_summary"]
    assert all(not any(character.isdigit() for character in row["term"]) for row in item["highlight_keywords"])
    assert item["news_charts"]


def test_topic_origin_overrides_korean_publisher_language() -> None:
    korean_source = [{"publisher": "연합뉴스", "region": "domestic"}]
    assert classify_topic_region("미 연준이 기준금리를 인상했다", korean_source) == "us"
    assert classify_topic_region("중국 인민은행이 위안화 정책을 발표했다", korean_source) == "global"
    assert classify_topic_region("한국은행이 국내 기준금리를 동결했다", korean_source) == "domestic"


def test_major_us_and_global_publishers_are_in_automatic_search() -> None:
    queries = " ".join(row[0] for row in GLOBAL_FEEDS)
    direct = " ".join(row[0] for row in DIRECT_RSS_FEEDS)
    assert "nypost.com" in queries and "nypost.com/business/feed" in direct
    assert all(domain in queries for domain in ("reuters.com", "bbc.com", "theguardian.com", "asia.nikkei.com"))


def test_news_pipeline_is_server_side_and_does_not_require_gpt() -> None:
    collector = (ROOT / "scripts" / "update_economic_news.py").read_text(encoding="utf-8").lower()
    server = (ROOT / "src" / "realestate" / "server.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "economic-indicators-daily.yml").read_text(encoding="utf-8")
    assert "openai" not in collector and "chatgpt" not in collector
    local_loop = "MARKET_REFRESH_HOURS = 4" in server and '("update_economic_news.py", ["--backfill-days", "2", "--limit-per-day", "60"])' in server
    hosted_loop = 'cron: "15 */3 * * *"' in workflow and "python scripts/update_economic_news.py --backfill-days 2 --limit-per-day 60" in workflow
    assert local_loop or hosted_loop


def test_video_caption_helpers_limit_and_preserve_chronology() -> None:
    assert youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert youtube_video_id("https://youtu.be/dQw4w9WgXcQ?t=10") == "dQw4w9WgXcQ"
    assert youtube_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    events = [
        {"start_seconds": 30, "text": "The Federal Reserve raised rates by 25 basis points today."},
        {"start_seconds": 10, "text": "Markets opened lower after the inflation report was published."},
        {"start_seconds": 50, "text": "Investors are now watching jobs and bond yields closely."},
    ]
    excerpts = select_caption_excerpts(events, limit=3, word_limit=30)
    assert [row["start_seconds"] for row in excerpts] == sorted(row["start_seconds"] for row in excerpts)
    assert sum(len(str(row["original"]).split()) for row in excerpts) <= 30


def test_video_news_enrichment_never_invents_missing_dialogue(monkeypatch) -> None:
    item = {"title": "[영상] 시장 브리핑", "sources": [{"url": "https://example.com/video"}]}
    monkeypatch.setattr("scripts.update_economic_news.discover_youtube_url", lambda _url: "")
    enrich_video_news([item])
    assert item["video_transcript"]["status"] == "captions_unavailable"
    assert "excerpts" not in item["video_transcript"]


def test_full_article_is_reduced_to_one_evidence_bound_sixw_summary() -> None:
    page = """<html><article>
    <p>신한글로벌액티브리츠가 원·달러 환율 하락으로 환헤지 정산 부담을 크게 덜게 됐습니다.</p>
    <p>25일 업계에 따르면 계약 기준환율은 달러당 1352원이며 최근 환율 1380원을 적용하면 7700만달러 계약의 정산금은 22억~25억원입니다.</p>
    <p>환율이 1550원일 때 예상 정산금은 150억원 안팎이었습니다.</p>
    <p>회사는 정산 목적으로 확보한 80억원 가운데 남을 수 있는 50억~60억원을 신규 투자에 활용할 계획입니다.</p>
    <p>계약 만기는 내년 1월 19일이며 환율이 1352원까지 하락하면 별도 정산금 없이 종료하는 방안도 검토합니다.</p>
    </article></html>"""
    sentences = article_sentences(page)
    result = sixw_summary_from_sentences("신한글로벌액티브리츠, 고환율 부담 완화", "딜사이트", "2026-08-30", sentences)
    assert len(result["narrative_paragraphs"]) == 1
    summary = result["narrative_paragraphs"][0]
    assert all(value in summary for value in ("신한글로벌액티브리츠", "25일", "1352원", "7700만달러", "22억~25억원", "50억~60억원", "내년 1월 19일"))
    assert result["core_summary"] in summary
    assert result["summary_basis"] == "공개 원문 본문"


def test_collector_enriches_current_and_archived_articles() -> None:
    collector = (ROOT / "scripts" / "update_economic_news.py").read_text(encoding="utf-8")
    assert "enrich_article_bodies(items)" in collector
    assert "enrich_archived_bodies(archive_limit)" in collector
    assert 'parser.add_argument("--archive-enrich-limit"' in collector
    assert "rss.blog.naver.com/dealsite.xml" in collector


def test_naver_rss_article_url_is_normalized_to_post_view(monkeypatch) -> None:
    captured = {}

    class Headers:
        def get(self, _name, default=""):
            return "text/html; charset=utf-8"
        def get_content_charset(self):
            return "utf-8"

    class Response:
        headers = Headers()
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def geturl(self): return captured["url"]
        def read(self, _limit): return b"<article><p>This is a sufficiently long public article sentence for extraction.</p></article>"

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        return Response()

    monkeypatch.setattr("scripts.update_economic_news.urlopen", fake_urlopen)
    fetch_article_sentences("https://blog.naver.com/dealsite/224394383227?fromRss=true")
    assert "PostView.naver" in captured["url"] and "logNo=224394383227" in captured["url"]
