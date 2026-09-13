from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_map_reset_button_restores_korea_bounds() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    assert 'id="resetMapView"' in html
    assert "지도 위치 초기화" in html
    assert 'map.fitBounds([[33.0,124.3],[38.8,131.2]]' in script
    assert "mapLocalityAnchor=null" in script


def test_map_marker_recovery_works_without_local_pc_api() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    assert 'PUBLIC_NOMINATIM="https://nominatim.openstreetmap.org"' in script
    assert "PUBLIC_OVERPASS_ENDPOINTS" in script
    assert "requestViewportComplexes" in script
    assert "requestGeocodeRows" in script
    assert "hasActualTradeData(group)" in script
    assert "MAX_VIEWPORT_MARKERS = 120" in script
    assert "MAX_VIEWPORT_FALLBACK_GEOCODES = 30" in script
    assert "[region,group.dong,parcel,fullName]" in script
    assert "seedApproximateMarkers" in script
    assert "동 중심 기준 임시 위치" in script
    assert '"실거래 단지 "+markers.size' in script
    assert "marker.__approximate&&bounds.contains(marker.getLatLng())" in script
    assert "SIDO_FALLBACK_CENTERS" in script


def test_cloudflare_worker_proxies_public_map_sources_when_pc_is_off() -> None:
    worker = (ROOT / "cloudflare-worker" / "worker.js").read_text(encoding="utf-8")

    assert "async function publicMapApi" in worker
    assert "nominatim.openstreetmap.org/search" in worker
    assert "nominatim.openstreetmap.org/reverse" in worker
    assert "overpass-api.de/api/interpreter" in worker
    assert 'x-real-estate-source", "public-map-fallback"' in worker
    assert '"x-real-estate-source": "published-trade-fallback"' in worker
    assert "public-building-source-unavailable" in worker
