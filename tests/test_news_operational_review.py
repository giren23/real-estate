"""Reproductions from the 2026-11-29 operational review; offline fixtures only."""
import gzip
import io
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import news_quality as NQ
import reprocess_news as R
import update_economic_news as U


def test_recycled_pid_cannot_keep_an_old_lock(monkeypatch, tmp_path):
    lock = tmp_path/'.lock'
    lock.write_text(json.dumps({'pid': 1234, 'token': 'old', 'process_identity': 'old-birth'}))
    os.utime(lock, (time.time()-4000, time.time()-4000))
    monkeypatch.setattr(U, 'LOCK_PATH', lock)
    monkeypatch.setattr(U, '_process_is_running', lambda _: True)
    monkeypatch.setattr(U, '_process_identity', lambda _: 'new-birth')
    assert U.acquire_run_lock()
    try:
        assert json.loads(lock.read_text())['process_identity'] == 'new-birth'
    finally:
        U.release_run_lock()


def test_crash_during_lock_creation_does_not_block_forever(monkeypatch, tmp_path):
    lock = tmp_path/'.lock'
    lock.write_text('')
    os.utime(lock, (time.time()-4000, time.time()-4000))
    monkeypatch.setattr(U, 'LOCK_PATH', lock)
    assert U.acquire_run_lock()
    U.release_run_lock()


def test_timeout_aborts_only_an_opted_in_collector_and_records_the_reason(monkeypatch, tmp_path):
    lock = tmp_path/'.lock'
    monkeypatch.setattr(U, 'LOCK_PATH', lock)
    assert U.acquire_run_lock()
    try:
        exits = []
        monkeypatch.setattr(U.os, '_exit', exits.append)
        U._abort_expired_collector()
        assert exits == []
        monkeypatch.setattr(U, '_collector_self_exit_enabled', True)
        U._abort_expired_collector()
        assert exits == [124]
        state = json.loads((tmp_path/'.lock.status.json').read_text())
        assert state['reason'] == 'collector_runtime_exceeded' and state['pid'] == os.getpid()
    finally:
        U.release_run_lock()


def test_expired_writer_is_fenced_instead_of_allowing_two_writers(monkeypatch, tmp_path):
    monkeypatch.setattr(U, 'LOCK_PATH', tmp_path/'.lock')
    assert U.acquire_run_lock()
    try:
        monkeypatch.setattr(U, '_run_lock_started', time.monotonic()-U.LOCK_MAX_RUN_SECONDS-1)
        with pytest.raises(RuntimeError, match='상한'):
            U.atomic_write_json(tmp_path/'day.json', {'items': []})
        assert not (tmp_path/'day.json').exists()
        assert U._guard_lock() is None  # live lease cannot be stolen even if stale
    finally:
        U.release_run_lock()


def test_heartbeat_renews_a_long_running_writer(monkeypatch, tmp_path):
    lock = tmp_path/'.lock'
    monkeypatch.setattr(U, 'LOCK_PATH', lock)
    assert U.acquire_run_lock()
    try:
        os.utime(lock, (time.time()-4000, time.time()-4000))
        class Stop:
            count = 0
            def wait(self, _):
                self.count += 1
                return self.count > 1
        U._heartbeat(Stop())
        assert time.time()-lock.stat().st_mtime < 5
    finally:
        U.release_run_lock()


def test_public_url_policy_checks_dns_and_redirects(monkeypatch):
    monkeypatch.setattr(U.socket, 'getaddrinfo', lambda *_a, **_kw: [(2, 1, 6, '', ('127.0.0.1', 80))])
    for url in ['https://example.org/article', 'http://127.0.0.1/', 'file:///D:/private', 'https://user:secret@example.org/a']:
        with pytest.raises(ValueError):
            U.validate_public_url(url)
    with pytest.raises(ValueError):
        U.PublicRedirectHandler().redirect_request(U.Request('https://example.org/a'), None, 302, '', {}, 'http://127.0.0.1/private')
    monkeypatch.setattr(U.socket, 'getaddrinfo', lambda *_a, **_kw: [(2, 1, 6, '', ('93.184.216.34', 443))])
    U.validate_public_url('https://example.org/article')


def test_socket_connection_uses_only_the_checked_public_address(monkeypatch):
    connected = []
    class Socket:
        def settimeout(self, _): pass
        def connect(self, address): connected.append(address)
        def close(self): pass
    monkeypatch.setattr(U.socket, 'socket', lambda *_: Socket())
    monkeypatch.setattr(U.socket, 'getaddrinfo', lambda *_a, **_kw: [(2, 1, 6, '', ('93.184.216.34', 443))])
    U._public_connection(('example.org', 443), timeout=12)
    assert connected == [('93.184.216.34', 443)]
    monkeypatch.setattr(U.socket, 'getaddrinfo', lambda *_a, **_kw: [(2, 1, 6, '', ('10.0.0.1', 443))])
    with pytest.raises(ValueError):
        U._public_connection(('example.org', 443), timeout=12)
    assert len(connected) == 1


