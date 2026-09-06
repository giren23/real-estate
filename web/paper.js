(() => {
  "use strict";
  const KEY = "manualPaperPortfolioV1";
  const QUOTE_KEY = "paperQuoteSymbolsV1";
  const CLOUD_KEY = "paperCloudCredentialsV1";
  const $ = selector => document.querySelector(selector);
  const money = value => `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(Math.round(Number(value) || 0))}원`;
  const clean = value => String(value || "").trim();
  const escapeHtml = value => String(value || "").replace(/[&<>"']/g, character => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[character]);
  const emptyState = cash => ({ version: 1, initialCash: cash, cash, realized: 0, positions: {}, orders: [] });
  let state;
  try { state = JSON.parse(localStorage.getItem(KEY) || "null"); } catch (_error) { state = null; }
  if (!state || state.version !== 1) state = emptyState(100000000);
  const quoteNames = {"005930":"삼성전자","000660":"SK하이닉스","005380":"현대차","035420":"NAVER","035720":"카카오","373220":"LG에너지솔루션","207940":"삼성바이오로직스","068270":"셀트리온","105560":"KB금융","005490":"POSCO홀딩스"};
  const defaultQuoteSymbols = Object.keys(quoteNames);
  let quoteSymbols = (localStorage.getItem(QUOTE_KEY) || defaultQuoteSymbols.join(",")).split(",").map(clean).filter(Boolean).slice(0, 20), quoteLoading = false;
  let cloudCredentials = null, cloudSaveTimer = 0;
  try { cloudCredentials = JSON.parse(localStorage.getItem(CLOUD_KEY) || "null"); } catch (_error) { cloudCredentials = null; }

  const cloudHeaders = () => ({"content-type":"application/json","x-paper-account":cloudCredentials?.account_id || "","authorization":`Bearer ${cloudCredentials?.token || ""}`});
  const updateCloudStatus = text => { const node=$("#paperSyncStatus"); if(node) node.textContent=text; };
  const saveCloud = async () => {
    if (!cloudCredentials) return;
    try {
      const response = await fetch("/api/paper/account", {method:"PUT",headers:cloudHeaders(),body:JSON.stringify({payload:{...state,watchlist:quoteSymbols}})});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      updateCloudStatus(`클라우드 저장 · ${new Date().toLocaleTimeString("ko-KR")}`);
    } catch (_error) { updateCloudStatus("클라우드 저장 재시도 필요"); }
  };
  const save = () => {
    localStorage.setItem(KEY, JSON.stringify(state));
    clearTimeout(cloudSaveTimer);
    cloudSaveTimer = setTimeout(saveCloud, 700);
  };
  const positionValue = position => position.quantity * position.currentPrice;
  const positionCost = position => position.quantity * position.averagePrice;
  const totals = () => {
    const positions = Object.values(state.positions);
    const evaluation = positions.reduce((sum, item) => sum + positionValue(item), 0);
    const cost = positions.reduce((sum, item) => sum + positionCost(item), 0);
    const unrealized = evaluation - cost;
    return { evaluation, cost, unrealized, assets: state.cash + evaluation, returnPct: cost ? unrealized / cost * 100 : 0 };
  };
  const message = (text, type = "") => {
    const node = $("#paperMessage");
    node.className = `paper-message ${type}`.trim(); node.textContent = text;
  };

  function render() {
    const sum = totals();
    $("#paperInitialCash").value = Math.round(state.initialCash);
    $("#paperMetrics").innerHTML = [
      ["총자산", money(sum.assets), `초기자금 대비 ${money(sum.assets - state.initialCash)}`],
      ["가상 현금", money(state.cash), "주문 가능 금액"],
      ["보유 평가액", money(sum.evaluation), `${Object.keys(state.positions).length}개 종목`],
      ["평가손익", money(sum.unrealized), `${sum.returnPct >= 0 ? "+" : ""}${sum.returnPct.toFixed(2)}%`],
      ["실현손익", money(state.realized), "매도 체결 누계"]
    ].map(([label, value, note], index) => `<article><span>${label}</span><b class="${index > 2 ? (Number(value.replace(/[^0-9-]/g, "")) >= 0 ? "paper-positive" : "paper-negative") : ""}">${value}</b><small>${note}</small></article>`).join("");
    const positions = Object.values(state.positions).sort((a, b) => a.name.localeCompare(b.name, "ko"));
    $("#paperPositions").innerHTML = positions.length ? positions.map(item => {
      const profit = positionValue(item) - positionCost(item), rate = positionCost(item) ? profit / positionCost(item) * 100 : 0;
      return `<tr><th>${item.name}<small>${item.symbol}</small></th><td>${item.quantity.toLocaleString("ko-KR")}</td><td>${money(item.averagePrice)}</td><td><input class="paper-mark-price" data-symbol="${item.symbol}" type="number" min="0.01" step="0.01" value="${item.currentPrice}" aria-label="${item.name} 현재가"></td><td>${money(positionValue(item))}</td><td class="${profit >= 0 ? "paper-positive" : "paper-negative"}">${profit >= 0 ? "+" : ""}${money(profit)}<small>${rate >= 0 ? "+" : ""}${rate.toFixed(2)}%</small></td></tr>`;
    }).join("") : '<tr><td class="paper-empty" colspan="6">아직 보유한 가상 종목이 없습니다.</td></tr>';
    $("#paperOrders").innerHTML = state.orders.length ? [...state.orders].reverse().map(order => `<tr><td>${new Date(order.time).toLocaleString("ko-KR")}</td><td class="${order.side === "BUY" ? "paper-positive" : "paper-negative"}">${order.side === "BUY" ? "매수" : "매도"}</td><td>${order.name}<small>${order.symbol}</small></td><td>${money(order.price)}</td><td>${order.quantity.toLocaleString("ko-KR")}</td><td>${money(order.costs)}</td><td>${money(order.cashAfter)}</td></tr>`).join("") : '<tr><td class="paper-empty" colspan="7">가상 거래내역이 없습니다.</td></tr>';
    $("#paperOrderCount").textContent = `${state.orders.length}건`;
    document.querySelectorAll(".paper-mark-price").forEach(input => input.addEventListener("change", event => {
      const position = state.positions[event.target.dataset.symbol], value = Number(event.target.value);
      if (!position || !(value > 0)) return message("현재가는 0보다 크게 입력해 주세요.", "error");
      position.currentPrice = value; save(); render(); message(`${position.name} 현재가를 ${money(value)}으로 갱신했습니다.`, "success");
    }));
  }

  function orderPreview() {
    const side = $("#paperSide").value, price = Number($("#paperPrice").value), quantity = Number($("#paperQuantity").value);
    const feeRate = Math.max(0, Number($("#paperFeeRate").value) || 0) / 100;
    const sellTaxRate = Math.max(0, Number($("#paperSellTaxRate").value) || 0) / 100;
    const gross = price * quantity, costs = gross * (feeRate + (side === "SELL" ? sellTaxRate : 0));
    const valid = price > 0 && Number.isInteger(quantity) && quantity > 0;
    $("#paperOrderPreview").textContent = valid ? `${side === "BUY" ? "매수" : "매도"} ${quantity.toLocaleString("ko-KR")}주 · 주문금액 ${money(gross)} · 예상비용 ${money(costs)} · ${side === "BUY" ? "필요현금" : "예상수령"} ${money(side === "BUY" ? gross + costs : gross - costs)}` : "종목·가격·수량을 입력하면 예상 금액이 표시됩니다.";
    $("#paperConfirm").checked = false; $("#paperSubmit").disabled = true;
  }

  const renderQuotes = items => {
    $("#paperQuoteGrid").innerHTML = items.length ? items.map(item => item.error ? `<article><button class="paper-quote-remove" data-remove-symbol="${escapeHtml(item.symbol)}" type="button" aria-label="목록에서 삭제">×</button><span>${escapeHtml(quoteNames[item.symbol] || item.symbol)}</span><b>조회 실패</b><small>${escapeHtml(item.symbol)}</small></article>` : `<article><button class="paper-quote-remove" data-remove-symbol="${escapeHtml(item.symbol)}" type="button" aria-label="목록에서 삭제">×</button><span>${escapeHtml(item.name || quoteNames[item.symbol] || item.symbol)}</span><b>${money(item.price)}</b><small class="${item.change_pct >= 0 ? "paper-positive" : "paper-negative"}">${item.change_pct >= 0 ? "+" : ""}${Number(item.change_pct).toFixed(2)}% · ${escapeHtml(item.symbol)}</small></article>`).join("") : "<p>표시할 현재가가 없습니다.</p>";
    document.querySelectorAll("[data-remove-symbol]").forEach(button => button.addEventListener("click", () => {
      quoteSymbols = quoteSymbols.filter(symbol => symbol !== button.dataset.removeSymbol);
      localStorage.setItem(QUOTE_KEY, quoteSymbols.join(",")); $("#paperQuoteSymbols").value = quoteSymbols.join(","); save(); refreshQuotes();
    }));
  };
  async function refreshQuotes() {
    if (quoteLoading || !quoteSymbols.length || document.hidden) return;
    quoteLoading = true;
    try {
      const response = await fetch(`/api/paper/quotes?symbols=${encodeURIComponent(quoteSymbols.join(","))}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      $("#paperQuoteStatus").textContent = payload.available ? `자동 갱신 · ${new Date().toLocaleTimeString("ko-KR")}` : "실시간 연결 대기";
      if (!payload.available) { $("#paperQuoteGrid").innerHTML = `<p>${payload.message || "PC의 읽기 전용 시세 연결을 확인해 주세요."}</p>`; return; }
      renderQuotes(payload.items || []);
      (payload.items || []).forEach(item => { if (!item.error && state.positions[item.symbol]) state.positions[item.symbol].currentPrice = item.price; });
      save(); render();
    } catch (_error) {
      $("#paperQuoteStatus").textContent = "시세 서버 연결 대기";
      $("#paperQuoteGrid").innerHTML = "<p>PC 서버가 켜지고 시세 연결이 준비되면 자동으로 표시됩니다.</p>";
    } finally { quoteLoading = false; }
  }
  $("#paperQuoteApply")?.addEventListener("click", () => {
    const values = $("#paperQuoteSymbols").value.split(",").map(clean).filter(Boolean);
    if (values.length > 20) return message("현재가 목록은 최대 20종목입니다.", "error");
    if (!values.length || values.some(value => !/^\d{6}$/.test(value))) return message("숫자 6자리 종목코드를 쉼표로 구분해 입력해 주세요.", "error");
    quoteSymbols = [...new Set(values)]; localStorage.setItem(QUOTE_KEY, quoteSymbols.join(",")); refreshQuotes();
    save();
  });

  const selectSearchResult = (symbol, name) => {
    if (!quoteSymbols.includes(symbol)) quoteSymbols = [...quoteSymbols, symbol].slice(0, 20);
    quoteNames[symbol] = name;
    localStorage.setItem(QUOTE_KEY, quoteSymbols.join(","));
    $("#paperQuoteSymbols").value = quoteSymbols.join(",");
    $("#paperSymbol").value = symbol; $("#paperName").value = name;
    $("#paperSearchResults").innerHTML = ""; save(); refreshQuotes(); orderPreview();
  };
  const searchCompanies = async () => {
    const query = clean($("#paperCompanySearch").value);
    if (!query) return;
    $("#paperSearchResults").innerHTML = "<p>검색 중…</p>";
    try {
      const response = await fetch(`/api/paper/search?q=${encodeURIComponent(query)}`, {cache:"no-store"});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "검색 실패");
      $("#paperSearchResults").innerHTML = (payload.items || []).map(item => `<button type="button" data-symbol="${escapeHtml(item.symbol)}" data-name="${escapeHtml(item.name)}"><span>${escapeHtml(item.name)}</span><small>${escapeHtml(item.symbol)} · ${escapeHtml(item.exchange)}</small></button>`).join("") || "<p>검색 결과가 없습니다.</p>";
      document.querySelectorAll("#paperSearchResults button").forEach(button => button.addEventListener("click", () => selectSearchResult(button.dataset.symbol, button.dataset.name)));
    } catch (error) { $("#paperSearchResults").innerHTML = `<p>${error.message}</p>`; }
  };
  $("#paperCompanySearchButton")?.addEventListener("click", searchCompanies);
  $("#paperCompanySearch")?.addEventListener("keydown", event => { if(event.key === "Enter"){event.preventDefault();searchCompanies();} });

  $("#paperCloudCreate")?.addEventListener("click", async () => {
    if (cloudCredentials && !window.confirm("이미 연결된 클라우드 계좌가 있습니다. 새 계좌를 만들까요?")) return;
    try {
      const response = await fetch("/api/paper/account", {method:"POST"});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "계좌 생성 실패");
      cloudCredentials = {account_id:payload.account_id,token:payload.token};
      localStorage.setItem(CLOUD_KEY, JSON.stringify(cloudCredentials));
      await saveCloud(); message("클라우드 보관을 시작했습니다. 복구키 파일을 안전하게 백업하세요.", "success");
    } catch (error) { message(error.message, "error"); }
  });
  $("#paperCloudExport")?.addEventListener("click", () => {
    if (!cloudCredentials) return message("먼저 클라우드 보관을 시작해 주세요.", "error");
    const blob = new Blob([JSON.stringify({version:1,...cloudCredentials}, null, 2)], {type:"application/json"}), link=document.createElement("a");
    link.href=URL.createObjectURL(blob); link.download="paper-account-recovery.json"; link.click(); URL.revokeObjectURL(link.href);
  });
  $("#paperCloudImport")?.addEventListener("click", () => $("#paperCloudFile").click());
  $("#paperCloudFile")?.addEventListener("change", async event => {
    try {
      const candidate=JSON.parse(await event.target.files[0].text());
      cloudCredentials={account_id:candidate.account_id,token:candidate.token};
      const response=await fetch("/api/paper/account",{headers:cloudHeaders()});
      const payload=await response.json(); if(!response.ok) throw new Error(payload.detail || "복구 실패");
      state=payload.payload; quoteSymbols=(payload.payload.watchlist || quoteSymbols).slice(0,20);
      localStorage.setItem(CLOUD_KEY,JSON.stringify(cloudCredentials)); localStorage.setItem(KEY,JSON.stringify(state)); localStorage.setItem(QUOTE_KEY,quoteSymbols.join(","));
      render(); refreshQuotes(); updateCloudStatus("클라우드 계좌 복구됨"); message("다른 기기의 모의계좌를 불러왔습니다.","success");
    } catch(error){cloudCredentials=null;message(error.message || "복구키 파일을 확인해 주세요.","error");}
  });
  $("#paperCloudDelete")?.addEventListener("click", async () => {
    if(!cloudCredentials) return message("연결된 클라우드 계좌가 없습니다.","error");
    if(!window.confirm("클라우드의 모의계좌를 영구 삭제할까요? 현재 브라우저 기록은 유지됩니다.")) return;
    const response=await fetch("/api/paper/account",{method:"DELETE",headers:cloudHeaders()});
    if(!response.ok) return message("클라우드 계좌를 삭제하지 못했습니다.","error");
    cloudCredentials=null; localStorage.removeItem(CLOUD_KEY); updateCloudStatus("이 브라우저에만 저장됨"); message("클라우드 계좌를 삭제했습니다.","success");
  });

  $("#paperOrderForm")?.addEventListener("input", event => { if (event.target.id !== "paperConfirm") orderPreview(); });
  $("#paperConfirm")?.addEventListener("change", event => { $("#paperSubmit").disabled = !event.target.checked; });
  $("#paperOrderForm")?.addEventListener("submit", event => {
    event.preventDefault();
    const symbol = clean($("#paperSymbol").value).toUpperCase(), name = clean($("#paperName").value);
    const side = $("#paperSide").value, price = Number($("#paperPrice").value), quantity = Number($("#paperQuantity").value);
    const feeRate = Math.max(0, Number($("#paperFeeRate").value) || 0) / 100, sellTaxRate = Math.max(0, Number($("#paperSellTaxRate").value) || 0) / 100;
    if (!symbol || !name || !(price > 0) || !Number.isInteger(quantity) || quantity < 1) return message("종목·가격·수량을 올바르게 입력해 주세요.", "error");
    if (!$("#paperConfirm").checked) return message("가상 주문 내용을 먼저 확인해 주세요.", "error");
    const gross = price * quantity, costs = gross * (feeRate + (side === "SELL" ? sellTaxRate : 0));
    const position = state.positions[symbol];
    if (side === "BUY" && state.cash < gross + costs) return message("가상 현금이 부족합니다.", "error");
    if (side === "SELL" && (!position || position.quantity < quantity)) return message("매도할 가상 보유수량이 부족합니다.", "error");
    const summary = `${name}(${symbol}) ${side === "BUY" ? "매수" : "매도"} ${quantity.toLocaleString("ko-KR")}주, ${money(price)}`;
    if (!window.confirm(`${summary}\n실제 주문이 아닌 브라우저 내 가상 체결로 기록할까요?`)) return message("가상 주문을 취소했습니다.");
    if (side === "BUY") {
      const oldQuantity = position?.quantity || 0, oldCost = position ? position.averagePrice * oldQuantity : 0;
      state.positions[symbol] = { symbol, name, quantity: oldQuantity + quantity, averagePrice: (oldCost + gross + costs) / (oldQuantity + quantity), currentPrice: price };
      state.cash -= gross + costs;
    } else {
      state.realized += (price - position.averagePrice) * quantity - costs;
      position.quantity -= quantity; position.currentPrice = price; state.cash += gross - costs;
      if (position.quantity === 0) delete state.positions[symbol];
    }
    state.orders.push({ time: new Date().toISOString(), side, symbol, name, price, quantity, costs, cashAfter: state.cash });
    save(); render(); $("#paperConfirm").checked = false; $("#paperSubmit").disabled = true; message(`${summary} 가상 체결을 기록했습니다.`, "success");
  });
  $("#paperApplyCapital")?.addEventListener("click", () => {
    const cash = Number($("#paperInitialCash").value);
    if (state.orders.length || Object.keys(state.positions).length) return message("거래내역이 있으면 초기자금을 바꿀 수 없습니다. 먼저 가상계좌를 초기화해 주세요.", "error");
    if (!(cash >= 100000)) return message("초기 가상자금은 10만원 이상 입력해 주세요.", "error");
    state = emptyState(cash); save(); render(); message(`초기 가상자금을 ${money(cash)}으로 설정했습니다.`, "success");
  });
  $("#paperReset")?.addEventListener("click", () => {
    if (!window.confirm("보유 종목과 모든 가상 거래내역을 초기화할까요? 이 브라우저의 모의투자 기록만 삭제됩니다.")) return;
    state = emptyState(Number($("#paperInitialCash").value) || 100000000); save(); render(); message("가상계좌를 초기화했습니다.", "success");
  });
  $("#paperExport")?.addEventListener("click", () => {
    const blob = new Blob([JSON.stringify(state, null, 2)], { type: "application/json" }), link = document.createElement("a");
    link.href = URL.createObjectURL(blob); link.download = `paper-portfolio-${new Date().toISOString().slice(0, 10)}.json`; link.click(); URL.revokeObjectURL(link.href);
  });
  $("#paperQuoteSymbols").value = quoteSymbols.join(",");
  render(); orderPreview(); refreshQuotes(); setInterval(refreshQuotes, 15000);
  if(cloudCredentials) fetch("/api/paper/account",{headers:cloudHeaders()}).then(async response => {
    if(!response.ok) throw new Error(); const payload=await response.json(); state=payload.payload;
    quoteSymbols=(payload.payload.watchlist || quoteSymbols).slice(0,20); localStorage.setItem(KEY,JSON.stringify(state)); localStorage.setItem(QUOTE_KEY,quoteSymbols.join(","));
    $("#paperQuoteSymbols").value=quoteSymbols.join(","); render(); refreshQuotes(); updateCloudStatus("클라우드 계좌 연결됨");
  }).catch(() => updateCloudStatus("복구키 확인 필요"));
})();
