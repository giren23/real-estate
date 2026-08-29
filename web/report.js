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
    return `<section class="report-sources"><h3>주요 경제·시장 뉴스 원문</h3><p>비슷한 보도를 매체별로 확인할 수 있습니다. 제목을 누르면 해당 언론사의 원문으로 이동합니다.</p><ol class="report-source-links">${sources.map((source, index) => `<li><a href="${safe(source.url)}" target="_blank" rel="noopener noreferrer"><span>${index === 0 ? "대표 기사 · " : ""}${esc(source.publisher || "원문")} · ${esc(source.published_at || "-")}</span><b>${esc(source.title || "원문 보기")}</b><em>원문 보기 ↗</em></a></li>`).join("")}</ol></section>`;
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
      { heading:"핵심 요약", paragraphs:[item.summary || item.easy_explanation || "기사의 핵심 내용을 원문과 함께 확인해야 합니다."], bullets:[`분류: ${category}`, `확인 범위: ${coverage}`, item.important ? "시장 영향과 보도 확산을 함께 반영해 중요 뉴스로 분류" : "후속 공식자료와 시장 반응을 추가 확인할 뉴스"] },
      { heading:"단계별 사고 흐름", paragraphs:["기사의 결론을 바로 받아들이지 않고 다음 전달 경로가 실제로 이어지는지 순서대로 봅니다."], bullets:template.path.map((step,index)=>`${index+1}단계 · ${step}`) },
      { heading:"예상되는 효과", paragraphs:[item.market_comment || "시장가격과 실물경제에 전달되는 시차와 반대 조건을 함께 확인합니다."], bullets:template.effects },
      { heading:"다음 확인값", paragraphs:["아래 값이 후속 발표에서 같은 방향으로 움직여야 최초 해석의 신뢰도가 높아집니다."], bullets:["공식 발표문과 확정 수치", "금리·환율·채권·주가의 1차 반응", "거래량·대출·소비·고용 등 실물 지표", "정책 시행일과 적용 대상, 예외 조건"] }
    ];
  }

  function render(item, options = {}) {
    let sections = Array.isArray(item.sections) ? item.sections : [];
    if (options.kind === "news") sections = structuredNewsSections(item);
    const charts = Array.isArray(item.charts) ? [...item.charts] : [];
    const coverage = options.kind === "news" ? null : inferredCoverage(item);
    if (!charts.length && coverage) charts.push(coverage);
    if (options.kind === "news" && !charts.length && item.metrics?.length) charts.push({ type: "bar", title: "보도·출처 확인 범위", subtitle: "자동 군집 기준", rows: item.metrics.slice(0, 2).map(row => ({ label: row.label, value: number(row.value), display: row.value })) });
    const flow = options.kind === "news" ? [] : item.causal_path || String(item.easy_explanation || "").split("→").map(value => value.trim()).filter(Boolean);
    const toc = sections.length ? `<nav class="report-toc"><b>이번 리포트 차례</b><ol>${sections.map((section, index) => `<li><a href="#report-section-${index + 1}">${esc(section.heading)}</a></li>`).join("")}</ol></nav>` : "";
    const methodology = item.methodology || "수집된 기사 제목·공개요약을 주제별로 묶고, 중복 매체를 제거한 뒤 수치·발표·공시 확인항목을 분리했습니다. 전망은 사실이 아니라 조건별 시나리오로 표시합니다.";
    const references = item.metrics?.length ? `<aside class="report-reference"><b>참고 수집정보</b>${metricsHtml(item.metrics)}</aside>` : "";
    return `<header class="report-head"><span>${esc(item.eyebrow)} · ${esc(item.date)} · 약 ${esc(item.read_minutes || 3)}분</span><h2 id="editorialDialogTitle">${esc(item.title)}</h2><p>${esc(item.summary)}</p></header>${toc}${flowHtml(flow)}${sections.map(sectionHtml).join("")}${charts.length ? `<section class="report-chart-grid">${charts.map(chartHtml).join("")}</section>` : ""}${sourceLedgerHtml(item.sources)}${references}<details class="report-method"><summary>수집·가공 방법</summary><p>${esc(methodology)}</p><ul><li>같은 사건의 단순 전재는 독립 근거로 과대 계산하지 않습니다.</li><li>기사 속 전망과 실제 공시·집행·실적을 구분합니다.</li><li>수치에는 기준일·단위·연결/별도 여부가 필요합니다.</li></ul></details><p class="report-disclaimer">${esc(item.disclaimer || "공개자료를 바탕으로 작성한 정보이며 투자 권유가 아닙니다.")}</p>`;
  }

  window.EditorialReport = { render };
})();
