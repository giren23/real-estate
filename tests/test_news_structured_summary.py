from importlib.util import module_from_spec, spec_from_file_location
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location("economic_news_structured", ROOT / "scripts" / "update_economic_news.py")
MODULE = module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def fake_extraction(paragraphs: list[str], path: str = "container"):
    """Network-free stand-in for fetch_article(): a recognised body region."""
    return MODULE.NQ.Extraction(paragraphs=list(paragraphs), path=path, boundary_closed=True)


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


def test_recent_unavailable_article_retries_in_three_hours() -> None:
    now = datetime(2026, 9, 15, 0, 0, tzinfo=timezone(timedelta(hours=9)))
    retry_at = MODULE.next_body_retry_at({"date": "2026-09-14", "article_body_attempts": 0}, now)
    assert retry_at == "2026-09-15T03:00:00+09:00"
    item = {
        "article_body_status": "unavailable",
        "summary_schema_version": MODULE.SUMMARY_SCHEMA_VERSION,
        "next_body_retry_at": retry_at,
    }
    assert not MODULE.article_retry_due(item, now + timedelta(hours=2, minutes=59))
    assert MODULE.article_retry_due(item, now + timedelta(hours=3))


def test_recent_legacy_seven_day_cooldown_is_shortened() -> None:
    now = datetime(2026, 9, 15, 1, 0, tzinfo=timezone(timedelta(hours=9)))
    item = {
        "date": "2026-09-14",
        "article_body_status": "unavailable",
        "article_body_attempts": 1,
        "article_body_checked_at": "2026-09-14T21:40:53+09:00",
        "summary_schema_version": MODULE.SUMMARY_SCHEMA_VERSION,
        "next_body_retry_at": "2026-09-21",
    }
    assert MODULE.article_retry_due(item, now)


def test_old_repeated_failures_back_off_for_seven_days() -> None:
    now = datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc)
    retry_at = MODULE.next_body_retry_at({"date": "2026-08-01", "article_body_attempts": 7}, now)
    assert retry_at == "2026-09-22T00:00:00+00:00"


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


def test_article_parser_reads_meta_and_article_content_container() -> None:
    page = """<html><head><meta property="og:description" content="미국 물가와 국채금리 상승으로 주식시장의 경계감이 커졌다."></head>
    <body><div class="article-content"><h1>시장 점검</h1>
    <div>국제유가는 배럴당 100달러를 돌파했고 미국 10년물 국채금리도 상승했다.</div>
    <div>투자자들은 다음 물가지표와 연방준비제도의 정책 경로를 함께 확인하고 있다.</div>
    </div><footer>Copyright All rights reserved</footer></body></html>"""
    sentences = MODULE.article_sentences(page)
    assert any("국제유가는" in sentence for sentence in sentences)
    assert any("연방준비제도" in sentence for sentence in sentences)
    assert all("Copyright" not in sentence for sentence in sentences)


def test_non_article_quote_pages_and_unrelated_incidents_are_rejected() -> None:
    assert not MODULE.is_news_article_candidate({"title": "ES00 | E-Mini S&P 500 Future Continuous Contract Overview"})
    assert not MODULE.is_news_article_candidate({"title": "About GraniteShares 2x Long SK Hynix Daily ETF (SKUU.OQ)"})
    assert not MODULE.is_news_article_candidate({"title": "부안 아파트 화재로 주민 40명 대피"})
    assert MODULE.is_news_article_candidate({"title": "정유공장 화재로 국제유가와 공급망 불안 확대"})


def test_entertainment_photo_and_fed_name_collision_are_rejected() -> None:
    assert not MODULE.is_news_article_candidate({"title": "[사진]투모로우바이투게더 연준, 파리 다녀올게요"})
    assert not MODULE.is_news_article_candidate({"title": "가수 연준, 공항 화보 같은 출국길"})
    assert MODULE.is_news_article_candidate({"title": "美 연준, 물가 상승에 금리 0.25%P 인상 결정"})
    assert not MODULE.is_news_article_candidate({"title": "곽상언 금품수수 팩트대로…한동훈 미국 아파트가 팩트"})
    assert not MODULE.is_news_article_candidate({"title": "28세 그리 \"경기도에 자가 아파트 두 채\""})
    assert not MODULE.is_news_article_candidate({
        "title": "한강뷰 아파트 17억에 샀는데 시세차익 40억",
        "article_source_url": "https://www.mt.co.kr/entertainment/2026/10/03/example",
    })
    assert not MODULE.is_news_article_candidate({
        "title": "뉴저지 아파트값 받은 것 팩트",
        "article_source_url": "https://biz.chosun.com/policy/politics/2026/10/03/example/",
    })


