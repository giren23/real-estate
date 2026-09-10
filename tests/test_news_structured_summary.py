from importlib.util import module_from_spec, spec_from_file_location
import json
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


def test_article_parser_excludes_reader_ui_from_body() -> None:
    page = """<html><article><p>요약보기 자동요약 기사 제목과 주요 문장을 기반으로 자동요약한 결과입니다.</p>
    <p>중동전이 확산하면서 브렌트유는 배럴당 100달러를 넘어섰다.</p>
    <p>로이터 조사에서 응답자 93명 중 70%가 9월 금리 동결을 예상했다.</p>
    <p>닫기 음성으로 듣기 번역 beta 글자 수 10,000자</p>
    <p>로이터 조사에서 금리 인상 전망은 전체 응답자의 30%로 집계됐다.</p></article></html>"""
    sentences = MODULE.article_sentences(page)
    assert len(sentences) == 3
    assert all("음성" not in sentence and "자동요약" not in sentence for sentence in sentences)


def test_mk_refid_body_excludes_ai_explainer_and_footer() -> None:
    page = """<article><p refId="2">WTI 선물은 배럴당 100.13달러에 거래됐다.</p>
    <p refId="3">브렌트유 선물도 배럴당 105.38달러로 상승했다.</p></article>
    <section class="tbl_ai_explain"><p>정부와 금융 시장 모두에게 큰 숙제가 될 것으로 보여요.</p></section>
    <footer><p>주소: 서울특별시 중구 퇴계로 190 전화: 02-2000-2114</p><p>일간신문등록번호: 가00196</p></footer>"""
    sentences = MODULE.article_sentences(page)
    assert len(sentences) == 2
    assert all("숙제가" not in sentence and "주소:" not in sentence for sentence in sentences)


def test_portal_republication_is_a_valid_fallback_not_an_original() -> None:
    assert MODULE.source_role_for_url("https://v.daum.net/v/20260910173927047") == "portal_republication"
    assert MODULE.source_role_for_url("https://news.naver.com/article/001/000000") == "portal_republication"
    assert MODULE.source_role_for_url("https://www.edaily.co.kr/News/Read?newsId=1") == "full_text"


def test_discovered_body_must_match_the_article_title() -> None:
    title = "미국 8월 생산자물가 5.4% 상승"
    assert MODULE.title_matches_sentences(title, [
        "미국 8월 생산자물가가 전년 동월 대비 5.4% 상승하면서 시장의 금리 경계가 커졌다.",
        "에너지 가격은 물가 압력의 주요 변수로 꼽혔다.",
    ])
    assert not MODULE.title_matches_sentences(title, [
        "서울 아파트 분양가는 공급 부족 우려로 상승했다.",
        "주택 시장의 거래량은 감소했다.",
    ])


def test_publisher_listing_similarity_requires_key_numbers_and_topic() -> None:
    original = "미국 8월 생산자물가 5.4% 상승, 연준 금리 인상 경계"
    verified_similar = "미국 8월 생산자물가 5.4% 올라…연준 금리 인상 우려"
    wrong_indicator = "미국 8월 소비자물가 상승…연준 정책 주목"
    assert MODULE.title_similarity(original, verified_similar) >= 0.5
    assert MODULE.title_similarity(original, wrong_indicator) == 0.0


def test_verified_publisher_listing_replaces_feed_title(monkeypatch) -> None:
    original = "미국 8월 생산자물가 5.4% 상승, 연준 금리 인상 경계"
    discovered = "미국 8월 생산자물가 5.4% 올라…연준 금리 인상 우려"
    sentences = [
        "미국의 8월 생산자물가가 전년 동월 대비 5.4% 상승하며 연준의 금리 인상 경계가 커졌다. 기업들은 비용 증가가 소비자 가격으로 전가될 수 있다고 우려했다.",
        "에너지 가격 상승은 기업의 비용 부담과 소비자 물가 압력으로 이어질 수 있다. 시장은 원자재 가격과 서비스 물가가 향후 지표에 미칠 영향을 점검하고 있다.",
        "시장 참가자들은 다음 연방공개시장위원회에서 물가와 고용 지표를 함께 확인할 전망이다. 금리 경로는 향후 발표될 소비와 고용 데이터에 따라 달라질 수 있다.",
        "전문가들은 이번 생산자물가 수치가 소매가격에 반영되는 시점과 범위를 추가로 확인해야 한다고 설명했다. 중앙은행은 단일 지표보다 여러 달의 추세를 기준으로 정책을 판단한다.",
    ]
    monkeypatch.setattr(MODULE, "search_public_article_urls", lambda *_args: [])
    monkeypatch.setattr(MODULE, "publisher_daily_candidates", lambda *_args: [(discovered, "https://example.com/article", "publisher_archive_economy")])
    monkeypatch.setattr(MODULE, "fetch_article_sentences", lambda _url: (sentences, "https://example.com/article"))
    item, fields = MODULE._article_enrichment({"title": original, "publisher": "Benzinga", "date": "2026-09-10", "sources": []})
    assert item["title"] == original
    assert fields["title"] == discovered
    assert fields["feed_title"] == original
    assert fields["title_match_status"] == "similar_article_verified"
    assert fields["article_body_status"] == "full_text"


