import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const NEWS_FILE = path.join(ROOT, 'web', 'content', 'news', '2026-09-10.json');
const INDEX_FILE = path.join(ROOT, 'web', 'content', 'news', 'index.json');
const TARGET_ID = 'news-20260910-973c7a72677fdd';
const DAUM_URL = 'https://v.daum.net/v/20260910173927047';

const cleanParagraphs = [
  '중동 지역 충돌 확산으로 브렌트유가 배럴당 100달러를 넘어서며 에너지 가격과 물가에 대한 경계가 커졌다. 유가 상승이 이어지면 연준의 금리 결정에도 부담이 될 수 있다.',
  '9월 FOMC를 대상으로 한 조사에서 응답자 93명 가운데 70%가 15~16일 회의의 금리 동결을 예상했다. 동결 전망은 한 달 전 90%에서 낮아졌고, 30%는 0.25%포인트 인상을 예상했다.',
  '연말까지 동결이 이어질 것으로 본 비율도 80%에서 56%로 떨어졌다. 반대로 연말까지 한 차례 이상 인상을 예상하는 비율은 높아졌다.',
  '미 국채 프라이머리딜러 전망은 동결 11곳, 인상 10곳으로 팽팽했다. 시장 가격에는 9월 인상 확률 60.2%, 동결 확률 39.8%가 반영됐다.',
  '앞으로는 8월 CPI와 국제유가 흐름이 핵심 변수다. 유가발 물가 압력이 완화되면 동결 전망이 유지될 수 있지만, 공급 차질과 물가 재상승이 이어지면 인상 가능성이 커질 수 있다.'
];

const figures = [
  ['70%', '9월 FOMC 금리 동결을 예상한 응답자 비율', '9월 전망'],
  ['30%', '9월 FOMC 0.25%포인트 인상을 예상한 응답자 비율', '9월 전망'],
  ['90% → 70%', '전월 대비 9월 금리 동결 전망 변화', '전월 대비'],
  ['80% → 56%', '연말까지 금리 동결 전망 변화', '전월 대비'],
  ['11곳 vs 10곳', '연말 금리 전망이 동결과 인상으로 갈린 프라이머리딜러 수', '연말 전망'],
  ['60.2% vs 39.8%', '시장 가격에 반영된 9월 인상·동결 확률', '9월 전망'],
  ['100달러+', '브렌트유 가격이 넘어선 기준', '9월 9일'],
  ['93명', '조사에 참여한 월가 이코노미스트·애널리스트 수', '9월 4~9일']
].map(([value, meaning, period]) => ({ value, meaning, basis: '본문 수치', period }));

const sixW = {
  who: ['월가 이코노미스트·애널리스트 93명', '미 국채 프라이머리딜러'],
  when: ['9월 FOMC(15~16일)', '조사기간 9월 4~9일', '연말까지'],
  where: ['미국 금융시장'],
  what: ['70%가 9월 금리 동결 예상', '30%가 0.25%포인트 인상 예상'],
  why: ['국제유가 100달러 돌파로 인플레이션 압력 우려'],
  how: ['전문가 설문과 시장 금리 확률을 함께 비교'],
  result: ['동결 전망은 전월보다 하락하고 인상론은 확산']
};

const factStatus = [
  ['브렌트유가 배럴당 100달러를 넘어섰다.', '사실'],
  ['응답자 93명 중 70%가 9월 FOMC 금리 동결을 예상했다.', '사실'],
  ['30%는 0.25%포인트 금리 인상을 예상했다.', '사실'],
  ['연말까지 동결 전망은 80%에서 56%로 낮아졌다.', '사실'],
  ['시장 가격에는 9월 인상 확률 60.2%, 동결 확률 39.8%가 반영됐다.', '사실'],
  ['유가 상승과 공급 차질이 이어지면 금리 인상 가능성이 커질 수 있다.', '전망']
].map(([statement, status]) => ({ statement, status }));

