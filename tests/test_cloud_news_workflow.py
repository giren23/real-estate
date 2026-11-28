"""Cloud refresh must run independently and fit within bounded free requests."""
from pathlib import Path

import pytest

from scripts import update_economic_context as context

ROOT = Path(__file__).resolve().parents[1]


def test_slow_macro_sources_cannot_block_the_news_job():
    workflow = (ROOT/'.github/workflows/economic-indicators-daily.yml').read_text(encoding='utf-8')
    news_job = workflow.split('\n  news:\n', 1)[1]
    assert 'needs: verify' in news_job and 'needs: refresh' not in news_job
    assert 'TZ: Asia/Seoul' in workflow
    assert 'python scripts/update_economic_news.py' in news_job
    assert 'ECON_REQUEST_TIMEOUT_SECONDS: "8"' in workflow
    assert 'if: steps.test.outcome == \'success\'' in workflow


def test_cloud_download_budget_does_not_retry_a_slow_source(monkeypatch):
    timeouts = []
    def fail(_request, **kwargs):
        timeouts.append(kwargs['timeout'])
        raise TimeoutError('slow source')
    monkeypatch.setenv('ECON_REQUEST_TIMEOUT_SECONDS', '8')
    monkeypatch.setenv('ECON_REQUEST_ATTEMPTS', '1')
    monkeypatch.setattr(context, 'urlopen', fail)
    monkeypatch.setattr(context.time, 'sleep', lambda _: pytest.fail('no retry sleep in the one-attempt cloud budget'))
    with pytest.raises(TimeoutError):
        context.download('https://example.org/public.csv')
    assert timeouts == [8]


def test_runtime_news_locks_are_never_published():
    assert 'web/content/news/.update-economic-news.lock*' in (ROOT/'.gitignore').read_text(encoding='utf-8')


def test_daily_briefing_completion_also_triggers_pages_deployment():
    workflow = (ROOT/'.github/workflows/pages.yml').read_text(encoding='utf-8')
    assert 'workflow_run:' in workflow and '"Daily 7AM investment briefing"' in workflow
