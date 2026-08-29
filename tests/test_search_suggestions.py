from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_apartment_search_exposes_selectable_suggestions_below_input() -> None:
    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    style = (ROOT / "web" / "style.css").read_text(encoding="utf-8")

    assert index.index('id="searchSuggestions"') > index.index('id="searchForm"')
    assert 'aria-controls="searchSuggestions"' in index
    assert "function matchingApartments" in script
    assert "function chooseSearchSuggestion" in script
    assert 'role="option"' in script
    assert 'road?"도로명":"소재지"' in script
    assert ".search-suggestion small" in style
