from realestate.development_opportunities import is_official_url, same_event_title, summarize_official_document


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
    assert result["category"] == "생활·공공시설"
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