def test_verified_public_excerpt_remains_publishable_but_is_not_full_text() -> None:
    item = {"publication_status": "detail", "article_body_status": "verified_excerpt"}
    assert MODULE.is_publishable_detail(item)
    details = MODULE.importance_details({
        **item,
        "title": "연준 금리 인상 전망",
        "category": "금리·채권",
        "sources": [{"publisher": "공식 발행사"}],
    })
    assert details["verified_body"] is True
    assert details["verification_score"] < 12


def test_article_txt_container_is_recognized_as_full_text() -> None:
    page = """<html><div class="article_txt"><div>일본 기업들이 전력반도체 생산 통합 계획을 발표했다.</div>
    <div>세 회사는 비용 절감과 경쟁력 확보를 위해 2027년부터 공동 생산을 추진한다.</div>
    <div>시장은 통합 결과로 설비투자와 공급망 효율이 개선될 것으로 전망했다.</div></div></html>"""
    sentences = MODULE.article_sentences(page)
    assert len(sentences) == 3
    assert any("공동 생산" in sentence for sentence in sentences)


def test_sixw_actor_is_article_subject_not_publisher_and_status_is_precise() -> None:
    fields = MODULE.structured_summary_fields(
        "한국은행 기준금리 동결 발표",
        "테스트뉴스",
        "2026-10-03",
        [
            "한국은행은 2026년 10월 3일 서울에서 기준금리 동결을 발표했다.",
            "물가 압력과 경기 둥화 우려를 함께 고려했기 때문이다.",
            "금융통화위원회 의결을 통해 현재 수준을 유지했다.",
        ],
        "한국은행이 기준금리를 동결했다.",
    )
    assert "한국은행" in fields["six_w_one_h"]["who"]
    assert "테스트뉴스" not in fields["six_w_one_h"]["who"]
    assert any(row["status"] == "발표" for row in fields["fact_status"])
    assert fields["six_w_one_h_meta"]["evidence_bound"] is True


def test_sixw_removes_dateline_and_does_not_treat_metrics_as_people_or_forecasts() -> None:
    fields = MODULE.structured_summary_fields(
        "미국 9월 신규 고용 예상치 상회",
        "CNBC",
        "2026-10-03",
        [
            "[서울=CNBC] = 미국의 9월 신규 고용은 시장 예상치보다 늘었다.",
            "미 노동통계국(BLS)은 신규 고용과 실업률을 발표했다.",
            "미국 담당 수석 이코노미스트는 이번 결과가 금리 경로에 영향을 줄 수 있다고 전망했다.",
        ],
        "미국의 신규 고용이 예상치를 웃돌았다.",
    )
    who = " ".join(fields["six_w_one_h"]["who"])
    assert "신규 고용" not in who
    assert "실업률" not in who
    assert "노동통계국" in who
    assert "서울" not in fields["six_w_one_h"]["where"]
    assert "미국" in fields["six_w_one_h"]["where"]
    assert fields["article_summary"][0].startswith("미국의 9월")
    assert fields["fact_status"][0]["status"] == "보도된 사실"
    assert fields["fact_status"][1]["status"] == "발표"
    assert fields["fact_status"][2]["status"] == "전망·예상"


def test_unverified_item_cannot_receive_important_badge() -> None:
    item = {
        "title": "美 연준 금리 0.25%P 인상 결정",
        "category": "금리·채권",
        "region": "us",
        "article_body_status": "unavailable",
        "publication_status": "statistics_only",
        "sources": [{"publisher": "로이터"}],
    }
    MODULE.mark_important([item])
    assert item["important"] is False
    assert item["importance"]["eligible_for_important"] is False


def test_unverified_article_is_never_publishable_as_important_detail() -> None:
    assert not MODULE.is_publishable_detail({
        "important": True,
        "publication_status": "statistics_only",
        "article_body_status": "unavailable",
    })
    assert MODULE.is_publishable_detail({
        "important": True,
        "publication_status": "detail",
        "article_body_status": "full_text",
    })


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
    monkeypatch.setattr(MODULE, "publisher_search_candidates", lambda *_args: [])
    monkeypatch.setattr(MODULE, "search_bing_news_article_urls", lambda *_args: [])
    monkeypatch.setattr(MODULE, "publisher_daily_candidates", lambda *_args: [(discovered, "https://example.com/article", "publisher_archive_economy")])
    monkeypatch.setattr(MODULE, "fetch_article", lambda _url, _title="": (fake_extraction(sentences), "https://example.com/article"))
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
    monkeypatch.setattr(MODULE, "fetch_article", lambda _url, _title="": (fake_extraction(sentences), "https://www.mt.co.kr/article"))
    result = MODULE.discover_article_body(title, "머니투데이", "2026-09-10")
    assert result and result[2] == "publisher_search_moneytoday"


