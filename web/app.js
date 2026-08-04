let allTrades=[], regions=[], priceChart, pyeongChart;
const $=id=>document.getElementById(id);
const fmt=n=>Number(n||0).toLocaleString("ko-KR",{maximumFractionDigits:2});

async function load(){
  const [tradeRes, regionRes]=await Promise.all([
    fetch("data/latest_trades.json").then(r=>r.ok?r.json():[]),
    fetch("data/regions.json").then(r=>r.ok?r.json():[])
  ]);
  allTrades=tradeRes; regions=regionRes;
  $("region").innerHTML='<option value="">전국</option>'+regions.map(r=>`<option value="${r.lawd_cd}">${r.region_name}</option>`).join("");
  apply();
}

function apply(){
  const code=$("region").value;
  const apt=$("apt").value.trim().toLowerCase();
  const min=Number($("areaMin").value||0);
  const max=Number($("areaMax").value||9999);
  const rows=allTrades
    .filter(r=>(!code||r.lawd_cd===code)&&(!apt||r.apt_name.toLowerCase().includes(apt))&&r.area_m2>=min&&r.area_m2<=max)
    .sort((a,b)=>a.trade_date.localeCompare(b.trade_date));
  renderMetrics(rows);
  renderCharts(rows);
  renderTable(rows.slice().reverse().slice(0,500));
}

function renderMetrics(rows){
  const prices=rows.map(r=>r.price_eok);
  const pps=rows.map(r=>r.price_per_pyeong_manwon);
  const avg=a=>a.length?a.reduce((x,y)=>x+y,0)/a.length:0;
  $("metrics").innerHTML=[
    ["거래건수",fmt(rows.length)+"건"],
    ["평균 실거래가",fmt(avg(prices))+"억"],
    ["평균 평당가",fmt(avg(pps))+"만원"],
    ["단지 수",fmt(new Set(rows.map(r=>r.apt_name)).size)]
  ].map(([a,b])=>`<div class="metric"><span>${a}</span><b>${b}</b></div>`).join("");
}

function makeChart(canvas, old, label, rows, key, suffix){
  if(old) old.destroy();
  return new Chart(canvas,{
    type:"line",
    data:{labels:rows.map(r=>r.trade_date),datasets:[{label,data:rows.map(r=>r[key]),pointRadius:3,tension:.15}]},
    options:{responsive:true,interaction:{mode:"index",intersect:false},
      plugins:{tooltip:{callbacks:{label:c=>`${c.dataset.label}: ${fmt(c.raw)}${suffix}`}}}}
  });
}

function renderCharts(rows){
  priceChart=makeChart($("priceChart"),priceChart,"거래금액",rows,"price_eok","억");
  pyeongChart=makeChart($("pyeongChart"),pyeongChart,"평당가",rows,"price_per_pyeong_manwon","만원");
}

function renderTable(rows){
  const cols=[
    ["trade_date","거래일"],["region_name","지역"],["apt_name","단지"],
    ["dong","법정동"],["area_m2","전용㎡"],["area_pyeong","평"],
    ["floor","층"],["price_eok","억원"],["price_per_pyeong_manwon","평당만원"]
  ];
  $("trades").innerHTML="<thead><tr>"+cols.map(c=>`<th>${c[1]}</th>`).join("")+
    "</tr></thead><tbody>"+rows.map(r=>"<tr>"+cols.map(c=>`<td>${fmt(r[c[0]])}</td>`).join("")+"</tr>").join("")+"</tbody>";
}

$("apply").addEventListener("click",apply);
load();
