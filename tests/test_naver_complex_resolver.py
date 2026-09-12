from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_listing_button_resolves_an_exact_complex_before_fallback() -> None:
    app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert 'const query=String(group.apt_name||"").replace(/[()（）]/g," ")' in app
    assert 'naverComplexUrl(complexNo)' in app
    assert 'openNaverListing(group,series' in app
