let allTrades = [], apartmentGroups = [], selected = [], priceChart, map, infoWindow;
const markers = new Map();
let lastGeocodeAt = 0;
const geoCache = JSON.parse(localStorage.getItem("aptGeoCache") || "{}");
const palette = ["#087a60","#175cd3","#b54708","#7f56d9","#c11574","#026aa2","#ca8504","#344054","#039855","#d92d20"];
const byId = id => document.getElementById(id);
const fmt = n => Number(n || 0).toLocaleString("ko-KR", {maximumFractionDigits: 2});
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

function groupKey(row){ return [row.lawd_cd,row.dong,row.apt_name].join("|"); }
function addressOf(group){ return [group.region_name,group.dong,group.jibun].filter(Boolean).join(" "); }
function median(values){
  if(!values.length) return 0;
  const sorted = [...values].sort((a,b)=>a-b), mid = Math.floor(sorted.length/2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid-1]+sorted[mid])/2;
}

async function load(){
  try{
    const rows = await fetch("data/latest_trades.json").then(r => { if(!r.ok) throw new Error("데이터 파일을 찾을 수 없습니다."); return r.json(); });
    allTrades = rows.filter(r => !r.cancelled);
    const groups = new Map();
    allTrades.forEach(row => {
      const key = groupKey(row);
      if(!groups.has(key)) groups.set(key,{key,lawd_cd:row.lawd_cd,region_name:row.region_name,dong:row.dong,jibun:row.jibun,apt_name:row.apt_name,trades:[]});
      groups.get(key).trades.push(row);
    });
    apartmentGroups = [...groups.values()].map(g => {
      g.trades.sort((a,b)=>a.trade_date.localeCompare(b.trade_date));
      g.areas = [...new Set(g.trades.map(r=>Number(r.area_m2)))].sort((a,b)=>a-b);
      g.latest = g.trades[g.trades.length-1];
      return g;
    }).sort((a,b)=>b.latest.trade_date.localeCompare(a.latest.trade_date));
    byId("dataCount").textContent = fmt(allTrades.length)+"건";
    renderQuickSearch();
    setStatus(apartmentGroups.length+"개 단지를 검색할 수 있습니다.");
    initMap();
  }catch(error){
    setStatus("데이터를 불러오지 못했습니다: "+error.message,true);
  }
}

function renderQuickSearch(){
  const names = [...new Set(apartmentGroups.map(g=>g.region_name))].slice(0,6);
  byId("quickSearch").innerHTML = names.map(name => '<button type="button" data-query="'+esc(name)+'">'+esc(name.replace(/광역시 |특별자치시 /," "))+"</button>").join("");
  byId("quickSearch").querySelectorAll("button").forEach(btn => btn.addEventListener("click",()=>{byId("searchInput").value=btn.dataset.query; search();}));
}

function score(group, query){
  const q=query.replace(/s+/g,"").toLowerCase();
  const apt=group.apt_name.replace(/s+/g,"").toLowerCase();
  const place=(group.region_name+group.dong+group.jibun).replace(/s+/g,"").toLowerCase();
  if(apt===q) return 1000;
  if(apt.startsWith(q)) return 700;
  if(apt.includes(q)) return 500;
  if(place.includes(q)) return 350;
  const tokens=query.toLowerCase().split(/s+/).filter(Boolean);
  return tokens.reduce((sum,t)=>sum+(apt.includes(t)?120:0)+(place.includes(t)?70:0),0);
}

async function search(){
  const query=byId("searchInput").value.trim();
  if(!query){ setStatus("검색어를 입력해 주세요.",true); return; }
  setStatus("‘"+query+"’ 주변 단지를 찾는 중입니다…");
  let matches=apartmentGroups.map(g=>({group:g,score:score(g,query)})).filter(x=>x.score>0).sort((a,b)=>b.score-a.score).slice(0,30);
  let queryCoord=null;
  if(window.L){
    queryCoord=await geocode(query);
    if(queryCoord){
      const located=[];
      for(const item of matches.slice(0,5)){
        const coord=await geocode(addressOf(item.group));
        located.push({...item,coord,distance:coord?haversine(queryCoord,coord):Infinity});
      }
      matches=located.sort((a,b)=>a.distance-b.distance||b.score-a.score).concat(matches.slice(5)).slice(0,12);
      map.setView([queryCoord.lat,queryCoord.lng],14);
    }else matches=matches.slice(0,12);
  }else matches=matches.slice(0,12);
  renderResults(matches,query);
  if(matches.length) await focusGroup(matches[0].group,matches[0].coord);
}

