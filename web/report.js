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
    return `<section class="report-sources"><h3>출처 원장 · 기준일</h3><p>제목·공개요약과 공식자료를 구분해 기록했습니다. 수치의 단위와 기준기간은 연결된 원문에서 다시 확인할 수 있습니다.</p><div><table><thead><tr><th>기준일</th><th>발행처</th><th>검증 자료</th></tr></thead><tbody>${sources.map(source => `<tr><td>${esc(source.published_at || "-")}</td><td>${esc(source.publisher || "-")}</td><td><a href="${safe(source.url)}" target="_blank" rel="noopener noreferrer">${esc(source.title || "원문")}</a></td></tr>`).join("")}</tbody></table></div></section>`;
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

  function enrichedNewsSections(item, sections) {
    if (sections.length >= 5) return sections;
    const metricRows = (item.metrics || []).map(row => [row.label, row.value, row.note || "-"]);
    return [...sections,
      { heading: "핵심 숫자 — 단위와 기준을 분리해서 보기", paragraphs: ["제목·공개요약에서 확인된 숫자입니다. 전망, 증감률, 금액과 실제 집행값을 같은 의미로 해석하지 않습니다."], bullets: [], tables: metricRows.length ? [{ title: "기사에서 확인된 수치", headers: ["항목", "값", "기준"], rows: metricRows }] : [] },
      { heading: "조건별 해석 — 무엇이 확인되면 결론이 달라지나", paragraphs: ["단일 보도로 방향을 단정하지 않고 후속 발표와 공식 통계가 같은 흐름인지 확인합니다."], bullets: [], scenarios: [
        { label: "강화", title: "후속 데이터가 확인", body: "공식 발표·공시·통계가 보도의 방향과 수치를 뒷받침" },
        { label: "중립", title: "기대만 선반영", body: "보도는 확산됐지만 집행·실적·거래 데이터는 아직 미확인" },
        { label: "반전", title: "전제조건이 이탈", body: "정책 변경, 비용 증가 또는 수요 둔화로 최초 해석이 약화" }
      ] }
    ];
  }

  function render(item, options = {}) {
    let sections = Array.isArray(item.sections) ? item.sections : [];
    if (options.kind === "news") sections = enrichedNewsSections(item, sections);
    const charts = Array.isArray(item.charts) ? [...item.charts] : [];
    const coverage = inferredCoverage(item);
    if (!charts.length && coverage) charts.push(coverage);
    if (options.kind === "news" && !charts.length && item.metrics?.length) charts.push({ type: "bar", title: "보도·출처 확인 범위", subtitle: "자동 군집 기준", rows: item.metrics.slice(0, 2).map(row => ({ label: row.label, value: number(row.value), display: row.value })) });
    const flow = item.causal_path || (options.kind === "news" ? ["사건·발표", "시장 기대 변화", "가격·수요 반응", "공식 통계·공시 검증"] : String(item.easy_explanation || "").split("→").map(value => value.trim()).filter(Boolean));
    const toc = sections.length ? `<nav class="report-toc"><b>이번 리포트 차례</b><ol>${sections.map((section, index) => `<li><a href="#report-section-${index + 1}">${esc(section.heading)}</a></li>`).join("")}</ol></nav>` : "";
    const methodology = item.methodology || "수집된 기사 제목·공개요약을 주제별로 묶고, 중복 매체를 제거한 뒤 수치·발표·공시 확인항목을 분리했습니다. 전망은 사실이 아니라 조건별 시나리오로 표시합니다.";
    return `<header class="report-head"><span>${esc(item.eyebrow)} · ${esc(item.date)} · 약 ${esc(item.read_minutes || 3)}분</span><h2 id="editorialDialogTitle">${esc(item.title)}</h2><p>${esc(item.summary)}</p></header>${metricsHtml(item.metrics)}${toc}<section class="report-summary-grid"><article><b>쉽게 풀어쓰면</b><p>${esc(item.easy_explanation)}</p></article><article><b>시장·실물 해석</b><p>${esc(item.market_comment)}</p></article></section>${flowHtml(flow)}${charts.length ? `<section class="report-chart-grid">${charts.map(chartHtml).join("")}</section>` : ""}${sections.map(sectionHtml).join("")}${sourceLedgerHtml(item.sources)}<details class="report-method"><summary>수집·가공 방법</summary><p>${esc(methodology)}</p><ul><li>같은 사건의 단순 전재는 독립 근거로 과대 계산하지 않습니다.</li><li>기사 속 전망과 실제 공시·집행·실적을 구분합니다.</li><li>수치에는 기준일·단위·연결/별도 여부가 필요합니다.</li></ul></details><p class="report-disclaimer">${esc(item.disclaimer || "공개자료를 바탕으로 작성한 정보이며 투자 권유가 아닙니다.")}</p>`;
  }

  window.EditorialReport = { render };
})();
