"""Independent behavioral checks from the 2026-11-28 review; synthetic data only."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import news_quality as NQ
import reprocess_news as R
import update_economic_news as U
import update_editorial_analysis as A


def test_direct_source_with_an_old_publication_date_is_not_verified():
    result = NQ.verify_identity('가나은행 예금 금리 인상', ['가나은행은 예금 금리를 인상했다.'],
                                {'og:title': '가나은행 예금 금리 인상', 'article:published_time': '2020-11-28'},
                                expected_date='2026-11-28')
    assert result['date_consistent'] is False
    assert result['ok'] is False


def test_short_real_headline_is_still_checked():
    result = NQ.verify_identity('한국 금리 동결', ['한국 금리 동결을 놓고 전망이 엇갈린다.'],
                                {'og:title': '일본 증시 폭락', 'og:site_name': '예시일보'})
    assert result['ok'] is False
    assert result['page_title_similarity'] == 0


def test_question_and_answer_interview_keeps_its_answers():
    paragraphs = ['금리 동결 배경은 무엇인가?', '물가가 다시 상승하면 어떻게 대응하나?',
                  '향후 금리 전망은 어떻게 보나?',
                  '위원장은 물가와 고용 지표를 함께 살펴 다음 회의에서 결정할 계획이라고 설명했다.',
                  '위원장은 가계대출 증가와 환율 변동을 주의 깊게 점검하고 있다고 답했다.']
    page = '<article>' + ''.join(f'<p>{p}</p>' for p in paragraphs) + '</article>'
    result = NQ.extract_article(page, '금리 전망 인터뷰')
    assert any('고용 지표' in p for p in result.sentences)
    assert not result.removed.get('question_list')


def test_certificate_failure_never_adds_an_unverified_issuer(monkeypatch):
    import ssl
    from urllib.error import URLError
    contexts = []

    def fail(request, **kwargs):
        contexts.append(kwargs['context'])
        raise URLError(ssl.SSLCertVerificationError(1, 'unable to get local issuer certificate'))

    monkeypatch.setattr(U, 'urlopen', fail)
    monkeypatch.setattr(U.socket, 'create_connection', lambda *_a, **_kw: pytest.fail('no unauthenticated probe'))
    with pytest.raises(URLError):
        U._download_page('https://news.example.com/article', 'text/html')
    assert len(contexts) == 1
    assert contexts[0].check_hostname
    assert contexts[0].verify_mode == ssl.CERT_REQUIRED


def test_wrong_header_charset_can_fall_back_to_page_charset():
    from email.message import Message
    headers = Message()
    headers['Content-Type'] = 'text/html; charset=utf-8'
    page = '<meta charset=euc-kr><p>가나은행은 금리를 동결했다.</p>'
    assert U._decode_page(page.encode('euc-kr'), headers) == page


def test_compressed_page_has_a_decoded_size_limit(monkeypatch):
    import gzip
    monkeypatch.setattr(U, 'MAX_PAGE_BYTES', 80)
    with pytest.raises(ValueError, match='크기'):
        U._decode_page(gzip.compress(b'x' * 1000), {})


def test_concurrent_body_edit_cannot_be_overwritten(tmp_path):
    old = {'id': 'a', 'core_summary': 'same', 'article_summary': ['old']}
    current = dict(old, article_summary=['collector updated body'])
    path = tmp_path / 'day.json'
    path.write_text(json.dumps({'items': [current]}), encoding='utf-8')
    count, skipped = R.apply_changes(path, {0: (old, dict(old, article_summary=['reprocessed']))})
    assert count == 0 and len(skipped) == 1
    assert json.loads(path.read_text())['items'][0] == current


def test_concurrent_noncontent_metadata_is_preserved(tmp_path):
    old = {'id': 'a', 'core_summary': 'old', 'source_count': 2}
    path = tmp_path / 'day.json'
    path.write_text(json.dumps({'items': [dict(old, source_count=9)]}), encoding='utf-8')
    count, _ = R.apply_changes(path, {0: (old, dict(old, core_summary='new'))})
    saved = json.loads(path.read_text())['items'][0]
    assert count == 1 and saved['core_summary'] == 'new'
    assert saved['source_count'] == 9


def test_http_only_evidence_is_not_silently_deleted():
    sources = A.source_contract([{'publisher': '공공기관', 'title': '원자료', 'url': 'http://example.org/article/1'}])
    assert len(sources) == 1 and sources[0]['url'] == 'http://example.org/article/1'


def test_successful_reprocess_clears_stale_failure_metadata():
    old = {'id': 'a', 'article_body_status': 'unavailable', 'publication_status': 'statistics_only',
           'detail_visible': False, 'article_body_failure_kind': 'fetch_error', 'article_body_error': 'old error',
           'next_body_retry_at': '2027-01-01', 'recovery_status': 'retry_scheduled'}
    fields = {'article_body_status': 'full_text', 'publication_status': 'detail', 'article_summary': ['검증된 본문'],
              'quality_gate': {'passed': True}, 'next_body_retry_at': '', 'recovery_status': 'verified'}
    updated = R.merged_item(old, fields)
    assert updated['detail_visible'] is True
    assert updated['next_body_retry_at'] == '' and updated['recovery_status'] == 'verified'
    assert not updated.get('article_body_error') and not updated.get('article_body_failure_kind')


def test_different_articles_with_the_same_homepage_are_not_merged():
    first = {'id': 'a', 'title': '은행 금리 인상', 'canonical_source_url': 'http://example.org/'}
    second = {'id': 'b', 'title': '자동차 수출 증가', 'canonical_source_url': 'http://example.org/'}
    assert len(U.merge_day_items([first], [second])) == 2


def test_long_running_writer_keeps_its_lock(monkeypatch, tmp_path):
    import os
    import time
    lock = tmp_path / '.lock'
    lock.write_text(json.dumps({'pid': os.getpid(), 'token': 'other'}), encoding='utf-8')
    os.utime(lock, (time.time()-4000, time.time()-4000))
    monkeypatch.setattr(U, 'LOCK_PATH', lock)
    monkeypatch.setattr(U, '_run_lock_token', None)
    assert not U.acquire_run_lock()
    U.release_run_lock()
    assert lock.exists()


def test_release_only_removes_the_owned_lock(monkeypatch, tmp_path):
    lock = tmp_path / '.lock'
    monkeypatch.setattr(U, 'LOCK_PATH', lock)
    monkeypatch.setattr(U, '_run_lock_token', None)
    assert U.acquire_run_lock()
    lock.write_text(json.dumps({'pid': 1, 'token': 'replacement-owner'}), encoding='utf-8')
    U.release_run_lock()
    assert lock.exists()


def test_related_link_and_editorial_instructions_are_not_article_prose():
    paragraphs = ['가나은행은 28일 예금 금리를 동결한다고 발표했다.',
                  '위원회는 물가와 고용 지표를 면밀하게 점검하겠다고 밝혔다.',
                  '다음 회의는 내달 열리며 정책 방향을 다시 논의할 계획이다.']
    page = ('<article>' + ''.join(f'<p>{p}</p>' for p in paragraphs)
            + '<p><a href="/other">전혀 다른 아파트 가격이 20% 오른 이유는?</a></p>'
            + '<p>크롤링 데이터 기준 확인되는 사실만 정리하고, 확인되지 않는 정보는 확인되지 않았다고 적는다.</p>'
            + '</article>')
    result = NQ.extract_article(page, '가나은행 금리 동결')
    assert result.sentences == paragraphs


def test_lexical_difference_does_not_hide_a_verified_summary():
    item = {'title': '전혀 겹치지 않는 다른 한국어 제목 예시', 'article_summary': ['위원회는 경제를 주시하고 있다.'],
            'identity_check': {'ok': True, 'page_title_similarity': 1.0},
            'article_body_status': 'full_text', 'publication_status': 'detail'}
    assert R.stored_summary_problem(item) == ''
    assert R.decide(item, None, '접근 제한 HTTP 403', demote=True).startswith('keep:')


def test_detail_can_display_late_figures_and_actual_body_publisher():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is unavailable')
    report = Path(__file__).resolve().parents[1] / 'web/report.js'
    item = {'title': '검증 기사', 'article_summary': ['확인된 본문'], 'core_summary': '핵심',
            'body_source_publisher': '실제 본문 매체', 'body_published_at': '2026-11-28',
            'key_figures': [{'value': f'{i}억원', 'context': f'문맥 {i}'} for i in range(1, 16)]}
    js = ('global.window={};global.location={origin:"http://localhost"};'
          + report.read_text(encoding='utf-8')
          + '\nconst html=window.EditorialReport.render(' + json.dumps(item, ensure_ascii=False) + ',{kind:"news"});'
          + 'if(!html.includes("15억원")||!html.includes("실제 본문 매체")||!html.includes("<details>"))process.exit(1);')
    subprocess.run([node, '-e', js], check=True, capture_output=True, text=True, encoding='utf-8')