function renderResults(matches,query){
  byId("resultCount").textContent=matches.length+"개";
  if(!matches.length){
    byId("results").innerHTML='<div class="empty">‘'+esc(query)+'’와 일치하는 수집 단지가 없습니다.<br>동 이름이나 단지명의 일부로 다시 검색해 보세요.</div>';
    setStatus("검색 결과가 없습니다.",true); return;
  }
  byId("results").innerHTML=matches.map(item=>{
    const g=item.group, added=selected.some(s=>s.key===g.key);
    const distance=Number.isFinite(item.distance)?fmt(item.distance)+"km":"실거래 "+g.trades.length+"건";
    return '<div class="result" data-key="'+esc(g.key)+'"><div class="result-top"><div><h3>'+esc(g.apt_name)+'</h3><p>'+esc(addressOf(g))+'</p></div><span class="price">'+fmt(g.latest.price_eok)+'억</span></div><div class="result-actions"><span>'+distance+' · 전용 '+g.areas.map(fmt).join(", ")+'㎡</span><button class="add-btn" type="button" '+(added?"disabled":"")+'>'+(added?"추가됨":"비교 추가")+"</button></div></div>";
  }).join("");
  byId("results").querySelectorAll(".result").forEach(card=>{
    const group=apartmentGroups.find(g=>g.key===card.dataset.key);
    card.addEventListener("click",e=>{ if(!e.target.classList.contains("add-btn")) focusGroup(group); });
    card.querySelector(".add-btn").addEventListener("click",e=>{e.stopPropagation();addSelection(group);});
  });
  setStatus("가까운 순서와 검색 일치도를 기준으로 "+matches.length+"개 단지를 표시했습니다.");
}

function addSelection(group){
  if(selected.some(s=>s.key===group.key)) return;
  if(selected.length>=10){ setStatus("비교 단지는 최대 10개까지 선택할 수 있습니다.",true); return; }
  const popular=[...group.areas].sort((a,b)=>group.trades.filter(r=>r.area_m2===b).length-group.trades.filter(r=>r.area_m2===a).length)[0];
  selected.push({key:group.key,group,area:popular});
  renderSelections(); renderComparison(); renderDetails(group,popular); focusGroup(group);
  const q=byId("searchInput").value.trim(); if(q) search();
}

function renderSelections(){
  byId("selectionCount").textContent=selected.length+" / 10";
  if(!selected.length){byId("selections").innerHTML='<div class="empty">검색 결과에서 비교할 단지를 추가하세요.</div>';return;}
  byId("selections").innerHTML=selected.map((item,index)=>{
    const g=item.group;
    return '<div class="selection" data-key="'+esc(item.key)+'"><div class="selection-name"><b><i style="background:'+palette[index]+'"></i>'+esc(g.apt_name)+'</b><span>'+esc(g.region_name+" "+g.dong)+'</span></div><select aria-label="'+esc(g.apt_name)+' 평형 선택">'+g.areas.map(a=>'<option value="'+a+'" '+(a===item.area?"selected":"")+'>전용 '+fmt(a)+'㎡ ('+fmt(a/3.3058)+'평)</option>').join("")+'</select><button class="remove-btn" type="button" aria-label="'+esc(g.apt_name)+' 삭제">삭제</button></div>';
  }).join("");
  byId("selections").querySelectorAll(".selection").forEach(card=>{
    const item=selected.find(s=>s.key===card.dataset.key);
    card.querySelector("select").addEventListener("change",e=>{item.area=Number(e.target.value);renderComparison();renderDetails(item.group,item.area);});
    card.querySelector(".remove-btn").addEventListener("click",()=>{selected=selected.filter(s=>s.key!==item.key);renderSelections();renderComparison();});
  });
}

function renderComparison(){
  const datasets=selected.map((item,index)=>{
    const daily=new Map();
    item.group.trades.filter(r=>Number(r.area_m2)===item.area).forEach(r=>{
      if(!daily.has(r.trade_date)) daily.set(r.trade_date,[]);
      daily.get(r.trade_date).push(r.price_eok);
    });
    return {label:item.group.apt_name+" · "+fmt(item.area)+"㎡",data:[...daily].map(([x,values])=>({x,y:median(values)})),borderColor:palette[index],backgroundColor:palette[index],pointRadius:4,pointHoverRadius:6,tension:.2,spanGaps:true};
  });
  if(priceChart) priceChart.destroy();
  priceChart=new Chart(byId("priceChart"),{type:"line",data:{datasets},options:{maintainAspectRatio:false,responsive:true,parsing:false,interaction:{mode:"nearest",intersect:false},scales:{x:{type:"category",title:{display:true,text:"거래일"}},y:{title:{display:true,text:"실거래가 (억원)"},beginAtZero:false}},plugins:{legend:{position:"bottom",labels:{usePointStyle:true,boxWidth:8}},tooltip:{callbacks:{label:c=>c.dataset.label+": "+fmt(c.raw.y)+"억원"}}}}});
}

