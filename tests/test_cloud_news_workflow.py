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


@pytest.mark.parametrize('title', [
    '도이체방크, 연준 회의가 주식 변동성 키울 수 있다 경고',
    '골드만 연준 10월 추가 인상 관측…매파 신호에 전망 수정',
    '美 연준 금융안정보고서, 최대 위험에 AI…응답자 87% 지목',
    '민주당 서울 의원들 부동산 총회…비거주 1주택 종부세 완화 공감',
    '美 민주당 압승에 AIDC규제 우려…K반도체·전력기기 흔들',
    '이 대통령 부동산 투기공화국 탈출 약속…집값 안정',
    '강남 아파트 전세권에 배우자 상가 2곳…재산 19억대 신고',
    'With Emmys Haul, Apple Joins the Big Leagues of TV',
])
def test_financial_reporting_is_not_mistaken_for_entertainment_or_politics(title):
    from scripts import update_economic_news as news
    assert news.is_news_article_candidate({'title': title})


def test_related_politics_links_cannot_disqualify_a_financial_article():
    from scripts import update_economic_news as news
    row = {'title': '기업 신규 공장 설비 투자 발표', 'sources': [
        {'url': 'https://example.org/business/article'}, {'url': 'https://example.org/policy/politics/other'}]}
    assert news.is_news_article_candidate(row)
    assert not news.is_news_article_candidate({'title': '연준이 미우미우 쇼에서 바라본 신발'})
    assert not news.is_news_article_candidate({'title': '워시 연준의장 경주마, 경마 대회 우승'})


def test_a_fresh_feed_entry_does_not_bypass_the_saved_access_cooldown(monkeypatch):
    from scripts import update_economic_news as news
    blocked = {'id': 'blocked', 'title': '은행 금리 동결', 'date': '2026-11-29',
               'article_body_status': 'unavailable', 'publication_status': 'statistics_only',
               'article_body_failure_kind': 'access_restricted', 'next_body_retry_at': '2999-01-01',
               'summary_schema_version': news.SUMMARY_SCHEMA_VERSION, 'article_body_attempts': 2}
    monkeypatch.setattr(news, '_load_day', lambda _: [blocked])
    fresh = {'id': 'new-feed-id', 'title': blocked['title'], 'date': blocked['date'], 'engagement': {'rank': 2}}
    items = news.reuse_verified_items(news.date(2026,11,29), [fresh])
    assert items[0]['id'] == 'blocked' and items[0]['next_body_retry_at'] == '2999-01-01'
    assert items[0]['engagement'] == {'rank': 2}
    monkeypatch.setattr(news, '_article_enrichment', lambda _: pytest.fail('blocked page must not be requested again'))
    news.enrich_article_bodies(items)
