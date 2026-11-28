"""Behavioural regression tests for news extraction, structuring and publication.

All inputs are fixed HTML/JSON fixtures; nothing here touches the network or
the stored archive.  Fixture prose is synthetic text written to reproduce the
failure patterns found in the 2026-11-28 archive (title/subtitle glue, blog
chrome, inline ad scripts, date fragments as actors, missing late figures).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "news"
SPEC = spec_from_file_location("economic_news_quality_regression", ROOT / "scripts" / "update_economic_news.py")
MODULE = module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)
NQ = MODULE.NQ

BLOG_TITLE = "SK리츠, 주유소 매각 속도 더뎌…3년간 15곳 처분"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def blog_fields() -> dict:
    extraction = MODULE.extract_article_page(fixture("blog_publisher_post.html"), BLOG_TITLE)
    identity = NQ.verify_identity(BLOG_TITLE, extraction.sentences, extraction.meta, expected_date="2026-11-28")
    return MODULE._build_verified_fields(BLOG_TITLE, "예시 미디어", "2026-11-28", extraction, "https://blog.naver.com/PostView.naver?blogId=example&logNo=1001", identity)


# --- 1/2: actors -------------------------------------------------------------
def test_dates_particles_and_common_nouns_are_never_actors() -> None:
    sentences = [
        "백민주 SK리츠운용 투자본부장은 26일 간담회에서 “2023년부터 매각을 추진했다”고 밝혔습니다.",
        "이후 2023년 9월부터 매각에 착수했습니다.",
        "은행의 15% 출자 제한에 예외가 인정되면 지분 경쟁이 본격화할 수 있습니다.",
        "현행 은행법은 다른 회사의 의결권 있는 지분증권을 15% 초과해 보유하지 못하게 합니다.",
        "업계에서는 KB·신한·하나금융이 주도권 확보에 나설 것이라는 관측이 나옵니다.",
        "매각 속도가 더 직접적으로 영향을 미치는 곳은 차입금 상환입니다.",
        "Official Cancellation of the deal was formally disclosed by the company.",
        "googletag.cmd.push(function() { googletag.display('ad'); });",
    ]
    who = MODULE.extract_article_actors(sentences, BLOG_TITLE)
    forbidden = {"2023년부", "9월부", "경쟁", "지분증권", "업계에서", "KB", "속도", "Official", "Cancellati", "on", "googletag", "SK", "투자본부", "컨소시엄부"}
    assert not forbidden & set(who), who
    assert "백민주 SK리츠운용 투자본부장" in who
    assert "KB·신한·하나금융" in who


def test_full_company_names_and_person_titles_are_preserved() -> None:
    fields = blog_fields()
    who = fields["six_w_one_h"]["who"]
    assert "SK리츠" in who
    assert "백민주 SK리츠운용 투자본부장" in who
    assert all(not name.endswith("부") or name.endswith("본부장") for name in who), who
    evidence = {row["value"]: row["evidence"] for row in fields["six_w_one_h_evidence"]["who"]}
    assert "SK리츠" in evidence["SK리츠"]


def test_parenthetical_figures_and_tickers_are_not_part_of_actor_names() -> None:
    # Found by the 2026-11-28 archive dry-run: "(IBIT)는" crashed actor
    # extraction, district price tables and "5만 달러 시장" became actors.
    sentences = [
        "블랙록의 아이셰어즈 비트코인 트러스트 (IBIT)는 2990만 달러의 순유입을 기록했다.",
        "광진구(2.29%)는 서울에서 가장 많이 올랐다.",
        "메타플래닛(3350)은 비트코인 추가 매입을 공시했다.",
        "격차를 좁힌 5만 달러 시장은 당분간 관망세가 이어질 것으로 보인다.",
        "업황 회복에 힘입어 2026년 3분기 시장은 반등했다.",
        "서대문구(44.4%→73.5%)는 거래 비중이 크게 늘었다.",
        "삼성전자($005930)는 장중 신고가를 기록했다.",
        "1만1521가구가 이번 달 입주를 시작한다.",
    ]
    who = MODULE.extract_article_actors(sentences, "메타플래닛, 비트코인 추가 매입")
    assert all(name and "(" not in name for name in who), who
    assert not any(name.endswith("시장") or name.startswith(("광진구", "서대문구", "1만")) for name in who), who
    assert "메타플래닛" in who
    assert "삼성전자" in who


def test_common_phrases_are_not_people_or_organisations() -> None:
    sentences = [
        "7명의 위원 가운데 3명이 인상을 주장했다.",
        "이런 가운데 뱅크오브아메리카 전략가는 추가 하락 가능성을 경고했다.",
        "배터리의 전도도가 크게 개선됐다.",
        "걸그룹이 3분기 실적에 기여했다.",
        "이민혁 KB국민은행 이코노미스트는 “내년 환율은 1,320원”이라고 말했다.",
        "이민혁 이코노미스트는 “상고하저 흐름”이라고 덧붙였다.",
        "제롬 파월 연준 의장은 “금리 인하를 서두르지 않겠다”고 말했다.",
    ]
    who = MODULE.extract_article_actors(sentences)
    assert not {"명의 위원", "이런 가운데 뱅크오브아메리카 전략가", "전도도", "걸그룹", "이민혁 이코노미스트"} & set(who), who
    assert "이민혁 KB국민은행 이코노미스트" in who
    assert "제롬 파월 연준 의장" in who


@pytest.mark.parametrize("raw", [
    "(서울=연합인포맥스) 이윤구 기자 = 중국인민은행이 유동성을 공급하겠다고 밝혔다.",
    "[뉴욕=연합뉴스] 홍길동 특파원 = 중국인민은행이 유동성을 공급하겠다고 밝혔다.",
    "(베이징=뉴스1) 김철수 기자 = 중국인민은행이 유동성을 공급하겠다고 밝혔다.",
])
def test_parenthesised_datelines_and_bylines_leave_no_residue(raw: str) -> None:
    assert MODULE.clean_evidence_sentence(raw) == "중국인민은행이 유동성을 공급하겠다고 밝혔다."
    assert MODULE.clean_summary_provenance(raw) == "중국인민은행이 유동성을 공급하겠다고 밝혔다"


def test_attribution_is_removed_but_claim_sources_and_sentences_stay_intact() -> None:
    assert MODULE.clean_summary_provenance("송유관이 멈췄다는 AP통신 보도가 나오자 유가가 올랐다.") == "송유관이 멈췄다는 AP통신 보도가 나오자 유가가 올랐다"
    assert MODULE.clean_summary_provenance("FT는 관계자 2명을 인용해 회의가 연기됐다고 전했다.") == "FT는 관계자 2명을 인용해 회의가 연기됐다고 전했다"
    assert MODULE.clean_summary_provenance("월가 표지판 (사진=AFP) 국제유가가 올랐다.") == "월가 표지판 국제유가가 올랐다"
    assert MODULE.clean_summary_provenance("블룸버그통신 보도에 따르면 애플은 감원을 검토 중이다.") == "애플은 감원을 검토 중이다"


def test_actor_is_left_empty_without_textual_support() -> None:
    who = MODULE.extract_article_actors(["가격이 크게 올랐다.", "거래량은 전월보다 12% 줄었다.", "시장 분위기는 위축됐다."])
    assert who == []


# --- 3: lead preserved ---------------------------------------------------------
def test_title_like_sentence_later_in_body_does_not_drop_the_lead() -> None:
    title = "정부, 공공주택 1만호 공급 계획 발표"
    sentences = MODULE.article_sentences(fixture("late_title_echo.html"), title)
    assert sentences[0].startswith("국토교통부는 28일")
    fields = MODULE.sixw_summary_from_sentences(title, "예시", "2026-11-28", sentences)
    assert fields["article_summary"][0].startswith("국토교통부는 28일")
    assert fields["core_summary"].startswith("국토교통부는 28일")
    assert "국토교통부" in fields["six_w_one_h"]["who"]
    assert any("대응하기 위해" in row for row in fields["six_w_one_h"]["why"])


# --- 4/5: one body source, no chrome/ads/related/AI summary -------------------------
def test_json_ld_and_dom_body_are_not_merged_or_duplicated() -> None:
    extraction = MODULE.extract_article_page(fixture("jsonld_and_dom.html"), "한국은행, 기준금리 3.25% 동결…물가 경계")
    sentences = extraction.sentences
    assert extraction.path == "json_ld_article_body"
    assert len(sentences) == 4
    assert len({NQ.normalized(row) for row in sentences}) == 4
    assert all("메타 설명" not in row and "관련기사" not in row for row in sentences)


def test_blog_chrome_scripts_captions_title_and_ai_summary_are_excluded() -> None:
    extraction = MODULE.extract_article_page(fixture("blog_publisher_post.html"), BLOG_TITLE)
    body = " ".join(extraction.sentences)
    for forbidden in ("블로그 아이디", "이웃새글", "googletag", "그래픽=", "reporter@example.com", "무단전재", "주요 요약", "SK REITs", "#SK리츠", "글보내기", "보유 주유소 101곳·누적 매각률 13%…"):
        assert forbidden not in body, forbidden
    assert extraction.sentences[0].startswith("SK리츠가 주유소를 팔아")
    assert extraction.path == "container" and extraction.boundary_closed
    diagnostics = extraction.diagnostics()
    assert diagnostics["removed"]["title"] >= 1 and diagnostics["removed"]["subtitle"] >= 1
    assert diagnostics["removed"]["after_boundary"] >= 3
    assert diagnostics["meta_description_excluded"] is True


def test_summary_does_not_glue_title_subtitle_and_first_sentence() -> None:
    fields = blog_fields()
    assert not fields["core_summary"].startswith("SK리츠, 주유소 매각")
    assert not fields["article_summary"][0].startswith("SK리츠, 주유소 매각")
    assert fields["summary_quality"]["title_glued"] is False
    assert fields["summary_quality"]["lead_preserved"] is True


# --- 6: short but important sentences and the final condition ------------------------
def test_short_sentences_and_late_conditions_survive() -> None:
    sentences = NQ.paragraph_sentences("금리는 동결됐다. 다만 내년 1월 재검토한다.")
    assert sentences == ["금리는 동결됐다.", "다만 내년 1월 재검토한다."]
    fields = blog_fields()
    summary = " ".join(fields["article_summary"])
    for value in ("86원", "72원", "64원", "66억원", "3,938억원", "142억원"):
        assert value in summary, value
    assert fields["figure_coverage"]["important_total"] >= 8
    assert "주당 22원을 특별배당할 예정" in summary


# --- 7: plan vs execution, forecast vs fact ------------------------------------------
@pytest.mark.parametrize(("sentence", "expected"), [
    ("한국은행은 금리 인하를 검토할 계획이라고 발표했다.", "검토(발표)"),
    ("정부는 내년 상반기에 제도를 시행할 예정이다.", "계획·예정"),
    ("개정안은 1일부터 시행됐다.", "시행"),
    ("금통위는 기준금리를 0.25%p 인하하기로 결정했다.", "결정·확정"),
    ("시장에서는 추가 인하 가능성이 거론된다.", "전망·예상"),
    ("미국의 9월 신규 고용은 시장 예상치보다 늘었다.", "보도된 사실"),
    ("SK리츠가 제시한 4분기 예상 배당금은 주당 86원 안팎입니다.", "전망·예상"),
    ("김 대표는 “내년 투자를 늘리겠다”고 말했다.", "계획·예정(발언)"),
])
def test_statement_status_keeps_plan_forecast_and_fact_apart(sentence: str, expected: str) -> None:
    assert NQ.classify_statement(sentence) == expected


# --- 8: nothing invented ----------------------------------------------------------
def test_absent_where_why_result_stay_empty_and_uncertainty_is_not_denied() -> None:
    fields = MODULE.structured_summary_fields(
        "가나전자 신제품 출시", "예시", "2026-11-28",
        ["가나전자는 신제품 두 종을 출시했다.", "제품 가격은 각각 120만원과 150만원이다."],
        "가나전자는 신제품 두 종을 출시했다.",
    )
    assert fields["six_w_one_h"]["where"] == []
    assert fields["six_w_one_h"]["why"] == []
    assert "추정해 채우지 않음" in fields["six_w_one_h_meta"]["missing_note"]
    assert all("없음" != row for row in fields["uncertainties"])
    assert "불확실성이 없다는 뜻은 아님" in fields["uncertainties"][0]


# --- 9: number formats ------------------------------------------------------------
def test_figures_keep_units_signs_ranges_and_korean_magnitudes() -> None:
    sentences = [
        "기준금리는 0.25%p 내린 연 3.00%가 됐다.",
        "수출은 전년 대비 -3.5% 감소했고 무역수지는 △12억달러를 기록했다.",
        "정산금은 22억~25억원으로 추정되며 비트코인은 6만2000달러에 거래됐다.",
        "국채금리는 8.8bp 올랐고 순이익은 1조2,300억원이었다.",
        "지분율을 15%에서 30%로 높이면 출자 부담은 2배가 된다.",
    ]
    figures = NQ.extract_figures(sentences)
    values = {row["value"]: row for row in figures}
    assert values["0.25%p"]["kind"] == "변동폭(포인트)"
    assert values["3.00%"]["kind"] == "비율"
    assert values["-3.5%"]["negative"] is True
    assert any(value.startswith("△12억") and row["negative"] for value, row in values.items())
    assert "22억~25억원" in values and values["22억~25억원"]["upper"]
    assert any(value.startswith("6만2000달러") for value in values)
    assert values["8.8bp"]["direction"] == "증가·상승"
    assert any(value.startswith("1조2,300억원") for value in values)
    assert "15%에서 30%" in values or {"15%", "30%"} <= set(values)
    assert NQ.unsupported_numbers("순이익은 1조2,300억원", " ".join(sentences)) == []
    assert NQ.unsupported_numbers("순이익은 1조3,300억원", " ".join(sentences)) == ["1조3,300억원"]


def test_relative_dates_are_resolved_with_basis_or_left_unresolved() -> None:
    rows = {row["text"]: row for row in NQ.extract_date_facts([
        "회의는 지난 26일 열렸다.", "결과는 오는 3일 발표된다.", "계약은 30일 만료된다.", "뉴욕증시는 27일(현지시간) 상승했다.",
    ], "2026-11-28")}
    assert rows["지난 26일"]["resolved"] == "2026-11-26" and "발행일 2026-11-28" in rows["지난 26일"]["basis"]
    assert rows["오는 3일"]["resolved"] == "2026-12-03"
    assert rows["30일"]["resolved"] == ""  # day after publication without month: not guessed
    assert rows["27일(현지시간)"]["local_time"] is True


# --- 10: translation is decided by language --------------------------------------------
def test_korean_article_about_the_us_is_never_translated(monkeypatch) -> None:
    monkeypatch.setattr(MODULE, "translate_to_korean", lambda _texts: (_ for _ in ()).throw(AssertionError("must not translate Korean")))
    extraction = NQ.Extraction(paragraphs=[
        "미국 연방준비제도는 27일(현지시간) 기준금리를 0.25%p 인하했다. 트럼프 대통령은 추가 인하를 요구했다. 월가에서는 내년 추가 인하 가능성이 거론된다.",
        "뉴욕증시는 이 소식에 일제히 상승했고 나스닥은 2.3% 올랐다. 10년물 국채금리는 4.1%로 내려왔다.",
    ], path="container", boundary_closed=True)
    identity = NQ.verify_identity("美 연준 금리 0.25%p 인하", extraction.sentences)
    fields = MODULE._build_verified_fields("美 연준 금리 0.25%p 인하", "예시", "2026-11-28", extraction, "https://news.example.com/a/1", identity)
    assert fields["translation_status"] == "not_needed"


def test_failed_or_number_changing_translation_is_not_marked_translated(monkeypatch) -> None:
    fields = {"summary_title": "Fed cuts rates by 0.25 points", "article_summary": ["The Fed cut its policy rate by 0.25 percentage points to 4.00% on Wednesday."], "core_summary": "The Fed cut rates by 0.25 points to 4.00%."}
    monkeypatch.setattr(MODULE, "translate_to_korean", lambda texts: ["연준 금리 인하", "연준이 수요일 정책금리를 0.5%p 내려 4.50%로 정했다.", "연준이 금리를 내렸다."])
    result = MODULE.translate_summary_fields(dict(fields))
    assert result["translation_status"] == "translation_unverified"
    assert result["article_summary"] == fields["article_summary"]
    monkeypatch.setattr(MODULE, "translate_to_korean", lambda texts: None)
    assert MODULE.translate_summary_fields(dict(fields))["translation_status"] == "translation_unavailable"


# --- 11: title + RSS/meta description never becomes full text --------------------------
def test_title_and_meta_description_alone_are_not_a_body() -> None:
    title = "美 연준 금리 0.25%p 인하 결정"
    extraction = MODULE.extract_article_page(fixture("title_only.html"), title)
    identity = NQ.verify_identity(title, extraction.sentences, extraction.meta)
    status, _ = NQ.body_status(extraction.sentences, boundary_closed=extraction.boundary_closed, path=extraction.path, identity_ok=bool(identity["ok"]))
    assert status == "unavailable"
    assert not any("메타 요약" in row for row in extraction.sentences)


# --- found by the 2026-11-28 archive dry-run: layouts that hid the whole body --------
BODY_ROWS = [
    "가나시는 28일 노후주택 단열 공사비를 가구당 최대 500만원까지 지원한다고 밝혔다.",
    "지원 대상은 준공 20년이 지난 단독주택과 연립주택 120가구다.",
    "신청은 다음 달 1일부터 15일까지 시청 누리집에서 받는다.",
    "시 관계자는 “에너지 비용 부담을 줄이는 데 도움이 될 것”이라고 말했다.",
]
LAYOUT_TITLE = "가나시, 노후주택 단열 공사비 최대 500만원 지원"


def test_body_container_inside_layout_column_is_read_and_related_list_cut() -> None:
    body = "".join(f"<div>{row}</div>" for row in BODY_ROWS)
    page = (f"<html><head><meta property='og:title' content='{LAYOUT_TITLE}'></head><body>"
            f"<section class='aside_left'><div class='news_body'>{body}<p>주요뉴스</p>"
            "<dl><dd>다른 기사 제목이 여기에 이어서 나온다…'충격 반전'</dd><dd>또 다른 인기 기사 제목도 여기에 붙어 있다[그해오늘]</dd></dl></div></section>"
            "<aside class='right'><div class='news_text'>사이드바 인기 기사 목록</div></aside></body></html>")
    extraction = NQ.extract_article(page, LAYOUT_TITLE)
    assert extraction.path == "container"
    assert extraction.sentences == BODY_ROWS
    assert extraction.removed.get("layout_zone_ignored") == 1


def test_nested_body_marker_and_article_inside_layout_zones_are_read() -> None:
    rows = BODY_ROWS + ["시는 올해 처음 시행한 사업에서 신청 가구의 85%가 공사를 마쳤다고 설명했다.", "내년에는 지원 대상을 공동주택까지 넓히는 방안을 검토하고 있다."]
    body = "".join(f"<p>{row}</p>" for row in rows)
    # donga: div.view_body > div.inner_aside > section.news_view
    nested = (f"<html><body><div class='view_body'><div class='inner inner_aside'><section class='news_view'>{body}"
              "<div class='related_news'><p>관련 기사 제목이 여기에 붙어 있다고 가정한 긴 문장입니다.</p></div>"
              "<div class='tag_list'>#노후주택 #단열공사 #가나시</div><div>몸 풀기부터 체력 증진까지, 한 번에 다 된다는 다른 기사 홍보 문구다”</div>"
              "</section></div></div></body></html>")
    extraction = NQ.extract_article(nested, LAYOUT_TITLE)
    assert extraction.sentences == rows
    # TV조선: section.news.menu > article (no body class at all)
    article = f"<html><body><section class='news menu sub-n article'><article><div class='text-box'>{body}</div></article></section></body></html>"
    extraction = NQ.extract_article(article, LAYOUT_TITLE)
    assert extraction.path == "article_tag" and extraction.sentences == rows
    # A real <aside> stays excluded even when it holds an <article>.
    aside = f"<html><body><aside class='menu'><article>{body}</article></aside></body></html>"
    assert NQ.extract_article(aside, LAYOUT_TITLE).sentences == []


def test_quality_score_does_not_contradict_a_passed_identity_check() -> None:
    # The body never repeats the headline's words, but the page title and date
    # confirm the article: the score must not carry "제목·본문 불일치".
    title = "Seoul district eases renovation rules"
    extraction = NQ.Extraction(paragraphs=[" ".join(BODY_ROWS)], path="container", boundary_closed=True, meta={"og:title": title})
    identity = {"ok": True, "reasons": [], "checks": {"page_title": "match"}}
    fields = MODULE._build_verified_fields(title, "예시", "2026-11-28", extraction, "https://news.example.com/1", identity)
    assert "제목·본문 불일치" not in fields["summary_quality"]["deductions"]
    assert fields["summary_quality"]["title_body_match"] is True


def test_page_wrapped_in_a_form_is_read_and_attachment_names_dropped() -> None:
    body = "".join(f"<p>{row}</p>" for row in BODY_ROWS)
    page = (f"<html><body><form id='obj_search'><input name='q'><div class='postBody'>{body}"
            "<p>바로보기 보도자료 지원사업 안내.hwpx 바로듣기 보도자료 지원사업 안내.hwpx</p><p>참여 가구 안내문 시안 132404.png</p></div></form></body></html>")
    extraction = NQ.extract_article(page, LAYOUT_TITLE)
    assert extraction.sentences == BODY_ROWS
    assert extraction.removed.get("attachment") == 2


def test_free_arc_story_data_is_read_but_subscriber_story_is_not() -> None:
    story = {"type": "story", "content_restrictions": {"content_code": "0"},
             "content_elements": [{"type": "image", "url": "x.jpg"}] + [{"type": "text", "content": f"<b>{row}</b>"} for row in BODY_ROWS]}
    page = f"<html><body><div id='fusion-app'></div><script>Fusion.globalContent={json.dumps(story, ensure_ascii=False)};Fusion.spa=true;</script></body></html>"
    extraction = NQ.extract_article(page, LAYOUT_TITLE)
    assert extraction.path == "arc_fusion_content"
    assert extraction.sentences == BODY_ROWS
    story["content_restrictions"]["content_code"] = "subscriber"
    locked = f"<html><body><script>Fusion.globalContent={json.dumps(story, ensure_ascii=False)};</script></body></html>"
    assert NQ.extract_article(locked, LAYOUT_TITLE).sentences == []


def test_page_data_content_array_is_read_but_never_behind_a_paywall(monkeypatch) -> None:
    arrange = [{"type": "image", "content": "사진 설명 ⓒ 예시"}] + [{"type": "text", "content": row} for row in BODY_ROWS]
    page = f"<html><body><div id='app'></div><script>window.__DATA__={{\"article\":{{\"contentArrange\":{json.dumps(arrange, ensure_ascii=False)}}}}}</script></body></html>"
    extraction = NQ.extract_article(page, LAYOUT_TITLE)
    assert extraction.path == "embedded_content_array" and extraction.sentences == BODY_ROWS

    class Response:
        def __init__(self, body: str) -> None:
            self.body, self.headers = body.encode("utf-8"), {"Content-Type": "text/html; charset=utf-8"}
            self.headers = type("H", (), {"get": lambda _self, key, default="": "text/html; charset=utf-8", "get_content_charset": lambda _self: "utf-8"})()
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def geturl(self): return "https://news.example.com/1"
        def read(self, _limit=0): return self.body

    walled = page.replace("<div id='app'></div>", "<div class='paywall'>회원 전용 기사입니다</div>")
    monkeypatch.setattr(MODULE, "urlopen", lambda request, timeout=0, **_kwargs: Response(walled))
    with pytest.raises(MODULE.AccessRestricted):
        MODULE.fetch_article("https://news.example.com/1", LAYOUT_TITLE)
    monkeypatch.setattr(MODULE, "urlopen", lambda request, timeout=0, **_kwargs: Response(page))
    assert MODULE.fetch_article("https://news.example.com/1", LAYOUT_TITLE)[0].sentences == BODY_ROWS


def test_json_ld_teaser_does_not_hide_the_complete_page_body() -> None:
    teaser = {"@type": "NewsArticle", "headline": LAYOUT_TITLE, "articleBody": BODY_ROWS[0] + " 지원 규모와 신청 방법, 대상 주택의 조건과 공사 범위, 신청 서류와 접수 일정은 시청 누리집 공지사항과 각 읍면동 행정복지센터 안내문에서 확인할 수 있으며 자세한 내용은 본문에서 이어서 안내한다는 요약문이다"}
    body = "".join(f"<p>{row}</p>" for row in BODY_ROWS)
    page = (f"<html><head><script type='application/ld+json'>{json.dumps(teaser, ensure_ascii=False)}</script></head>"
            f"<body><div class='article_body'>{body}</div></body></html>")
    extraction = NQ.extract_article(page, LAYOUT_TITLE)
    assert extraction.path == "container"
    assert extraction.sentences == BODY_ROWS
    assert extraction.removed.get("structured_body_too_short") == 1


def test_reprocess_never_hides_a_summary_when_only_extraction_failed(monkeypatch) -> None:
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = spec_from_file_location("reprocess_news_regression", ROOT / "scripts" / "reprocess_news.py")
    reprocess = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(reprocess)
    item = {"id": "news-x", "title": LAYOUT_TITLE, "date": "2026-11-28", "publisher": "예시", "article_source_url": "https://news.example.com/1",
            "article_body_status": "full_text", "publication_status": "detail", "article_summary": BODY_ROWS[:2]}
    empty = NQ.Extraction(path="paragraph_fallback", meta={"og:title": LAYOUT_TITLE})
    monkeypatch.setattr(reprocess.U, "fetch_article", lambda url, title="": (empty, url))
    fields, error = reprocess.refetch_fields(item)
    assert fields is None and error.startswith("본문 추출 실패")
    assert reprocess.decide(item, fields, error, demote=True).startswith("keep:")
    other_body = ["전혀 다른 회사가 신제품을 출시했다고 밝혔다. 판매는 다음 달부터 전국 매장에서 시작된다. 가격은 지난 모델과 같은 수준으로 정했다."]
    # Body avoids the headline's words but the page title is the same: held, not hidden.
    same_page = NQ.Extraction(paragraphs=other_body, path="container", boundary_closed=True, meta={"og:title": LAYOUT_TITLE})
    monkeypatch.setattr(reprocess.U, "fetch_article", lambda url, title="": (same_page, url))
    fields, error = reprocess.refetch_fields(item)
    assert error.startswith("제목·본문 일부 불일치(판정 보류)")
    assert reprocess.decide(item, fields, error, demote=True).startswith("keep:")
    other = NQ.Extraction(paragraphs=other_body, path="container", boundary_closed=True, meta={"og:title": "다른 회사 신제품 출시"})
    monkeypatch.setattr(reprocess.U, "fetch_article", lambda url, title="": (other, url))
    fields, error = reprocess.refetch_fields(item)
    assert error.startswith("제목·본문 불일치")
    assert reprocess.decide(item, fields, error, demote=True).startswith("demote:")


# --- 2026-11-28 evening: remaining failure types of the archive re-run -------
def _reprocess_module(name: str):
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = spec_from_file_location(name, ROOT / "scripts" / "reprocess_news.py")
    module = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_utility_css_class_with_figcaption_does_not_turn_the_body_into_captions() -> None:
    body = "".join(f"<p>{row}</p>" for row in BODY_ROWS)
    page = (f"<html><body><article><div class='fw_400 [&_figcaption]:fs_14px [&>:first-child]:!mt-0'>"
            f"<figure><img src='a.jpg'><figcaption>현장 사진 / 사진 = 뉴스1 제공</figcaption></figure>{body}</div></article></body></html>")
    extraction = NQ.extract_article(page, LAYOUT_TITLE)
    assert extraction.sentences == BODY_ROWS
    assert extraction.removed.get("caption") == 1


def test_itemprop_article_body_is_a_container_even_with_a_data_table() -> None:
    table = "<table><tr><td>항목</td><td>내용</td></tr><tr><td>준공</td><td>1996년 10월</td></tr></table>"
    page = (f"<html><body><section class='sec_body'><div class='news_cnt_detail_wrap' itemprop='articleBody'>"
            f"{BODY_ROWS[0]}<br><br>{table}{BODY_ROWS[1]} {BODY_ROWS[2]}<br>{BODY_ROWS[3]}</div></section>"
            "<p>다른 기사로 이어지는 추천 문단이 본문 밖에 길게 붙어 있다고 가정한 문장이다.</p></body></html>")
    extraction = NQ.extract_article(page, LAYOUT_TITLE)
    assert extraction.path == "container"
    assert extraction.sentences == BODY_ROWS


def test_anchor_cue_in_a_broadcast_transcript_is_not_the_closing_byline() -> None:
    rows = ["[앵커]", "서울 아파트 매물이 연중 최고 수준까지 늘었지만, 거래는 오히려 줄고 있습니다.", "매수세가 위축된 영향이 크다는 분석인데요.",
            "취재기자 연결해 자세한 내용 알아보겠습니다. 김웅래 기자!", "[기자]", "부동산 정보업체 자료를 보면 오늘 기준 서울 아파트 매물은 7만9천여 건입니다.",
            "지난달 매매 거래량은 3천9백여 건으로 지난 5월보다 56% 줄었습니다.", "YTN 김웅래입니다.", "김웅래 기자 woong@example.com"]
    page = "<html><body><div id='CmAdContent' class='paragraph'>" + "".join(f"<span>{row}</span><br>" for row in rows) + "</div></body></html>"
    sentences = NQ.extract_article(page, "서울 아파트 매물 8만 건 육박...매수세 위축에 거래 절벽").sentences
    assert "지난달 매매 거래량은 3천9백여 건으로 지난 5월보다 56% 줄었습니다." in sentences
    assert not any("woong@" in sentence for sentence in sentences)


def test_multiply_escaped_json_ld_body_in_english_is_not_code() -> None:
    body = ("&amp;lt;p&amp;gt;Wall Street&amp;amp;#039;s wider index S&amp;amp;amp;P 500 trades just 2% away from a record high.&amp;lt;/p&amp;gt;"
            "&amp;lt;p&amp;gt;Analysts expect a return to growth in earnings next year as spending recovers across the sector.&amp;lt;/p&amp;gt;"
            "&amp;lt;p&amp;gt;Nearly 84% of index members are down at least 10% from their peaks, the report said.&amp;lt;/p&amp;gt;")
    page = ("<html><head><script type='application/ld+json'>" + json.dumps({"@type": "NewsArticle", "articleBody": body})
            + "</script></head><body></body></html>")
    extraction = NQ.extract_article(page, "84 Percent Stocks In Correction, Yet S&P 500 Nears Record High")
    assert extraction.path == "json_ld_article_body"
    assert extraction.sentences[0] == "Wall Street's wider index S&P 500 trades just 2% away from a record high."
    assert len(extraction.sentences) == 3 and not extraction.removed.get("code")


def test_next_js_payload_article_html_and_text_row_are_read() -> None:
    html_body = "<div id='ijam_content'>" + "".join(f"<p>{row}</p>" for row in BODY_ROWS) + "</div>"
    state = json.dumps({"data": {"articleTitle": LAYOUT_TITLE, "articleContent": html_body}}, ensure_ascii=False)
    push = "self.__next_f.push(" + json.dumps([1, f"7:[\"$\",\"div\",null,{state}]\n"], ensure_ascii=False) + ")"
    page = f"<html><body><div class='MuiBox-root'>로딩 중</div><script>{push}</script></body></html>"
    extraction = NQ.extract_article(page, LAYOUT_TITLE)
    assert extraction.path == "next_flight_article_html" and extraction.sentences == BODY_ROWS
    # Large bodies are moved to a text row ("$82" → "82:T<hex bytes>,…").
    text = "\n\n".join(BODY_ROWS)
    row = f"82:T{len(text.encode('utf-8')):x},{text}"
    ref_state = json.dumps({"articleContent": "$82"})
    page = ("<html><body><script>self.__next_f.push(" + json.dumps([1, f"5:{ref_state}\n"]) + ")</script>"
            "<script>self.__next_f.push(" + json.dumps([1, row + "9:null\n"], ensure_ascii=False) + ")</script></body></html>")
    assert NQ.extract_article(page, LAYOUT_TITLE).sentences == BODY_ROWS


def test_disclaimer_container_falls_back_to_page_paragraphs_but_not_to_teasers() -> None:
    body = "".join(f"<p>{row}</p>" for row in BODY_ROWS)
    page = (f"<html><body><div id='common_content_wrap'>{body}"
            "<div class='article_view_disclaimer'>본 기사는 시장 데이터 및 차트 분석을 바탕으로 작성되었으며, 특정 종목에 대한 투자 권유가 아닙니다.</div></div></body></html>")
    extraction = NQ.extract_article(page, LAYOUT_TITLE)
    assert extraction.sentences == BODY_ROWS and extraction.removed.get("weak_container_fallback") == 1
    teasers = "".join(f"<li><p>{row}</p></li>" for row in ["'상간 소송' 박지윤, 뜻밖의 고백 \"사실혼 배우자 있는 사람을...\"",
                                                           "업계서 나온 뜻밖의 예언 \"삼성전자 50만원은...\"", "조국, 의미심장한 발언 \"오세훈 시장, 한동훈 의원 보다...\""])
    short = (f"<html><body><article><div class='article_body'><p>{BODY_ROWS[0]}</p></div>"
             f"<ul class='list'>{teasers}</ul></article></body></html>")
    assert NQ.extract_article(short, LAYOUT_TITLE).sentences == BODY_ROWS[:1]


def test_paywall_notice_read_through_the_loose_reading_is_access_restricted() -> None:
    page = ("<html><body><div class='modal_dialog'><p>중앙일보로 이동합니다.</p><p>새 창을 닫으면 이 화면으로 돌아옵니다.</p></div>"
            "<div class='article_body'><p>구독</p></div><div class='paywall_wrap'><p id='paywall_heading' class='paywall_headline'>구독자 전용 콘텐츠입니다</p></div>"
            "<p>계정/결제 관리를 위해 로 이동합니다.</p><p>Global Money Club 멤버는 매월 5개 의 콘텐츠를 누구에게나 선물할 수 있어요.</p></body></html>")
    with pytest.raises(MODULE.AccessRestricted):
        MODULE.read_article_page(page, LAYOUT_TITLE, "https://www.example.com/gmc/article/1")


def test_page_bytes_are_decoded_whatever_the_server_declares() -> None:
    import gzip as gzip_module

    class Headers:
        def __init__(self, values: dict, charset: str | None) -> None:
            self.values, self.charset = values, charset
        def get(self, key, default=""):
            return self.values.get(key, default)
        def get_content_charset(self):
            return self.charset

    text = f"<html><body><p>{BODY_ROWS[0]}</p></body></html>"
    assert MODULE._decode_page(gzip_module.compress(text.encode("utf-8")), Headers({}, "utf-8")) == text  # gzip sent unasked
    assert MODULE._decode_page(text.encode("utf-8"), Headers({}, "utf-8,gbk")) == text  # "unknown encoding: utf-8,gbk"
    euc = f"<html><head><meta http-equiv='Content-Type' content='text/html; charset=euc-kr'></head><body>{BODY_ROWS[0]}</body></html>"
    assert MODULE._decode_page(euc.encode("euc-kr"), Headers({}, None)) == euc


def test_download_retries_a_timeout_but_never_relaxes_certificate_trust(monkeypatch) -> None:
    import ssl
    from urllib.error import URLError

    class Response:
        headers = type("H", (), {"get": lambda _s, key, default="": "text/html" if key == "Content-Type" else default, "get_content_charset": lambda _s: "utf-8"})()
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def geturl(self): return "https://news.example.com/1"
        def read(self, _limit=0): return f"<p>{BODY_ROWS[0]}</p>".encode("utf-8")

    calls = []

    def flaky(request, timeout=0, **kwargs):
        calls.append(timeout)
        if len(calls) == 1:
            raise TimeoutError("The read operation timed out")
        return Response()

    monkeypatch.setattr(MODULE, "urlopen", flaky)
    page, _final, _type = MODULE._download_page("https://news.example.com/1", "text/html")
    assert BODY_ROWS[0] in page and calls == [12, 30]

    attempts = []

    def missing_intermediate(request, timeout=0, context=None, **_kwargs):
        attempts.append(context)
        if len(attempts) == 1:
            raise URLError(ssl.SSLCertVerificationError(1, "certificate verify failed: unable to get local issuer certificate"))
        return Response()

    monkeypatch.setattr(MODULE, "urlopen", missing_intermediate)
    monkeypatch.setattr(MODULE.socket, "create_connection", lambda *_a, **_kw: pytest.fail("unauthenticated certificate probes are forbidden"))
    with pytest.raises(URLError):
        MODULE._download_page("https://news.example.com/1", "text/html")
    assert len(attempts) == 1
    assert attempts[0].verify_mode == ssl.CERT_REQUIRED and attempts[0].check_hostname


def test_gone_pages_bot_checks_and_data_pages_are_classified_not_read(monkeypatch) -> None:
    with pytest.raises(MODULE.ArticleGone):
        MODULE.read_article_page("<script>alert('존재하지 않는 링크 입니다.\\n링크를 확인해 주세요.'); history.back(); </script>", LAYOUT_TITLE)
    with pytest.raises(MODULE.AccessRestricted):
        MODULE.read_article_page("<html><title>You are being redirected...</title><script>var sucuri_cloudproxy_js='';</script></html>", LAYOUT_TITLE)
    monkeypatch.setattr(MODULE, "_download_page", lambda *args, **kwargs: pytest.fail("data pages are not downloaded"))
    with pytest.raises(MODULE.NotAnArticlePage):
        MODULE.fetch_article("https://markets.ft.com/data/etfs/tearsheet/summary?s=VWO:PCQ:USD", "Vanguard FTSE Emerging Markets")
    reprocess = _reprocess_module("reprocess_news_classify_regression")
    item = {"id": "x", "title": LAYOUT_TITLE, "article_body_status": "full_text", "publication_status": "detail", "article_summary": BODY_ROWS[:2]}
    assert reprocess.decide(item, None, "기사 아님: 기사 아님(시세·펀드 데이터 페이지)", demote=True).startswith("demote:")
    assert reprocess.decide(item, None, "원문 삭제: 원문 삭제(HTTP 404)", demote=True).startswith("keep:")


def test_only_a_stored_summary_that_is_page_debris_is_hidden_when_refetch_fails() -> None:
    reprocess = _reprocess_module("reprocess_news_stored_regression")
    base = {"id": "x", "title": LAYOUT_TITLE, "article_body_status": "full_text", "publication_status": "detail"}
    clean = dict(base, article_summary=BODY_ROWS[:3])
    assert reprocess.stored_summary_problem(clean) == ""
    assert reprocess.decide(clean, None, "접근 제한: 접근 제한 HTTP 403", demote=True).startswith("keep:")
    debris = {
        "페이지 코드 혼입": [BODY_ROWS[0] + " photo_img 클래스를 가진 모든 요소 찾기 및 제거 var photoImgElements = ('.photo_img');"],
        "유료·안내 문구": ["Global Money Club 멤버는 매월 5개 의 콘텐츠를 누구에게나 선물할 수 있어요."],
        "다른 기사 제목 목록": ["美재무 연준 과잉 긴축 시 실수 가능성 02. 건설사 현장서 중대재해 발생 03 준감위 주주환원 논란 이번 주 심의"],
        "제목과 무관한 내용": ["오라클의 재무 보고서에 공개된 GPU 재계약 데이터는 컴퓨팅 인프라 기업들에게 긍정적인 신호를 보내고 있다."],
    }
    for reason, summary in debris.items():
        item = dict(base, article_summary=summary)
        if reason == "제목과 무관한 내용":
            item["identity_check"] = {"ok": False, "page_title_similarity": 0.0}
        assert reprocess.stored_summary_problem(item) == reason
        assert reprocess.decide(item, None, "본문 추출 실패(경로 none, 0문장, 페이지 제목 일치)", demote=True).startswith(f"demote:저장 요약 오염({reason})")
        assert reprocess.decide(item, None, "본문 추출 실패", demote=False).startswith("keep:")
    # An English headline over a Korean translation shares no keyword and is fine.
    translated = dict(base, title="Fed officials signal caution on rates", article_summary=BODY_ROWS[:2])
    assert reprocess.stored_summary_problem(translated) == ""


def test_replay_page_of_question_headings_and_disclaimers_are_not_a_body() -> None:
    questions = ["뉴욕증시 나흘째 하락‥이유는?", "트럼프 5천달러 공약‥국채 금리에 영향?", "연준의 금리인상 확률 높아졌나?", "코스피 하락세 원인은?", "향후 원·달러 환율 전망은?"]
    page = ("<html><body><div class='news_txt'><p>Your browser doesn't support HTML5 video.</p>"
            + "".join(f"<p>{row}</p>" for row in questions) + "</div></body></html>")
    extraction = NQ.extract_article(page, "[경제쏙] 트럼프 5천 달러 살포, 세계 경제 휘청")
    assert extraction.sentences == [] and extraction.removed.get("question_list") == 1
    mai = ("<html><body><div class='news_cnt_detail_wrap' itemprop='articleBody'>" + "".join(f"<p>{row}</p>" for row in BODY_ROWS)
           + "<p>AI 기술 특성상 데이터 처리 과정 중 오류가 있을 수 있으며 정확한 정보는 국토교통부 실거래 데이터를 확인하시기 바랍니다.</p></div></body></html>")
    assert NQ.extract_article(mai, LAYOUT_TITLE).sentences == BODY_ROWS
    assert MODULE.NON_ARTICLE_URL.search("https://www.investing.com/etfs/qqbf")
    assert not MODULE.NON_ARTICLE_URL.search("https://kr.investing.com/news/stock-market-news/article-1234")


def test_an_empty_collection_never_creates_a_blank_day_page(tmp_path, monkeypatch) -> None:
    from datetime import date as date_type
    monkeypatch.setattr(MODULE, "NEWS_DIR", tmp_path)
    MODULE.write_day(date_type(2026, 11, 29), [])  # 00:00 run: the new day's feed has no items yet
    assert not (tmp_path / "2026-11-29.json").exists()


def test_reprocess_apply_never_clobbers_a_concurrent_update(tmp_path) -> None:
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = spec_from_file_location("reprocess_news_apply_regression", ROOT / "scripts" / "reprocess_news.py")
    reprocess = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(reprocess)
    moved = {"id": "a", "core_summary": "옛 요약 A", "extraction_version": 1}
    refreshed = {"id": "b", "core_summary": "옛 요약 B", "extraction_version": 1}
    gone = {"id": "c", "core_summary": "옛 요약 C", "extraction_version": 1}
    day = tmp_path / "2026-11-27.json"
    # The collector inserted a new item at the top and re-enriched "b" meanwhile.
    stored = [{"id": "new"}, dict(moved), dict(refreshed, core_summary="정기 수집이 새로 쓴 요약", extraction_version=9)]
    day.write_text(json.dumps({"date": day.stem, "items": stored}, ensure_ascii=False), encoding="utf-8")
    changes = {0: (moved, dict(moved, core_summary="새 요약 A")), 1: (refreshed, dict(refreshed, core_summary="재처리 요약 B")),
               2: (gone, dict(gone, core_summary="새 요약 C"))}
    applied, skipped = reprocess.apply_changes(day, changes)
    items = json.loads(day.read_text(encoding="utf-8"))["items"]
    assert applied == 1 and len(skipped) == 2
    assert [row["id"] for row in items] == ["new", "a", "b"]
    assert items[1]["core_summary"] == "새 요약 A"
    assert items[2]["core_summary"] == "정기 수집이 새로 쓴 요약"


def test_paragraphs_without_a_closed_boundary_are_at_most_an_excerpt() -> None:
    sentences = ["가나은행은 28일 정기예금과 적금 금리를 상품에 따라 0.2%p에서 0.3%p까지 올린다고 밝혔다."] + [f"인상 대상은 {n}개월 만기 정기예금 상품이며 영업점과 모바일 앱에서 새로 가입하거나 만기 후 재예치하는 고객에게 모두 같은 금리가 적용된다." for n in (6, 12, 24, 36)]
    assert NQ.body_status(sentences, boundary_closed=False, path="paragraph_fallback", identity_ok=True) == ("verified_excerpt", "boundary_unconfirmed")
    assert NQ.body_status(sentences, boundary_closed=True, path="container", identity_ok=True)[0] == "full_text"


def test_access_restriction_is_recorded_not_bypassed(monkeypatch) -> None:
    from urllib.error import HTTPError

    def refuse(request, timeout=0, **_kwargs):
        raise HTTPError(request.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(MODULE, "urlopen", refuse)
    with pytest.raises(MODULE.AccessRestricted):
        MODULE.fetch_article("https://news.example.com/paywalled")


# --- 12: similar article is not saved as the original ---------------------------------
def test_searched_article_with_different_key_number_or_date_is_rejected() -> None:
    title = "미국 8월 생산자물가 5.4% 상승"
    other = NQ.Extraction(paragraphs=["미국 8월 소비자물가가 3.1% 올랐다. 에너지 가격이 상승을 이끌었다. 시장은 연준의 다음 회의를 주시했다."], path="container", boundary_closed=True, meta={"og:title": "미국 8월 소비자물가 3.1% 상승"})
    ok, identity = MODULE._discovered_candidate_ok(title, "미국 8월 소비자물가 3.1% 상승", other, "2026-09-10")
    assert not ok and identity["reasons"]
    stale = NQ.Extraction(paragraphs=["미국 8월 생산자물가가 5.4% 상승했다. 에너지 가격 상승이 컸다. 시장은 금리 경로를 다시 계산했다."], path="container", boundary_closed=True, meta={"og:title": title, "article:published_time": "2025-09-10T09:00:00+09:00"})
    ok, identity = MODULE._discovered_candidate_ok(title, title, stale, "2026-09-10")
    assert not ok and any("발행일" in reason for reason in identity["reasons"])


# --- 13: failed verification stays hidden in backend and frontend ------------------------
def test_quality_gate_failure_is_never_publishable_even_with_long_summary() -> None:
    item = {
        "publication_status": "detail", "article_body_status": "full_text",
        "quality_gate": {"passed": False, "failures": ["요약에 UI·코드 문장 혼입"]},
        "article_summary": ["충분히 긴 문단입니다. " * 40] * 4,
    }
    assert not MODULE.is_publishable_detail(item)
    upgraded = MODULE.upgrade_existing_item(dict(item, summary_schema_version=MODULE.SUMMARY_SCHEMA_VERSION))
    assert upgraded["publication_status"] == "statistics_only"


def _node() -> str | None:
    candidates = [shutil.which("node"), str(Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node.exe")]
    return next((path for path in candidates if path and Path(path).exists()), None)


def test_frontend_visibility_rule_matches_backend_and_ignores_length() -> None:
    script = (ROOT / "web" / "news.js").read_text(encoding="utf-8")
    editorial = (ROOT / "web" / "editorial.js").read_text(encoding="utf-8")
    for source in (script, editorial):
        assert "hasSubstantiveSummary" not in source and "hasVerifiedLegacySummary" not in source
        assert "detail_visible" in source
    node = _node()
    if not node:
        pytest.skip("node runtime not available for executing the browser rule")
    start = script.index("const PUBLISHABLE_BODY=")
    end = script.index("const categoryOf=")
    program = script[start:end] + """
