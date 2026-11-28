"""Recovery keeps the story identity while correcting provable source errors."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import news_quality as NQ
import reprocess_news as R
import update_economic_news as U


TITLE = '가나은행 예금 금리 동결…대출 지원 확대'
BODY = ['가나은행은 예금 금리를 동결하고 대출 지원을 확대한다고 발표했다.',
        '은행은 지역 기업과 가계의 금융 부담을 살피며 기존 고객에게도 동일한 금리를 적용한다고 설명했다.',
        '은행은 금융 지원 대상과 신청 일정을 추후 공지하고 영업점과 모바일 애플리케이션에서 접수를 진행할 계획이라고 덧붙였다.']


def page(title=TITLE, published='2026-09-10T09:00:00+09:00'):
    return NQ.Extraction(paragraphs=list(BODY), path='container', boundary_closed=True,
                         meta={'og:title': title, 'article:published_time': published, 'publisher': '예시뉴스'})


def item():
    return {'id': 'same-id', 'title': TITLE, 'date': '2026-09-15', 'publisher': '예시뉴스',
            'article_body_status': 'full_text', 'publication_status': 'statistics_only', 'detail_visible': False,
            'article_source_url': 'https://example.org/wrong',
            'sources': [{'url': 'https://example.org/wrong', 'resolved_url': 'https://example.org/original'}]}


def test_recovery_checks_original_source_before_wrong_discovered_page():
    assert R.recovery_source_urls(item())[0] == 'https://example.org/original'


def test_date_correction_requires_opt_in_and_exact_headline():
    original = item()
    fields, _ = R.recovered_source_fields(original, page(), 'https://example.org/original')
    assert fields is None
    fields, _ = R.recovered_source_fields(original, page(), 'https://example.org/original', allow_date_correction=True)
    assert fields and fields['date'] == '2026-09-10'
    assert fields['feed_date'] == '2026-09-15'
    assert fields['date_correction']['previous_date'] == '2026-09-15'
    updated = R.merged_item(original, fields)
    assert updated['id'] == original['id'] and U.is_publishable_detail(updated) and updated['detail_visible']
    assert updated['sources'][0]['url'] == 'https://example.org/original'
    assert updated['source_corrections'][0]['previous']['article_source_url'] == 'https://example.org/wrong'


def test_similar_headline_never_authorizes_changing_the_date():
    fields, error = R.recovered_source_fields(item(), page('가나은행 대출 금리 인하'), 'https://example.org/other', allow_date_correction=True)
    assert fields is None and '발행일' in error


def test_no_date_correction_is_needed_when_the_correct_source_matches():
    fields, _ = R.recovered_source_fields(item(), page(published='2026-09-15T09:00:00+09:00'), 'https://example.org/original', allow_date_correction=True)
    assert fields and 'date_correction' not in fields and fields['identity_check']['date_consistent']


def test_recovery_never_promotes_code_or_ui_contamination():
    dirty = page()
    dirty.paragraphs += ['document.write("광고");']
    fields, _ = R.recovered_source_fields(item(), dirty, 'https://example.org/original', allow_date_correction=True)
    assert fields is None or 'document.' not in ' '.join(fields.get('article_summary') or [])


def test_broadcast_notice_is_removed_before_selecting_the_lead():
    page_html = '<article><p>* 아래 텍스트는 실제 방송 내용과 차이가 있을 수 있으니 보다 정확한 내용은 방송으로 확인하시기 바랍니다.</p>'
    page_html += ''.join(f'<p>{row}</p>' for row in BODY) + '</article>'
    assert NQ.extract_article(page_html, TITLE).sentences[0] == BODY[0]


def test_public_js_shell_can_use_its_explicit_same_host_static_article(monkeypatch):
    called = []

    def download(url, accept):
        called.append(url)
        page_html = ('<html><link rel="amphtml" href="/amp/article/1"></html>' if '/amp/' not in url
                     else '<article>' + ''.join(f'<p>{row}</p>' for row in BODY) + '</article>')
        return page_html, url, 'text/html'

    monkeypatch.setattr(U, '_download_page', download)
    extraction, url = U.fetch_article('https://news.example.org/article/1', TITLE)
    assert len(called) == 2 and url == 'https://news.example.org/amp/article/1'
    assert extraction.sentences == BODY


def test_amp_is_not_used_after_a_paywall_or_from_an_unrelated_host(monkeypatch):
    calls = []

    def download(url, accept):
        calls.append(url)
        return '<html><link rel="amphtml" href="https://other.example.org/x"></html>', url, 'text/html'

    monkeypatch.setattr(U, '_download_page', download)
    U.fetch_article('https://news.example.org/article/1', TITLE)
    assert len(calls) == 1
    def wall(url, accept):
        return '<html>subscribe to continue<link rel="amphtml" href="/amp/x"></html>', url, 'text/html'
    monkeypatch.setattr(U, '_download_page', wall)
    import pytest
    with pytest.raises(U.AccessRestricted):
        U.fetch_article('https://news.example.org/article/1', TITLE)


def test_failed_verification_with_an_old_full_text_status_can_retry():
    row = {**item(), 'summary_schema_version': U.SUMMARY_SCHEMA_VERSION,
           'quality_gate': {'passed': False}, 'next_body_retry_at': '2020-01-01'}
    assert U.article_retry_due(row)
    row['next_body_retry_at'] = '2999-01-01'
    assert not U.article_retry_due(row)


def test_quote_page_is_never_retried_as_a_news_article():
    row = {**item(), 'title': 'Ishares Top 20 U S Stocks ETF (TOPT.N) | Stock Price & Latest News'}
    assert not U.article_retry_due(row)
    assert U.NON_ARTICLE_URL.search('https://www.reuters.com/markets/quote/TOPT.N/')


def test_index_reclassification_preserves_archived_records_and_text(monkeypatch, tmp_path):
    import json
    quote = {**item(), 'title': 'Ishares Top 20 U S Stocks ETF (TOPT.N) | Stock Price & Latest News',
             'article_summary': ['이미 저장된 내용은 통계 기록으로 보존한다.']}
    path = tmp_path/'2026-09-15.json'
    path.write_text(json.dumps({'date': path.stem, 'items': [quote]}), encoding='utf-8')
    monkeypatch.setattr(U, 'NEWS_DIR', tmp_path)
    monkeypatch.setattr(U, 'INDEX_PATH', tmp_path/'index.json')
    U.rebuild_index()
    saved = json.loads(path.read_text(encoding='utf-8'))['items']
    assert len(saved) == 1 and saved[0]['id'] == quote['id']
    assert saved[0]['article_summary'] == quote['article_summary']
    assert not U.is_publishable_detail(saved[0])


def test_scheduled_enrichment_repairs_original_source_and_date_without_ai_key(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    called = []
    def fetch(url, title):
        called.append(url)
        assert url == 'https://example.org/original'
        return page(), url
    monkeypatch.setattr(U, 'fetch_article', fetch)
    monkeypatch.setattr(U, 'discover_article_extraction', lambda *_: None)
    original = item()
    _, fields = U._article_enrichment(original)
    assert called == ['https://example.org/original']
    assert fields['date'] == '2026-09-10'
    assert fields['feed_date'] == '2026-09-15'
    assert fields['sources'][0]['url'] == 'https://example.org/original'
    assert U.apply_enrichment(original, fields) == 'updated'
    assert original['id'] == 'same-id' and original['detail_visible']


def test_automatic_date_repair_refuses_similar_old_or_unrelated_pages(monkeypatch):
    import copy
    monkeypatch.setattr(U, 'discover_article_extraction', lambda *_: None)
    for extraction, final_url in [
        (page('가나은행 대출 금리 인하'), 'https://example.org/original'),
        (page(published='2026-07-10T09:00:00+09:00'), 'https://example.org/original'),
        (page(), 'https://unrelated.example.net/article/1'),
    ]:
        original = item()
        before = copy.deepcopy(original)
        monkeypatch.setattr(U, 'fetch_article', lambda *_: (extraction, final_url))
        _, fields = U._article_enrichment(original)
        assert fields['article_body_status'] == 'unavailable'
        assert fields['recovery_status'] == 'retry_scheduled'
        assert 'date_correction' not in fields and original == before


def test_a_failed_quality_gate_cannot_replace_a_good_summary():
    original = {**item(), 'publication_status': 'detail', 'article_summary': list(BODY),
                'quality_gate': {'passed': True}}
    failed = {'article_body_status': 'full_text', 'publication_status': 'detail',
              'article_summary': ['document.write("광고");'],
              'quality_gate': {'passed': False, 'failures': ['요약에 UI·코드 문장 혼입']}}
    assert U.apply_enrichment(original, failed) == 'kept_existing'
    assert original['article_summary'] == BODY


def test_successful_automatic_recovery_clears_old_failure_flags():
    original = {**item(), 'article_body_error': '예전 오류', 'article_body_failure_kind': 'title_mismatch'}
    fields, _ = U.recovered_source_fields(original, page(), 'https://example.org/original', allow_date_correction=True)
    assert U.apply_enrichment(original, fields) == 'updated'
    assert original['detail_visible'] and 'article_body_error' not in original
    assert 'article_body_failure_kind' not in original


def test_editorial_verified_summary_survives_force_retry_and_fresh_day_merge():
    original = {**item(), 'publication_status': 'detail', 'article_body_status': 'verified_reconstruction',
                'manual_verified': True, 'editorial_verification': {'method': 'public_original_review'},
                'article_summary': ['직접 원문을 검수한 상세 요약을 보존함.'],
                'summary_schema_version': 1, 'extraction_version': 0}
    fresh = {**item(), 'publication_status': 'detail', 'article_summary': list(BODY),
             'quality_gate': {'passed': True}}
    assert not U.article_retry_due(original)
    assert U.apply_enrichment(original, fresh) == 'kept_existing'
    merged = U.merge_day_items([original], [fresh])[0]
    assert merged['article_summary'] == original['article_summary'] and merged['manual_verified']


def test_scheduled_archive_recovery_round_trip_preserves_record_and_retries(monkeypatch, tmp_path):
    import json
    original = {**item(), 'summary_schema_version': U.SUMMARY_SCHEMA_VERSION,
                'quality_gate': {'passed': False}, 'next_body_retry_at': '2020-01-01',
                'article_body_error': '발행일 불일치', 'article_body_failure_kind': 'title_mismatch'}
    path = tmp_path/'2026-09-15.json'
    path.write_text(json.dumps({'date': path.stem, 'items': [original]}), encoding='utf-8')
    monkeypatch.setattr(U, 'NEWS_DIR', tmp_path)
    monkeypatch.setattr(U, 'INDEX_PATH', tmp_path/'index.json')
    monkeypatch.setattr(U, 'fetch_article', lambda url, *_: (page(), url))
    monkeypatch.setattr(U, 'discover_article_extraction', lambda *_: None)
    assert U.enrich_archived_bodies(1) == 1
    U.rebuild_index()
    saved = json.loads(path.read_text(encoding='utf-8'))['items']
    assert len(saved) == 1 and saved[0]['id'] == original['id']
    assert saved[0]['date'] == '2026-09-10' and saved[0]['detail_visible']
    assert not U.article_retry_due(saved[0])
    assert U.enrich_archived_bodies(1) == 0
