(() => {
  "use strict";
  const KEY = "manualPaperPortfolioV1";
  const QUOTE_KEY = "paperQuoteSymbolsV1";
  const $ = selector => document.querySelector(selector);
  const money = value => `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(Math.round(Number(value) || 0))}원`;
  const clean = value => String(value || "").trim();
  const emptyState = cash => ({ version: 1, initialCash: cash, cash, realized: 0, positions: {}, orders: [] });
  let state;
  try { state = JSON.parse(localStorage.getItem(KEY) || "null"); } catch (_error) { state = null; }
  if (!state || state.version !== 1) state = emptyState(100000000);
  const quoteNames = {"005930":"삼성전자","000660":"SK하이닉스","005380":"현대차","035420":"NAVER","035720":"카카오","373220":"LG에너지솔루션","207940":"삼성바이오로직스","068270":"셀트리온","105560":"KB금융","005490":"POSCO홀딩스"};
  let quoteSymbols = (localStorage.getItem(QUOTE_KEY) || $("#paperQuoteSymbols")?.value || "").split(",").map(clean).filter(Boolean).slice(0, 10), quoteLoading = false;

  const save = () => localStorage.setItem(KEY, JSON.stringify(state));
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
    $("#paperQuoteGrid").innerHTML = items.length ? items.map(item => item.error ? `<article><span>${quoteNames[item.symbol] || item.symbol}</span><b>조회 실패</b><small>${item.symbol}</small></article>` : `<article><span>${quoteNames[item.symbol] || item.symbol}</span><b>${money(item.price)}</b><small class="${item.change_pct >= 0 ? "paper-positive" : "paper-negative"}">${item.change_pct >= 0 ? "+" : ""}${Number(item.change_pct).toFixed(2)}% · ${item.symbol}</small></article>`).join("") : "<p>표시할 현재가가 없습니다.</p>";
  };
  async function refreshQuotes() {
    if (quoteLoading || !quoteSymbols.length || document.hidden) return;
    quoteLoading = true;
    try {
      const response = await fetch(`/api/paper-quotes?symbols=${encodeURIComponent(quoteSymbols.join(","))}`, { cache: "no-store" });
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
    if (values.length > 10) return message("현재가 목록은 최대 10종목입니다.", "error");
    if (!values.length || values.some(value => !/^\d{6}$/.test(value))) return message("숫자 6자리 종목코드를 쉼표로 구분해 입력해 주세요.", "error");
    quoteSymbols = [...new Set(values)]; localStorage.setItem(QUOTE_KEY, quoteSymbols.join(",")); refreshQuotes();
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
})();
