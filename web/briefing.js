(() => {
  "use strict";
  const $ = selector => document.querySelector(selector);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
  const safeUrl = value => { try { const url = new URL(String(value || ""), location.href); return ["http:", "https:"].includes(url.protocol) ? url.href : "#"; } catch (_error) { return "#"; } };
  const pageNumber = () => Math.max(1, Number(new URLSearchParams(location.search).get("page")) || 1);
  const pagesHtml = (pages, active) => pages.map((_page, index) => `<a href="?page=${index + 1}" class="${index + 1 === active ? "active" : ""}" aria-label="${index + 1}페이지${index + 1 === active ? " 현재" : ""}">${index + 1}</a>`).join("");
  const metricsHtml = metrics => `<section class="brief-card"><div class="brief-card-head"><h2>아침 핵심 지표</h2><p>현재값과 전일 변화를 함께 확인합니다.</p></div><div class="brief-metrics">${metrics.map(item => `<article class="brief-metric"><span>${esc(item.label)}</span><b>${esc(item.value)}</b><em class="${esc(item.tone)}">${esc(item.change)}</em><small>${esc(item.date)}</small></article>`).join("")}</div></section>`;
  const listHtml = (title, note, items) => `<section class="brief-card"><div class="brief-card-head"><h2>${esc(title)}</h2><p>${esc(note)}</p></div><ul class="brief-checks">${items.map(item => `<li>${esc(item)}</li>`).join("")}</ul></section>`;
  const scenariosHtml = items => `<section class="brief-card"><div class="brief-card-head"><h2>오늘의 세 가지 시나리오</h2><p>예측이 아니라 조건별 대응 점검표입니다.</p></div><div class="brief-scenarios">${items.map(item => `<article><span>${esc(item.name)}</span><b>${esc(item.condition)}</b><p>${esc(item.response)}</p></article>`).join("")}</div></section>`;
  const newsHtml = items => `<section class="brief-card"><div class="brief-card-head"><h2>오늘 확인할 주요 이슈</h2><p>제목만 보지 말고 연결된 원문을 확인하세요.</p></div><div class="brief-news">${items.map(item => `<article><time datetime="${esc(item.date)}">${esc(String(item.date).slice(5).replace("-", "."))}</time><h3><a href="${safeUrl(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.title)}</a></h3><p>${esc(item.summary)}</p><div>${(item.tags || []).map(tag => `<span>${esc(tag)}</span>`).join("")}</div></article>`).join("") || "<p>오늘 연결할 주요 이슈를 준비 중입니다.</p>"}</div></section>`;
  const render = data => {
    $("#briefingDate").textContent = data.date;
    $("#briefingContent").innerHTML = `<section class="brief-card brief-summary"><div><span>오늘의 시장 문장</span><h2>${esc(data.title)}</h2><p>${esc(data.stance)}</p></div><strong>시장 기준일 ${esc(data.market_date || "확인 중")}</strong></section>${metricsHtml(data.core_metrics || [])}${listHtml("시장 전 확인", "달러·금리·안전자산을 함께 봅니다.", data.morning_checks || [])}${listHtml("직접 판단 체크리스트", "모든 결정과 주문은 사용자가 직접 통제합니다.", data.decision_checklist || [])}${scenariosHtml(data.scenarios || [])}${newsHtml(data.news || [])}<p class="brief-sources"><b>출처</b> ${(data.sources || []).map(source => `<a href="${safeUrl(source.url)}" target="_blank" rel="noopener">${esc(source.name)}</a>`).join(" · ")}</p><p class="brief-disclaimer">${esc(data.disclaimer)}</p>`;
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