def test_oversized_plain_page_is_only_an_excerpt_and_compression_stays_bounded(monkeypatch):
    paragraphs = ['가나은행은 29일 예금 금리를 동결하고 지역 기업과 가계에 대한 금융 지원을 확대한다고 발표했다.',
                  '은행은 기존 고객에게 동일한 금리를 적용하고 영업점과 모바일 앱에서 대출 신청을 받을 계획이라고 설명했다.',
                  '위원회는 물가와 고용 지표를 추가로 확인하고 다음 회의에서 지원 규모와 시행 일정을 다시 논의한다고 밝혔다.']
    body = '<article>' + ''.join('<p>'+row+'</p>' for row in paragraphs) + '</article>'
    raw = (body + '<!--' + 'x'*5000).encode()
    class Response(io.BytesIO):
        headers = {'Content-Type': 'text/html'}
        def geturl(self): return 'https://example.org/article'
    monkeypatch.setattr(U, 'urlopen', lambda *_a, **_kw: Response(raw))
    page, url, content_type = U._download_page('https://example.org/article', 'text/html', limit=2500)
    extraction, _ = U.read_article_page(page, '가나은행 금리 대출 지원', url, content_type)
    assert extraction.path == 'bounded_prefix' and not extraction.boundary_closed
    status, _ = NQ.body_status(extraction.sentences, boundary_closed=False, path=extraction.path, identity_ok=True)
    assert status == 'verified_excerpt'
    monkeypatch.setattr(U, 'MAX_PAGE_BYTES', 100)
    with pytest.raises(ValueError, match='크기'):
        U._decode_page(gzip.compress(b'x'*10000), {})


def test_access_restriction_respects_seven_day_cooldown_even_on_old_schema():
    now = datetime(2026, 11, 29, tzinfo=timezone.utc)
    row = {'date': now.date().isoformat(), 'article_body_status': 'unavailable', 'summary_schema_version': 1,
           'article_body_failure_kind': 'access_restricted', 'article_body_attempts': 1,
           'article_body_checked_at': now.isoformat(), 'quality_gate': {'passed': False}}
    row['next_body_retry_at'] = U.next_body_retry_at(row, now, failure_kind='access_restricted')
    assert not U.article_retry_due(row, now+timedelta(hours=8))
    assert U.article_retry_due(row, now+timedelta(days=7))
    row['article_body_failure_kind'] = 'article_gone'
    assert not U.article_retry_due(row, now+timedelta(days=100))


def test_partial_page_still_obeys_the_original_embedded_paywall_check(monkeypatch):
    extraction = NQ.Extraction(paragraphs=['가나은행은 지원 대상을 확대했다. ' * 30],
                               path=next(iter(NQ.PAGE_DATA_PATHS)), boundary_closed=True)
    monkeypatch.setattr(U, 'extract_article_page', lambda *_: extraction)
    with pytest.raises(U.AccessRestricted):
        U.read_article_page('<html>subscribe to continue</html>', '은행 지원', 'https://example.org/a', 'text/html; x-news-prefix=1')


def test_inline_debris_removal_preserves_facts_and_bullet_lists():
    fact = '가나은행은 금리를 동결했다.'
    assert NQ.clean_article_text(fact+' (adsbygoogle = []).push({});') == fact
    assert NQ.clean_article_text(fact+' (제공 = 파이낸셜뉴스 & NAVER MEDIA API) 발행인 및 편집인: 홍길동') == fact
    notice = '* 아래 텍스트는 실제 방송 내용과 차이가 있을 수 있으니 보다 정확한 내용은 방송으로 확인하시기를 바랍니다. '
    assert NQ.clean_article_text(notice+fact) == fact
    legitimate = '주택은 ▶75㎡ 108세대 ▶84㎡ 105세대로 구성된다.'
    assert NQ.clean_article_text(legitimate) == legitimate
    assert NQ._is_entity('G7') and NQ._is_entity('MI5') and NQ._is_entity('GS25')
    assert not NQ._is_entity('S&P500') and not NQ._is_entity('1월부')


def test_url_normalization_never_discards_an_article_identifier():
    assert U.normalize_article_url('https://www.yna.co.kr/view/AKR123?input=1195m') == 'https://www.yna.co.kr/view/AKR123'
    assert U.normalize_article_url('https://example.org/news?idxno=123&utm_source=feed') == 'https://example.org/news?idxno=123'
    assert U.normalize_article_url('https://example.org/news?idxno=124') != U.normalize_article_url('https://example.org/news?idxno=123')
    assert U._source_urls({'sources': [{'url': 'https://example.org/a'}, {'url': 'https://example.org/b'}]}) == {'https://example.org/a'}


