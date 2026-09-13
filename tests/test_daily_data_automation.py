from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_all_public_data_families_have_at_least_daily_scheduled_refresh() -> None:
    real_estate = (ROOT / ".github" / "workflows" / "daily-update.yml").read_text(encoding="utf-8")
    markets = (ROOT / ".github" / "workflows" / "economic-indicators-daily.yml").read_text(encoding="utf-8")

    assert 'cron: "10 21 * * *"' in real_estate
    assert "collect-complexes" in real_estate
    assert "--priority-coverage" in real_estate
    assert "python -m realestate.cli.main publish" in real_estate

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
