(() => {
  "use strict";

  const esc = value => String(value ?? "").replace(/[&<>"']/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[character]);
  const safe = value => {
    try {
      const url = new URL(String(value || ""), location.origin);
      return /^https?:$/.test(url.protocol) ? url.href : "#";
    } catch (_error) {
      return "#";
    }
  };
  const isAggregatorUrl = value => {
    try {
      const host = new URL(String(value || ""), location.origin).hostname.toLowerCase();
      return ["news.google.com", "google.com", "www.google.com", "bing.com", "www.bing.com"].includes(host);
    } catch (_error) {
      return true;
    }
  };
  const number = value => {
    const match = String(value ?? "").replace(/,/g, "").match(/-?\d+(?:\.\d+)?/);
    return match ? Math.abs(Number(match[0])) : 0;
  };

  function metricsHtml(rows) {
    if (!Array.isArray(rows) || !rows.length) return "";
    return `<div class="report-metrics">${rows.map(row => `<div><span>${esc(row.label)}</span><b>${esc(row.value)}</b><small>${esc(row.note || "")}</small></div>`).join("")}</div>`;
  }

  function barChartHtml(chart) {
    const rows = Array.isArray(chart.rows) ? chart.rows : [];
    const maximum = Math.max(1, ...rows.map(row => number(row.value)));
    return `<figure class="report-chart"><figcaption><b>${esc(chart.title)}</b><span>${esc(chart.subtitle || "")}</span></figcaption><div class="report-bars">${rows.map(row => {
      const width = Math.max(3, Math.round(number(row.value) / maximum * 100));
      return `<div class="report-bar-row"><span>${esc(row.label)}</span><i><em style="width:${width}%"></em></i><b>${esc(row.display ?? row.value)}</b></div>`;
    }).join("")}</div>${chart.note ? `<p>${esc(chart.note)}</p>` : ""}</figure>`;
  }

  function donutChartHtml(chart) {
    const rows = Array.isArray(chart.rows) ? chart.rows : [];
    const total = rows.reduce((sum, row) => sum + number(row.value), 0) || 1;
    let cursor = 0;
    const colors = ["#5b3f8c", "#2f80ed", "#0f9d76", "#f2994a", "#c94f7c"];
    const stops = rows.map((row, index) => {
      const start = cursor;
      cursor += number(row.value) / total * 100;
      return `${colors[index % colors.length]} ${start.toFixed(1)}% ${cursor.toFixed(1)}%`;
    }).join(",");
    return `<figure class="report-chart report-donut-chart"><figcaption><b>${esc(chart.title)}</b><span>${esc(chart.subtitle || "")}</span></figcaption><div class="report-donut-layout"><div class="report-donut" style="background:conic-gradient(${stops})"><span><b>${esc(chart.center || String(total))}</b><small>${esc(chart.center_label || "합계")}</small></span></div><ol>${rows.map((row, index) => `<li><i style="background:${colors[index % colors.length]}"></i><span>${esc(row.label)}</span><b>${esc(row.display ?? row.value)}</b></li>`).join("")}</ol></div></figure>`;
  }

  function chartHtml(chart) {
    return chart?.type === "donut" ? donutChartHtml(chart) : barChartHtml(chart || {});
  }

  function flowHtml(steps) {
    if (!Array.isArray(steps) || steps.length < 2) return "";
    return `<section class="report-flow" aria-label="영향 전달 경로"><b>영향 전달 경로</b><div>${steps.map((step, index) => `<span><i>${index + 1}</i>${esc(step)}</span>`).join('<em aria-hidden="true">→</em>')}</div></section>`;
  }

  function tableHtml(table) {
    if (!table?.headers?.length || !table?.rows?.length) return "";
    return `<figure class="report-table"><figcaption><b>${esc(table.title || "근거 표")}</b><span>${esc(table.subtitle || "")}</span></figcaption><div><table><thead><tr>${table.headers.map(header => `<th>${esc(header)}</th>`).join("")}</tr></thead><tbody>${table.rows.map(row => `<tr>${row.map(cell => `<td>${esc(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div></figure>`;
  }

  function scenariosHtml(rows) {
    if (!Array.isArray(rows) || rows.length < 3) return "";
    return `<div class="report-scenarios">${rows.slice(0, 3).map((row, index) => `<article class="scenario-${index}"><span>${esc(row.label || ["상방", "기본", "하방"][index])}</span><b>${esc(row.title || "확인 조건")}</b><p>${esc(row.body || row)}</p></article>`).join("")}</div>`;
  }

  function sourceLedgerHtml(sources) {
    if (!Array.isArray(sources) || !sources.length) return "";
    const labels={domestic:"국내",us:"미국",global:"글로벌"};
    return `<section class="report-sources"><h3>공식 원자료·관련 보도</h3><p>주요 경제·시장 뉴스 원문과 공시·정부통계·거래소 자료를 구분해 제공합니다.</p><ol class="report-source-links">${sources.map((source, index) => {
      const unresolved = source.link_status === "unresolved_aggregator" || isAggregatorUrl(source.url) || safe(source.url) === "#";
      const label = `<span>${index === 0 ? "대표 근거 · " : ""}${esc(source.source_type||labels[source.region]||"언론")} · ${esc(source.publisher || "원문")} · ${esc(source.published_at || "-")}</span><b>${esc(source.title_ko || source.document || source.title || "원문")}</b>`;
      const link = unresolved ? `<div class="source-link-unresolved">${label}<em>원문 주소 확인 중</em></div>` : `<a href="${safe(source.url)}" target="_blank" rel="noopener noreferrer">${label}<em>원문 보기 ↗</em></a>`;
      return `<li>${link}${source.summary_ko?`<p class="source-translation"><b>한국어 번역 요약</b>${esc(source.summary_ko)}</p>`:source.region&&source.region!=="domestic"?'<p class="source-translation pending">번역 API가 연결되면 검증된 한국어 요약이 이 위치에 자동 표시됩니다.</p>':""}</li>`;
    }).join("")}</ol></section>`;
  }

  const WIKI_SEARCH = "https://namu.wiki/Search?q=";
  const CURATED_HWASEONG = {
    sourceUrl:"https://www.newscj.com/news/articleView.html?idxno=3428672",
    paragraphs:[
      "정명근 화성특례시장이 지난 27일 전국 시·군·구청장이 참석한 국정설명회에서(정부서울청사·청와대 영빈관) 시민협치 모델인 ‘화성동행기구’를 소개하고, ‘1만호 공공주택 프로젝트’와 ‘수도권 재생에너지 공급 거점 조성’을 정부에 건의함.",
      "‘화성동행기구’는 행정이 정책을 일방적으로 결정하는 기존 방식에서 벗어나 환경·도시개발·교통 분야 시민단체와 청년·어르신·노동자·기업인 등이 지역 의제 발굴 → 숙의 → 정책 설계 → 실행 → 점검까지 전 과정에 참여하는 협치 체계임. 단순히 시민 의견을 수렴하는 수준을 넘어 시민의 목소리가 실제 정책으로 연결되고 결정과 책임까지 함께하는 지방자치 모델을 만들겠다는 취지임.",
      "이와 함께 ‘화성 1만호 공공주택 프로젝트’를 정부에 건의함. 새로운 택지를 처음부터 개발하는 대신 기존 택지개발지구 내 유보지와 도시 여건 변화로 당초 용도에 맞지 않게 된 화성시·LH 소유 토지를 주택용지로 전환해 공공주택을 신속하게 공급한다는 계획임. 국토교통부 협의와 지구단위계획 변경 등의 행정절차가 원활하게 진행되면 빠르면 1년, 늦어도 2년 안에 1만 세대 이상 공급 가능하다는 게 화성시 판단임.",
      "또한 화옹지구 등을 ‘수도권 재생에너지 공급 거점’으로 조성하는 방안도 제시함. 재생에너지 전력공급 기반을 확대해 기업의 RE100 대응을 지원하는 동시에, 발전사업에 주민이 참여하고 발생한 수익을 지역사회와 나누는 주민참여형 발전수익 공유 모델을 도입할 계획임. 이를 경기도 최초의 주민참여형 발전수익 공유 사례로 추진해 기업의 친환경 전환과 지역주민의 실질적인 경제적 혜택을 동시에 달성한다는 구상임.",
      "결국 화성시는 시민이 정책 결정에 직접 참여하는 협치체계를 구축하고, 기존 공공부지를 활용해 주택공급 속도를 높이는 동시에, 재생에너지 산업의 성과를 기업과 지역주민이 함께 누리는 지역상생 모델을 만들겠다는 방향임."
    ],
    core:"정명근 화성시장이 정부에 ① 시민이 정책 전 과정에 참여하는 ‘화성동행기구’ 모델을 소개하고, ② 시·LH 보유 유휴·유보지를 주택용지로 바꿔 1~2년 내 공공주택 1만호 이상을 공급하는 방안과 ③ 화옹지구 등에 수도권 재생에너지 거점을 조성해 기업 RE100을 지원하고 발전수익을 주민과 공유하는 방안을 건의함.",
    keywords:[
      {term:"1년, 늦어도 2년 안에 1만 세대 이상 공급 가능",importance:"max",query:"화성시 1만호 공공주택 프로젝트"},
      {term:"1~2년 내 공공주택 1만호 이상",importance:"max",query:"화성시 1만호 공공주택 프로젝트"},
      {term:"1만호 공공주택 프로젝트",importance:"max"},{term:"화성 1만호 공공주택 프로젝트",importance:"max",query:"화성시 1만호 공공주택 프로젝트"},
      {term:"수도권 재생에너지 공급 거점",importance:"max"},{term:"주민참여형 발전수익 공유 모델",importance:"max"},
      {term:"화성동행기구",importance:"high"},{term:"정명근",importance:"high"},{term:"화성특례시",importance:"high"},
      {term:"LH",importance:"high",query:"한국토지주택공사"},{term:"국토교통부",importance:"high"},{term:"지구단위계획",importance:"high"},
      {term:"화옹지구",importance:"high"},{term:"RE100",importance:"high"},{term:"재생에너지",importance:"high"}
    ]
  };

  function newsNarrative(item) {
    const title = String(item.title || "");
    if (/화성특례시장|화성동행기구/.test(title) && /1만호/.test(title)) return CURATED_HWASEONG;
    const paragraphs = Array.isArray(item.article_summary) && item.article_summary.length
      ? item.article_summary
      : Array.isArray(item.narrative_paragraphs) && item.narrative_paragraphs.length
      ? item.narrative_paragraphs
      : [item.easy_explanation || item.summary || "공개 기사에서 확인된 내용은 원문 링크에서 확인할 수 있습니다."];
    return {title:item.summary_title || "기사 요약",paragraphs,core:item.core_summary || item.summary || paragraphs[0],keywords:item.highlight_keywords || []};
  }

  function emphasizedText(value, keywords) {
    const rows = (keywords || []).filter(row=>row?.term && !/\d/.test(row.term) && String(row.term).trim().length >= 2).sort((a,b)=>b.term.length-a.term.length);
    const numeric = String.raw`(?:[$€£¥]\s*)?\d[\d,.]*(?:\s*(?:조|억|만)\s*\d[\d,.]*)*\s*(?:조원|억원|만원|원|달러|엔|유로|%p|%|bp|bps|포인트|년|개월|월|일|분기|건|척|호|명|대|배럴)?`;
    const parts = rows.map(row=>row.term.replace(/[.*+?^${}()|[\]\\]/g,"\\$&"));
    const pattern = new RegExp(`(${[...parts,numeric].join("|")})`,"g");
    return String(value || "").split(pattern).map(part=>{
      const row = rows.find(item=>item.term === part);
      if (row) {
        const href = `${WIKI_SEARCH}${encodeURIComponent(row.wiki_query || row.query || row.term)}`;
        return `<a class="news-keyword ${row.importance === "max" ? "max" : "high"}" href="${href}" target="_blank" rel="noopener noreferrer">${esc(part)}</a>`;
      }
      return /^\s*(?:[$€£¥]\s*)?\d/.test(part) ? `<strong class="news-number">${esc(part)}</strong>` : esc(part);
    }).join("");
  }

  function newsReportHtml(item) {
    const narrative = newsNarrative(item);
    const summaryHeading = narrative.title === "기사 요약" ? "기사 요약" : `${narrative.title} 요약`;
    const body = narrative.paragraphs.map(paragraph=>`<p>${emphasizedText(paragraph,narrative.keywords)}</p>`).join("");
    const verifiedSourceUrl = narrative.sourceUrl || item.article_source_url;
    const sources = verifiedSourceUrl ? (item.sources || []).map((source,index)=>index === 0 ? {...source,url:verifiedSourceUrl,link_status:"verified_direct"} : source) : item.sources;
    const charts = Array.isArray(item.news_charts) && item.news_charts.length ? `<section class="news-evidence-charts"><h3>관련 통계·비교</h3><div class="report-chart-grid">${item.news_charts.map(chartHtml).join("")}</div></section>` : "";
    const uncertainties = Array.isArray(item.uncertainties) && item.uncertainties.length ? item.uncertainties : ["기사 원문에서 별도로 확인할 중대한 불확실성 없음"];
    const checks = `<section class="news-checks"><h3>확인이 필요한 사항</h3><ul>${uncertainties.map(value=>`<li>${esc(value)}</li>`).join("")}</ul></section>`;
    return `<header class="report-head news-report-head"><span>${esc(item.eyebrow)} · ${esc(item.date)} · 약 ${esc(item.read_minutes || 3)}분</span><h2 id="editorialDialogTitle">${esc(item.title)}</h2></header><section class="news-sixw-summary"><h3>${esc(summaryHeading)}</h3>${body}</section><section class="news-core-summary"><h3>핵심 요약</h3><p>${emphasizedText(narrative.core,narrative.keywords)}</p></section>${checks}${videoTranscriptHtml(item.video_transcript)}${charts}${sourceLedgerHtml(sources)}<p class="report-disclaimer">${esc(item.disclaimer || "공개자료를 바탕으로 작성한 정보이며 투자 권유가 아닙니다.")}</p>`;
  }

  function videoTranscriptHtml(video) {
    if (!video) return "";
    if (video.status !== "available") return `<section class="news-video-transcript unavailable"><h3>동영상 대화</h3><p>${esc(video.message || "공개 영어 자막이 없어 대화를 추측해 표시하지 않습니다.")}</p>${video.source_url ? `<a href="${esc(video.source_url)}" target="_blank" rel="noopener noreferrer">영상 원문 보기 ↗</a>` : ""}</section>`;
    const translated = video.translation_status === "translated";
    const rows = (video.excerpts || []).map(row=>`<li><time>${esc(row.time || "--:--")}</time><div><b>영문</b><p lang="en">${esc(row.original || "")}</p><b>한국어 번역</b><p class="video-translation ${translated ? "" : "pending"}">${translated ? esc(row.translation || "") : "번역 API가 연결되지 않아 번역문을 표시하지 않습니다."}</p></div></li>`).join("");
    return `<section class="news-video-transcript"><h3>동영상 내용 요약</h3><p class="video-summary">${esc(video.summary || "공개 자막의 주요 대화를 확인했습니다.")}</p><h4>주요 영문 대화와 번역</h4><p class="video-caption-note">공개 영어 자막 중 투자 판단과 관련된 주요 구간만 시간순으로 발췌했습니다. 자동 자막은 발음을 잘못 인식할 수 있습니다.</p><ol>${rows}</ol><a href="${esc(video.source_url)}" target="_blank" rel="noopener noreferrer">영상 원문 보기 ↗</a></section>`;
  }

  function coverageHtml(item) {
    const note = item.coverage_note || "과거 수집본의 공개 기사 제목·RSS 요약 범위입니다. 원문 전체·유료벽 내부는 추측해 채우지 않았으므로 원문 링크에서 세부 내용을 재확인해야 합니다.";
    return `<aside class="report-coverage ${item.coverage_status === "title_only" || !item.coverage_status ? "limited" : ""}"><b>요약의 확보 범위</b><p>${esc(note)}</p></aside>`;
  }

  function timelineHtml(rows) {
    if (!Array.isArray(rows) || !rows.length) return "";
    const labels={domestic:"국내",us:"미국",global:"글로벌"};
    return `<section class="report-section report-timeline"><span class="report-section-number">FACT FLOW</span><h3>시간순 사실·발언 전체 기록</h3><p>확보된 공개 원문 범위 안에서 발표·발언·반응을 시간순으로 배열했습니다. 서로 다른 매체가 같은 사실을 반복한 경우도 출처별 확인이 가능하도록 남겼습니다.</p><ol>${rows.map((row,index)=>`<li><time>${esc(row.published_time || "시간 미제공")}</time><div><b>${index+1}. ${esc(row.publisher || "원문")} · ${esc(labels[row.region] || "국내")}</b><strong>${esc(row.title_ko || row.title || "")}</strong><p>${esc(row.summary_ko || row.summary || "공개 요약이 제공되지 않았습니다.")}</p>${row.summary_ko ? `<small>번역 원문 제목: ${esc(row.title || "")}</small>` : ""}</div></li>`).join("")}</ol></section>`;
  }

  function factLedgerHtml(rows) {
    if (!Array.isArray(rows) || !rows.length) return `<section class="report-section report-facts"><span class="report-section-number">NUMBER LEDGER</span><h3>수치·발언 원장</h3><p>공개 제목·요약에서 확인된 구체적 수치가 없습니다. 원문 전체를 확보하지 않은 상태에서 숫자를 추측하지 않습니다.</p></section>`;
    return `<section class="report-section report-facts"><span class="report-section-number">NUMBER LEDGER</span><h3>수치·발언 원장</h3><p>수치의 단위와 문맥을 잃지 않도록 발견된 값을 모두 원문 문장과 함께 표시합니다.</p><div><table><thead><tr><th>시간</th><th>수치</th><th>발언·문맥</th><th>출처</th></tr></thead><tbody>${rows.map(row=>`<tr><td>${esc(row.published_time || "-")}</td><td><b>${esc(row.value)}</b></td><td>${esc(row.context)}</td><td>${esc(row.publisher || "원문")}</td></tr>`).join("")}</tbody></table></div></section>`;
  }

  function expertHtml(analysis) {
    if (!analysis) return "";
    const scenarios = Array.isArray(analysis.scenarios) ? analysis.scenarios : [];
    return `<section class="report-section report-expert"><span class="report-section-number">EXPERT VIEW</span><h3>세계 경제·투자 전문가 총평</h3><p>${esc(analysis.assessment || "후속 공식자료와 시장 반응을 함께 확인해야 합니다.")}</p>${scenarios.length ? `<div class="report-scenarios">${scenarios.map((row,index)=>`<article class="scenario-${index}"><span>${esc(row.label)}</span><b>${esc(row.title)}</b><p>${esc(row.body)}</p></article>`).join("")}</div>` : ""}<div class="report-warning-grid"><article><b>즉시 경고 조건</b><ul>${(analysis.warnings || []).map(value=>`<li>${esc(value)}</li>`).join("")}</ul></article><article><b>다음 확인 일정·값</b><ul>${(analysis.next_checks || []).map(value=>`<li>${esc(value)}</li>`).join("")}</ul></article></div></section>`;
  }

  function legacyNewsTimeline(item) {
    if (Array.isArray(item.timeline) && item.timeline.length) return item.timeline;
    return (item.sources || []).map((source,index)=>({
      published_time:source.published_time || source.published_at || item.date,
      publisher:source.publisher,
      title:source.title,
      title_ko:source.title_ko,
      summary_ko:source.summary_ko,
      summary:source.summary_original || (index === 0 ? item.easy_explanation || item.summary : "이 과거 수집본에는 공개 요약이 저장되지 않아 제목과 원문 링크만 제공합니다."),
      region:source.region || item.region
    }));
  }

  function legacyFactLedger(item) {
    if (Array.isArray(item.fact_ledger)) return item.fact_ledger;
    return (item.metrics || []).filter(row=>String(row.label || "").startsWith("기사 수치")).map(row=>({value:row.value,context:item.summary || "과거 수집본에 저장된 기사 수치",publisher:item.publisher,published_time:item.date}));
  }

  function legacyExpert(item) {
    if (item.expert_analysis) return item.expert_analysis;
    return {assessment:item.market_comment || "후속 공식 발표와 금융시장·실물경제의 반응을 순서대로 확인해야 합니다.",scenarios:[{label:"기본",title:"기사의 전제가 유지될 때",body:"후속 확정치가 같은 방향인지 확인합니다."},{label:"상방",title:"성장·이익 개선",body:"금융여건 안정과 수요 회복이 함께 확인될 때 가능성이 커집니다."},{label:"하방",title:"충격 확대",body:"금리·달러·신용위험이 동시에 상승하면 경계해야 합니다."}],warnings:["공식 확정치가 기사 전망과 반대로 바뀌는지","금리·환율·주가가 동시에 급변하는지","실물 지표가 가격 반응을 뒷받침하는지"],next_checks:["공식 발표문","다음 물가·고용·실적 발표","금리·환율의 후속 반응"]};
  }

  function sectionHtml(section, index) {
    const charts = Array.isArray(section.charts) ? section.charts.map(chartHtml).join("") : "";
    const tables = Array.isArray(section.tables) ? section.tables.map(tableHtml).join("") : "";
    const scenarios = section.scenarios ? scenariosHtml(section.scenarios) : "";
    return `<section class="report-section" id="report-section-${index + 1}"><span class="report-section-number">No. ${index + 1}</span><h3>${esc(section.heading)}</h3>${(section.paragraphs || []).map(paragraph => `<p>${esc(paragraph)}</p>`).join("")}${section.bullets?.length ? `<ul>${section.bullets.map(bullet => `<li>${esc(bullet)}</li>`).join("")}</ul>` : ""}${charts}${tables}${scenarios}</section>`;
  }

  function inferredCoverage(item) {
    const sourceCounts = new Map();
    (item.sources || []).forEach(source => sourceCounts.set(source.publisher || "기타", (sourceCounts.get(source.publisher || "기타") || 0) + 1));
    const rows = [...sourceCounts].sort((a, b) => b[1] - a[1]).slice(0, 8).map(([label, value]) => ({ label, value, display: `${value}건` }));
    return rows.length > 1 ? { type: "bar", title: "근거 출처 구성", subtitle: "동일 발행처 중복 포함", rows } : null;
  }

  function structuredNewsSections(item) {
    const category = item.category || item.tags?.[0] || "거시경제";
    const templates = {
      "금리·채권": { path:["중앙은행 결정 또는 금리 기대 변화","국채금리·환율·은행 조달비용 재조정","대출금리와 기업 자금조달비용 변화","소비·투자·주택·주식 가격에 시차를 두고 반영"], effects:["단기: 채권가격과 환율, 성장주 변동성이 먼저 커질 수 있음","중기: 가계대출 이자와 기업 금융비용이 소비·투자를 압박하거나 완화","부동산: 주택담보대출 부담과 매수 가능 금액이 변해 거래량에 선행","반대 조건: 시장이 이미 결정을 선반영했거나 물가·경기 지표가 빠르게 반전"] },
      "환율": { path:["금리차·무역수지·위험선호 변화","외환 수급과 원화 가치 조정","수입단가·수출기업 환산실적 변화","물가·기업이익·외국인 자금 흐름으로 확산"], effects:["단기: 외국인 수급과 수입 원자재 비용에 즉시 반영","중기: 수출기업과 내수기업의 이익 방향이 엇갈릴 수 있음","실물: 원화 약세가 길어지면 소비자물가와 금리 부담을 자극","반대 조건: 당국 개입, 무역수지 개선 또는 글로벌 달러 방향 전환"] },
      "원자재": { path:["공급 차질 또는 수요 전망 변화","국제 원자재 가격 조정","운송·제조·에너지 비용 변화","기업마진·소비자물가·통화정책 기대에 반영"], effects:["단기: 에너지·소재 업종과 운송 업종의 수익 전망이 갈릴 수 있음","중기: 생산자물가를 거쳐 소비자물가로 전가될 가능성","실물: 비용 상승이 오래가면 소비와 설비투자 여력을 약화","반대 조건: 재고 증가, 공급 정상화 또는 경기 수요 급감"] },
      "증시": { path:["정책·실적·유동성 정보 공개","이익 전망과 할인율 재평가","업종·지수별 자금 이동","투자·고용·소비 심리에 간접 반영"], effects:["단기: 기대와 실제 수치의 차이가 주가 변동성을 결정","중기: 실적과 현금흐름이 뒷받침되는 업종으로 차별화","실물: 자산효과와 기업 자금조달 여건을 통해 소비·투자에 영향","반대 조건: 일회성 수급, 과도한 선반영 또는 후속 실적 부진"] },
      "부동산": { path:["정책·금리·공급 정보 변화","대출 가능액과 매수·매도 기대 조정","지역별 거래량·매물·분양 수요 변화","가격·전월세·착공과 입주에 시차를 두고 반영"], effects:["단기: 규제 대상과 비대상 지역의 거래량이 먼저 갈릴 수 있음","중기: 입주물량과 대출비용이 매매·전세 가격에 누적 반영","지역: 서울 핵심지·수도권 외곽·지방의 수요 기반이 달라 차별화","반대 조건: 정책 집행 지연, 공급 일정 변경 또는 금리 방향 전환"] },
      "산업·기업": { path:["수주·실적·정책 정보 공개","매출·마진·현금흐름 기대 수정","설비투자·고용·협력사 주문 변화","산업 생산과 수출 지표에 후행 반영"], effects:["단기: 시장 기대치 대비 실적 차이가 주가에 우선 반영","중기: 수주잔고와 현금흐름이 투자·고용 지속성을 결정","실물: 공급망과 협력업체로 효과가 확산될 수 있음","반대 조건: 일회성 이익, 비용 증가 또는 수요 둔화"] },
      "거시경제": { path:["물가·고용·성장 지표 공개","금리와 경기 경로 기대 수정","환율·채권·주식·대출 조건 변화","소비·투자·고용에 시차를 두고 반영"], effects:["단기: 예상치와 실제치의 차이가 금융시장 변동성을 결정","중기: 여러 지표가 같은 방향인지에 따라 경기 판단의 신뢰도 상승","실물: 금융여건 변화가 가계와 기업의 지출 결정에 영향","반대 조건: 한 번의 지표만 튀거나 계절·기저효과가 큰 경우"] }
    };
    const template = templates[category] || templates["거시경제"];
    const coverage = item.importance?.attention_basis || `${item.related_reports || 1}건 보도 · ${item.source_count || item.sources?.length || 1}개 매체 확인`;
    return [
      { heading:"투자자가 먼저 볼 결론", paragraphs:[item.summary || item.easy_explanation || "기사의 핵심 내용을 원문과 함께 확인해야 합니다."], bullets:[`분류: ${category}`, `확인 범위: ${coverage}`, item.important ? "시장 파급력·공개 반응·보도 확산을 반영한 중요 뉴스" : "후속 공식자료와 시장 반응을 추가 확인할 뉴스"] },
      { heading:"시장 전달 경로", paragraphs:["기사의 결론을 바로 받아들이지 않고 실제 전달 경로가 이어지는지 순서대로 봅니다."], bullets:template.path.map((step,index)=>`${index+1}단계 · ${step}`) },
      { heading:"예상 효과와 반대 조건", paragraphs:[item.market_comment || "시장가격과 실물경제에 전달되는 시차와 반대 조건을 함께 확인합니다."], bullets:template.effects }
    ];
  }

  function render(item, options = {}) {
    if (options.kind === "news") return newsReportHtml(item);
    let sections = Array.isArray(item.sections) ? item.sections : [];
    const charts = Array.isArray(item.charts) ? [...item.charts] : [];
    const coverage = options.kind === "news" ? null : inferredCoverage(item);
    if (!charts.length && coverage) charts.push(coverage);
    if (options.kind === "news" && !charts.length && item.metrics?.length) charts.push({ type: "bar", title: "보도·출처 확인 범위", subtitle: "자동 군집 기준", rows: item.metrics.slice(0, 2).map(row => ({ label: row.label, value: number(row.value), display: row.value })) });
    const flow = options.kind === "news" ? [] : item.causal_path || String(item.easy_explanation || "").split("→").map(value => value.trim()).filter(Boolean);
    const toc = sections.length ? `<nav class="report-toc"><b>이번 리포트 차례</b><ol>${sections.map((section, index) => `<li><a href="#report-section-${index + 1}">${esc(section.heading)}</a></li>`).join("")}</ol></nav>` : "";
    const methodology = item.methodology || "수집된 기사 제목·공개요약을 주제별로 묶고, 중복 매체를 제거한 뒤 수치·발표·공시 확인항목을 분리했습니다. 전망은 사실이 아니라 조건별 시나리오로 표시합니다.";
    const references = item.metrics?.length ? `<aside class="report-reference"><b>참고 수집정보</b>${metricsHtml(item.metrics)}</aside>` : "";
    const deepNews = options.kind === "news" ? `${coverageHtml(item)}${timelineHtml(legacyNewsTimeline(item))}${factLedgerHtml(legacyFactLedger(item))}${expertHtml(legacyExpert(item))}` : "";
    const verification=item.verification_status?`<p class="report-verification ${item.verification_status==='official_verified'?'verified':'review'}">${item.verification_status==='official_verified'?'공식 원자료 연결·검증 완료':'공식 원자료 접수번호 재검증 필요'}</p>`:"";
    return `<header class="report-head"><span>${esc(item.eyebrow)} · ${esc(item.date)} · 약 ${esc(item.read_minutes || 3)}분</span><h2 id="editorialDialogTitle">${esc(item.title)}</h2><p>${esc(item.summary)}</p>${verification}</header>${deepNews}${toc}${flowHtml(flow)}${sections.map(sectionHtml).join("")}${charts.length ? `<section class="report-chart-grid">${charts.map(chartHtml).join("")}</section>` : ""}${sourceLedgerHtml(item.sources)}${references}<details class="report-method"><summary>수집·가공 방법</summary><p>${esc(methodology)}</p><ul><li>같은 사건의 단순 전재는 독립 근거로 과대 계산하지 않습니다.</li><li>기사 속 전망과 실제 공시·집행·실적을 구분합니다.</li><li>수치에는 기준일·단위·연결/별도 여부가 필요합니다.</li></ul></details><p class="report-disclaimer">${esc(item.disclaimer || "공개자료를 바탕으로 작성한 정보이며 투자 권유가 아닙니다.")}</p>`;
  }

  window.EditorialReport = { render };
})();
