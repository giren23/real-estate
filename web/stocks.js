(()=>{
const $=selector=>document.querySelector(selector);
const formatNumber=(value,digits=2)=>new Intl.NumberFormat('ko-KR',{maximumFractionDigits:digits}).format(Number(value||0));
const signed=(value,unit='%')=>value===null||value===undefined?'—':`<span class="${value>0?'up':value<0?'down':'flat'}">${value>0?'+':''}${formatNumber(value,2)}${unit}</span>`;
const escapeHtml=value=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const safeUrl=value=>{try{const url=new URL(String(value||''),location.href);return url.protocol==='https:'?url.href:'';}catch{return '';}};
const shortDate=value=>String(value||'').slice(5,10).replace('-','.');

function connection(data){
  const connected=data.credentials_configured;
  return `<div><span class="status-dot ${connected?'ready':'waiting'}"></span><div><b>${connected?'KIS 모의 API 준비됨':'KIS 모의 API 연결 대기'}</b><p>${data.error||`모의투자 전용 · 계좌 ${data.account_configured?'확인됨':'미설정'} · 자동 주문 없음`}</p></div></div><strong class="lock safe">🔒 매 주문 직접 승인</strong>`;
}
function marketCard(item){
  return `<article><span>${escapeHtml(item.label)}</span><b>${formatNumber(item.value,Math.abs(item.value)>=100?2:4)}<small>${escapeHtml(item.unit)}</small></b><p>전일 ${signed(item.changes?.day,item.change_unit||'%')} · 1개월 ${signed(item.changes?.month,item.change_unit||'%')}</p><time>${escapeHtml(item.date)}</time></article>`;
}
function signalBadge(action){
  const labels={BUY_CANDIDATE:'매수 후보',SELL_CANDIDATE:'매도 후보',HOLD:'관망'};
  return `<span class="signal ${String(action).toLowerCase()}">${labels[action]||action}</span>`;
}
function watchCard(item){
  const signal=item.signal||{};
  if(item.error)return `<article><div><b>${escapeHtml(item.name)}</b><small>${escapeHtml(item.symbol)}</small></div>${signalBadge('HOLD')}<p>${escapeHtml(item.error)}</p></article>`;
  return `<article><div><b>${escapeHtml(item.name)}</b><small>${escapeHtml(item.symbol)}</small></div>${signalBadge(signal.action)}<strong>${formatNumber(item.price,0)}원 <em>${signed(item.change_pct)}</em></strong><p>${escapeHtml(signal.reason)} · RSI ${signal.rsi14===null?'—':formatNumber(signal.rsi14,1)}</p></article>`;
}
function newsCard(item){
  const source=item.sources?.[0];
  const title=escapeHtml(item.title);
  const url=safeUrl(source?.url);
  return `<article><time datetime="${escapeHtml(item.date)}">${escapeHtml(shortDate(item.date))}</time><div><span>${(item.tags||[]).slice(0,2).map(tag=>`#${escapeHtml(tag)}`).join(' ')}</span><h3>${url?`<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${title}</a>`:title}</h3><p>${escapeHtml(item.market_comment||item.summary)}</p></div></article>`;
}
function riskCards(risk){
  const rows=[['1회 주문 한도',`${formatNumber(risk.max_order_krw,0)}원`],['하루 주문',`${risk.max_daily_orders}회`],['종목 비중',`${risk.max_position_pct}%`],['일일 손실 중단',`-${risk.max_daily_loss_pct}%`],['총 노출 한도',`${risk.max_total_exposure_pct}%`],['시장가·공매도',`${risk.allow_market_orders?'허용':'금지'} · ${risk.allow_short_selling?'허용':'금지'}`]];
  return rows.map(([label,value])=>`<article><span>${label}</span><b>${value}</b></article>`).join('');
}
async function init(){
  try{
    const response=await fetch(`data/stock_briefing.json?v=${Date.now()}`);
    if(!response.ok)throw new Error(`HTTP ${response.status}`);
    const data=await response.json();
    if ($('#briefingDate')) $('#briefingDate').textContent=data.briefing_date;
    if ($('#briefingUpdatedAt')) $('#briefingUpdatedAt').textContent=`업데이트 ${new Date(data.updated_at).toLocaleString('ko-KR')}`;
    $('#connection').innerHTML=connection(data.connection);
    $('#marketGrid').innerHTML=data.market.map(marketCard).join('')||'<p class="empty">시장 자료를 준비 중입니다.</p>';
    $('#watchlist').innerHTML=data.watchlist.map(watchCard).join('')||'<p class="empty">관심종목이 비어 있습니다. KIS 모의투자 연결 후 config/trading.json에 종목을 추가하세요.</p>';
    $('#riskGrid').innerHTML=riskCards(data.risk);
    $('#safetyList').innerHTML=data.safety.map(item=>`<li>${escapeHtml(item)}</li>`).join('');
    $('#disclaimer').textContent=data.disclaimer;
  }catch(error){
    $('#connection').innerHTML=`<p class="error">브리핑을 불러오지 못했습니다: ${escapeHtml(error.message)}</p>`;
  }
}
init();
})();
