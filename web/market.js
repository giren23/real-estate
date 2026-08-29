const $=selector=>document.querySelector(selector);
const charts=[];

function number(value, digits=2){
  return new Intl.NumberFormat("ko-KR",{maximumFractionDigits:digits,minimumFractionDigits:digits}).format(Number(value));
}
function signed(value, unit){
  if(value===null||value===undefined)return '<span class="flat">—</span>';
  const cls=value>0?'up':value<0?'down':'flat';
  return `<span class="${cls}">${value>0?'+':''}${number(value,2)}${unit}</span>`;
}
function current(item){
  const digits=Math.abs(item.value)>=1000?2:Math.abs(item.value)>=10?2:4;
  return `${number(item.value,digits)}<small>${item.unit}</small>`;
}
function sparkline(item){
  const values=item.history.map(row=>Number(row.value));
  if(values.length<2)return '';
  const min=Math.min(...values),max=Math.max(...values),span=max-min||1;
  const points=values.map((value,index)=>`${index/(values.length-1)*92+4},${30-(value-min)/span*24}`).join(' ');
  const color=values.at(-1)>=values[0]?'#dc2626':'#2563eb';
  return `<svg viewBox="0 0 100 34" aria-label="13개월 미니 추세"><polyline points="${points}" fill="none" stroke="${color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}
function section(category){
  return `<article class="market-card" id="${category.id}">
    <details open><summary><span>${category.title}<small>${category.note}</small></span><b>${category.items.length}개</b></summary>
    <div class="table-scroll"><table><thead><tr><th>지표</th><th>현재</th><th>전일</th><th>1주</th><th>1개월</th><th>3개월</th><th>추세</th></tr></thead><tbody>
    ${category.items.map(item=>`<tr><th>${item.label}<small>${item.date}</small></th><td class="current">${current(item)}</td><td>${signed(item.changes.day,item.change_unit)}</td><td>${signed(item.changes.week,item.change_unit)}</td><td>${signed(item.changes.month,item.change_unit)}</td><td>${signed(item.changes.quarter,item.change_unit)}</td><td class="spark">${sparkline(item)}</td></tr>`).join('')}
    </tbody></table></div><p class="market-insight">💡 ${category.insight}</p></details></article>`;
}
function trend(item,index){
  return `<figure class="trend-card"><figcaption><div><b>${item.label}</b><small>최근 13개월 · 월말 종가</small></div><strong aria-label="최신값 ${item.date}"><em>최신</em>${current(item)}</strong></figcaption><div class="trend-canvas"><canvas id="trend-${index}"></canvas></div><p><b>${item.date} 최신값</b> · ${signed(item.changes.month,item.change_unit)} (1개월)</p></figure>`;
}
function drawTrend(item,index){
  const ctx=document.querySelector(`#trend-${index}`);
  const rising=item.history.at(-1)?.value>=item.history[0]?.value;
  charts.push(new Chart(ctx,{type:'line',data:{labels:item.history.map(row=>row.month),datasets:[{data:item.history.map(row=>row.value),borderColor:rising?'#dc2626':'#2563eb',backgroundColor:rising?'rgba(220,38,38,.08)':'rgba(37,99,235,.08)',fill:true,borderWidth:2.5,tension:.22,pointRadius:2.5,pointHoverRadius:6}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:context=>`${number(context.raw,4)} ${item.unit}`}}},scales:{x:{grid:{display:false},ticks:{maxRotation:0,autoSkip:true,maxTicksLimit:7}},y:{grace:'8%',ticks:{callback:value=>number(value,Math.abs(value)>=100?0:2)}}}}}));
}
async function init(){
  try{
    const response=await fetch(`data/market_snapshot.json?v=${Date.now()}`);
    if(!response.ok)throw new Error(`HTTP ${response.status}`);
    const data=await response.json();
    $('#marketDate').textContent=data.market_date||'—';
    $('#updatedAt').textContent=`확인 ${new Date(data.updated_at).toLocaleString('ko-KR')}`;
    $('#marketNav').innerHTML=data.categories.map(item=>`<a href="#${item.id}">${item.title}</a>`).join('');
    $('#marketSections').innerHTML=data.categories.map(section).join('');
    $('#trendCharts').innerHTML=data.charts.map(trend).join('');
    data.charts.forEach(drawTrend);
    $('#domesticNotice').innerHTML=`<h2>${data.domestic_data.title}</h2><p>${data.domestic_data.message}</p>`;
    $('#sourceLinks').innerHTML=`<b>데이터 출처</b> ${data.sources.map(source=>`<a href="${source.url}" target="_blank" rel="noopener">${source.name}</a>`).join(' · ')}`;
    $('#marketMethod').textContent=data.method;
    $('#marketStatus').hidden=true;
  }catch(error){
    $('#marketStatus').classList.add('error');
    $('#marketStatus').textContent=`시장 자료를 불러오지 못했습니다: ${error.message}`;
  }
}
init();
