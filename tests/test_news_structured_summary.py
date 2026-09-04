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
