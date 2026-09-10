(() => {
  "use strict";
  const $ = selector => document.querySelector(selector);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
  const pageNumber = () => Math.max(1, Number(new URLSearchParams(location.search).get("page")) || 1);
  const pagesHtml = (pages, active) => pages.map((_page, index) => `<a href="?page=${index + 1}" class="${index + 1 === active ? "active" : ""}" aria-label="${index + 1}페이지${index + 1 === active ? " 현재" : ""}">${index + 1}</a>`).join("");
  const orderedSections = sections => {
    const preferredOrder = ["verdict", "us", "kr", "sectors", "risk", "action", "core", "events", "hynix", "world"];
    const rank = new Map(preferredOrder.map((id, index) => [id, index]));
    return [...(sections || [])].sort((left, right) => (rank.get(left.id) ?? preferredOrder.length) - (rank.get(right.id) ?? preferredOrder.length));
  };
  const metricHtml = metric => `<div class="brief-metric"><span>${esc(metric.label)}</span><b>${esc(metric.value)}</b><em class="${esc(metric.tone || "flat")}">${esc(metric.change)}</em><small>기준일 ${esc(metric.date)}</small></div>`;
  const newsHtml = news => (news || []).map(item => `<article><time>${esc(item.publisher || "출처 미상")}${item.important ? " · [중요]" : ""}</time><h3>${item.url ? `<a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.title)}</a>` : esc(item.title)}</h3><p>${esc(item.summary || "원문 요약을 확인 중입니다.")}</p></article>`).join("");
  const detailHtml = section => (section.details || []).map(paragraph => `<p class="brief-detail">${esc(paragraph)}</p>`).join("");
  const renderSection = section => `<section class="brief-card"><div class="brief-card-head"><div><h2>${esc(section.title)}</h2><p>${esc(section.subtitle || "핵심 총평")}</p></div></div><p class="brief-section-summary">${esc(section.summary || "자료 준비 중")}</p>${detailHtml(section)}${(section.metrics || []).length ? `<div class="brief-metrics">${section.metrics.map(metricHtml).join("")}</div>` : ""}${(section.checks || []).length ? `<ul class="brief-checks">${section.checks.map(check => `<li>${esc(check)}</li>`).join("")}</ul>` : ""}${(section.scenarios || []).length ? `<div class="brief-scenarios">${section.scenarios.map(scenario => `<article><span>${esc(scenario.label)}</span><b>${esc(scenario.title)}</b><p>${esc(scenario.body)}</p></article>`).join("")}</div>` : ""}${(section.news || []).length ? `<div class="brief-news">${newsHtml(section.news)}</div>` : ""}</section>`;
  const render = data => {
    $("#briefingDate").textContent = data.date;
    $("#briefingContent").innerHTML = `<section class="brief-card brief-summary"><div><span>AM 08:10 · CHAT BRIEFING FORMAT</span><h2>${esc(data.title)}</h2><p>${esc(data.summary || "시장 스냅샷과 주요 뉴스를 결합한 오전 브리핑입니다.")}</p></div><strong>매일 자동 갱신</strong></section><div class="briefing-outline">${orderedSections(data.sections).map(renderSection).join("")}</div><p class="brief-disclaimer">${esc(data.disclaimer)}</p>`;
  };
  async function init() {
    const indexResponse = await fetch(`content/investment-briefing/index.json?v=${Date.now()}`, { cache: "no-store" });
    if (!indexResponse.ok) throw new Error("브리핑 목록을 불러오지 못했습니다.");
    const index = await indexResponse.json(), pages = index.pages || [];
    if (!pages.length) throw new Error("아직 생성된 투자 브리핑이 없습니다.");
    const active = Math.min(pageNumber(), pages.length), pagination = pagesHtml(pages, active);
    $("#briefingPaginationTop").innerHTML = pagination; $("#briefingPaginationBottom").innerHTML = pagination;
    const response = await fetch(`content/investment-briefing/${encodeURIComponent(pages[active - 1].file)}?v=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error("선택한 날짜의 브리핑을 불러오지 못했습니다.");
    render(await response.json()); $("#briefingStatus").hidden = true;
  }
  init().catch(error => { $("#briefingStatus").classList.add("error"); $("#briefingStatus").textContent = error.message; });
})();
