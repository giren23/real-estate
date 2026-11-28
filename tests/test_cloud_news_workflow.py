"""Cloud refresh must run independently and fit within bounded free requests."""
from pathlib import Path
import json
import shutil
import subprocess

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


def test_unverified_new_day_keeps_the_latest_verified_news_visible(monkeypatch, tmp_path):
    from scripts import update_economic_news as news
    title = '한국은행 기준금리 동결 결정'
    sentences = ['한국은행은 기준금리를 동결하고 향후 물가와 고용 지표를 추가 확인한다고 발표했다.',
                 '위원회는 가계부채와 환율 변동을 함께 점검하고 다음 회의에서 정책 방향을 다시 논의한다고 설명했다.',
                 '한국은행은 금융시장의 변동성이 확대될 경우 필요한 조치를 검토하고 결정 내용을 공개할 계획이라고 밝혔다.']
    verified = {**news.sixw_summary_from_sentences(title, '한국은행', '2026-11-28', sentences),
                'id': 'verified', 'title': title, 'date': '2026-11-28', 'category': '금리·채권',
                'article_body_status': 'full_text', 'publication_status': 'detail',
                'sources': [{'publisher': '한국은행', 'url': 'https://example.org/article'}],
                'source_count': 3, 'related_reports': 5, 'summary_schema_version': news.SUMMARY_SCHEMA_VERSION}
    pending = {'id': 'pending', 'title': '미국 증시 원문 확인 대기', 'date': '2026-11-29',
               'article_body_status': 'unavailable', 'publication_status': 'statistics_only',
               'summary_schema_version': news.SUMMARY_SCHEMA_VERSION}
    for day, item in [('2026-11-29', pending), ('2026-11-28', verified)]:
        (tmp_path/(day+'.json')).write_text(json.dumps({'date': day, 'items': [item]}, ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(news, 'NEWS_DIR', tmp_path)
    monkeypatch.setattr(news, 'INDEX_PATH', tmp_path/'index.json')
    news.rebuild_index()
    index = json.loads(news.INDEX_PATH.read_text(encoding='utf-8'))
    assert index['total_articles'] == 2 and index['archives'][0]['detailed_count'] == 0
    assert index['latest_verified_archive'] == '2026-11-28.json'
    assert index['important_archive_date'] == '2026-11-28'
    assert [item['id'] for item in index['important_items']] == ['verified']
    assert index['important_items'][0]['date'] == '2026-11-28'


def test_default_archive_fallback_respects_an_explicit_page_selection():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable')
    code = next(line for line in (ROOT/'web/news.js').read_text(encoding='utf-8').splitlines() if 'const defaultArchivePage=' in line)
    code += '\nconst archives=[{file:"new.json"},{file:"verified.json"}];console.log(JSON.stringify([defaultArchivePage(archives,"verified.json",null),defaultArchivePage(archives,"verified.json","1"),defaultArchivePage(archives,"verified.json","99")]));'
    result = subprocess.run([node,'-e',code],check=True,capture_output=True,text=True)
    assert json.loads(result.stdout) == [2,1,2]