def test_article_restore_preserves_new_articles_and_concurrent_edits(monkeypatch, tmp_path):
    news = tmp_path/'news'
    news.mkdir()
    path = news/'2026-11-29.json'
    before = {'id': 'a', 'core_summary': 'old'}
    after = {'id': 'a', 'core_summary': 'cleaned'}
    path.write_text(json.dumps({'items': [before]}))
    journal = tmp_path/'change-journal.jsonl'
    assert R.apply_changes(path, {0: (before, after)}, journal=journal)[0] == 1
    payload = json.loads(path.read_text())
    payload['items'].append({'id': 'new', 'core_summary': 'new collection'})
    payload['items'][0]['source_count'] = 9
    path.write_text(json.dumps(payload))
    monkeypatch.setattr(U, 'NEWS_DIR', news)
    monkeypatch.setattr(U, 'rebuild_index', lambda: None)
    R.restore(tmp_path)
    saved = json.loads(path.read_text())['items']
    assert saved == [{**before, 'source_count': 9}, {'id': 'new', 'core_summary': 'new collection'}]
    assert R.apply_changes(path, {0: ({**before, 'source_count': 9}, after)}, journal=tmp_path/'again.jsonl')[0] == 1
    payload = json.loads(path.read_text())
    payload['items'][0]['core_summary'] = 'later editorial correction'
    path.write_text(json.dumps(payload))
    R.restore(tmp_path)
    assert json.loads(path.read_text())['items'][0]['core_summary'] == 'later editorial correction'


def test_legacy_whole_file_restore_is_refused(tmp_path):
    (tmp_path/'day-files').mkdir()
    with pytest.raises(SystemExit, match='이후 수집분'):
        R.restore(tmp_path)


def test_invalid_visibility_never_overwrites_the_archive(monkeypatch, tmp_path):
    monkeypatch.setattr(U, 'NEWS_DIR', tmp_path)
    path = tmp_path/'2026-11-29.json'
    path.write_text('{"items": []}')
    with pytest.raises(ValueError, match='노출 상태'):
        U.atomic_write_json(path, {'items': [{'id': 'a', 'article_body_status': 'unavailable', 'detail_visible': True}]})
    assert json.loads(path.read_text()) == {'items': []}


def test_offline_cleanup_preserves_every_surviving_fact():
    sentences = [f'가나은행은 지역 기업 지원 사업의 {i}차 신청을 접수하며 기업당 {i+10}억원을 지원한다고 발표했다.' for i in range(1, 20)]
    row = {'title': '가나은행 기업 지원', 'date': '2026-11-29', 'article_body_status': 'full_text',
           'article_summary': [' '.join(sentences)+' © 2026 발행사'], 'identity_check': {'ok': True}}
    fields, _ = R.offline_fields(row)
    assert fields
    text = ' '.join(fields['article_summary'])
    assert all(sentence in text for sentence in sentences)
    assert '©' not in text


def test_audit_is_read_only_and_synchronises_actor_evidence(monkeypatch, tmp_path):
    news = tmp_path/'news'
    news.mkdir()
    path = news/'2026-11-29.json'
    row = {'id': 'actor', 'title': '은행 금리 동결', 'article_body_status': 'full_text', 'publication_status': 'detail',
           'six_w_one_h': {'who': ['S&P500']}, 'six_w_one_h_evidence': {'who': [{'value': 'S&P500', 'evidence': '지수임'}]},
           'six_w_one_h_meta': {'covered': 7, 'total': 7, 'missing': []}}
    original = json.dumps({'items': [row]})
    path.write_text(original)
    monkeypatch.setattr(U, 'NEWS_DIR', news)
    plan = R.archive_audit(tmp_path/'plan')
    after = plan['changes'][0]['after']
    assert after['six_w_one_h']['who'] == after['six_w_one_h_evidence']['who'] == []
    assert after['six_w_one_h_meta']['missing'] == ['who']
    assert after['six_w_one_h_meta']['covered'] == 6
    assert path.read_text() == original


def test_index_counts_follow_visibility_not_just_body_status(monkeypatch, tmp_path):
    row = {'id': 'x', 'title': '은행 금리 동결', 'article_body_status': 'full_text', 'publication_status': 'statistics_only',
           'quality_gate': {'passed': False}, 'summary_schema_version': U.SUMMARY_SCHEMA_VERSION}
    (tmp_path/'2026-11-29.json').write_text(json.dumps({'date': '2026-11-29', 'items': [row]}))
    monkeypatch.setattr(U, 'NEWS_DIR', tmp_path)
    monkeypatch.setattr(U, 'INDEX_PATH', tmp_path/'index.json')
    U.rebuild_index()
    index = json.loads(U.INDEX_PATH.read_text(encoding='utf-8'))
    assert index['detailed_articles'] == 0 and index['body_verified_articles'] == 1
    assert index['statistics_only_articles'] == 1
