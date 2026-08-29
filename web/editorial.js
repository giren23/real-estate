(() => {
  "use strict";

  const hub = document.getElementById("editorialSections");
  const updated = document.getElementById("editorialUpdated");
  const dialog = document.getElementById("editorialDialog");
  const article = document.getElementById("editorialArticle");
  const importantList = document.getElementById("newsList");
  if (!hub || !updated || !dialog || !article) return;

  const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[character]);
  const safeUrl = value => {
    try {
      const parsed = new URL(String(value || ""), location.origin);
      return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : "#";
    } catch (_error) {
      return "#";
    }
  };
  const formatDate = value => {
    const parts = String(value || "").split("-");
    return parts.length === 3 ? `${parts[0]}.${parts[1]}.${parts[2]}` : String(value || "");
  };

  let contentById = new Map();

  function cardHtml(item) {
    const tags = (item.tags || []).slice(0, 3).map(tag => `<span>${escapeHtml(tag)}</span>`).join("");
    return `<button type="button" class="editorial-card" data-editorial-id="${escapeHtml(item.id)}">
      <time class="editorial-date" datetime="${escapeHtml(item.date)}">${escapeHtml(String(item.date || "").slice(5).replace("-", "."))}</time>
      <span class="editorial-card-body">
        <span class="editorial-card-meta">${escapeHtml(item.eyebrow)} · 약 ${escapeHtml(item.read_minutes)}분</span>
        <strong>${item.important ? '<span class="important-prefix">[중요]</span> ' : ''}${escapeHtml(item.title)}</strong>
        <span class="editorial-card-summary">${escapeHtml(item.summary)}</span>
        <span class="editorial-card-tags">${tags}</span>
      </span>
      <span class="editorial-arrow" aria-hidden="true">›</span>
    </button>`;
  }

  function importantHtml(items) {
    if (!importantList) return;
    const order = ["증시", "금리·채권", "환율", "원자재", "산업·기업", "거시경제", "부동산", "가상자산"];
    const groups = order.map(category => ({ category, items: items.filter(item => (item.category || item.tags?.[0]) === category) })).filter(group => group.items.length);
    importantList.innerHTML = groups.length ? groups.map(group => `<section class="important-news-group">
      <header><a href="news.html?category=${encodeURIComponent(group.category)}">${escapeHtml(group.category)}</a><small>${group.items.length}건</small></header>
      <div>${group.items.map(cardHtml).join("")}</div>
    </section>`).join("") : '<p class="editorial-loading">오늘의 중요 경제·시장 뉴스를 준비 중입니다.</p>';
  }

  function sectionHtml(section) {
    const more = section.more_url ? `<a class="editorial-more" href="${safeUrl(section.more_url)}">더보기 →</a>` : "";
    return `<section class="editorial-section editorial-${escapeHtml(section.id)}">
      <div class="editorial-section-title">
        <div><span aria-hidden="true">${escapeHtml(section.icon)}</span><h3>${escapeHtml(section.title)}</h3></div>
        <span class="editorial-section-tools"><small>${escapeHtml(section.description)}</small>${more}</span>
      </div>
      <div class="editorial-list">${(section.items || []).map(cardHtml).join("")}</div>
    </section>`;
  }

  function metricsHtml(metrics) {
    if (!Array.isArray(metrics) || !metrics.length) return "";
    return `<div class="editorial-metrics">${metrics.map(metric => `<div><span>${escapeHtml(metric.label)}</span><b>${escapeHtml(metric.value)}</b><small>${escapeHtml(metric.note || "")}</small></div>`).join("")}</div>`;
  }

  function articleSectionsHtml(sections) {
    return (sections || []).map((section, index) => `<section class="editorial-article-section">
      <span class="editorial-section-number">No. ${index + 1}</span>
      <h3>${escapeHtml(section.heading)}</h3>
      ${(section.paragraphs || []).map(paragraph => `<p>${escapeHtml(paragraph)}</p>`).join("")}
      ${Array.isArray(section.bullets) && section.bullets.length ? `<ul>${section.bullets.map(bullet => `<li>${escapeHtml(bullet)}</li>`).join("")}</ul>` : ""}
    </section>`).join("");
  }

  function sourcesHtml(sources) {
    if (!Array.isArray(sources) || !sources.length) return "";
    return `<section class="editorial-sources"><h3>출처·기준일</h3><ol>${sources.map(source => `<li><a href="${safeUrl(source.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.publisher)} · ${escapeHtml(source.title)}</a><time>${escapeHtml(formatDate(source.published_at))}</time></li>`).join("")}</ol></section>`;
  }

  function detailHtml(item) {
    if (window.EditorialReport) return window.EditorialReport.render(item);
    const toc = item.longform && item.sections?.length ? `<nav class="editorial-toc"><b>이번 글 차례</b><ol>${item.sections.map(section => `<li>${escapeHtml(section.heading)}</li>`).join("")}</ol></nav>` : "";
    return `<header class="editorial-article-head">
      <span>${escapeHtml(item.eyebrow)} · ${escapeHtml(formatDate(item.date))} · 약 ${escapeHtml(item.read_minutes)}분</span>
      <h2 id="editorialDialogTitle">${escapeHtml(item.title)}</h2>
      <p>${escapeHtml(item.summary)}</p>
    </header>
    ${metricsHtml(item.metrics)}
    ${toc}
    <section class="editorial-easy"><b>쉽게 풀어쓰면</b><p>${escapeHtml(item.easy_explanation)}</p></section>
    <section class="editorial-market"><b>시장 해석</b><p>${escapeHtml(item.market_comment)}</p></section>
    ${articleSectionsHtml(item.sections)}
    ${sourcesHtml(item.sources)}
    <p class="editorial-disclaimer">${escapeHtml(item.disclaimer || "공개자료를 바탕으로 작성한 정보이며 투자 권유가 아닙니다.")}</p>`;
  }

  function openArticle(id) {
    const item = contentById.get(id);
    if (!item) return;
    article.innerHTML = detailHtml(item);
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    document.body.classList.add("dialog-open");
  }

  function closeArticle() {
    if (dialog.open && typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
    document.body.classList.remove("dialog-open");
  }

  dialog.querySelector(".editorial-dialog-close")?.addEventListener("click", closeArticle);
  dialog.addEventListener("click", event => {
    if (event.target === dialog) closeArticle();
  });
  dialog.addEventListener("close", () => document.body.classList.remove("dialog-open"));

  Promise.all([
    fetch("content/editorial.json?v=2", { cache: "no-store" }).then(response => {
      if (!response.ok) throw new Error("브리핑 자료를 불러오지 못했습니다.");
      return response.json();
    }),
    fetch("content/news/index.json?v=1", { cache: "no-store" }).then(response => response.ok ? response.json() : null).catch(() => null),
    fetch("content/analysis/index.json?v=1", { cache: "no-store" }).then(response => response.ok ? response.json() : null).catch(() => null)
  ])
    .then(([data, news, automatic]) => {
      const sections = Array.isArray(data.sections) ? data.sections : [];
      const newsSection = sections.find(section => section.id === "news");
      if (newsSection && news && Array.isArray(news.latest_items)) {
        newsSection.title = "경제 통합 뉴스";
        newsSection.description = `${news.total_articles || 0}건 · 경제·금융·증시·산업·부동산`;
        newsSection.items = news.latest_items.slice(0, 6);
        newsSection.more_url = "news.html";
      }
      if (news && Array.isArray(news.important_items)) importantHtml(news.important_items);
      const mergeSection = (id, generated, label, moreUrl) => {
        const section = sections.find(row => row.id === id);
        if (!section || !Array.isArray(generated)) return;
        const merged = [...generated, ...(section.items || [])].filter((item, index, rows) => rows.findIndex(row => row.id === item.id) === index);
        section.items = merged.slice(0, 6);
        section.description = `${label} ${merged.length}건 · 원문 링크와 검증항목 포함`;
        section.more_url = moreUrl;
      };
      if (automatic) {
        mergeSection("company", automatic.company_items, "기업분석", "analysis.html?type=company");
        mergeSection("analysis", automatic.analysis_items, "심층분석", "analysis.html?type=analysis");
      }
      const importantItems = news?.important_items || [];
      contentById = new Map([...sections.flatMap(section => section.items || []), ...importantItems].map(item => [item.id, item]));
      hub.innerHTML = sections.map(sectionHtml).join("");
      updated.textContent = `기준 ${formatDate(data.as_of)} · 원문 링크 포함`;
      hub.querySelectorAll("[data-editorial-id]").forEach(button => button.addEventListener("click", () => openArticle(button.dataset.editorialId)));
      importantList?.querySelectorAll("[data-editorial-id]").forEach(button => button.addEventListener("click", () => openArticle(button.dataset.editorialId)));
    })
    .catch(error => {
      hub.innerHTML = `<p class="editorial-loading editorial-error">${escapeHtml(error.message)}</p>`;
      updated.textContent = "불러오기 실패";
    });
})();
