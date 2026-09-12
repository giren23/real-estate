from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_listing_resolver_uses_a_fixed_naver_endpoint_and_cache() -> None:
    worker = (ROOT / "cloudflare-worker" / "worker.js").read_text(encoding="utf-8")
    assert 'incoming.pathname === "/api/naver-complex"' in worker
    assert 'https://new.land.naver.com/api/regions/complexes' in worker
    assert 'target.searchParams.set("cortarNo", bjdCode)' in worker
    assert 'await caches.default.put(cacheKey, response.clone())' in worker
    assert 'upstream.status === 429' in worker


def test_listing_button_resolves_an_exact_complex_before_fallback() -> None:
    app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert 'const NAVER_COMPLEX_RESOLVER =' in app
    assert 'new URLSearchParams({bjd_code:bjdCode,names:names.join(",")})' in app
    assert 'naverComplexUrl(complexNo)' in app
    assert 'openNaverListing(group,series' in app
