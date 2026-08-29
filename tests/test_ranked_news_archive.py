from __future__ import annotations

import json
from pathlib import Path

from scripts.update_economic_news import classify_region, importance_details, mark_important, representative_score


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
