let allTrades = [], apartmentGroups = [], graphBoards = [], activeGraphId = null, map, infoWindow;
const markers = new Map(), charts = new Map();
let lastGeocodeAt = 0;
const geoCache = JSON.parse(localStorage.getItem("aptGeoCache") || "{}");
const GRAPH_STORAGE_KEY = "realEstateGraphWorkspacesV1";
const graphColors = [
  {name:"검은색",value:"#111827"},{name:"빨강",value:"#ef4444"},{name:"주황",value:"#f97316"},{name:"노랑",value:"#eab308"},
  {name:"초록",value:"#22c55e"},{name:"파랑",value:"#3b82f6"},{name:"남색",value:"#4f46e5"},{name:"보라",value:"#8b5cf6"}
];
const byId = id => document.getElementById(id);
const fmt = n => Number(n || 0).toLocaleString("ko-KR", {maximumFractionDigits: 2});
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

function normalized(value){ return String(value||"").replace(/\s+/g,"").replace(/아파트$/,"").toLowerCase(); }
function identity(row){ return [normalized(row.region_name),normalized(row.dong),normalized(row.apt_name)].join("|"); }
function groupKey(row){ return [row.lawd_cd,row.dong,row.apt_name].join("|"); }
function addressOf(group){ return group.address||[group.region_name,group.dong,group.jibun].filter(Boolean).join(" "); }
function isSubsequence(needle,haystack){ let i=0; for(const char of haystack){if(char===needle[i]) i++;} return i===needle.length; }
async function fetchJson(path){ try{const response=await fetch(path);return response.ok?response.json():[];}catch{return [];} }
function median(values){
  if(!values.length) return 0;
  const sorted = [...values].sort((a,b)=>a-b), mid = Math.floor(sorted.length/2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid-1]+sorted[mid])/2;
}

async function load(){
  try{
    const [rows,complexes,history]=await Promise.all([
      fetchJson("data/latest_trades.json"),
      fetchJson("data/complexes.json"),
      fetchJson("data/apartment_history.json")
    ]);
    allTrades=rows.filter(r=>!r.cancelled);
    const groups=new Map(), lookup=new Map();
    complexes.forEach(c=>{
      const key="complex|"+(c.complex_code||identity(c));
      const group={key,lawd_cd:String(c.bjd_code||"").slice(0,5),region_name:c.region_name,dong:c.dong,jibun:"",address:c.address,apt_name:c.apt_name,trades:[],history:[]};
      groups.set(key,group);lookup.set(identity(group),group);
    });
    allTrades.forEach(row=>{
      let group=lookup.get(identity(row));
      if(!group){
        const key=groupKey(row);
        if(!groups.has(key)) groups.set(key,{key,lawd_cd:row.lawd_cd,region_name:row.region_name,dong:row.dong,jibun:row.jibun,address:"",apt_name:row.apt_name,trades:[],history:[]});
        group=groups.get(key);lookup.set(identity(group),group);
      }
      group.trades.push(row);
    });
    history.forEach(row=>{
      let group=lookup.get(identity(row));
      if(!group){
        const key=groupKey(row);
        if(!groups.has(key)) groups.set(key,{key,lawd_cd:row.lawd_cd,region_name:row.region_name,dong:row.dong,jibun:"",address:"",apt_name:row.apt_name,trades:[],history:[]});
        group=groups.get(key);lookup.set(identity(group),group);
      }
      group.history.push(row);
    });
    apartmentGroups=[...groups.values()].map(g=>{
      g.trades.sort((a,b)=>a.trade_date.localeCompare(b.trade_date));
      g.history.sort((a,b)=>a.month.localeCompare(b.month));
      g.areas=[...new Set(g.trades.map(r=>Number(r.area_m2)).concat(g.history.map(r=>Number(r.area_m2))))].filter(Boolean).sort((a,b)=>a-b);
      const lastTrade=g.trades[g.trades.length-1],lastHistory=g.history[g.history.length-1];
      g.latest=lastTrade||(lastHistory?{trade_date:lastHistory.month,price_eok:lastHistory.median_price_eok}:null);
      return g;
    }).sort((a,b)=>(b.latest?.trade_date||"").localeCompare(a.latest?.trade_date||""));
    byId("dataCount").textContent=fmt(allTrades.length)+"건 · "+fmt(apartmentGroups.length)+"단지";
    renderQuickSearch();
    restoreGraphBoards();
    renderGraphBoards();
    setStatus(apartmentGroups.length+"개 전국 단지를 검색할 수 있습니다.");
    initMap();
  }catch(error){setStatus("데이터를 불러오지 못했습니다: "+error.message,true);}
}

