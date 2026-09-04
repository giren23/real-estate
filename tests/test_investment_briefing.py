from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_investment_briefing_page_has_top_and_bottom_pagination() -> None:
    html = (ROOT / "web" / "briefing.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "briefing.js").read_text(encoding="utf-8")
    market = (ROOT / "web" / "market.html").read_text(encoding="utf-8")
    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

    assert 'id="briefingPaginationTop"' in html
    assert 'id="briefingPaginationBottom"' in html
    assert "?page=${index + 1}" in script
    assert 'href="briefing.html"' in index
    assert "오늘의 투자 브리핑" in index
    assert 'href="briefing.html"' not in market
    assert index.index('href="market.html"') < index.index('href="briefing.html"')
    assert "briefing-outline" in script and "개발 중" in script


def test_daily_generator_archives_by_date_and_reorders_pages() -> None:
    output_dir = ROOT / "web" / "content" / "investment-briefing"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "update_investment_briefing.py"), "--date", "2026-08-29"], cwd=ROOT, check=True)
    payload = json.loads((output_dir / "2026-08-29.json").read_text(encoding="utf-8"))
    index = json.loads((output_dir / "index.json").read_text(encoding="utf-8"))

    assert payload["date"] == "2026-08-29"
    assert payload["schema_version"] == 2
    assert payload["title"] == "2026년 8월 29일 토요일 아침 — 전수 스캔 투자 브리핑"
    assert [section["id"] for section in payload["sections"]] == ["world", "us", "kr"]
    assert all(section["summary"] == "" for section in payload["sections"])
    page_dates = [page["date"] for page in index["pages"]]
    assert "2026-08-29" in page_dates
    assert page_dates == sorted(page_dates, reverse=True)
    archived_page = next(page for page in index["pages"] if page["date"] == "2026-08-29")
    assert archived_page["file"] == "2026-08-29.json"


def test_morning_workflow_generates_and_commits_the_archive_once() -> None:
    workflow = (ROOT / ".github" / "workflows" / "economic-indicators-daily.yml").read_text(encoding="utf-8")

    assert "python scripts/update_investment_briefing.py" in workflow
    assert "github.event.schedule == '15 22 * * *'" in workflow
    assert "web/content/investment-briefing" in workflow


def test_generator_filters_accident_news_from_investment_briefing() -> None:
    from scripts.update_investment_briefing import select_investment_news

    rows = [
        {"title": "아파트 화재로 주민 대피", "tags": ["부동산"]},
        {"title": "연준 금리 결정과 미국 국채 시장", "tags": ["금리·채권"]},
        {"title": "비트코인 ETF 자금 유출", "tags": ["가상자산"]},
    ]
    selected = select_investment_news(rows)

    assert [row["title"] for row in selected] == [
        "연준 금리 결정과 미국 국채 시장",
        "비트코인 ETF 자금 유출",
    ]
