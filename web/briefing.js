(() => {
  "use strict";
  const $ = selector => document.querySelector(selector);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
  const pageNumber = () => Math.max(1, Number(new URLSearchParams(location.search).get("page")) || 1);
  const pagesHtml = (pages, active) => pages.map((_page, index) => `<a href="?page=${index + 1}" class="${index + 1 === active ? "active" : ""}" aria-label="${index + 1}페이지${index + 1 === active ? " 현재" : ""}">${index + 1}</a>`).join("");
  const render = data => {
    $("#briefingDate").textContent = data.date;
    $("#briefingContent").innerHTML = `<section class="brief-card brief-summary"><div><span>전수 스캔 · 약식</span><h2>${esc(data.title)}</h2><p>상세 내용은 현재 개발 중입니다.</p></div><strong>매일 오전 7시 15분</strong></section><div class="briefing-outline">${(data.sections || []).map(section => `<section class="brief-card brief-outline-card"><div class="brief-card-head"><h2>${esc(section.title)}</h2><p>${esc(section.subtitle || "핵심 총평")}</p></div><div class="brief-placeholder">${section.summary ? esc(section.summary) : "개발 중"}</div></section>`).join("")}</div><p class="brief-disclaimer">${esc(data.disclaimer)}</p>`;
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
