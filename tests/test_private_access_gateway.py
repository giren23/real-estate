from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_worker_hides_all_pages_and_apis_behind_private_cookie() -> None:
    worker = (ROOT / "cloudflare-worker" / "worker.js").read_text(encoding="utf-8")

    gate = 'if (!(await hasPrivateAccess(request, env)))'
    paper_route = 'if (incoming.pathname.startsWith("/api/paper/"))'
    real_estate_route = 'if (incoming.pathname.startsWith("/api/")) return localRealEstateApi'
    assert worker.index(gate) < worker.index(paper_route)
    assert worker.index(gate) < worker.index(real_estate_route)
    assert 'incoming.pathname.startsWith("/api/")' in worker
    assert 'return developmentPage();' in worker
    assert "아직 개발 중입니다." in worker


def test_private_access_secret_is_not_committed_and_cookie_is_hardened() -> None:
    worker = (ROOT / "cloudflare-worker" / "worker.js").read_text(encoding="utf-8")
    config = (ROOT / "cloudflare-worker" / "wrangler.toml").read_text(encoding="utf-8")

    assert "env.PRIVATE_ACCESS_HASH" in worker
    assert "PRIVATE_ACCESS_HASH" not in config
    assert "HttpOnly; Secure; SameSite=Strict" in worker
    assert '"cache-control": "private, no-store"' in worker
    assert '"referrer-policy": "no-referrer"' in worker
    assert "constantTimeEqual" in worker
