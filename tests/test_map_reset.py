from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_map_reset_button_restores_korea_bounds() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    assert 'id="resetMapView"' in html
    assert "지도 위치 초기화" in html
    assert 'map.fitBounds([[33.0,124.3],[38.8,131.2]]' in script
    assert "mapLocalityAnchor=null" in script
