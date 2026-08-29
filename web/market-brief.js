(()=>{
const q=s=>document.querySelector(s);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=v=>new Intl.NumberFormat('ko-KR',{maximumFractionDigits:2}).format(Number(v||0));
const sign=(v,u='%')=>v==null?'—':`<span class="${v>0?'up':v<0?'down':'flat'}">${v>0?'+':''}${num(v)}${u}</span>`;
const shortDate=v=>String(v||'').slice(5,10).replace('-','.');
async function init(){
  const [marketResponse,newsResponse]=await Promise.all([fetch(`data/market_snapshot.json?v=${Date.now()}`),fetch(`content/news/index.json?v=${Date.now()}`)]);
  const market=await marketResponse.json(),news=await newsResponse.json();
  q('#briefingDate').textContent=market.market_date||'—';
  q('#briefingUpdatedAt').textContent=`업데이트 ${new Date(market.updated_at).toLocaleString('ko-KR')}`;
  q('#connection').innerHTML='<div><b>🔒 공개 브리핑 · 실제 거래 연결 없음</b><p>아래 모의투자는 브라우저 안의 가상 기록이며 증권사나 실제 계좌로 전송되지 않습니다.</p></div>';
  const wanted=new Set(['kospi','kosdaq','sp500','nasdaq','krw_usd','us10y','wti','gold']);
  const items=market.categories.flatMap(c=>c.items).filter(i=>wanted.has(i.key));
  q('#marketGrid').innerHTML=items.map(i=>`<article><span>${esc(i.label)}</span><b>${num(i.value)} <small>${esc(i.unit)}</small></b><p>전일 ${sign(i.changes?.day,i.change_unit)} · 1개월 ${sign(i.changes?.month,i.change_unit)}</p><time>${esc(i.date)}</time></article>`).join('');
  q('#newsList').innerHTML=(news.latest_items||[]).slice(0,8).map(i=>`<article><time datetime="${esc(i.date)}">${esc(shortDate(i.date))}</time><span>${(i.tags||[]).slice(0,2).map(t=>`#${esc(t)}`).join(' ')}</span><h3><a href="${esc(i.sources?.[0]?.url||'#')}" target="_blank" rel="noopener noreferrer">${esc(i.title)}</a></h3><p>${esc(i.market_comment||i.summary)}</p></article>`).join('')||'<p class="empty">최신 시장 뉴스를 준비 중입니다.</p>';
  q('#safetyList').innerHTML=['계좌번호·API 키·인증정보를 저장하거나 요청하지 않습니다.','가상 체결은 사용자가 확인한 뒤 이 브라우저에만 기록됩니다.','증권사 연결·실제 주문·예약 주문 코드는 공개 페이지에 없습니다.'].map(v=>`<li>${v}</li>`).join('');
}
init().catch(error=>{q('#connection').innerHTML=`<p class="error">브리핑을 불러오지 못했습니다: ${esc(error.message)}</p>`;});
})();
