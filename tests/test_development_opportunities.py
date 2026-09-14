from realestate.development_opportunities import (
    DevelopmentOpportunityStore,
    is_official_url,
    is_rumor_evidence,
    same_event_title,
    summarize_official_document,
)


def test_only_public_official_hosts_are_accepted() -> None:
    assert is_official_url("https://molit.go.kr/news/example.do")
    assert is_official_url("https://snvision.seongnam.go.kr/123")
    assert is_official_url("https://www.kr.or.kr/board/1")
    assert not is_official_url("https://example.com/article")
    assert not is_official_url("https://random.or.kr/article")


def test_official_document_summary_preserves_stage_and_numbers() -> None:
    result = summarize_official_document(
        "성남시 이매동 복지청사 착공",
        [
            "성남시는 2026년 9월 이매동 주민을 위한 복지청사 공사를 시작했으며 2027년 12월 준공할 계획임.",
            "사업비 320억원을 투입해 도서관과 체육시설을 함께 조성할 계획임.",
            "시범우성에서 사업 경계까지의 실제 거리는 별도 확인이 필요함.",
        ],
        "경기도 성남시 분당구", "이매동", "시범우성",
    )
    assert result is not None
    assert result["category"] == "공공시설"
    assert result["stage"] == "착공·공사"
    assert "320억원" in result["summary"]
    assert result["scope"] == "선택 단지 직접 언급"


def test_similar_headlines_for_the_same_event_are_grouped() -> None:
    assert same_event_title(
        "분당 이매동 아름마을 풍선효 통합재건축 2차 주민설명회",
        "분당 이매동 아름마을 풍선효 통합재건축 주민설명회 개최",
    )
    assert not same_event_title(
        "분당 이매동 아름마을 풍선효 통합재건축 주민설명회",
        "이매동 성남역 광역교통 환승센터 계획",
    )


def test_only_non_official_explicit_speculation_is_labeled_as_rumor() -> None:
    assert is_rumor_evidence("신설역 유치설이 다시 거론됐다는 관측", official=False)
    assert not is_rumor_evidence("신설역 실시계획 인가를 고시함", official=False)
    assert not is_rumor_evidence("신설역 유치설이 다시 거론됐다는 관측", official=True)


def test_fetched_rumor_keeps_distance_and_verification_warning(monkeypatch) -> None:
    class Response:
        url = "https://example.com/report"
        headers = {"Content-Type": "text/html; charset=utf-8"}
        apparent_encoding = "utf-8"
        encoding = "utf-8"
        text = """<html><body><p>2026년 서현동 철도 신설역 유치설이 다시 거론됐다는 관측이 나왔으나 공식 확정되지 않았음.</p><p>서현동 철도 사업은 2027년 일정과 300억원 예산이 있다는 주장도 나왔지만 공식 문서에서는 확인되지 않았음.</p></body></html>"""

        @staticmethod
        def raise_for_status() -> None:
            return None

    monkeypatch.setattr("realestate.development_opportunities.requests.get", lambda *args, **kwargs: Response())
    result = DevelopmentOpportunityStore._fetch_document(
        {
            "url": Response.url,
            "title": "서현동 신설역 유치설 재점화",
            "publisher": "테스트보도",
            "published_at": "2026-09-15",
        },
        "경기도 성남시 분당구",
        "서현동",
        "시범한신",
    )
    assert result is not None
    assert result["is_rumor"] is True
    assert result["evidence_label"] == "[루머]"
    assert result["stage"] == "공식 단계 미확인"
    assert result["distance_check_required"] is True