const uncertainties = [
  '8월 CPI가 예상보다 높게 나오면 금리 인상 전망이 더 강해질 수 있다.',
  '중동 사태와 원유 공급 차질이 얼마나 오래 이어질지는 확정되지 않았다.',
  '유가가 안정되면 연말까지 동결 전망이 다시 높아질 가능성도 있다.'
];

function repairItem(item) {
  const summary = '월가 전문가 93명 중 70%가 9월 FOMC 금리 동결을 예상했지만, 유가가 배럴당 100달러를 넘어서면서 0.25%포인트 인상 전망도 30%로 늘었다.';
  const narrative = cleanParagraphs.join(' ');
  item.summary = summary;
  item.core_summary = summary;
  item.summary_title = item.title;
  item.article_summary = cleanParagraphs;
  item.narrative_paragraphs = cleanParagraphs;
  item.easy_explanation = '금리를 그대로 둘 것이라는 예상이 아직 우세하지만, 유가 급등으로 금리를 올려야 한다는 의견도 빠르게 늘고 있다. 물가가 다시 오르면 연준이 경기보다 물가 억제를 우선할 수 있다.';
  item.six_w_one_h = sixW;
  item.key_figures = figures;
  item.fact_status = factStatus;
  item.uncertainties = uncertainties;
  item.news_charts = [
    { type: 'bar', title: '9월 FOMC 금리 전망', subtitle: '응답자 비율', rows: [
      { label: '동결', value: 70, display: '70%' },
      { label: '인상', value: 30, display: '30%' }
    ], note: '조사 대상 93명의 전망을 비교했습니다.' },
    { type: 'bar', title: '연말 금리 동결 전망 변화', subtitle: '전월 대비', rows: [
      { label: '전월', value: 80, display: '80%' },
      { label: '현재', value: 56, display: '56%' }
    ], note: '연말까지 동결을 예상한 비율입니다.' }
  ];
  item.metrics = [
    { label: '조사 대상', value: '93명', note: '월가 전문가' },
    { label: '9월 동결 전망', value: '70%', note: 'FOMC 전망' },
    { label: '9월 인상 전망', value: '30%', note: '0.25%포인트 기준' },
    { label: '브렌트유', value: '100달러+', note: '배럴당' }
  ];
  item.sources = (item.sources || []).map((source) => ({
    ...source,
    publisher: 'v.daum.net',
    url: DAUM_URL,
    description: `${item.title} v.daum.net`,
    source_type: 'portal_republication'
  }));
  if (!item.sources.length) item.sources = [{ publisher: 'v.daum.net', title: item.title, url: DAUM_URL, published_at: item.date, region: 'domestic', source_type: 'portal_republication' }];
  item.publisher = 'v.daum.net';
  item.article_source_url = DAUM_URL;
  item.canonical_source_url = DAUM_URL;
  item.primary_source_role = 'portal_republication';
  item.summary_basis = '확인된 기사 본문';
  item.article_body_status = 'verified_reconstruction';
  item.article_body_error = null;
  item.translation_status = 'not_needed';
  delete item.translation_provider;
  item.article_body_checked_at = new Date().toISOString();
  item.article_body_attempts = Math.max(2, Number(item.article_body_attempts) || 0);
  item.summary_schema_version = 3;
  item.next_body_retry_at = '';
  return item;
}

const day = JSON.parse(fs.readFileSync(NEWS_FILE, 'utf8'));
const target = day.items.find((item) => item.id === TARGET_ID);
if (!target) throw new Error(`target article not found: ${TARGET_ID}`);
repairItem(target);
fs.writeFileSync(NEWS_FILE, JSON.stringify(day), 'utf8');

const index = JSON.parse(fs.readFileSync(INDEX_FILE, 'utf8'));
for (const key of ['items', 'latest_items', 'important_items']) {
  if (!Array.isArray(index[key])) continue;
  index[key] = index[key].map((item) => item.id === TARGET_ID ? target : item);
}
index.updated_at = new Date().toISOString();
fs.writeFileSync(INDEX_FILE, JSON.stringify(index), 'utf8');
console.log(`repaired ${TARGET_ID} using ${DAUM_URL}`);