def test_recovery_links_prefer_supported_publisher_search_before_portals() -> None:
    rows = MODULE.recovery_search_links("국제유가 급등", "글로벌이코노믹")
    assert rows[0]["method"] == "publisher_search_global_economy"
    assert rows[0]["url"].startswith("https://news.g-enews.com/search.php?sn=")
    assert [row["method"] for row in rows[1:]] == ["naver_search", "daum_search", "bing_news_search"]


def test_bloomingbit_uses_its_public_magnifier_search_api(monkeypatch) -> None:
    title = '美 연준, 3년 만에 금리 인상 유력…경제학자 85% "이번 주 0.25%P 올린다"'
    payload = {
        "data": {"content": [
            {"seq": 120309, "title": title},
            {"seq": 999999, "title": "비트코인 가격 전망"},
        ]}
    }
    captured = {}

    def fake_request(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr(MODULE, "_paced_public_request", fake_request)
    rows = MODULE.publisher_search_candidates(title, "bloomingbit.io")
    assert rows == [(title, "https://bloomingbit.io/feed/news/120309", "publisher_search_bloomingbit")]
    assert captured["url"].startswith(MODULE.BLOOMINGBIT_SEARCH_API)
    assert captured["kwargs"]["accept"] == "application/json"


def test_bing_news_rss_unwraps_the_original_article_url(monkeypatch) -> None:
    title = "유가 100달러에 막힌 원화 강세 환율 다시 1350원 눈앞"
    original = "https://v.daum.net/v/QOK5D41yyj"
    rss = f"""<rss><channel><item><title>{title}</title>
    <link>https://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;url={MODULE.quote(original, safe='')}</link>
    </item></channel></rss>"""
    monkeypatch.setattr(MODULE, "_paced_public_request", lambda *_args, **_kwargs: rss)
    assert MODULE.search_bing_news_article_urls(title) == [("bing_news_search", original)]


def test_crime_story_with_apartment_keyword_is_never_market_important() -> None:
    items = MODULE.mark_important([{
        "title": "파주 아파트서 탈북 여성 시신 발견…살인 용의자 해외 출국",
        "category": "부동산",
        "publisher": "KBS 뉴스",
        "sources": [{"publisher": "KBS 뉴스"}],
        "related_reports": 7,
        "source_count": 7,
    }])
    assert not items[0]["importance"]["investment_relevant"]
    assert not items[0]["important"]


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


def test_summary_provenance_cleaner_keeps_wire_service_that_is_the_actor() -> None:
    # Behaviour change (2026-11-28): a wire service that conducted the survey
    # is the subject of the fact, not attribution, and must not be deleted.
    assert MODULE.clean_summary_provenance("14일 로이터가 경제학자 101명을 대상으로 조사했다.") == "14일 로이터가 경제학자 101명을 대상으로 조사했다"
    assert MODULE.clean_summary_provenance("14일 로이터통신에 따르면 경제학자 70%가 동결을 예상했다.") == "14일 경제학자 70%가 동결을 예상했다"
    assert MODULE.clean_summary_provenance("[서울=연합뉴스] 한국은행이 기준금리를 동결했다.") == "한국은행이 기준금리를 동결했다"
    assert MODULE.clean_summary_provenance("14일(현지시간) 가 지난 11일 조사했다.") == "14일(현지시간) 지난 11일 조사했다"


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
def test_portal_promotion_is_removed_from_article_and_summary() -> None:
    promo = "가장 빠른 뉴스가 있고 다양한 정보, 쌍방향 소통이 숨쉬는 다음뉴스를 만나보세요."
    page = f"<article><p>국제유가 급등으로 원화 약세 우려가 커지면서 금융시장 변동성이 확대되고 있다.</p><p>{promo}</p><p>미국 국채금리 상승도 환율 변동성을 키우는 주요 요인으로 지목됐다.</p></article>"
    sentences = MODULE.article_sentences(page)
    assert len(sentences) == 2
    assert all("다음뉴스" not in sentence and "쌍방향" not in sentence for sentence in sentences)
    assert "다음뉴스" not in MODULE.clean_summary_provenance(f"기사 요약. {promo}")
