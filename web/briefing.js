(() => {
  "use strict";
  const $ = selector => document.querySelector(selector);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
  const pageNumber = () => Math.max(1, Number(new URLSearchParams(location.search).get("page")) || 1);
  const pagesHtml = (pages, active) => pages.map((_page, index) => `<a href="?page=${index + 1}" class="${index + 1 === active ? "active" : ""}" aria-label="${index + 1}페이지${index + 1 === active ? " 현재" : ""}">${index + 1}</a>`).join("");
  const orderedSections = sections => {
    const preferredOrder = ["core", "events", "risk", "us", "kr", "hynix"];
    const rank = new Map(preferredOrder.map((id, index) => [id, index]));
    return [...(sections || [])].sort((left, right) =>
      (rank.get(left.id) ?? preferredOrder.length) - (rank.get(right.id) ?? preferredOrder.length)
    );
  };
  const metricHtml = metrics => metrics?.length ? `<section class="brief-card"><div class="brief-card-head"><h2>시장 숫자</h2><p>기준일과 등락을 함께 표시합니다</p></div><div class="brief-metrics">${metrics.map(item => `<article class="brief-metric"><span>${esc(item.label)}</span><b>${esc(item.value)}</b><em class="${esc(item.tone || "flat")}">${esc(item.change)}</em><small>${esc(item.date)}</small></article>`).join("")}</div></section>` : "";
  const sectionBody = section => {
    const summary = section.summary ? `<p class="brief-section-summary">${esc(section.summary)}</p>` : "";
    const bullets = section.bullets?.length ? `<ul class="brief-checks">${section.bullets.map(item => `<li>${esc(item)}</li>`).join("")}</ul>` : "";
    const rankings = section.rankings?.length ? `<div class="brief-rankings">${section.rankings.map(group => `<article><b>${esc(group.label)}</b><ol>${group.items.map(item => `<li>${esc(item)}</li>`).join("")}</ol></article>`).join("")}</div>` : "";
    const rows = section.rows?.length ? `<div class="brief-table-scroll"><table class="brief-table"><thead><tr>${section.columns.map(column => `<th>${esc(column)}</th>`).join("")}</tr></thead><tbody>${section.rows.map(row => `<tr>${row.map(value => `<td>${esc(value)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : "";
    const news = section.news?.length ? `<div class="brief-news">${section.news.map(item => `<article><time>${esc(item.date)}</time><h3>${item.url ? `<a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.title)}</a>` : esc(item.title)}</h3><p>${esc(item.summary)}</p><div>${(item.tags || []).map(tag => `<span>${esc(tag)}</span>`).join("")}</div></article>`).join("")}</div>` : "";
    return `${summary}${bullets}${rankings}${rows}${news}`;
  };
  const render = data => {
    $("#briefingDate").textContent = data.date;
    $("#briefingContent").innerHTML = `<section class="brief-card brief-summary"><div><span>MORNING INVESTMENT BRIEF</span><h2>${esc(data.title)}</h2><p>${esc(data.lead || "확인 가능한 시장자료를 정리했습니다.")}</p>${data.stance ? `<p class="brief-stance">${esc(data.stance)}</p>` : ""}</div><strong>매일 오전 7시</strong></section>${metricHtml(data.metrics)}<div class="briefing-outline">${orderedSections(data.sections).map(section => `<section class="brief-card brief-outline-card"><div class="brief-card-head"><h2>${esc(section.title)}</h2><p>${esc(section.subtitle || "핵심 총평")}</p></div>${sectionBody(section)}</section>`).join("")}</div><p class="brief-disclaimer">${esc(data.disclaimer)}</p>`;
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