function renderQuickSearch(){
  const names = [...new Set(apartmentGroups.map(g=>g.region_name))].slice(0,6);
  byId("quickSearch").innerHTML = names.map(name => '<button type="button" data-query="'+esc(name)+'">'+esc(name.replace(/광역시 |특별자치시 /," "))+"</button>").join("");
  byId("quickSearch").querySelectorAll("button").forEach(btn => btn.addEventListener("click",()=>{byId("searchInput").value=btn.dataset.query; search();}));
}

function score(group, query){
  const q=query.replace(/\s+/g,"").toLowerCase();
  const apt=group.apt_name.replace(/\s+/g,"").toLowerCase();
  const place=(group.region_name+group.dong+group.jibun).replace(/\s+/g,"").toLowerCase();
  if(apt===q) return 1000;
  if(apt.startsWith(q)) return 700;
  if(apt.includes(q)) return 500;
  if(place.includes(q)) return 350;
  if(q.length>=3&&isSubsequence(q,apt)) return 300;
  const tokens=query.toLowerCase().split(/\s+/).filter(Boolean);
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

function activeBoard(){
  return graphBoards.find(board=>board.id===activeGraphId)||null;
}

function makeId(prefix){
  return prefix+"-"+Date.now().toString(36)+"-"+Math.random().toString(36).slice(2,8);
}

function preferredArea(group){
  const activity=area=>group.trades.filter(r=>Number(r.area_m2)===area).length+
    group.history.filter(r=>Number(r.area_m2)===area).reduce((sum,r)=>sum+Number(r.trade_count||0),0);
  return [...group.areas].sort((a,b)=>activity(b)-activity(a))[0]||0;
}

function seriesAdded(group){
  const board=activeBoard();
  return Boolean(board&&board.series.some(series=>series.key===group.key));
}

function renderResults(matches,query){
  byId("resultCount").textContent=matches.length+"개";
  if(!matches.length){
    byId("results").innerHTML='<div class="empty">‘'+esc(query)+'’와 일치하는 수집 단지가 없습니다.<br>동 이름이나 단지명의 일부로 다시 검색해 보세요.</div>';
    setStatus("검색 결과가 없습니다.",true); return;
  }
  byId("results").innerHTML=matches.map(item=>{
    const g=item.group,added=seriesAdded(g);
    const distance=Number.isFinite(item.distance)?fmt(item.distance)+"km":(g.trades.length||g.history.length?"거래자료 있음":"단지 기본정보");
    const price=g.latest?fmt(g.latest.price_eok)+"억":"거래 없음";
    const areas=g.areas.length?"전용 "+g.areas.map(fmt).join(", ")+"㎡":"평형 거래자료 없음";
    return '<div class="result" data-key="'+esc(g.key)+'"><div class="result-top"><div><h3>'+esc(g.apt_name)+'</h3><p>'+esc(addressOf(g))+'</p></div><span class="price">'+price+'</span></div><div class="result-actions"><span>'+distance+' · '+areas+'</span><button class="add-btn" type="button" '+(added?"disabled":"")+'>'+(added?"현재 그래프에 추가됨":"추가")+"</button></div></div>";
  }).join("");
  byId("results").querySelectorAll(".result").forEach(card=>{
    const group=apartmentGroups.find(g=>g.key===card.dataset.key);
    card.addEventListener("click",e=>{ if(!e.target.classList.contains("add-btn")) focusGroup(group); });
    card.querySelector(".add-btn").addEventListener("click",e=>{e.stopPropagation();addSeries(group);});
  });
  setStatus("가까운 순서와 검색 일치도를 기준으로 "+matches.length+"개 단지를 표시했습니다.");
}

function refreshResultButtons(){
  byId("results").querySelectorAll(".result").forEach(card=>{
    const button=card.querySelector(".add-btn");
    const group=apartmentGroups.find(g=>g.key===card.dataset.key);
    const added=group&&seriesAdded(group);
    button.disabled=Boolean(added);
    button.textContent=added?"현재 그래프에 추가됨":"추가";
  });
}

function addGraphBoard(){
  if(graphBoards.length>=10){setStatus("그래프는 최대 10개까지 만들 수 있습니다.",true);return;}
  const board={id:makeId("graph"),name:"그래프 "+(graphBoards.length+1),series:[]};
  graphBoards.push(board);
  activeGraphId=board.id;
  renderGraphBoards();
  markUnsaved("새 그래프가 만들어졌습니다. 이름을 바꾸고 단지를 추가해 보세요.");
}

function removeActiveGraphBoard(){
  const board=activeBoard();
  if(!board) return;
  if(!window.confirm("‘"+board.name+"’ 그래프를 제거할까요?")) return;
  graphBoards=graphBoards.filter(item=>item.id!==board.id);
  activeGraphId=graphBoards[0]?.id||null;
  renderGraphBoards();
  markUnsaved("그래프를 제거했습니다.");
}

function addSeries(group){
  const board=activeBoard();
  if(!board){setStatus("먼저 지도 아래의 ‘그래프 추가’ 버튼을 눌러 주세요.",true);return;}
  if(board.series.some(series=>series.key===group.key)){setStatus("이 단지는 현재 그래프에 이미 있습니다.",true);return;}
  if(board.series.length>=10){setStatus("한 그래프에는 단지를 최대 10개까지 추가할 수 있습니다.",true);return;}
  const area=preferredArea(group);
  board.series.push({id:makeId("series"),key:group.key,area,color:graphColors[0].value});
  renderGraphBoards();
  renderDetails(group,area);
  focusGroup(group);
  markUnsaved(group.apt_name+"을(를) ‘"+board.name+"’에 추가했습니다.");
}

function removeSeries(boardId,seriesId){
  const board=graphBoards.find(item=>item.id===boardId);
  if(!board) return;
  board.series=board.series.filter(series=>series.id!==seriesId);
  renderGraphBoards();
  markUnsaved("단지 그래프를 제거했습니다.");
}

function restoreGraphBoards(){
  try{
    const saved=JSON.parse(localStorage.getItem(GRAPH_STORAGE_KEY)||"null");
    if(!saved||!Array.isArray(saved.boards)) return;
    graphBoards=saved.boards.slice(0,10).map((board,index)=>({
      id:String(board.id||makeId("graph")),
      name:String(board.name||"그래프 "+(index+1)).slice(0,30),
      series:Array.isArray(board.series)?board.series.slice(0,10).filter(series=>apartmentGroups.some(g=>g.key===series.key)).map(series=>({
        id:String(series.id||makeId("series")),
        key:String(series.key),
        area:Number(series.area||0),
        color:graphColors.some(color=>color.value===series.color)?series.color:graphColors[0].value
      })):[]
    }));
    activeGraphId=graphBoards.some(board=>board.id===saved.activeGraphId)?saved.activeGraphId:(graphBoards[0]?.id||null);
    if(graphBoards.length) byId("saveState").textContent="저장된 그래프를 불러왔습니다.";
  }catch{
    graphBoards=[];activeGraphId=null;
  }
}

function saveGraphBoards(){
  try{
    localStorage.setItem(GRAPH_STORAGE_KEY,JSON.stringify({version:1,activeGraphId,boards:graphBoards}));
    byId("saveState").textContent="이 브라우저에 저장되었습니다.";
    byId("saveState").classList.remove("unsaved");
    setStatus("현재 그래프 상태를 저장했습니다. 다음에 다시 열어도 그대로 보입니다.");
  }catch(error){
    setStatus("그래프를 저장하지 못했습니다: "+error.message,true);
  }
}

function markUnsaved(message){
  byId("saveState").textContent="저장되지 않은 변경";
  byId("saveState").classList.add("unsaved");
  setStatus(message);
  refreshResultButtons();
}

function renderGraphBoards(){
  charts.forEach(chart=>chart.destroy());
  charts.clear();
  byId("graphCount").textContent=graphBoards.length+" / 10";
  byId("removeGraphBtn").disabled=!activeBoard();
  byId("saveGraphsBtn").disabled=!graphBoards.length;

  if(!graphBoards.length){
    byId("graphTabs").innerHTML="";
    byId("graphBoards").innerHTML='<div class="graph-empty"><b>아직 만든 그래프가 없습니다.</b><span>‘그래프 추가’를 누른 뒤 검색 결과의 ‘추가’ 버튼으로 단지를 담아보세요.</span></div>';
    refreshResultButtons();
    return;
  }

  byId("graphTabs").innerHTML=graphBoards.map((board,index)=>
    '<button type="button" class="graph-tab '+(board.id===activeGraphId?"active":"")+'" data-board-id="'+esc(board.id)+'">'+(index+1)+'. '+esc(board.name)+'</button>'
  ).join("");
  byId("graphTabs").querySelectorAll(".graph-tab").forEach(tab=>tab.addEventListener("click",()=>{
    activeGraphId=tab.dataset.boardId;
    renderGraphBoards();
    markUnsaved("‘"+activeBoard().name+"’ 그래프를 선택했습니다.");
  }));

  const board=activeBoard()||graphBoards[0];
  activeGraphId=board.id;
  byId("graphBoards").innerHTML='<article class="graph-board" data-board-id="'+esc(board.id)+'">'+
    '<div class="graph-board-head"><div><label for="graphName">그래프 이름</label><input id="graphName" class="graph-name" maxlength="30" value="'+esc(board.name)+'"></div>'+
    '<span>'+board.series.length+' / 10개 단지</span></div>'+
    '<div class="series-list">'+(board.series.length?board.series.map(series=>seriesControl(board,series)).join(""):'<div class="series-empty">검색한 단지의 ‘추가’ 버튼을 누르면 검은색 선으로 표시됩니다.</div>')+'</div>'+
    '<div class="chart-wrap graph-chart-wrap"><canvas aria-label="'+esc(board.name)+' 장기 실거래가 그래프"></canvas></div>'+
    '<p class="chart-help">점을 누르거나 마우스를 올리면 해당 월의 중앙 실거래가와 거래 건수를 확인할 수 있습니다.</p></article>';

  const nameInput=byId("graphName");
  nameInput.addEventListener("input",e=>{
    board.name=e.target.value.slice(0,30)||"이름 없는 그래프";
    const activeTab=byId("graphTabs").querySelector('[data-board-id="'+CSS.escape(board.id)+'"]');
    if(activeTab) activeTab.textContent=(graphBoards.indexOf(board)+1)+". "+board.name;
    markUnsaved("그래프 이름을 변경했습니다.");
  });

  byId("graphBoards").querySelectorAll(".series-item").forEach(card=>{
    const series=board.series.find(item=>item.id===card.dataset.seriesId);
    card.querySelector(".area-select").addEventListener("change",e=>{
      series.area=Number(e.target.value);renderGraphBoards();markUnsaved("평형을 변경했습니다.");
      const group=apartmentGroups.find(g=>g.key===series.key);if(group)renderDetails(group,series.area);
    });
    card.querySelector(".color-select").addEventListener("change",e=>{
      series.color=e.target.value;renderGraphBoards();markUnsaved("그래프 색상을 변경했습니다.");
    });
    card.querySelector(".remove-btn").addEventListener("click",()=>removeSeries(board.id,series.id));
  });
  renderBoardChart(board,byId("graphBoards").querySelector("canvas"));
  refreshResultButtons();
}

function seriesControl(board,series){
  const group=apartmentGroups.find(g=>g.key===series.key);
  if(!group) return "";
  const areaOptions=group.areas.length?group.areas.map(area=>'<option value="'+area+'" '+(Number(area)===Number(series.area)?"selected":"")+'>전용 '+fmt(area)+'㎡ ('+fmt(area/3.3058)+'평)</option>').join(""):'<option value="0">평형 자료 없음</option>';
  const colorOptions=graphColors.map(color=>'<option value="'+color.value+'" '+(color.value===series.color?"selected":"")+'>'+color.name+'</option>').join("");
  return '<div class="series-item" data-series-id="'+esc(series.id)+'"><i class="series-color" style="background:'+esc(series.color)+'"></i>'+
    '<div class="series-name"><b>'+esc(group.apt_name)+'</b><span>'+esc(group.region_name+" "+group.dong)+'</span></div>'+
    '<select class="area-select" aria-label="'+esc(group.apt_name)+' 평형 선택">'+areaOptions+'</select>'+
    '<select class="color-select" aria-label="'+esc(group.apt_name)+' 색상 선택">'+colorOptions+'</select>'+
    '<button class="remove-btn" type="button" aria-label="'+esc(group.apt_name)+' 그래프에서 삭제">삭제</button></div>';
}

function renderBoardChart(board,canvas){
  const datasets=board.series.map(series=>{
    const group=apartmentGroups.find(g=>g.key===series.key);
    if(!group) return null;
    let points=group.history.filter(r=>Number(r.area_m2)===series.area).map(r=>({x:r.month,y:Number(r.median_price_eok),count:Number(r.trade_count||0)}));
    if(!points.length){
      const daily=new Map();
      group.trades.filter(r=>Number(r.area_m2)===series.area).forEach(r=>{if(!daily.has(r.trade_date))daily.set(r.trade_date,[]);daily.get(r.trade_date).push(r.price_eok);});
      points=[...daily].map(([x,values])=>({x,y:median(values),count:values.length}));
    }
    return {label:group.apt_name+" · "+(series.area?fmt(series.area)+"㎡":"평형 없음"),data:points,borderColor:series.color,backgroundColor:series.color,pointRadius:2.5,pointHoverRadius:6,borderWidth:2,tension:.18,spanGaps:true};
  }).filter(Boolean);
  const chart=new Chart(canvas,{type:"line",data:{datasets},options:{maintainAspectRatio:false,responsive:true,interaction:{mode:"nearest",intersect:true},scales:{x:{type:"category",title:{display:true,text:"거래월"}},y:{title:{display:true,text:"월 중앙 실거래가 (억원)"},beginAtZero:false}},plugins:{legend:{position:"bottom",labels:{usePointStyle:true,boxWidth:8}},tooltip:{displayColors:true,callbacks:{title:items=>items[0]?.raw?.x||"",label:c=>c.dataset.label+": "+fmt(c.raw.y)+"억원",afterLabel:c=>"해당 월 거래 "+fmt(c.raw.count)+"건의 중앙값"}}}}});
  charts.set(board.id,chart);
}

function renderDetails(group,area){
  const rows=group.trades.filter(r=>Number(r.area_m2)===Number(area)).sort((a,b)=>b.trade_date.localeCompare(a.trade_date));
  const prices=rows.map(r=>r.price_eok), latest=rows[0];
  byId("metrics").innerHTML=[
    ["선택 단지",group.apt_name],["선택 평형",area?"전용 "+fmt(area)+"㎡ · "+fmt(area/3.3058)+"평":"거래 평형 없음"],["최근 실거래",latest?fmt(latest.price_eok)+"억원":"—"],["최근 상세 거래",fmt(rows.length)+"건"]
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
  renderDetails(group,activeBoard()?.series.find(s=>s.key===group.key)?.area||group.areas[0]);
  if(!map) return;
  const coord=knownCoord||await geocode(addressOf(group));
  if(!coord) return;
  let marker=markers.get(group.key);
  if(!marker){
    marker=L.marker([coord.lat,coord.lng]).addTo(map);
    marker.bindPopup('<div class="map-popup"><b>'+esc(group.apt_name)+'</b><br><small>'+esc(addressOf(group))+'</small><br><strong>'+(group.latest?'최근 '+fmt(group.latest.price_eok)+'억원':'최근 거래 없음')+'</strong></div>');
    marker.on("click",()=>renderDetails(group,activeBoard()?.series.find(s=>s.key===group.key)?.area||group.areas[0]));
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
byId("addGraphBtn").addEventListener("click",addGraphBoard);
byId("removeGraphBtn").addEventListener("click",removeActiveGraphBoard);
byId("saveGraphsBtn").addEventListener("click",saveGraphBoards);
load();
