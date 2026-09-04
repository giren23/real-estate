from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location("economic_news_structured", ROOT / "scripts" / "update_economic_news.py")
MODULE = module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_automatic_body_summary_has_stable_json_contract() -> None:
    sentences = [
        "산업통상부는 2026년 9월 4일 광주에서 교육기관을 개교했다고 발표함.",
        "반도체 인력 부족에 대응하기 위해 대학과 기업이 공동 교육과정을 운영할 계획임.",
        "2026년 하반기부터 2030년까지 석박사 400명과 재직자 1,000명 등 총 1,400명을 양성할 계획임.",
        "구체적인 연도별 예산과 취업 성과는 아직 확정되지 않음.",
    ]
    result = MODULE.sixw_summary_from_sentences("반도체 인재 1,400명 양성", "산업통상부", "2026-09-04", sentences)
    for key in ("summary_title", "article_summary", "core_summary", "six_w_one_h", "key_figures", "fact_status", "uncertainties"):
        assert result[key]
    assert 3 <= len(result["article_summary"]) <= 7
    assert set(result["six_w_one_h"]) == {"who", "when", "where", "what", "why", "how", "result"}


def test_number_highlights_are_not_wiki_keywords() -> None:
    result = MODULE.narrative_fields(
        [{"title": "재산 신고", "description": "2026년 재산 3,093만원을 신고했고 한국은행이 확인함.", "publisher": "연합뉴스", "published_at": "2026-09-05"}],
        "재산 신고",
    )
    assert all(not any(char.isdigit() for char in row["term"]) for row in result["highlight_keywords"])
    assert any(row["term"] == "한국은행" for row in result["highlight_keywords"])


def test_browser_renders_complete_numbers_as_plain_bold_not_links() -> None:
    script = (ROOT / "web" / "report.js").read_text(encoding="utf-8")
    assert 'class="news-number"' in script
    assert "!/\\d/.test(row.term)" in script
    assert "조원|억원|만원|원|달러" in script


def test_old_fetched_article_is_upgraded_without_network() -> None:
    item = {
        "title": "주택 공급 계획", "publisher": "연합뉴스", "date": "2026-09-04",
        "article_body_status": "fetched", "narrative_paragraphs": ["정부가 2026년 9월 4일 주택 1만호 공급 계획을 발표함.", "인허가 절차를 거쳐 추진할 계획임.", "구체적인 착공일은 확정되지 않음."],
        "core_summary": "정부가 주택 1만호 공급 계획을 발표함.",
    }
    result = MODULE.upgrade_existing_item(item)
    assert result["article_body_status"] == "full_text"
    assert result["publication_status"] == "detail"
    assert result["summary_schema_version"] == MODULE.SUMMARY_SCHEMA_VERSION
    assert all(key in result for key in MODULE.STRUCTURED_KEYS)


def test_failed_old_article_gets_one_new_schema_retry_then_cooldown() -> None:
    old = {"article_body_status": "unavailable", "article_body_attempts": 3}
    assert MODULE.article_retry_due(old)
    updated = {**old, "summary_schema_version": MODULE.SUMMARY_SCHEMA_VERSION, "next_body_retry_at": "2999-01-01"}
    assert not MODULE.article_retry_due(updated)


def test_feed_only_article_is_kept_for_statistics_not_detail_publication() -> None:
    result = MODULE.upgrade_existing_item({
        "title": "제목뿐인 기사",
        "summary": "제목뿐인 기사",
        "publisher": "매체",
        "date": "2026-09-05",
        "article_body_status": "unavailable",
        "sources": [],
    })
    assert result["publication_status"] == "statistics_only"


def test_substantive_legacy_manual_summary_is_preserved_as_verified_reconstruction() -> None:
    item = {
        "title": "검증된 과거 기사", "publisher": "연합뉴스", "date": "2026-09-04",
        "article_summary": ["정부가 정책을 발표함. " * 8, "관계 기관이 집행 절차와 적용 대상을 설명함. " * 7, "후속 일정과 불확실성을 구분해 설명함. " * 7],
        "core_summary": "정부의 발표 주체와 정책 내용, 집행 절차, 적용 대상, 핵심 수치 및 남은 조건을 원문에 따라 종합한 핵심 요약임. " * 2,
        "six_w_one_h": {key: [key] for key in ("who", "when", "where", "what", "why", "how", "result")},
        "sources": [{"url": "https://example.com/full-article"}],
    }
    result = MODULE.upgrade_existing_item(item)
    assert result["article_body_status"] == "verified_reconstruction"
    assert result["publication_status"] == "detail"


def test_title_only_legacy_item_is_not_promoted() -> None:
    item = {"title": "제목뿐인 기사", "summary": "제목뿐인 기사", "sources": [{"url": "https://example.com"}]}
    assert not MODULE.has_verified_legacy_summary(item)
    assert MODULE.upgrade_existing_item(item)["publication_status"] == "statistics_only"


def test_dialog_backdrop_does_not_blur_or_dim_article_heavily() -> None:
    css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
    assert ".editorial-dialog::backdrop{background:transparent;backdrop-filter:none}" in css
