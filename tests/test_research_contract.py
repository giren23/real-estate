from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_analysis_uses_source_traceable_research_contract() -> None:
    payload = json.loads((ROOT / "web" / "content" / "analysis" / "index.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] >= 2
    for item in payload["company_items"] + payload["analysis_items"]:
        assert item["type"] in {"company_analysis", "deep_dive"}
        assert item["as_of"] and item["key_message"]
        assert len(item["sections"]) >= 5
        assert all({"id", "number", "title", "summary", "fact_or_analysis"} <= section.keys() for section in item["sections"])
        assert all(source.get("source_id") and source.get("url", "").startswith("https://") and source.get("source_type") for source in item["sources"])
        assert item["verification_status"] in {"official_verified", "official_source_review_required"}


def test_workflow_passes_dart_key_without_exposing_it() -> None:
    workflow = (ROOT / ".github" / "workflows" / "economic-indicators-daily.yml").read_text(encoding="utf-8")
    assert "DART_API_KEY: ${{ secrets.DART_API_KEY }}" in workflow
    assert "tests/test_research_contract.py" in workflow


def test_daily_selection_withholds_unverified_reports() -> None:
    from scripts.update_editorial_analysis import daily_company_selection

    result = daily_company_selection([{"id":"unverified", "verification_status":"official_source_review_required", "issue_score":100}], {})
    assert result["selection"]["status"] == "no_eligible_company"
    assert result["selection"]["message"] == "오늘은 검증 조건을 통과한 신규 기업이 없음"


def test_dialog_does_not_dim_the_page() -> None:
    css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
    assert ".editorial-dialog::backdrop{background:transparent;backdrop-filter:none}" in css