def test_publisher_search_precedes_public_indexes_and_section_listing(monkeypatch) -> None:
    title = "국제유가 또 급등 WTI 100달러 돌파 브렌트유 105달러"
    sentences = [
        "국제유가가 다시 급등하면서 WTI는 배럴당 100달러를 돌파했고 브렌트유는 105달러를 기록했다.",
        "중동 공급 차질 우려가 원유 선물 가격 상승의 배경으로 지목됐다.",
        "시장 참가자들은 향후 산유국 대응과 재고 지표를 주시하고 있다. " * 8,
    ]
    monkeypatch.setattr(MODULE, "publisher_search_candidates", lambda *_args: [(title, "https://www.mt.co.kr/article", "publisher_search_moneytoday")])
    monkeypatch.setattr(MODULE, "search_public_article_urls", lambda *_args: (_ for _ in ()).throw(AssertionError("publisher search must run first")))
    monkeypatch.setattr(MODULE, "fetch_article_sentences", lambda _url: (sentences, "https://www.mt.co.kr/article"))
    result = MODULE.discover_article_body(title, "머니투데이", "2026-09-10")
    assert result and result[2] == "publisher_search_moneytoday"


def test_search_and_navigation_urls_are_not_article_candidates() -> None:
    assert not MODULE.is_article_candidate_url("https://www.melon.com/search/total/index.htm?q=test")
    assert not MODULE.is_article_candidate_url("https://search.shopping.naver.com/search/all?query=test")
    assert not MODULE.is_article_candidate_url("https://www.newspim.com/")
    assert MODULE.is_article_candidate_url("https://www.edaily.co.kr/News/Read?newsId=123")


def test_translation_is_not_triggered_by_region_for_korean_text() -> None:
    assert not MODULE.is_probably_foreign("월가 금융인 70%가 연준 금리 동결을 예상했다.")
    assert MODULE.is_probably_foreign("Reuters reports that the Federal Reserve may hold rates in September.")


def test_summary_provenance_cleaner_preserves_facts() -> None:
    item = {
        "summary": "연합뉴스 홍길동 기자 2026. 09:30 보도에 따르면 금리 동결 전망은 70%다.",
        "sources": [{"publisher": "연합뉴스", "url": "https://example.com"}],
    }
    MODULE.strip_summary_provenance(item)
    assert item["summary"] == "금리 동결 전망은 70%다"
    assert item["sources"][0]["publisher"] == "연합뉴스"


def test_summary_provenance_cleaner_keeps_decimal_percentages() -> None:
    assert MODULE.clean_summary_provenance("WTI는 전장보다 4.3% 오른 100.13달러에 거래됐다.") == "WTI는 전장보다 4.3% 오른 100.13달러에 거래됐다"


def test_daum_repaired_article_has_clean_summary_prose() -> None:
    payload = json.loads((ROOT / "web" / "content" / "news" / "2026-09-10.json").read_text(encoding="utf-8"))
    item = next(row for row in payload["items"] if "v.daum.net" in str(row.get("article_source_url", "")))
    prose = json.dumps({key: item.get(key) for key in (
        "summary", "easy_explanation", "article_summary", "core_summary", "six_w_one_h",
        "key_figures", "fact_status", "uncertainties", "narrative_paragraphs",
    )}, ensure_ascii=False)
    for forbidden in ("v.daum.net", "로이터", "연합뉴스", "이규화", "요약보기", "자동요약", "음성으로 듣기", "번역 beta"):
        assert forbidden not in prose
    assert item["article_source_url"].startswith("https://v.daum.net/v/")
    assert item["article_body_status"] in {"full_text", "verified_reconstruction"}
