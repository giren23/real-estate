from __future__ import annotations

import json
from pathlib import Path

from scripts.update_economic_news import importance_details, mark_important


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


def test_news_archive_has_two_paginations_and_clickable_filters() -> None:
    html = (ROOT / "web" / "news.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "news.js").read_text(encoding="utf-8")
    editorial = (ROOT / "web" / "editorial.js").read_text(encoding="utf-8")
    index = json.loads((ROOT / "web" / "content" / "news" / "index.json").read_text(encoding="utf-8"))

    assert 'id="newsPaginationTop"' in html
    assert 'id="newsPaginationBottom"' in html
    assert "data-filter-category" in script
    assert "data-source" in script
    assert "[중요]" in script
    assert "important_items" in editorial
    assert index["important_items"]
    assert index["importance_method"]


def test_latest_policy_is_the_default_selection() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert ".sort((a,b)=>b.date.localeCompare(a.date))" in script
