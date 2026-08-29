from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_housing_tax_estimator_is_rendered_below_policy_panel() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    policy_position = script.index('class="policy-panel"')
    tax_position = script.index('class="tax-estimator"')

    assert policy_position < tax_position
    assert "주택 세금 예상 계산" in script
    assert "2023~2027년" in script
    assert 'value="20"' in script
    assert "tax-growth-range" in script
    assert "tax-growth-number" in script


def test_tax_estimator_covers_the_requested_tax_types_and_safety_notes() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    for function in (
        "estimatedPropertyTax",
        "estimatedComprehensiveTax",
        "estimatedAcquisitionTax",
        "bindTaxEstimator",
    ):
        assert f"function {function}" in script
    for label in ("재산세", "지방교육세", "도시지역분", "종합부동산세", "농어촌특별세", "보유세 합계", "취득세"):
        assert label in script
    assert "재산세 등" not in script
    assert "종부세 등" not in script
    assert "세무 신고용이 아닌 모의 계산" in script
    assert "고령자·장기보유 세액공제" in script


def test_tax_estimator_searches_apartment_area_before_official_price_input() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    assert "tax-property-search" in script
    assert "tax-property-results" in script
    assert "tax-area-select" in script
    assert "matchingApartments(query,8)" in script
    assert "공동주택 공시가격" in script
    assert "동·호" in script
    assert "realtyprice.kr/notice/m/gss/search.do" in script
    assert 'placeholder="단지·평형 선택"' in script
    assert "/api/official-price?" in script
    assert 'value="8"' not in script


def test_tax_estimator_has_responsive_table_and_chart_styles() -> None:
    style = (ROOT / "web" / "style.css").read_text(encoding="utf-8")

    assert ".tax-table-wrap{overflow:auto" in style
    assert ".tax-chart-wrap" in style
    assert "@media(max-width:520px)" in style
