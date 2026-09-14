from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_all_public_data_families_have_at_least_daily_scheduled_refresh() -> None:
    real_estate = (ROOT / ".github" / "workflows" / "daily-update.yml").read_text(encoding="utf-8")
    markets = (ROOT / ".github" / "workflows" / "economic-indicators-daily.yml").read_text(encoding="utf-8")

    assert 'cron: "5 21 * * *"' in real_estate
    assert "  push:" not in real_estate
    assert "--nationwide-coverage" in real_estate
    assert "retry-trades" in real_estate
    assert "publish_collection_status.py" in real_estate
    assert "build_public_trade_shards.py" in real_estate
    assert "git pull --rebase --autostash origin main" in real_estate
    assert 'if [ "$(TZ=Asia/Seoul date +%d)" = "01" ]; then months=3; fi' in real_estate
    assert "python scripts/merge_incremental_public_data.py" in real_estate
    assert "--all-history" not in real_estate
    assert "without deleting published history" in real_estate

    directory = (ROOT / ".github" / "workflows" / "complex-directory-weekly.yml").read_text(encoding="utf-8")
    assert 'cron: "35 21 * * 6"' in directory
    assert "collect-complexes" in directory
    assert "publish_complex_directory.py" in directory

    validation = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "python -m pytest -q" in validation
    assert "node --check web/app.js" in validation

    assert 'cron: "15 */3 * * *"' in markets
    for script in (
        "update_economic_context.py",
        "update_market_snapshot.py",
        "update_reb_market_map.py",
        "update_economic_news.py",
        "update_editorial_analysis.py",
        "update_investment_briefing.py",
    ):
        assert script in markets


def test_reb_refresh_never_treats_a_full_day_old_snapshot_as_fresh() -> None:
    script = (ROOT / "scripts" / "update_reb_market_map.py").read_text(encoding="utf-8")
    assert "def snapshot_is_fresh(max_age_hours: int = 18)" in script
    assert "snapshot_is_fresh()" in script