function renderDetails(group,area){
  const rows=group.trades.filter(r=>Number(r.area_m2)===Number(area)).sort((a,b)=>b.trade_date.localeCompare(a.trade_date));
  const prices=rows.map(r=>r.price_eok), latest=rows[0];
  byId("metrics").innerHTML=[
    ["선택 단지",group.apt_name],["선택 평형","전용 "+fmt(area)+"㎡ · "+fmt(area/3.3058)+"평"],["최근 실거래",latest?fmt(latest.price_eok)+"억원":"—"],["거래 건수",fmt(rows.length)+"건"]
  ].map(x=>'<div class="metric"><span>'+esc(x[0])+'</span><b>'+esc(x[1])+"</b></div>").join("");
  const cols=[["trade_date","거래일"],["apt_name","단지"],["dong","법정동"],["area_m2","전용㎡"],["area_pyeong","평"],["floor","층"],["price_eok","억원"],["price_per_pyeong_manwon","평당만원"]];
  byId("trades").innerHTML="<thead><tr>"+cols.map(c=>"<th>"+c[1]+"</th>").join("")+"</tr></thead><tbody>"+rows.map(r=>"<tr>"+cols.map(c=>"<td>"+esc(typeof r[c[0]]==="number"?fmt(r[c[0]]):r[c[0]])+"</td>").join("")+"</tr>").join("")+"</tbody>";
}

function initMap(){
  map=L.map("map",{zoomControl:true}).setView([36.5,127.8],7);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{
    maxZoom:19,
    attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'
  }).addTo(map);
  byId("mapState").textContent="무료 지도 연결됨";
  byId("mapState").classList.add("ready");
}

async function geocode(query){
  if(geoCache[query]) return geoCache[query];
  const elapsed=Date.now()-lastGeocodeAt;
  if(elapsed<1100) await new Promise(resolve=>setTimeout(resolve,1100-elapsed));
  lastGeocodeAt=Date.now();
  try{
    const url="https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&countrycodes=kr&accept-language=ko&q="+encodeURIComponent(query);
    const rows=await fetch(url).then(r=>{if(!r.ok) throw new Error("주소 검색 실패");return r.json();});
    if(!rows.length) return null;
    const coord={lat:Number(rows[0].lat),lng:Number(rows[0].lon)};
    geoCache[query]=coord;
    localStorage.setItem("aptGeoCache",JSON.stringify(geoCache));
    return coord;
  }catch(error){
    setStatus("지도 주소 검색이 잠시 원활하지 않습니다. 단지명 검색 결과는 계속 이용할 수 있습니다.",true);
    return null;
  }
}

async function focusGroup(group,knownCoord){
  renderDetails(group,selected.find(s=>s.key===group.key)?.area||group.areas[0]);
  if(!map) return;
  const coord=knownCoord||await geocode(addressOf(group));
  if(!coord) return;
  let marker=markers.get(group.key);
  if(!marker){
    marker=L.marker([coord.lat,coord.lng]).addTo(map);
    marker.bindPopup('<div class="map-popup"><b>'+esc(group.apt_name)+'</b><br><small>'+esc(addressOf(group))+'</small><br><strong>최근 '+fmt(group.latest.price_eok)+'억원</strong></div>');
    marker.on("click",()=>renderDetails(group,selected.find(s=>s.key===group.key)?.area||group.areas[0]));
    markers.set(group.key,marker);
  }
  map.setView([coord.lat,coord.lng],16);
  marker.openPopup();
}

function haversine(a,b){
  const rad=x=>x*Math.PI/180,R=6371,dLat=rad(b.lat-a.lat),dLon=rad(b.lng-a.lng);
  const h=Math.sin(dLat/2)**2+Math.cos(rad(a.lat))*Math.cos(rad(b.lat))*Math.sin(dLon/2)**2;
  return 2*R*Math.asin(Math.sqrt(h));
}
function setStatus(message,error=false){byId("status").textContent=message;byId("status").style.color=error?"#b42318":"";}
byId("searchForm").addEventListener("submit",e=>{e.preventDefault();search();});
load();