const long = "충분히 긴 요약 문장입니다. ".repeat(60);
const cases = [
  {article_body_status:"unavailable", publication_status:"statistics_only", article_summary:[long,long,long], core_summary:long, sources:[{url:"https://x"}], six_w_one_h:{who:["a"],when:["b"],what:["c"],why:["d"],how:["e"]}},
  {article_body_status:"full_text", publication_status:"detail", quality_gate:{passed:false}},
  {article_body_status:"full_text", publication_status:"detail"},
  {detail_visible:false, article_body_status:"full_text", publication_status:"detail"},
];
const override = {article_body_status:"full_text", publication_status:"detail", detail_visible:true, article_summary:["수동"]};
console.log(JSON.stringify([...cases.map(canShow), canShow(applyOverride(cases[0], override)), canShow(applyOverride(cases[0], {...override, manual_verified:true, sources:[{url:"https://example.com/a"}]}))]));
"""
    result = subprocess.run([node, "-e", program], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip()) == [False, False, True, False, False, True]


# --- 14/15: preserve good summaries, stable ids, no duplicates -----------------------------
def test_failed_refresh_keeps_existing_verified_summary_and_ids_are_stable() -> None:
    good = {"id": "news-20261128-aaa", "title": "SK리츠, 주유소 매각", "publication_status": "detail", "article_body_status": "full_text", "article_summary": ["기존 정상 요약"], "sources": [{"url": "https://example.com/a"}]}
    other = {"id": "news-20261128-bbb", "title": "다른 기사", "publication_status": "detail", "article_body_status": "full_text", "sources": [{"url": "https://example.com/b"}]}
    failed_fresh = {"id": "news-20261128-zzz", "title": "SK리츠, 주유소 매각", "publication_status": "statistics_only", "article_body_status": "unavailable", "article_body_error": "HTTP 503", "sources": [{"url": "https://example.com/a"}]}
    merged = MODULE.merge_day_items([good, other], [failed_fresh])
    assert [row["id"] for row in merged] == ["news-20261128-aaa", "news-20261128-bbb"]
    assert merged[0]["article_summary"] == ["기존 정상 요약"]
    assert merged[0]["last_refresh"]["result"] == "kept_existing"
    again = MODULE.merge_day_items(merged, [dict(failed_fresh)])
    assert [row["id"] for row in again] == ["news-20261128-aaa", "news-20261128-bbb"]
    item = dict(good)
    assert MODULE.apply_enrichment(item, {"article_body_status": "unavailable", "publication_status": "statistics_only", "article_body_error": "timeout"}) == "kept_existing"
    assert item["article_summary"] == ["기존 정상 요약"]


def test_collection_run_end_to_end_offline(monkeypatch, tmp_path) -> None:
    """collect_day → write_day(merge) → rebuild_index on a temp archive, no network."""
    monkeypatch.setattr(MODULE, "NEWS_DIR", tmp_path)
    monkeypatch.setattr(MODULE, "INDEX_PATH", tmp_path / "index.json")
    monkeypatch.setattr(MODULE, "LOCK_PATH", tmp_path / ".lock")
    rows = [
        {"title": BLOG_TITLE, "url": "https://blog.naver.com/example/1001", "publisher": "예시 미디어", "description": "리츠 배당과 금리 부담", "published_at": "2026-11-28", "published_time": "2026-11-28T08:30+09:00", "region": "domestic"},
        {"title": "가나은행 예금 금리 0.2%p 인상", "url": "https://news.example.com/2", "publisher": "예시뉴스", "description": "예금 금리 인상", "published_at": "2026-11-28", "published_time": "2026-11-28T09:00+09:00", "region": "domestic"},
    ]
    monkeypatch.setattr(MODULE, "fetch_feed", lambda *args, **kwargs: list(rows))
    monkeypatch.setattr(MODULE, "fetch_direct_feed", lambda *args, **kwargs: [])
    monkeypatch.setattr(MODULE, "fetch_nyt_most_popular", lambda *args, **kwargs: [])
    monkeypatch.setattr(MODULE, "discover_article_extraction", lambda *args, **kwargs: None)
    monkeypatch.setattr(MODULE, "enrich_video_news", lambda *args, **kwargs: None)
    monkeypatch.setattr(MODULE.time, "sleep", lambda *_args: None)
    blog_page = fixture("blog_publisher_post.html")

    def fake_fetch(url, title=""):
        if "blog.naver.com" in url:
            return MODULE.extract_article_page(blog_page, title), "https://blog.naver.com/PostView.naver?blogId=example&logNo=1001"
        raise OSError("HTTP Error 503")

    monkeypatch.setattr(MODULE, "fetch_article", fake_fetch)
    target = MODULE.date(2026, 11, 28)
    items = MODULE.collect_day(target, 6)
    MODULE.write_day(target, items)
    first = json.loads((tmp_path / "2026-11-28.json").read_text(encoding="utf-8"))
    by_title = {row["title"]: row for row in first["items"]}
    assert by_title[BLOG_TITLE]["article_body_status"] == "full_text"
    assert by_title[BLOG_TITLE]["primary_source_role"] == "publisher_blog_republication"
    assert by_title["가나은행 예금 금리 0.2%p 인상"]["article_body_status"] == "unavailable"
    # Second run: the publisher now fails too; the verified item must survive with the same id.
    monkeypatch.setattr(MODULE, "fetch_article", lambda url, title="": (_ for _ in ()).throw(OSError("HTTP Error 503")))
    MODULE.write_day(target, MODULE.collect_day(target, 6))
    second = json.loads((tmp_path / "2026-11-28.json").read_text(encoding="utf-8"))
    assert len(second["items"]) == len(first["items"])
    assert {row["id"] for row in second["items"]} == {row["id"] for row in first["items"]}
    kept = next(row for row in second["items"] if row["title"] == BLOG_TITLE)
    assert kept["article_body_status"] == "full_text" and kept["article_summary"] == by_title[BLOG_TITLE]["article_summary"]
    MODULE.rebuild_index()
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert index["body_contract"]["statuses"]["full_text"]["min_chars"] == 350
    visible = {row["title"]: row["detail_visible"] for row in json.loads((tmp_path / "2026-11-28.json").read_text(encoding="utf-8"))["items"]}
    assert visible == {BLOG_TITLE: True, "가나은행 예금 금리 0.2%p 인상": False}
    assert not (tmp_path / ".lock").exists()


def test_article_already_stored_in_a_neighbour_day_is_not_saved_twice(monkeypatch, tmp_path) -> None:
    # 2026-11-28 16:00 run: the feed date of a cluster changed between runs and
    # the same article was written to the 11-27 and the 11-28 file.
    monkeypatch.setattr(MODULE, "NEWS_DIR", tmp_path)
    stored = {"id": "news-20261128-aaa", "title": "가나은행 예금 금리 0.2%p 인상", "date": "2026-11-28", "publisher": "예시뉴스",
              "article_source_url": "https://news.example.com/2", "article_body_status": "full_text", "publication_status": "detail",
              "sources": [{"url": "https://news.example.com/2"}, {"url": "https://other.example.com/related"}]}
    (tmp_path / "2026-11-27.json").write_text(json.dumps({"date": "2026-11-27", "items": [stored]}, ensure_ascii=False), encoding="utf-8")
    same = {"id": "news-20261128-new", "title": "가나은행, 예금 금리 인상", "date": "2026-11-28", "sources": [{"url": "https://news.example.com/2"}]}
    recurring = {"id": "news-20261128-ccc", "title": "가나은행 예금 금리 0.2%p 인상", "date": "2026-11-28", "sources": [{"url": "https://news.example.com/3"}]}
    # A different article whose feed cluster happens to list the same related report.
    cluster_mate = {"id": "news-20261128-ddd", "title": "나다은행 대출 금리 인하", "date": "2026-11-28",
                    "sources": [{"url": "https://news.example.com/9"}, {"url": "https://other.example.com/related"}]}
    kept, skipped = MODULE.drop_stored_in_neighbour_days(MODULE.date(2026, 11, 28), [same, recurring, cluster_mate])
    assert skipped == 1
    assert [row["id"] for row in kept] == ["news-20261128-ccc", "news-20261128-ddd"]


def test_merge_never_joins_different_articles_that_share_a_related_report() -> None:
    old = {"id": "news-mbc", "title": "뉴욕증시, AI·기술주 반등에 일제히 상승 마감", "article_body_status": "full_text", "publication_status": "detail",
           "sources": [{"url": "https://imnews.example.com/1"}, {"url": "https://relay.example.com/shared"}]}
    fresh = {"id": "news-mbn", "title": "뉴욕증시, AI·기술주 반등에 상승 마감", "article_body_status": "full_text", "publication_status": "detail",
             "sources": [{"url": "https://mbn.example.com/2"}, {"url": "https://relay.example.com/shared"}]}
    merged = MODULE.merge_day_items([old], [fresh])
    assert sorted(row["id"] for row in merged) == ["news-mbc", "news-mbn"]


def test_reprocessing_the_same_body_is_deterministic() -> None:
    first, second = blog_fields(), blog_fields()
    for key in ("article_summary", "core_summary", "six_w_one_h", "key_figures", "fact_status", "uncertainties"):
        assert first[key] == second[key], key


# --- 16: detail renderer shows coverage, figures and sources (incl. mobile CSS) -----------
def test_detail_view_renders_coverage_figures_and_sources() -> None:
    css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
    assert "@media(max-width:700px){.news-coverage dl{grid-template-columns:1fr}.news-figures li{grid-template-columns:1fr}" in css
    node = _node()
    if not node:
        pytest.skip("node runtime not available for rendering report.js")
    fields = blog_fields()
    item = {**fields, "id": "x", "title": BLOG_TITLE, "date": "2026-11-28", "eyebrow": "ECONOMY NEWS · 부동산", "sources": [{"publisher": "예시 미디어", "url": "https://blog.naver.com/x", "title": BLOG_TITLE, "region": "domestic"}]}
    program = (
        "global.window={};global.location={origin:'http://localhost'};"
        + (ROOT / "web" / "report.js").read_text(encoding="utf-8")
        + "\nconst item=JSON.parse(require('fs').readFileSync(0,'utf8'));process.stdout.write(window.EditorialReport.render(item,{kind:'news'}));"
    )
    result = subprocess.run([node, "-e", program], input=json.dumps(item, ensure_ascii=False), capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    html = result.stdout
    for text in ("원문 확보 범위", "발행사 운영 블로그 게시본", "핵심 수치와 문맥", "86원", "근거 문장 보기", "원문 보기 ↗", "번역 불필요"):
        assert text in html, text
    assert "중대한 불확실성 없음" not in html
