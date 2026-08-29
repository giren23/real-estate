let allTrades = [], apartmentGroups = [], graphBoards = [], activeGraphId = null, map, infoWindow;
let localApi = false, localMeta = {};
const minorVersion = location.hostname.endsWith(".github.io") || new URLSearchParams(location.search).get("minor") === "1";
const minorVersionBadge = document.getElementById("minorVersionBadge");
if(minorVersionBadge) minorVersionBadge.hidden = !minorVersion;
let economicContext = {exchange_rates:[],base_rates:[],us_policy_rates:[],japan_policy_rates:[],money_supply:[],metal_prices:[],bond_yields:[],oil_prices:[],market_indices:[],fear_greed:[],policies:[]};
const markers = new Map(), charts = new Map();
const groupByKey = new Map(), groupsByLawd = new Map(), groupsByMapName = new Map();
const regionHierarchy = new Map();
let regionSelection={sido:"",sigungu:"",dong:""},regionFilteredKeys=null,regionSelectionRunId=0;
let lastGeocodeAt = 0, searchRunId = 0, searchSuggestionTimer = null;
const geoCache = JSON.parse(localStorage.getItem("aptGeoCache") || "{}");
const groupCoordinates = new Map();
const mapNameGroupCache = new Map();
const viewportLocalityCache = new Map();
const MAX_VIEWPORT_MARKERS = 28, MIN_MARKER_ZOOM = 14;
const MAX_REGION_MARKERS = 160;
const MAX_NEARBY_GEOCODES = 0, NEARBY_RADIUS_KM = 3;
const MIN_BUILDING_ZOOM = 14, MAX_BUILDING_MARKERS = 28;
const MAX_VIEWPORT_FALLBACK_GEOCODES = 8;
let viewportMarkerTimer = null, viewportRefreshSuspended = false, viewportComplexCache = null, mapLocalityAnchor = null;
let buildingRequestId = 0, buildingAbortController = null;
let catalogRefreshChecking = false, lastCatalogRefreshCheck = 0;
const CATALOG_REFRESH_INTERVAL_MS = 5 * 60 * 1000;
const GRAPH_STORAGE_KEY = "realEstateGraphWorkspacesV1";
const TAX_BASE_YEAR = 2026;
const graphColors = [
  {name:"검은색",value:"#111827"},{name:"빨강",value:"#ef4444"},{name:"주황",value:"#f97316"},{name:"노랑",value:"#eab308"},
  {name:"초록",value:"#22c55e"},{name:"파랑",value:"#3b82f6"},{name:"남색",value:"#4f46e5"},{name:"보라",value:"#8b5cf6"},
  {name:"청록",value:"#0891b2"},{name:"분홍",value:"#db2777"},{name:"갈색",value:"#92400e"},{name:"회색",value:"#64748b"}
];
const graphLineStyles = [
  {name:"기본 선",value:"solid",width:1.4,dash:[]},
  {name:"굵은 선",value:"thick",width:3.2,dash:[]},
  {name:"점선",value:"dashSmall",width:1.8,dash:[3,3]}
];
function graphLineStyle(value){return graphLineStyles.find(style=>style.value===value)||graphLineStyles[0];}
const POLICY_DETAILS = {
  "2017-08-02": {
    "before": [
      "투기과열지구·투기지역이 제한적으로 운영되고 규제지역의 대출·청약 규제가 상대적으로 완화돼 있었습니다.",
      "조정대상지역 다주택자에 대한 양도소득세 추가과세와 장기보유특별공제 배제가 적용되기 전이었습니다."
    ],
    "after": [
      "서울 전역 등을 투기과열지구·투기지역으로 지정하고, 해당 지역 LTV·DTI를 원칙적으로 40%로 강화했습니다.",
      "조정대상지역 2주택자는 양도세 기본세율에 10%p, 3주택 이상은 20%p를 더하고 장기보유특별공제를 배제하도록 했습니다.",
      "재건축 조합원 지위 양도와 청약 1순위 자격, 분양권 전매 관련 규제를 강화했습니다."
    ],
    "impact": "단기적으로 서울·수도권의 레버리지 투자수요와 거래량을 줄이는 하락 요인입니다. 다만 현금 여력이 큰 강남권 핵심지는 대출 규제 영향이 상대적으로 작고, 규제를 피한 수도권 외곽·지방 비규제지역에는 수요가 이동하는 풍선효과가 나타날 수 있습니다. 정비사업 규제가 장기화되면 서울 신규 공급 부족을 키워 중장기 가격 상승 요인으로 되돌아올 가능성도 있습니다.",
    "url": "https://www.molit.go.kr/USR/NEWS/m_71/dtl.jsp?id=95079700"
  },
  "2018-09-13": {
    "before": [
      "규제지역에서도 다주택자의 신규 주택담보대출이 전면 금지되지는 않았고, 고가·다주택 보유세 강화 폭도 제한적이었습니다.",
      "임대사업자 등록 주택에는 대출·세제상 혜택이 폭넓게 적용됐습니다."
    ],
    "after": [
      "2주택 이상 보유세대는 규제지역 신규 주택구입 목적 주택담보대출을 금지하고, 1주택자도 처분·실거주 조건을 붙였습니다.",
      "조정대상지역 2주택 및 3주택 이상 보유자 종부세율을 최고 3.2%까지 높이고 세부담 상한도 강화했습니다.",
      "규제지역에서 새로 취득한 임대주택의 양도세 중과·종부세 합산배제 혜택을 제한하고 수도권 공공택지 30만호 계획을 병행했습니다."
    ],
    "impact": "다주택자의 추가 매수와 갭투자를 위축시켜 서울·수도권 거래량을 낮추는 요인입니다. 보유세 부담 매물이 늘 수 있지만 인기지역의 매물 잠김이 함께 나타나면 강남·용산 등 희소 입지는 가격 조정폭이 제한될 수 있습니다. 수도권 30만호 공급은 외곽·신도시의 중장기 상승 압력을 낮추지만 실제 입주까지 시차가 길어 단기 공급 부족을 바로 해소하지는 못합니다.",
    "url": "https://www.moef.go.kr/nw/nes/detailNesDtaView.do?menuNo=4010100&searchBbsId1=MOSFBBS_000000000028&searchNttId1=MOSF_000000000019155"
  },
  "2019-12-16": {
    "before": [
      "투기지역·투기과열지구 주택담보대출은 주택가격 구간과 관계없이 주로 LTV 40% 기준을 적용했습니다.",
      "민간택지 분양가상한제 적용지역과 고가주택 보유세·거래 규제가 이후 기준보다 좁았습니다."
    ],
    "after": [
      "시가 9억원 초과분의 LTV를 20%로 낮추고, 투기지역·투기과열지구의 시가 15억원 초과 아파트 주택담보대출을 금지했습니다.",
      "종부세율을 1주택자 0.1~0.3%p, 다주택자 0.2~0.8%p 인상하는 안을 내고 고가주택의 실수요·자금조달 심사를 강화했습니다.",
      "민간택지 분양가상한제 적용지역을 서울 13개 구 전역과 경기 일부 등으로 확대했습니다."
    ],
    "impact": "15억원 초과 주택은 대출 의존 매수자가 빠져 거래절벽과 단기 가격 조정 가능성이 커집니다. 반면 현금 부자의 강남 핵심지 수요는 남고, 대출이 가능한 9억~15억원대 서울 외곽·수도권 중가주택으로 수요가 이동할 수 있습니다. 분양가상한제가 정비사업 수익성을 낮추면 서울 도심 공급 지연과 신축 희소성이 커져 장기적으로 신축 가격 상승 요인이 될 수 있습니다.",
    "url": "https://www.korea.kr/briefing/policyBriefingView.do?newsId=148867548"
  },
  "2020-06-17": {
    "before": [
      "조정대상지역·투기과열지구가 수도권 일부에 한정돼 비규제지역으로 투자수요가 이동하는 현상이 있었습니다.",
      "주택 매매·임대사업자의 주택담보대출과 고가주택 보유자의 전세대출 이용 제한이 이후보다 느슨했습니다."
    ],
    "after": [
      "수도권 대부분과 대전·청주 등을 조정대상지역 또는 투기과열지구로 추가 지정했습니다.",
      "규제지역 주택구입 시 전입·처분 요건을 강화하고, 주택 매매·임대사업자의 주택담보대출을 원칙적으로 금지했습니다.",
      "투기지역·투기과열지구에서 3억원 초과 아파트를 구입하면 전세대출 보증을 제한·회수하도록 했습니다."
    ],
    "impact": "새로 규제된 경기·인천·대전·청주의 투자수요와 거래량을 즉시 낮추는 요인입니다. 전세대출을 활용한 갭투자와 중저가 실수요자의 자금 조달도 어려워져 수도권 중가주택 수요가 감소할 수 있습니다. 규제에서 빠진 지방 중소도시나 저가 주택으로 단기 자금이 이동할 수 있지만, 지역 일자리·인구가 약한 곳은 상승세가 오래 유지되기 어렵습니다.",
    "url": "https://www.korea.kr/news/policyNewsView.do?newsId=148874587"
  },
  "2020-07-10": {
    "before": [
      "다주택자 취득세는 일반세율 중심이었고 종부세·단기 양도세 중과 수준이 이후보다 낮았습니다.",
      "생애최초 취득세 감면은 신혼부부 등 제한된 대상 위주로 적용됐습니다."
    ],
    "after": [
      "조정대상지역 2주택은 취득세 8%, 3주택 이상과 법인은 12%로 중과하고 다주택자 종부세 최고세율을 6%로 높였습니다.",
      "단기보유·규제지역 다주택자의 양도세율을 높이고 등록임대사업 제도를 축소했습니다.",
      "생애최초 주택 취득세 감면 대상을 연령·혼인 여부와 관계없이 확대하고 서민·실수요자 대출 기준을 보완했습니다."
    ],
    "impact": "다주택자의 신규 매수를 강하게 줄이고 세 부담 매물을 유도해 수도권 투자수요를 낮추는 요인입니다. 동시에 높은 양도세 때문에 기존 주택을 팔지 않는 매물 잠김이 생기면 서울 핵심지의 공급 부족이 오히려 심해질 수 있습니다. 등록임대 축소는 장기적으로 민간 임대물량을 줄여 전월세 가격 상승 압력을 만들 수 있고, 생애최초 지원은 중저가 실수요 시장의 하방을 받칩니다.",
    "url": "https://www.molit.go.kr/USR/NEWS/m_71/dtl.jsp?id=95084142"
  },
  "2021-02-04": {
    "before": [
      "도심 정비사업은 민간 조합 중심으로 진행돼 사업기간이 길고 사업성·주민동의 문제로 공급 속도가 불확실했습니다.",
      "기존 공급계획만으로 서울 등 대도시권의 추가 공급 기대를 충분히 만들기 어렵다는 평가가 있었습니다."
    ],
    "after": [
      "공공이 직접 시행하는 도심공공주택복합사업과 공공 직접시행 정비사업을 도입해 절차 단축과 용적률 등 인센티브를 제시했습니다.",
      "2025년까지 서울 32만호를 포함해 전국 83만호 규모의 신규 주택부지를 추가 공급하는 계획을 발표했습니다.",
      "개발이익은 토지주·세입자 보호와 공공기여로 나누고, 후보지 지정 이후 투기성 취득에는 우선공급권을 제한했습니다."
    ],
    "impact": "서울 도심 공급 확대 기대는 중장기 가격 상승 압력을 낮추는 요인이지만 후보지 지정부터 입주까지 시간이 길어 단기 체감 공급은 제한적입니다. 사업 후보지와 역세권 노후주택은 개발 기대감으로 가격이 먼저 오를 수 있고, 주민동의나 사업성 부족으로 지연되면 기대가 빠르게 되돌려질 수 있습니다. 토지가 부족한 강남 핵심지보다 비강남 역세권·노후 주거지에 영향이 더 큽니다.",
    "url": "https://www.molit.go.kr/USR/NEWS/m_71/dtl.jsp?id=95085147"
  },
  "2022-08-16": {
    "before": [
      "공공주도 공급과 재건축 안전진단·부담금 규제가 중심이어서 민간 정비사업의 속도와 사업성이 제한됐습니다.",
      "주택공급 목표가 개별 사업·택지 위주로 흩어져 있었습니다."
    ],
    "after": [
      "2023~2027년 전국 270만호, 수도권 158만호·서울 50만호 공급 청사진을 제시했습니다.",
      "재건축 안전진단 기준과 재건축부담금을 합리화하고 민간 도심복합사업 등 민간 주도의 도심 공급 수단을 도입했습니다.",
      "청년원가주택·역세권 첫집 등 부담 가능한 공공분양과 재해취약주택 지원을 확대했습니다."
    ],
    "impact": "재건축 규제 완화 기대는 서울·1기 신도시 노후 아파트의 사업성과 가격에 상승 요인으로 작용할 수 있습니다. 다만 실제 입주물량은 수년 뒤에 늘어나므로 단기 수도권 공급 부족을 바로 해소하기 어렵고, 고금리·공사비가 사업 속도를 늦출 수 있습니다. 지방은 공급 목표보다 미분양·인구 감소의 영향이 커 신규 공급 확대가 가격 상승으로 곧바로 이어지기 어렵습니다.",
    "url": "https://www.korea.kr/briefing/policyBriefingView.do?newsId=148904787"
  },
  "2023-01-03": {
    "before": [
      "서울 대부분과 과천·성남 등 수도권 핵심지가 규제지역 또는 민간택지 분양가상한제 지역이었습니다.",
      "수도권 분양권 전매제한은 최대 10년, 비수도권은 최대 4년이었고 실거주·중도금대출 규제가 폭넓게 적용됐습니다."
    ],
    "after": [
      "강남·서초·송파·용산을 제외한 규제지역을 해제하고 민간택지 분양가상한제 적용지역도 같은 범위로 축소했습니다.",
      "전매제한을 수도권 최대 3년, 비수도권 최대 1년으로 완화하고 수도권 분양가상한제 주택 실거주 의무 폐지를 추진했습니다.",
      "중도금대출 보증의 분양가 상한과 특별공급 분양가 기준을 폐지하는 등 청약·대출 규제를 정상화했습니다."
    ],
    "impact": "규제가 풀린 서울 비강남권과 경기 핵심지의 대출·청약·거래 부담이 낮아져 실수요와 투자수요 회복 요인이 됩니다. 강남3구·용산은 규제가 유지돼 희소한 핵심지라는 인식이 강화될 수 있고, 비규제지역과의 가격 차이가 조정될 가능성도 있습니다. 지방 미분양 지역은 전매·대출 완화만으로 수요가 충분히 살아나기 어려워 지역별 양극화가 계속될 수 있습니다.",
    "url": "https://www.molit.go.kr/2023plan/news/bodo.pdf"
  },
  "2023-09-26": {
    "before": [
      "고금리·원자재 가격 상승과 부동산 PF 경색으로 인허가·착공이 줄고 민간 사업장이 자금조달에 어려움을 겪었습니다.",
      "공공주택 공급계획만으로 단기 공급 위축을 보완하기 어려운 상황이었습니다."
    ],
    "after": [
      "3기 신도시 용적률 상향과 신규택지 발굴 등으로 공공주택 12만호를 추가 확보하기로 했습니다.",
      "HUG·HF PF 보증 규모를 확대하고 보증 심사·대출 절차를 개선해 정상 사업장의 자금조달을 지원했습니다.",
      "공공택지 전매제한을 한시 완화하고 비아파트·민간 임대 등 대기 사업의 재개를 지원했습니다."
    ],
    "impact": "PF 보증 확대는 정상 사업장의 부도·중단 위험을 낮춰 2~4년 뒤 수도권 입주 부족을 완화하는 요인입니다. 그러나 공사비와 금리가 높은 상태에서는 수익성이 낮은 지방·비아파트 사업이 계속 지연될 수 있어 공급 회복이 지역별로 갈릴 가능성이 큽니다. 단기 가격보다 건설사·시행사 유동성과 향후 입주물량에 더 직접적인 영향을 주는 정책입니다.",
    "url": "https://www.molit.go.kr/USR/NEWS/m_71/dtl.jsp?id=95088868"
  },
  "2024-01-10": {
    "before": [
      "재건축은 안전진단을 통과해야 정비계획 수립 등 본격적인 사업절차를 시작할 수 있었습니다.",
      "소형 비아파트도 주택 수에 포함돼 세제 부담이 공급·매입을 제약한다는 지적이 있었습니다."
    ],
    "after": [
      "준공 30년이 지난 아파트는 안전진단 전에 재건축 절차에 착수할 수 있도록 하고, 안전진단 명칭·시점을 사업인가 전으로 조정하는 방안을 제시했습니다.",
      "60㎡ 이하 소형 신축주택 구입 시 일정 요건 아래 취득세·양도세·종부세 산정에서 주택 수 제외를 추진했습니다.",
      "공공주택 14만호 이상 공급과 1기 신도시 선도지구·건설금융 지원을 병행했습니다."
    ],
    "impact": "재건축 기대가 큰 강남·목동·노원과 1기 신도시 노후 단지에는 사업기간 단축 기대가 가격 상승 요인입니다. 이주가 한꺼번에 진행되면 주변 전세 수요와 임대료가 단기 상승할 수 있지만, 준공 이후에는 신축 공급이 늘어 지역 가격 압력을 낮출 수 있습니다. 소형 비아파트 지원은 서울 1~2인 가구 임대 공급에 도움이 되지만 아파트 매매시장에 미치는 영향은 제한적입니다.",
    "url": "https://www.molit.go.kr/USR/NEWS/m_71/dtl.jsp?id=95089245"
  },
  "2024-08-08": {
    "before": [
      "수도권 공급 부족 우려가 커졌고 비아파트 공공 신축매입 목표는 12만호 수준이었습니다.",
      "정비사업·3기 신도시와 신규택지의 사업 속도를 더 높일 필요가 있었습니다."
    ],
    "after": [
      "그린벨트 해제 8만호, 3기 신도시 추가 2만호 등을 포함해 서울·수도권 21만호를 추가 공급하고 21.7만호의 조기 착공을 추진했습니다.",
      "서울 정비사업 37만호의 속도를 높이고 수도권 공공 신축매입임대를 12만호에서 16만호 이상으로 확대했습니다.",
      "신규택지 후보지와 주변 지역에는 토지거래허가구역 지정 등 투기방지 조치를 병행했습니다."
    ],
    "impact": "중장기적으로 3기 신도시·수도권 외곽의 공급을 늘려 해당 지역 가격 상승 압력을 낮추는 요인입니다. 그러나 입주 전까지 수년의 시차가 있어 서울의 당장 부족한 신축 물량은 계속 가격 상승 요인으로 남을 수 있습니다. 그린벨트 후보지와 교통계획 주변은 개발 기대에 토지가격이 먼저 오를 수 있으며, 강남 등 도심 핵심지는 대체 공급이 제한돼 영향이 상대적으로 작습니다.",
    "url": "https://www.molit.go.kr/USR/NEWS/dtl.jsp?id=95090063"
  },
  "2025-09-07": {
    "before": [
      "공급목표를 인허가 기준으로 관리해 실제 착공·입주로 이어지는 체감도가 낮다는 문제가 제기됐습니다.",
      "공공택지는 민간에 매각해 주택사업을 맡기는 방식이 큰 비중을 차지했습니다."
    ],
    "after": [
      "2026~2030년 수도권에서 총 135만호, 연평균 27만호를 ‘착공’ 기준으로 관리하기로 했습니다.",
      "공공택지에서는 LH 직접 시행을 확대하고 노후 공공임대·공공청사·미사용 학교용지 등을 활용해 도심 공급을 늘립니다.",
      "수도권 신축매입임대 14만호와 정비사업·유휴부지 공급을 함께 추진해 공급 시기를 앞당깁니다."
    ],
    "impact": "착공 중심 관리는 발표만 된 물량보다 실제 입주 가능성을 높여 수도권의 중장기 공급 부족을 완화하는 요인입니다. LH 직접 시행과 도심 유휴부지 활용은 수도권 외곽뿐 아니라 서울 생활권 공급에도 영향을 줄 수 있지만, 공사비·재원·주민갈등으로 속도가 늦어지면 단기 가격 안정 효과는 약해집니다. 지방은 수도권 중심 공급 확대보다 지역 미분양 해소와 일자리 회복 여부가 가격을 더 크게 좌우합니다.",
    "url": "https://molit.go.kr/USR/NEWS/m_71/dtl.jsp?id=95091185"
  },
  "2025-10-15": {
    "before": [
      "규제지역은 강남3구·용산구 등 일부에 집중됐고 수도권 주택담보대출 한도는 가격구간별 세분화가 덜했습니다.",
      "토지거래허가구역과 자금출처 조사가 서울·경기 전역의 과열 우려 지역을 모두 포괄하지 않았습니다."
    ],
    "after": [
      "서울 전역과 과천·성남 등 경기 12곳을 조정대상지역·투기과열지구·토지거래허가구역으로 확대 지정했습니다.",
      "수도권·규제지역 주택담보대출 한도를 시가 15억원 이하 6억원, 15억 초과~25억원 이하 4억원, 25억원 초과 2억원으로 차등 축소했습니다.",
      "가격 띄우기·편법 증여 등 불법행위 감독과 자금출처 검증을 강화하고 9·7 공급대책 후속조치를 가속했습니다."
    ],
    "impact": "대출 한도가 줄어드는 수도권 15억원 초과 주택과 중산층 갈아타기 수요에는 직접적인 수요 감소 요인입니다. 현금 비중이 높은 강남 초고가 시장은 영향이 제한될 수 있지만 서울 외곽·경기 상급지의 대출 의존 매수는 더 크게 위축될 가능성이 있습니다. 매매 수요 일부가 전월세로 이동하면 수도권 임대료 상승 압력이 생길 수 있고, 지방은 직접 규제보다 수도권에서 빠져나온 투자자금의 이동 여부에 간접 영향을 받습니다.",
    "url": "https://www.korea.kr/news/policyNewsView.do?newsId=148950973"
  },
  "2026-01-23": {
    "before": [
      "월세 세액공제는 무주택 세대주 중심이었고, 지방 준공 후 미분양 주택의 세제 특례는 일몰 여부가 남아 있었습니다.",
      "주택청약종합저축의 소득공제·비과세 혜택도 연장 여부를 확인해야 했습니다."
    ],
    "after": [
      "월세 세액공제 대상을 무주택 세대주의 배우자까지 확대하고 부부합산 공제 한도를 1,000만원으로 적용합니다.",
      "3자녀 이상 가구는 월세 세액공제 대상 주택 면적을 지역과 관계없이 100㎡까지 확대합니다.",
      "주택청약종합저축 세제혜택을 2028년까지 연장하고, 요건을 충족한 지방 준공 후 미분양 주택의 취득세 감면·주택 수 제외 특례를 2026년 말까지 적용합니다."
    ],
    "impact": "월세·청약 지원은 무주택 실수요자의 주거비를 낮추지만 서울 매매가격을 직접 낮출 정도의 공급 확대책은 아닙니다. 지방 미분양 세제 지원은 준공 물량 소진과 건설사 유동성에 도움이 되지만, 일자리·인구가 약한 지역은 세금 혜택만으로 수요가 오래 유지되기 어렵습니다. 수도권보다 지방 준공 후 미분양 시장에 영향이 큽니다.",
    "url": "https://www.korea.kr/multi/visualNewsView.do?newsId=148958477"
  },
  "2026-08-11": {
    "before": [
      "1세대 1주택 장기보유특별공제는 보유·거주 기간을 함께 반영하고, 종부세 기본공제는 거주 여부를 세분하지 않았습니다.",
      "조정대상지역 다주택자 양도세 중과는 높은 법정 가산세율이 적용되는 구조였습니다."
    ],
    "after": [
      "개편안은 2027년부터 장기보유특별공제를 거주 중심으로 단계 전환하고 2028년부터 공제한도를 두는 방안을 제시했습니다.",
      "종부세 기본공제를 거주용 1주택 14억원, 비거주 1주택 9억원 등으로 조정하는 방안을 담았습니다.",
      "조정대상지역 다주택자 양도세 중과를 2027~2028년에 한시적으로 낮춘 뒤 2029년에 원래 수준으로 복귀시키는 일정을 제시했습니다. 아직 국회 입법 전입니다."
    ],
    "impact": "실거주 1주택자는 종부세 공제 확대와 장기 거주 우대로 부담이 줄 수 있어 서울·수도권의 장기 보유 성향을 강화합니다. 반대로 비거주 고가주택과 다주택자는 보유·양도 부담이 커질 수 있어 임대 또는 매도 결정을 앞당길 가능성이 있습니다. 중과 한시 완화 기간에는 서울·수도권 매물이 늘어 단기 가격 상승 압력을 낮출 수 있지만, 핵심지에서 매수 대기수요가 강하면 거래만 늘고 가격 하락은 제한될 수 있습니다.",
    "url": "https://www.korea.kr/multi/visualNewsView.do?newsId=148969827"
  },
  "2026-08-26": {
    "before": [
      "생애최초 취득세 감면은 주택 중심이고 기본 한도는 200만원이었으며, 1주택 재산세 특례는 추가 연장이 필요했습니다.",
      "매입약정 임대주택과 재개발 사업의 취득세 지원 폭도 개편안보다 작았습니다."
    ],
    "after": [
      "일정 요건의 주거용 오피스텔까지 생애최초 취득세 감면 대상을 넓히고 40세 미만 청년의 감면 한도를 300만원으로 높이는 방안입니다.",
      "공시가격 9억원 이하 1세대 1주택 재산세율 0.05%p 인하 특례를 2029년까지 연장합니다.",
      "매입약정 임대주택 건설과 재개발 착공에 대한 취득세 감면을 확대합니다. 입법예고와 국회 심의 전 개편안입니다."
    ],
    "impact": "청년·생애최초 실수요자의 초기 취득 비용을 낮춰 소형 주택과 주거용 오피스텔 수요를 보완하는 요인입니다. 1주택 재산세 특례 연장은 중저가 실거주자의 보유 부담을 낮추지만 수도권 고가주택에는 직접 효과가 제한적입니다. 임대주택·재개발 취득세 감면은 서울과 수도권 도심 공급을 중장기적으로 늘리는 데 도움이 되지만 실제 입주까지 시차가 있어 단기 가격 안정 효과는 크지 않을 수 있습니다.",
    "url": "https://www.korea.kr/news/policyNewsView.do?newsId=148970644"
  }
};
const byId = id => document.getElementById(id);
const fmt = n => Number(n || 0).toLocaleString("ko-KR", {maximumFractionDigits: 2});
function shortMonthLabel(value){
  const match=String(value||"").match(/^(\d{4})-(\d{2})/);
  return match?match[1].slice(2)+"."+match[2]:String(value||"");
}
function shortMonthTick(value){return shortMonthLabel(this.getLabelForValue(value));}
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

function normalized(value){
  return String(value||"").normalize("NFKC").toLowerCase().replace(/\s+/g,"").replace(/(아파트|apt)$/g,"");
}
function compactName(value){ return normalized(value).replace(/[()（）\[\]{}·.,\-_/]/g,""); }
function looseName(value){
  return compactName(value).replace(/\d+(?:단지|차)$/g,"").replace(/(마을|타운|단지|촌)/g,"");
}
function nameVariants(value){
  const compact=compactName(value),withoutPhase=compact.replace(/\d+차$/,""),loose=looseName(value);
  return [...new Set([compact,withoutPhase,loose].filter(Boolean))];
}
function identity(row){ return [normalized(row.region_name),normalized(row.dong),normalized(row.apt_name)].join("|"); }
function groupKey(row){ return [String(row.lawd_cd||"").slice(0,5),row.dong,row.apt_name].join("|"); }
function localityKey(row){ return [String(row.lawd_cd||row.bjd_code||"").slice(0,5),normalized(row.dong)].join("|"); }
function normalizeAdministrativeAddress(value){
  return String(value||"").replace(/(수원|성남|안양|안산|고양|용인|부천|화성|청주|천안|전주|포항|창원)(?=[가-힣]+구(?:\s|$))/g,"$1시 ");
}
function addressOf(group){ return normalizeAdministrativeAddress(group.address||[group.region_name,group.dong,group.jibun].filter(Boolean).join(" ")); }
function searchAddressOf(group){
  const road=normalizeAdministrativeAddress(group.road_address||group.roadAddress||"");
  const base=addressOf(group),jibun=String(group.jibun||"").trim();
  const value=road||[base,jibun&&!base.endsWith(jibun)?jibun:""].filter(Boolean).join(" ");
  return {label:road?"도로명":"소재지",value:value||group.region_name||group.dong||"주소 정보 없음"};
}
function apartmentGeocodeName(value){
  const name=String(value||"").trim();
  return name&& !name.endsWith("아파트")?name+"아파트":name;
}
function geocodeQueryOf(group){ return [addressOf(group),apartmentGeocodeName(group.directory_name||group.apt_name)].filter(Boolean).join(" "); }
function isSubsequence(needle,haystack){ let i=0; for(const char of haystack){if(char===needle[i]) i++;} return i===needle.length; }
function apartmentNameScore(left,right){
  const leftVariants=nameVariants(left),rightVariants=nameVariants(right);
  if(!leftVariants.length||!rightVariants.length) return 0;
  let best=0;
  leftVariants.forEach(a=>rightVariants.forEach(b=>{
    if(a===b){best=Math.max(best,a.length>=4?1000:920);return;}
    const shorter=a.length<=b.length?a:b,longer=a.length>b.length?a:b;
    if(shorter.length>=4&&longer.includes(shorter)){
      best=Math.max(best,860+Math.round(shorter.length/longer.length*100));
    }else if(shorter.length>=4&&isSubsequence(shorter,longer)&&shorter.length/longer.length>=.7){
      best=Math.max(best,850+Math.round(shorter.length/longer.length*80));
    }
  }));
  return best;
}
function findCompatibleGroup(row,localityLookup){
  const candidates=(localityLookup.get(localityKey(row))||[]).filter(group=>group.fromDirectory);
  const ranked=candidates.map(group=>({group,score:apartmentNameScore(group.apt_name,row.apt_name)})).filter(item=>item.score>=860).sort((a,b)=>b.score-a.score);
  if(!ranked.length) return null;
  if(ranked[1]&&ranked[0].score-ranked[1].score<20) return null;
  return ranked[0].group;
}
function registerGroup(group,groups,lookup,localityLookup){
  groups.set(group.key,group);
  lookup.set(identity(group),group);
  const localKey=localityKey(group);
  if(!localityLookup.has(localKey)) localityLookup.set(localKey,[]);
  localityLookup.get(localKey).push(group);
}
function createGroup(row,key,address="",fromDirectory=false){
  return {
    key,
    lawd_cd:String(row.lawd_cd||row.bjd_code||"").slice(0,5),
    region_name:row.region_name,
    dong:row.dong,
    jibun:row.jibun||"",
    address,
    apt_name:row.apt_name,
    build_year:Number(row.build_year)||null,
    directory_name:fromDirectory?row.apt_name:"",
    trades:[],
    history:[],
    tradeAliases:new Set(),
    tradeNameCounts:new Map(),
    fromDirectory
  };
}
function rememberTradeName(group,name,weight=1){
  const label=String(name||"").trim();
  if(!label) return;
  group.tradeNameCounts.set(label,(group.tradeNameCounts.get(label)||0)+Math.max(1,Number(weight)||1));
  if(normalized(group.directory_name||group.apt_name)!==normalized(label)) group.tradeAliases.add(label);
}
async function fetchJson(path){ try{const response=await fetch(path);return response.ok?response.json():[];}catch{return [];} }
async function hydrateGroup(group){
  if(!localApi||group.hydrated||group.hydrating) return group.hydrating||group;
  if(!group.data_apt_name){group.hydrated=true;return group;}
  group.hydrating=(async()=>{
    const query=new URLSearchParams({lawd_cd:group.lawd_cd,dong:group.dong,apt_name:group.data_apt_name});
    const [history,trades]=await Promise.all([
      fetchJson("/api/history?"+query),
      fetchJson("/api/trades?"+query+"&limit=5000")
    ]);
    group.history=Array.isArray(history)?history:[];
    group.trades=Array.isArray(trades)?trades:[];
    group.history.sort((a,b)=>String(a.month).localeCompare(String(b.month)));
    group.trades.sort((a,b)=>String(a.trade_date).localeCompare(String(b.trade_date)));
    group.build_year=Number([...group.trades].reverse().find(row=>Number(row.build_year)>0)?.build_year)||group.build_year||null;
    group.areas=[...new Set(group.areas.concat(group.trades.map(r=>Number(r.area_m2)),group.history.map(r=>Number(r.area_m2))))].filter(Boolean).sort((a,b)=>a-b);
    group.hydrated=true;
    group.hydrating=null;
    return group;
  })();
  return group.hydrating;
}
function expandHistory(payload){
  if(Array.isArray(payload)) return payload;
  if(!payload||payload.version!==2||!Array.isArray(payload.apartments)||!Array.isArray(payload.rows)) return [];
  return payload.rows.map(row=>{
    const apartment=payload.apartments[Number(row[0])]||[];
    return {
      lawd_cd:String(apartment[0]||""),
      region_name:String(apartment[1]||""),
      dong:String(apartment[2]||""),
      apt_name:String(apartment[3]||""),
      area_m2:Number(row[1]||0),
      month:String(row[2]||""),
      median_price_eok:Number(row[3]||0),
      trade_count:Number(row[4]||0)
    };
  });
}
function median(values){
  if(!values.length) return 0;
  const sorted = [...values].sort((a,b)=>a-b), mid = Math.floor(sorted.length/2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid-1]+sorted[mid])/2;
}

async function load(){
  try{
    const localPayload=await fetchJson("/api/catalog");
    if(localPayload&&Array.isArray(localPayload.catalog)){
      localApi=true;
      localMeta=localPayload.meta||{};
      economicContext=await fetchJson("data/economic_context.json");
      apartmentGroups=localPayload.catalog.map(row=>{
        const group=createGroup(row,row.key,row.address||"",Boolean(row.directory_name));
        group.directory_name=row.directory_name||"";
        group.search_names=Array.isArray(row.search_names)?row.search_names:[row.apt_name];
        group.areas=Array.isArray(row.areas)?row.areas.map(Number).filter(Boolean).sort((a,b)=>a-b):[];
        group.latest=row.latest||null;
        group.build_year=Number(row.build_year)||group.build_year||null;
        group.data_apt_name=row.data_apt_name||"";
        group.coverage_years=Number(row.coverage_years||0);
        group.hydrated=false;
        return group;
      });
      byId("dataCount").textContent=fmt(localMeta.represented_trades||localMeta.transaction_rows||0)+"건 · "+fmt(apartmentGroups.length)+"단지";
      rebuildGroupIndexes();
      renderQuickSearch();
      restoreGraphBoards();
      ensureInitialGraphBoard();
      await Promise.all(graphBoards.flatMap(board=>board.series).map(series=>apartmentGroups.find(group=>group.key===series.key)).filter(Boolean).map(hydrateGroup));
      renderGraphBoards();
      const finished=Number(localMeta.districts_complete||0);
      setStatus(apartmentGroups.length+"개 단지를 검색할 수 있습니다. 전체 이력 완료 지역 "+finished+" / 97개");
      indexCachedGroupCoordinates();
      initMap();
      return;
    }
    const [rows,complexes,historyPayload,economic,publicMeta]=await Promise.all([
      fetchJson("data/latest_trades.json"),
      fetchJson("data/complexes.json"),
      fetchJson("data/apartment_history.json"),
      fetchJson("data/economic_context.json"),
      fetchJson("data/meta.json")
    ]);
    const history=expandHistory(historyPayload);
    economicContext=economic&&Array.isArray(economic.exchange_rates)?economic:economicContext;
    allTrades=rows.filter(r=>!r.cancelled);
    const groups=new Map(), lookup=new Map(), localityLookup=new Map();
    complexes.forEach(c=>{
      const key="complex|"+(c.complex_code||identity(c));
      registerGroup(createGroup(c,key,c.address||"",true),groups,lookup,localityLookup);
    });
    allTrades.forEach(row=>{
      let group=lookup.get(identity(row))||findCompatibleGroup(row,localityLookup);
      if(!group){
        const key=groupKey(row);
        group=groups.get(key);
        if(!group){
          group=createGroup(row,key);
          registerGroup(group,groups,lookup,localityLookup);
        }
      }
      lookup.set(identity(row),group);
      rememberTradeName(group,row.apt_name);
      group.trades.push(row);
    });
    history.forEach(row=>{
      let group=lookup.get(identity(row))||findCompatibleGroup(row,localityLookup);
      if(!group){
        const key=groupKey(row);
        group=groups.get(key);
        if(!group){
          group=createGroup(row,key);
          registerGroup(group,groups,lookup,localityLookup);
        }
      }
      lookup.set(identity(row),group);
      rememberTradeName(group,row.apt_name,row.trade_count);
      group.history.push(row);
    });
    apartmentGroups=[...groups.values()].map(g=>{
      g.trades.sort((a,b)=>a.trade_date.localeCompare(b.trade_date));
      g.history.sort((a,b)=>a.month.localeCompare(b.month));
      g.trade_names=[...(g.tradeNameCounts||new Map()).entries()].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0],"ko")).map(item=>item[0]);
      if(g.trade_names.length) g.apt_name=g.trade_names[0];
      g.search_names=[...new Set([g.apt_name,g.directory_name,...g.trade_names,...(g.tradeAliases||[])].filter(Boolean))];
      g.areas=[...new Set(g.trades.map(r=>Number(r.area_m2)).concat(g.history.map(r=>Number(r.area_m2))))].filter(Boolean).sort((a,b)=>a-b);
      const lastTrade=g.trades[g.trades.length-1],lastHistory=g.history[g.history.length-1];
      g.latest=lastTrade||(lastHistory?{trade_date:lastHistory.month,price_eok:lastHistory.median_price_eok}:null);
      g.build_year=Number([...g.trades].reverse().find(row=>Number(row.build_year)>0)?.build_year)||g.build_year||null;
      return g;
    }).sort((a,b)=>(b.latest?.trade_date||"").localeCompare(a.latest?.trade_date||""));
    const representedTrades=Number(publicMeta?.trade_count)||history.reduce((sum,row)=>sum+Number(row.trade_count||0),0)||allTrades.length;
    byId("dataCount").textContent=fmt(representedTrades)+"건 · "+fmt(apartmentGroups.length)+"단지";
    rebuildGroupIndexes();
    renderQuickSearch();
    restoreGraphBoards();
    ensureInitialGraphBoard();
    renderGraphBoards();
    setStatus(apartmentGroups.length+"개 전국 단지를 검색할 수 있습니다.");
    indexCachedGroupCoordinates();
    initMap();
  }catch(error){setStatus("데이터를 불러오지 못했습니다: "+error.message,true);}
}

function renderQuickSearch(){
  const names = [...new Set(apartmentGroups.map(g=>g.region_name))].slice(0,6);
  byId("quickSearch").innerHTML = names.map(name => '<button type="button" data-query="'+esc(name)+'">'+esc(name.replace(/광역시 |특별자치시 /," "))+"</button>").join("");
  byId("quickSearch").querySelectorAll("button").forEach(btn => btn.addEventListener("click",()=>{byId("searchInput").value=btn.dataset.query; search();}));
}

function score(group, query){
  const queryNames=nameVariants(query);
  const names=(group.search_names||[group.apt_name,...(group.trade_names||[])]).flatMap(nameVariants);
  const place=compactName(group.region_name+group.dong+group.jibun);
  const tokens=query.toLowerCase().split(/\s+/).map(compactName).filter(Boolean);
  const tokenScores=tokens.map(token=>{
    const related=names.some(name=>name.includes(token)||token.includes(name)||(token.length>=3&&isSubsequence(token,name)));
    return related?140:(place.includes(token)?100:0);
  });
  if(tokens.length>1&&tokenScores.every(Boolean)) return 850+tokenScores.reduce((sum,value)=>sum+value,0);
  const nameScore=Math.max(0,...(group.search_names||[group.apt_name]).map(name=>apartmentNameScore(name,query)));
  if(nameScore>=860) return nameScore;
  if(queryNames.some(q=>names.some(name=>name.startsWith(q)))) return 720;
  if(queryNames.some(q=>names.some(name=>name.includes(q)||q.includes(name)))) return 560;
  if(queryNames.some(q=>place.includes(q))) return 350;
  if(queryNames.some(q=>q.length>=3&&names.some(name=>isSubsequence(q,name)))) return 320;
  return tokenScores.reduce((sum,value)=>sum+value,0);
}

function matchingApartments(query,limit=12){
  return apartmentGroups.map(group=>({group,score:score(group,query)}))
    .filter(item=>item.score>0)
    .sort((a,b)=>b.score-a.score||a.group.apt_name.localeCompare(b.group.apt_name,"ko",{numeric:true,sensitivity:"base"})||searchAddressOf(a.group).value.localeCompare(searchAddressOf(b.group).value,"ko"))
    .slice(0,limit);
}

function hideSearchSuggestions(){
  const suggestions=byId("searchSuggestions"),input=byId("searchInput");
  suggestions.hidden=true;suggestions.innerHTML="";input.setAttribute("aria-expanded","false");
}

function renderSearchSuggestions(matches,query){
  const suggestions=byId("searchSuggestions"),input=byId("searchInput");
  if(!query){hideSearchSuggestions();return;}
  if(!matches.length){
    suggestions.innerHTML='<div class="search-suggestion-empty">‘'+esc(query)+'’와 비슷한 단지를 찾지 못했습니다.</div>';
  }else{
    suggestions.innerHTML=matches.map((item,index)=>{
      const group=item.group,address=searchAddressOf(group);
      const area=group.latest?.area_m2?'최근 '+fmt(group.latest.area_m2)+'㎡':(group.areas?.length?fmt(group.areas.length)+'개 평형':'단지 정보');
      return '<button class="search-suggestion" type="button" role="option" aria-selected="false" data-key="'+esc(group.key)+'" data-index="'+index+'"><span class="search-suggestion-main"><b>'+esc(group.apt_name)+'</b><small><em>'+address.label+'</em>'+esc(address.value)+'</small></span><span>'+esc(area)+'</span></button>';
    }).join("");
    suggestions.querySelectorAll(".search-suggestion").forEach(button=>{
      button.addEventListener("click",()=>chooseSearchSuggestion(button.dataset.key));
      button.addEventListener("keydown",event=>{
        const buttons=[...suggestions.querySelectorAll(".search-suggestion")],index=buttons.indexOf(button);
        if(event.key==="ArrowDown"){event.preventDefault();buttons[(index+1)%buttons.length].focus();}
        if(event.key==="ArrowUp"){event.preventDefault();buttons[(index-1+buttons.length)%buttons.length].focus();}
        if(event.key==="Escape"){event.preventDefault();hideSearchSuggestions();input.focus();}
      });
    });
  }
  suggestions.hidden=false;input.setAttribute("aria-expanded","true");
}

async function chooseSearchSuggestion(key){
  const group=apartmentGroups.find(item=>item.key===key);
  if(!group)return;
  const runId=++searchRunId;
  byId("searchInput").value=group.apt_name;
  hideSearchSuggestions();regionFilteredKeys=null;clearMapMarkers();
  renderResults([{group,score:1000}],group.apt_name);
  setStatus("‘"+group.apt_name+"’ 단지를 선택했습니다.");
  await selectSearchGroup(group,runId);
}

async function search(){
  const runId=++searchRunId;
  const query=byId("searchInput").value.trim();
  if(!query){ setStatus("검색어를 입력해 주세요.",true); return; }
  regionFilteredKeys=null;
  clearMapMarkers();
  setStatus("‘"+query+"’ 주변 단지를 찾는 중입니다…");
  const matches=matchingApartments(query,12);
  renderResults(matches,query);
  renderSearchSuggestions(matches,query);
  if(matches.length===1){hideSearchSuggestions();await selectSearchGroup(matches[0].group,runId);}
  else if(matches.length>1)setStatus("비슷한 단지 "+matches.length+"개 중 하나를 선택해 주세요.");
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

function estimatedSupplyPyeong(area){return Number(area)/3.3058/.75;}
function defaultSupplyPyeong(area){return Math.round(estimatedSupplyPyeong(area)*100)/100;}
function areaComparisonLabel(area,supplyPyeong=null){
  const exclusive=Number(area),supply=Number(supplyPyeong)||estimatedSupplyPyeong(exclusive);
  return '공급 약 '+fmt(supply*3.3058)+'㎡ · '+fmt(supply)+'평 (전용 '+fmt(exclusive)+'㎡ · '+fmt(exclusive/3.3058)+'평)';
}

function sameSeriesCount(group){
  const board=activeBoard();
  return board?board.series.filter(series=>series.key===group.key).length:0;
}
function graphAddLabel(group){
  const count=sameSeriesCount(group);
  return count?'그래프에 추가 · 현재 '+count+'개':'그래프에 추가';
}
function compactGraphAddLabel(group){
  const count=sameSeriesCount(group);
  return count?'그래프 추가 ('+count+')':'그래프 추가';
}
function refreshGraphAddButtons(group){
  const label=graphAddLabel(group);
  document.querySelectorAll('.map-popup-add').forEach(button=>{if(button.dataset.key===group.key&&!button.disabled)button.textContent=label;});
}

function renderResults(matches,query){
  byId("resultCount").textContent=matches.length+"개";
  if(!matches.length){
    byId("results").innerHTML='<div class="empty">‘'+esc(query)+'’와 일치하는 수집 단지가 없습니다.<br>동 이름이나 단지명의 일부로 다시 검색해 보세요.</div>';
    setStatus("검색 결과가 없습니다.",true); return;
  }
  byId("results").innerHTML=matches.map(item=>{
    const g=item.group;
    const distance=Number.isFinite(item.distance)?fmt(item.distance)+"km":(g.trades.length||g.history.length?"거래자료 있음":"단지 기본정보");
    const collecting=localApi&&Number(g.coverage_years||0)<20;
    const price=g.latest?fmt(g.latest.price_eok)+"억":(collecting?"과거 자료 수집 중":"공식 실거래 없음");
    const areas=g.areas.length?"전용 "+g.areas.map(fmt).join(", ")+"㎡":(collecting?"평형 자료 수집 중":"공식 거래 평형 없음");
    const csvNames=(g.trade_names||[]).slice(0,3);
    const aliasParts=[];
    if(csvNames.length) aliasParts.push("실거래 자료 표기: "+csvNames.map(esc).join(", "));
    if(g.directory_name&&normalized(g.directory_name)!==normalized(g.apt_name)) aliasParts.push("지도 표기: "+esc(g.directory_name));
    const aliases=aliasParts.length?'<small class="trade-alias">'+aliasParts.join(" · ")+'</small>':"";
    return '<div class="result" data-key="'+esc(g.key)+'"><div class="result-top"><div><h3>'+esc(g.apt_name)+'</h3><p>'+esc(addressOf(g))+'</p>'+aliases+'</div><span class="price">'+price+'</span></div><div class="result-actions"><span>'+distance+' · '+areas+'</span><button class="add-btn" type="button">'+esc(graphAddLabel(g))+'</button></div></div>';
  }).join("");
  bindResultCards(byId("results"));
  setStatus("가까운 순서와 검색 일치도를 기준으로 "+matches.length+"개 단지를 표시했습니다.");
}

function bindResultCards(container){
  container.querySelectorAll(".result").forEach(card=>{
    const group=apartmentGroups.find(g=>g.key===card.dataset.key);
    card.addEventListener("click",e=>{if(!e.target.classList.contains("add-btn"))selectSearchGroup(group,++searchRunId);});
    card.querySelector(".add-btn").addEventListener("click",async e=>{
      e.stopPropagation();
      const button=e.currentTarget;
      button.disabled=true;button.classList.add("is-pressed");button.textContent="추가 중...";
      const added=await addSeries(group);
      await new Promise(resolve=>setTimeout(resolve,180));
      button.disabled=false;button.classList.remove("is-pressed");
      if(added){button.classList.add("is-added");button.textContent=sameSeriesCount(group)+"번째 추가됨";setTimeout(()=>{button.classList.remove("is-added");refreshResultButtons();},650);}
      else refreshResultButtons();
    });
  });
}

function renderRegionComplexList(groups,label){
  const panel=byId("regionComplexPanel"),list=byId("regionComplexList");
  if(!panel||!list)return;
  const sorted=[...groups].sort((a,b)=>a.apt_name.localeCompare(b.apt_name,"ko",{numeric:true,sensitivity:"base"})||addressOf(a).localeCompare(addressOf(b),"ko"));
  byId("regionComplexTitle").textContent=label+" 단지 목록";
  byId("regionComplexCount").textContent=fmt(sorted.length)+"개 · 가나다순";
  list.innerHTML=sorted.map(g=>{
    const collecting=localApi&&Number(g.coverage_years||0)<20;
    const price=g.latest?fmt(g.latest.price_eok)+"억":(collecting?"과거 자료 수집 중":"공식 실거래 없음");
    const latestArea=Number(g.latest?.area_m2);
    const otherAreaCount=Number.isFinite(latestArea)?g.areas.filter(area=>Math.abs(Number(area)-latestArea)>.01).length:0;
    const areaSummary=Number.isFinite(latestArea)&&latestArea>0
      ?'최근 거래 · 약 '+fmt(Math.round(estimatedSupplyPyeong(latestArea)))+'평형 (전용 '+fmt(latestArea)+'㎡)'+(otherAreaCount?' · 외 '+fmt(otherAreaCount)+'개 평형':'')
      :(g.areas.length?'등록 평형 '+fmt(g.areas.length)+'개':(collecting?'평형 자료 수집 중':'평형 정보 없음'));
    return '<div class="result" data-key="'+esc(g.key)+'"><div class="result-top"><div><h3>'+esc(g.apt_name)+'</h3><p>'+esc(addressOf(g))+'</p></div><span class="price">'+price+'</span></div><div class="result-actions"><span>'+areaSummary+'</span><button class="add-btn" type="button">'+esc(compactGraphAddLabel(g))+'</button></div></div>';
  }).join("");
  bindResultCards(list);
  panel.hidden=false;
}

function hideRegionComplexList(){
  const panel=byId("regionComplexPanel");
  if(panel)panel.hidden=true;
}

function clearMapMarkers(){
  markers.forEach(marker=>{if(map)map.removeLayer(marker);});
  markers.clear();
}

function rebuildGroupIndexes(){
  groupByKey.clear();groupsByLawd.clear();groupsByMapName.clear();regionHierarchy.clear();
  apartmentGroups.forEach(group=>{
    groupByKey.set(group.key,group);
    if(!groupsByLawd.has(group.lawd_cd))groupsByLawd.set(group.lawd_cd,[]);
    groupsByLawd.get(group.lawd_cd).push(group);
    (group.search_names||[group.apt_name]).forEach(name=>{
      const key=compactName(mapComplexName(name));
      if(key.length<3)return;
      if(!groupsByMapName.has(key))groupsByMapName.set(key,[]);
      const bucket=groupsByMapName.get(key);
      if(!bucket.includes(group))bucket.push(group);
    });
    const parts=regionParts(group);
    if(!regionHierarchy.has(parts.sido))regionHierarchy.set(parts.sido,new Map());
    const districts=regionHierarchy.get(parts.sido);
    if(!districts.has(parts.sigungu))districts.set(parts.sigungu,new Map());
    const dongs=districts.get(parts.sigungu);
    if(!dongs.has(parts.dong))dongs.set(parts.dong,[]);
    dongs.get(parts.dong).push(group);
  });
  renderRegionSelector();
}

function regionParts(group){
  const tokens=normalizeAdministrativeAddress(group.region_name||"").trim().split(/\s+/).filter(Boolean);
  return {sido:tokens.shift()||"기타",sigungu:tokens.join(" ")||"기타",dong:String(group.dong||"기타")};
}

function shortSido(value){return String(value).replace("서울특별시","서울시").replace("부산광역시","부산시").replace("광역시","시");}

const sidoDistanceOrder=["서울특별시","경기도","인천광역시","강원특별자치도","강원도","충청북도","충청남도","세종특별자치시","대전광역시","경상북도","전북특별자치도","전라북도","대구광역시","경상남도","광주광역시","전라남도","울산광역시","부산광역시","제주특별자치도"];
function sidoDistanceRank(value){const rank=sidoDistanceOrder.indexOf(value);return rank<0?sidoDistanceOrder.length:rank;}

function renderRegionSelector(){
  const breadcrumb=byId("regionBreadcrumb"),options=byId("regionOptions");
  if(!breadcrumb||!options)return;
  const crumbs=[
    {stage:"sido",label:regionSelection.sido?shortSido(regionSelection.sido):"시도 선택",selected:Boolean(regionSelection.sido)},
    {stage:"sigungu",label:regionSelection.sigungu||"시군구 선택",selected:Boolean(regionSelection.sigungu)},
    {stage:"dong",label:regionSelection.dong||"읍면동 선택",selected:Boolean(regionSelection.dong)}
  ];
  breadcrumb.innerHTML=crumbs.map((item,index)=>'<button type="button" class="'+(item.selected?'selected':'')+'" data-stage="'+item.stage+'">'+esc(item.label)+'</button>'+(index<2?'<i>›</i>':'')).join("");
  breadcrumb.querySelectorAll("button").forEach(button=>button.addEventListener("click",()=>{
    if(button.dataset.stage==="sido")regionSelection={sido:"",sigungu:"",dong:""};
    else if(button.dataset.stage==="sigungu")regionSelection={sido:regionSelection.sido,sigungu:"",dong:""};
    else if(button.dataset.stage==="dong")regionSelection.dong="";
    regionFilteredKeys=null;clearMapMarkers();hideRegionComplexList();renderRegionSelector();
  }));
  if(regionSelection.dong){options.innerHTML="";options.hidden=true;return;}
  options.hidden=false;
  let items=[];
  if(!regionSelection.sido){
    items=[...regionHierarchy].map(([value,districts])=>({value,label:shortSido(value),count:[...districts.values()].reduce((sum,dongs)=>sum+[...dongs.values()].reduce((n,groups)=>n+groups.length,0),0)}));
  }else if(!regionSelection.sigungu){
    items=[...(regionHierarchy.get(regionSelection.sido)||new Map())].map(([value,dongs])=>({value,label:value,count:[...dongs.values()].reduce((sum,groups)=>sum+groups.length,0)}));
  }else{
    items=[...(regionHierarchy.get(regionSelection.sido)?.get(regionSelection.sigungu)||new Map())].map(([value,groups])=>({value,label:value,count:groups.length}));
  }
  if(!regionSelection.sido)items.sort((a,b)=>sidoDistanceRank(a.value)-sidoDistanceRank(b.value)||a.label.localeCompare(b.label,"ko"));
  else items.sort((a,b)=>a.label.localeCompare(b.label,"ko"));
  options.innerHTML=items.map(item=>'<button type="button" data-value="'+esc(item.value)+'"><b>'+esc(item.label)+'</b><small>'+fmt(item.count)+'개 단지</small></button>').join("");
  options.querySelectorAll("button").forEach(button=>button.addEventListener("click",()=>{
    const value=button.dataset.value;
    if(!regionSelection.sido)regionSelection={sido:value,sigungu:"",dong:""};
    else if(!regionSelection.sigungu)regionSelection={...regionSelection,sigungu:value,dong:""};
    else{
      regionSelection.dong=value;
      const groups=regionHierarchy.get(regionSelection.sido)?.get(regionSelection.sigungu)?.get(value)||[];
      const label=[shortSido(regionSelection.sido),regionSelection.sigungu,value].join(" ");
      renderRegionComplexList(groups,label);
      applyRegionSelection();
    }
    renderRegionSelector();
  }));
}

function currentMarkerLimit(){return regionFilteredKeys?MAX_REGION_MARKERS:MAX_VIEWPORT_MARKERS;}

async function applyRegionSelection(){
  const selectionRunId=++regionSelectionRunId;
  const groups=regionHierarchy.get(regionSelection.sido)?.get(regionSelection.sigungu)?.get(regionSelection.dong)||[];
  const selectedKeys=new Set(groups.map(group=>group.key));
  regionFilteredKeys=selectedKeys;
  clearMapMarkers();viewportRefreshSuspended=false;
  const known=groups.map(group=>({group,coord:cachedCoordinate(group)})).filter(item=>item.coord);
  known.slice(0,MAX_REGION_MARKERS).forEach(item=>ensureMapMarker(item.group,item.coord));
  const label=[shortSido(regionSelection.sido),regionSelection.sigungu,regionSelection.dong].join(" ");
  setStatus(label+"의 등록 단지 "+groups.length+"개를 지도에서 확인합니다.");
  let center=null;
  if(known.length){
    map.fitBounds(L.latLngBounds(known.map(item=>[item.coord.lat,item.coord.lng])),{padding:[35,35],maxZoom:16});
    center=known[0].coord;
  }else{
    center=await geocode(label);
    if(center){mapLocalityAnchor={coord:center,lawd_cd:groups[0]?.lawd_cd||"",group:groups[0]};map.setView([center.lat,center.lng],15);}
  }
  if(center)populateRegionMarkers(groups,center,selectionRunId,label,selectedKeys);
  // Region selection positions the map and seeds its markers. Once positioned,
  // free the viewport so panning into a neighbouring dong can discover markers.
  regionFilteredKeys=null;
  scheduleViewportMarkers();
}

async function populateRegionMarkers(groups,center,selectionRunId,label,selectedKeys){
  let located=0;
  for(const group of groups){
    if(selectionRunId!==regionSelectionRunId||!selectedKeys.has(group.key))return;
    let coord=cachedCoordinate(group);
    if(!coord){
      const query=[normalizeAdministrativeAddress(group.region_name),group.dong,apartmentGeocodeName(group.directory_name||group.apt_name)].filter(Boolean).join(" ");
      coord=await geocode(query);
      if(coord&&haversine(center,coord)>8){delete geoCache[query];localStorage.setItem("aptGeoCache",JSON.stringify(geoCache));coord=null;}
    }
    if(!coord)continue;
    groupCoordinates.set(group.key,coord);ensureMapMarker(group,coord);located++;
    byId("mapState").textContent="지역 단지 좌표 확인 중 · "+located+" / "+groups.length+"개";
  }
  if(selectionRunId!==regionSelectionRunId)return;
  byId("mapState").textContent="지역 단지 표시 완료 · "+markers.size+" / "+groups.length+"개";
  setStatus(label+"의 등록 단지 "+groups.length+"개 중 좌표가 확인된 "+markers.size+"개를 표시했습니다.");
}

function ensureMapMarker(group,coord){
  if(!map||!coord)return null;
  groupCoordinates.set(group.key,coord);
  let marker=markers.get(group.key);
  if(marker)return marker;
  marker=L.marker([coord.lat,coord.lng],{title:group.apt_name,alt:group.apt_name+" 단지 마커",keyboard:true}).addTo(map);
  marker.bindPopup(mapPopupHtml(group),{closeOnClick:false});
  marker.on("popupopen",event=>{
    event.popup.setContent(mapPopupHtml(group));
    const popupElement=event.popup.getElement();
    if(popupElement){
      L.DomEvent.disableClickPropagation(popupElement);
      L.DomEvent.disableScrollPropagation(popupElement);
    }
  });
  marker.on("click",()=>renderDetails(group,activeBoard()?.series.find(s=>s.key===group.key)?.area||group.areas[0]));
  markers.set(group.key,marker);
  return marker;
}

function mapPopupHtml(group){
  const latest=group.latest,area=Number(latest?.area_m2);
  const areaText=Number.isFinite(area)&&area>0?areaComparisonLabel(area):'';
  const priceText=latest?'최근 '+fmt(latest.price_eok)+'억원'+(areaText?' · '+areaText:''):'최근 거래 없음';
  const buildYear=Number(group.build_year||latest?.build_year);
  const yearText=Number.isFinite(buildYear)&&buildYear>0?' · '+buildYear+'년식':'';
  return '<div class="map-popup"><b>'+esc(group.apt_name)+'</b><small>'+esc(addressOf(group))+yearText+'</small><strong>'+priceText+'</strong><button class="map-popup-add" type="button" data-key="'+esc(group.key)+'">'+esc(graphAddLabel(group))+'</button></div>';
}

function indexCachedGroupCoordinates(){
  groupCoordinates.clear();
  apartmentGroups.forEach(group=>{
    const coord=geoCache[geocodeQueryOf(group)]||geoCache[apartmentGeocodeName(group.apt_name)];
    if(coord&&Number.isFinite(Number(coord.lat))&&Number.isFinite(Number(coord.lng)))groupCoordinates.set(group.key,{lat:Number(coord.lat),lng:Number(coord.lng)});
  });
}

function scheduleViewportMarkers(){
  clearTimeout(viewportMarkerTimer);
  if(viewportRefreshSuspended)return;
  viewportMarkerTimer=setTimeout(()=>{syncViewportMarkers();refreshViewportBuildings(++buildingRequestId);},350);
}

function syncViewportMarkers(){
  if(!map||viewportRefreshSuspended)return;
  if(map.getZoom()<MIN_MARKER_ZOOM){
    clearMapMarkers();
    byId("mapState").textContent="지도를 확대하면 주변 단지를 표시합니다";
    return;
  }
  const bounds=map.getBounds().pad(.08),center=map.getCenter(),visible=[];
  groupCoordinates.forEach((coord,key)=>{
    if(!bounds.contains([coord.lat,coord.lng]))return;
    const group=groupByKey.get(key);
    if(group)visible.push({group,coord,distance:haversine({lat:center.lat,lng:center.lng},coord)});
  });
  visible.sort((a,b)=>a.distance-b.distance);
  const candidates=regionFilteredKeys?visible.filter(item=>regionFilteredKeys.has(item.group.key)):visible;
  const selected=candidates.slice(0,currentMarkerLimit()),selectedKeys=new Set(selected.map(item=>item.group.key));
  markers.forEach((marker,key)=>{if(!selectedKeys.has(key)){map.removeLayer(marker);markers.delete(key);}});
  selected.forEach(item=>ensureMapMarker(item.group,item.coord));
  byId("mapState").textContent=selected.length?"화면 중심 주변 "+selected.length+"개 단지":"이 화면에서 확인된 단지 좌표가 없습니다";
}

function buildingPoint(element){
  const lat=Number(element.lat??element.center?.lat),lng=Number(element.lon??element.center?.lon);
  return Number.isFinite(lat)&&Number.isFinite(lng)?{lat,lng}:null;
}

function mapComplexName(value){
  return String(value||"").trim().replace(/\s*\d{1,4}동$/g,"").replace(/(?:아파트|공동주택)$/g,"").trim();
}

function groupForMapName(value,localityTokens=[],lawdCd=""){
  const name=mapComplexName(value),nameKey=compactName(name),cacheKey=nameKey+"|"+lawdCd+"|"+localityTokens.join("|");
  if(nameKey.length<3)return null;
  if(mapNameGroupCache.has(cacheKey))return mapNameGroupCache.get(cacheKey)||null;
  const ranked=[];
  const exactCandidates=groupsByMapName.get(nameKey)||[];
  const candidates=exactCandidates.length?exactCandidates:(lawdCd?groupsByLawd.get(lawdCd)||[]:apartmentGroups);
  candidates.forEach(group=>{
    if(lawdCd&&group.lawd_cd!==lawdCd)return;
    const place=compactName(group.region_name+" "+addressOf(group));
    if(localityTokens.length&&!localityTokens.every(token=>place.includes(token)))return;
    const score=Math.max(0,...(group.search_names||[group.apt_name]).map(candidate=>apartmentNameScore(mapComplexName(candidate),name)));
    if(score>=(localityTokens.length||lawdCd?860:940))ranked.push({group,score});
  });
  ranked.sort((a,b)=>b.score-a.score);
  const matched=ranked.length&&(!ranked[1]||ranked[0].score-ranked[1].score>=20)?ranked[0].group:null;
  mapNameGroupCache.set(cacheKey,matched||false);
  return matched;
}

async function reverseMapLocality(center){
  const key=center.lat.toFixed(2)+","+center.lng.toFixed(2);
  if(viewportLocalityCache.has(key))return viewportLocalityCache.get(key);
  const elapsed=Date.now()-lastGeocodeAt;
  if(elapsed<1100)await new Promise(resolve=>setTimeout(resolve,1100-elapsed));
  lastGeocodeAt=Date.now();
  try{
    const url="/api/reverse-geocode?zoom=16&lat="+encodeURIComponent(center.lat)+"&lon="+encodeURIComponent(center.lng);
    const response=await Promise.race([
      fetch(url),
      new Promise((_,reject)=>setTimeout(()=>reject(new Error("지도 지역 확인 시간 초과")),6000))
    ]);
    if(!response.ok)throw new Error("지도 지역 확인 실패");
    const payload=await response.json();
    const address=payload.address||{};
    const tokens=[address.quarter,address.neighbourhood,address.suburb,address.village,address.town,address.hamlet,address.city_district,address.borough,address.county,address.city,address.municipality,address.province].map(compactName).filter((value,index,items)=>value&&value.length>=2&&items.indexOf(value)===index).slice(0,6);
    viewportLocalityCache.set(key,tokens);
    return tokens;
  }catch{return [];}
}

function lawdCodeForLocality(localityTokens){
  if(!localityTokens.length)return "";
  const scores=new Map();
  apartmentGroups.forEach(group=>{
    const place=compactName(group.region_name+" "+addressOf(group));
    const dong=localityToken(group.dong);
    let score=0;
    localityTokens.forEach(token=>{
      const clean=localityToken(token);
      if(!clean)return;
      if(dong&&(clean.includes(dong)||dong.includes(clean)))score+=9;
      else if(place.includes(token))score+=/[도시군구]$/.test(token)?3:1;
    });
    if(score>0)scores.set(group.lawd_cd,Math.max(score,scores.get(group.lawd_cd)||0));
  });
  const ranked=[...scores].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]));
  return ranked.length&&ranked[0][1]>=4&&(!ranked[1]||ranked[0][1]>ranked[1][1])?ranked[0][0]:"";
}

async function geocodeNearbyGroup(group,center){
  const cacheKey=geocodeQueryOf(group),cached=geoCache[cacheKey];
  if(cached&&haversine(center,cached)<=5)return cached;
  const elapsed=Date.now()-lastGeocodeAt;
  if(elapsed<1100)await new Promise(resolve=>setTimeout(resolve,1100-elapsed));
  lastGeocodeAt=Date.now();
  try{
    const fullName=mapComplexName(group.directory_name||group.apt_name);
    const villageName=mapComplexName(group.apt_name).replace(/[（(].*?[）)]/g,"").replace(/\d+(?:단지|차)/g,"").trim();
    const queries=[[group.dong,fullName].filter(Boolean).join(" "),[group.dong,villageName].filter(Boolean).join(" ")].filter((value,index,items)=>value&&items.indexOf(value)===index);
    let nearby=null;
    for(const query of queries){
      const url="/api/geocode?limit=5&q="+encodeURIComponent(query);
      const rows=await Promise.race([
        fetch(url).then(response=>{if(!response.ok)throw new Error("단지 좌표 검색 실패");return response.json();}),
        new Promise((_,reject)=>setTimeout(()=>reject(new Error("단지 좌표 검색 시간 초과")),10000))
      ]);
      nearby=rows.map(row=>({lat:Number(row.lat),lng:Number(row.lon)})).filter(coord=>Number.isFinite(coord.lat)&&Number.isFinite(coord.lng)&&haversine(center,coord)<=5).sort((a,b)=>haversine(center,a)-haversine(center,b))[0]||null;
      if(nearby)break;
    }
    if(!nearby)return null;
    geoCache[cacheKey]=nearby;
    localStorage.setItem("aptGeoCache",JSON.stringify(geoCache));
    groupCoordinates.set(group.key,nearby);
    return nearby;
  }catch{return null;}
}

function localityToken(value){return compactName(value).replace(/\d/g,"").replace(/^제(?=.+동$)/,"");}

function groupMatchesViewportLocality(group,localityTokens){
  const dong=localityToken(group.dong);
  return Boolean(dong)&&localityTokens.some(token=>{
    const clean=localityToken(token);
    return clean&&(clean.includes(dong)||dong.includes(clean));
  });
}

async function discoverLocalViewportGroups(runId,bounds,center,lawdCd,localityTokens=[],allowGeocode=false){
  if(!lawdCd)return 0;
  const anchorDong=mapLocalityAnchor?.group?.dong||"";
  const candidates=(groupsByLawd.get(lawdCd)||[]).filter(group=>!markers.has(group.key)&&(!regionFilteredKeys||regionFilteredKeys.has(group.key))).sort((a,b)=>{
    const viewportA=groupMatchesViewportLocality(a,localityTokens)?1:0,viewportB=groupMatchesViewportLocality(b,localityTokens)?1:0;
    const sameDongA=a.dong===anchorDong?1:0,sameDongB=b.dong===anchorDong?1:0;
    const namedA=a.directory_name?1:0,namedB=b.directory_name?1:0;
    return viewportB-viewportA||sameDongB-sameDongA||namedB-namedA||(b.latest?.trade_date||"").localeCompare(a.latest?.trade_date||"");
  });
  let added=0,geocoded=0;
  for(const group of candidates){
    if(runId!==buildingRequestId||viewportRefreshSuspended)return added;
    let coord=cachedCoordinate(group);
    if(!coord&&allowGeocode&&geocoded<MAX_VIEWPORT_FALLBACK_GEOCODES&&groupMatchesViewportLocality(group,localityTokens)){
      geocoded++;
      byId("mapState").textContent="주변 단지 좌표 복구 중 · "+geocoded+" / "+MAX_VIEWPORT_FALLBACK_GEOCODES;
      coord=await geocodeNearbyGroup(group,center);
    }
    if(!coord||!bounds.pad(.08).contains([coord.lat,coord.lng]))continue;
    ensureMapMarker(group,coord);added++;
    byId("mapState").textContent="보조 좌표 확인 중 · 현재 화면 단지 "+markers.size+"개";
    if(markers.size>=currentMarkerLimit())break;
  }
  return added;
}

async function refreshViewportBuildings(runId){
  if(!map||viewportRefreshSuspended)return;
  if(map.getZoom()<MIN_BUILDING_ZOOM){
    if(buildingAbortController)buildingAbortController.abort();
    byId("mapState").textContent="지도를 더 확대하면 단지 마커를 표시합니다";
    return;
  }
  if(buildingAbortController)buildingAbortController.abort();
  buildingAbortController=new AbortController();
  const bounds=map.getBounds(),center=map.getCenter(),queryBounds=bounds.pad(.08);
  const cachedViewport=viewportComplexCache&&viewportComplexCache.bounds.contains(bounds.getSouthWest())&&viewportComplexCache.bounds.contains(bounds.getNorthEast());
  const anchorLawdCd=mapLocalityAnchor&&haversine(center,mapLocalityAnchor.coord)<=5?mapLocalityAnchor.lawd_cd:"";
  byId("mapState").textContent=cachedViewport?"저장된 주변 단지 확인 중…":"주변 단지 조회 중…";
  const localityPromise=reverseMapLocality(center);
  let localFallbackPromise=anchorLawdCd?discoverLocalViewportGroups(runId,bounds,center,anchorLawdCd):Promise.resolve(0);
  // Start the slower but reliable local-coordinate recovery immediately instead
  // of waiting for the bulk map provider to time out first.
  const progressiveFallbackPromise=(async()=>{
    const tokens=await localityPromise;
    if(runId!==buildingRequestId||viewportRefreshSuspended)return 0;
    const fallbackLawdCd=anchorLawdCd||lawdCodeForLocality(tokens);
    return discoverLocalViewportGroups(runId,bounds,center,fallbackLawdCd,tokens,true);
  })();
  try{
    let payload=cachedViewport?{elements:viewportComplexCache.elements}:null;
    if(!payload){
      try{
        const params=new URLSearchParams({south:queryBounds.getSouth(),west:queryBounds.getWest(),north:queryBounds.getNorth(),east:queryBounds.getEast()});
        const response=await fetch("/api/map-complexes?"+params,{signal:buildingAbortController.signal});
        if(!response.ok)throw new Error("로컬 지도 조회 실패");
        payload=await response.json();
      }catch(localError){
        if(localError.name==="AbortError")throw localError;
        throw localError;
      }
      viewportComplexCache={bounds:queryBounds,elements:payload.elements||[]};
    }
    if(runId!==buildingRequestId||viewportRefreshSuspended)return;
    // Do not hold marker rendering behind a rate-limited reverse-geocode call.
    const localityTokens=await Promise.race([localityPromise,new Promise(resolve=>setTimeout(()=>resolve([]),350))]);
    if(runId!==buildingRequestId||viewportRefreshSuspended)return;
    const localLawdCd=anchorLawdCd||lawdCodeForLocality(localityTokens);
    if(!anchorLawdCd&&localLawdCd)localFallbackPromise=discoverLocalViewportGroups(runId,bounds,center,localLawdCd);
    const buckets=new Map();
    (payload.elements||[]).forEach(element=>{
      const coord=buildingPoint(element),group=groupForMapName(element.tags?.name||element.tags?.["name:ko"],localityTokens,localLawdCd);
      if(!coord||!bounds.contains([coord.lat,coord.lng])||!group||(regionFilteredKeys&&!regionFilteredKeys.has(group.key)))return;
      const bucket=buckets.get(group.key)||{group,lat:0,lng:0,count:0};
      bucket.lat+=coord.lat;bucket.lng+=coord.lng;bucket.count++;
      buckets.set(group.key,bucket);
    });
    const selected=[...buckets.values()].map(bucket=>({group:bucket.group,coord:{lat:bucket.lat/bucket.count,lng:bucket.lng/bucket.count}})).sort((a,b)=>haversine(center,a.coord)-haversine(center,b.coord)).slice(0,regionFilteredKeys?MAX_REGION_MARKERS:MAX_BUILDING_MARKERS);
    let geoCacheChanged=false;
    selected.forEach(item=>{
      groupCoordinates.set(item.group.key,item.coord);
      const key=geocodeQueryOf(item.group),cached=geoCache[key];
      if(!cached||haversine(cached,item.coord)>.03){geoCache[key]=item.coord;geoCacheChanged=true;}
    });
    if(geoCacheChanged)localStorage.setItem("aptGeoCache",JSON.stringify(geoCache));
    syncViewportMarkers();
    await localFallbackPromise;
    await progressiveFallbackPromise;
    byId("mapState").textContent=markers.size?"조회 완료 · 현재 화면 단지 "+markers.size+"개":"조회 완료 · 이 화면에 연결 가능한 단지 없음";
  }catch(error){
    if(error.name!=="AbortError"&&runId===buildingRequestId){
      const localityTokens=await localityPromise;
      const localLawdCd=anchorLawdCd||lawdCodeForLocality(localityTokens);
      if(!anchorLawdCd&&localLawdCd)localFallbackPromise=discoverLocalViewportGroups(runId,bounds,center,localLawdCd);
      await localFallbackPromise;
      await progressiveFallbackPromise;
      if(runId!==buildingRequestId||viewportRefreshSuspended)return;
      byId("mapState").textContent=markers.size?"외부 조회 실패 · 로컬 좌표 단지 "+markers.size+"개 표시":"외부 조회 실패 · 배율 문제 아님";
    }
  }
}

function cachedCoordinate(group){
  return groupCoordinates.get(group.key)||geoCache[geocodeQueryOf(group)]||geoCache[apartmentGeocodeName(group.apt_name)]||null;
}

async function selectSearchGroup(group,runId){
  viewportRefreshSuspended=true;
  if(buildingAbortController)buildingAbortController.abort();
  clearMapMarkers();
  const coord=await focusGroup(group,cachedCoordinate(group));
  if(runId!==searchRunId||!coord){viewportRefreshSuspended=false;return;}
  await showNearbyMarkers(group,coord,runId);
}

async function showNearbyMarkers(selectedGroup,centerCoord,runId){
  viewportRefreshSuspended=true;
  let newGeocodes=0,shown=1;
  const candidates=apartmentGroups.filter(group=>group.key!==selectedGroup.key&&group.lawd_cd===selectedGroup.lawd_cd).sort((a,b)=>{
    const sameDongA=a.dong===selectedGroup.dong?1:0,sameDongB=b.dong===selectedGroup.dong?1:0;
    const cachedA=cachedCoordinate(a)?1:0,cachedB=cachedCoordinate(b)?1:0;
    return sameDongB-sameDongA||cachedB-cachedA||(b.latest?.trade_date||"").localeCompare(a.latest?.trade_date||"");
  });
  setStatus(selectedGroup.apt_name+" 주변 단지를 지도에 표시하는 중입니다…");
  for(const group of candidates){
    if(runId!==searchRunId){viewportRefreshSuspended=false;return;}
    if(shown>=MAX_VIEWPORT_MARKERS)break;
    let coord=cachedCoordinate(group);
    if(!coord){
      if(newGeocodes>=MAX_NEARBY_GEOCODES)continue;
      newGeocodes++;
      coord=await geocodeGroup(group,false);
    }
    if(!coord||haversine(centerCoord,coord)>NEARBY_RADIUS_KM)continue;
    ensureMapMarker(group,coord);
    shown++;
  }
  viewportRefreshSuspended=false;
  scheduleViewportMarkers();
  setStatus(selectedGroup.apt_name+"을 중심으로 주변 단지 "+shown+"개를 지도에 표시했습니다.");
}

function refreshResultButtons(){
  document.querySelectorAll("#results .result,#regionComplexList .result").forEach(card=>{
    const button=card.querySelector(".add-btn");
    const group=apartmentGroups.find(item=>item.key===card.dataset.key);
    button.disabled=false;
    button.textContent=group?(card.closest("#regionComplexList")?compactGraphAddLabel(group):graphAddLabel(group)):"그래프에 추가";
  });
}

function addGraphBoard(){
  if(graphBoards.length>=10){setStatus("그래프는 최대 10개까지 만들 수 있습니다.",true);return;}
  const board=newGraphBoard();
  graphBoards.push(board);
  activeGraphId=board.id;
  renderGraphBoards();
  markUnsaved("새 그래프가 만들어졌습니다. 이름을 바꾸고 단지를 추가해 보세요.");
}

function newGraphBoard(){
  return {id:makeId("graph"),name:"그래프 "+(graphBoards.length+1),periodYears:20,priceMode:"trade",chartWidth:100,chartHeight:0,economicWidth:100,series:[]};
}

function ensureInitialGraphBoard(){
  if(graphBoards.length)return activeBoard()||graphBoards[0];
  const board=newGraphBoard();
  graphBoards.push(board);activeGraphId=board.id;
  return board;
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

async function addSeries(group,requestedArea=null){
  const board=activeBoard()||ensureInitialGraphBoard();
  if(board.series.length>=10){setStatus("한 그래프에는 단지를 최대 10개까지 추가할 수 있습니다.",true);return false;}
  if(localApi){setStatus(group.apt_name+" 전체 평형과 실거래를 불러오는 중입니다.");await hydrateGroup(group);}
  if(!group.areas.length){setStatus(group.apt_name+"의 공식 실거래 평형이 아직 확인되지 않았습니다.",true);renderDetails(group,0);return false;}
  const requested=Number(requestedArea);
  const area=Number.isFinite(requested)&&group.areas.some(value=>Math.abs(Number(value)-requested)<.001)?requested:preferredArea(group);
  board.series.push({id:makeId("series"),key:group.key,area,supplyPyeong:Math.max(1,defaultSupplyPyeong(area)),color:graphColors[board.series.length%graphColors.length].value,lineStyle:"solid"});
  renderGraphBoards();
  renderDetails(group,area);
  focusGroup(group);
  refreshGraphAddButtons(group);
  setTimeout(()=>refreshGraphAddButtons(group),300);
  markUnsaved(group.apt_name+"을(를) ‘"+board.name+"’에 추가했습니다.");
  return true;
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
      periodYears:[1,3,5,10,20,0].includes(Number(board.periodYears))?Number(board.periodYears):20,
      priceMode:board.priceMode==="pyeong"?"pyeong":"trade",
      chartWidth:Math.min(200,Math.max(100,Number(board.chartWidth)||100)),
      chartHeight:Number(board.chartHeight)>=260&&Number(board.chartHeight)<=720?Number(board.chartHeight):0,
      economicWidth:Math.min(200,Math.max(100,Number(board.economicWidth)||100)),
      series:Array.isArray(board.series)?board.series.slice(0,10).filter(series=>apartmentGroups.some(g=>g.key===series.key)).map((series,seriesIndex)=>({
        id:String(series.id||makeId("series")),
        key:String(series.key),
        area:Number(series.area||0),
        supplyPyeong:Number(series.supplyPyeong||0),
        color:graphColors.some(color=>color.value===series.color)?series.color:graphColors[seriesIndex%graphColors.length].value,
        lineStyle:graphLineStyle(series.lineStyle).value
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
  byId("saveGraphsBtn").disabled=false;

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
  if(![1,3,5,10,20,0].includes(Number(board.periodYears))) board.periodYears=20;
  const periodOptions=[[1,"최근 1년"],[3,"최근 3년"],[5,"최근 5년"],[10,"최근 10년"],[20,"최근 20년"],[0,"전체 기간"]]
    .map(([value,label])=>'<option value="'+value+'" '+(Number(board.periodYears)===value?"selected":"")+'>'+label+'</option>').join("");
  const priceModeOptions=[["trade","실거래가"],["pyeong","공급평당가"]]
    .map(([value,label])=>'<option value="'+value+'" '+(board.priceMode===value?"selected":"")+'>'+label+'</option>').join("");
  const chartHeading=board.priceMode==="pyeong"?"아파트 공급평당가":"아파트 실거래가";
  const chartSubtitle=board.priceMode==="pyeong"?"입력한 공급면적 기준 · 만원/평":"선택 평형의 월별 중앙값 · 억원";
  board.chartWidth=Math.min(200,Math.max(100,Number(board.chartWidth)||100));
  board.chartHeight=Number(board.chartHeight)>=260&&Number(board.chartHeight)<=720?Number(board.chartHeight):0;
  board.economicWidth=Math.min(200,Math.max(100,Number(board.economicWidth)||100));
  const defaultChartHeight=window.matchMedia("(max-width:600px)").matches?320:390;
  const shownChartHeight=board.chartHeight||defaultChartHeight;
  const chartSizeStyle='width:'+board.chartWidth+'%;'+(board.chartHeight?'height:'+board.chartHeight+'px;':'');
  byId("graphBoards").innerHTML='<article class="graph-board" data-board-id="'+esc(board.id)+'" style="--economic-chart-width:'+board.economicWidth+'%">'+
    '<div class="graph-board-head"><div class="graph-head-fields"><div><label for="graphName">그래프 이름</label><input id="graphName" class="graph-name" maxlength="30" value="'+esc(board.name)+'"></div>'+
    '<div class="period-control"><label for="graphPeriod">그래프 표시 기간</label><select id="graphPeriod">'+periodOptions+'</select></div>'+
    '<div class="period-control"><label for="priceMode">그래프 기준</label><select id="priceMode">'+priceModeOptions+'</select></div></div>'+
    '<span>'+board.series.length+' / 10개 단지</span></div>'+
    '<div class="series-list">'+(board.series.length?board.series.map(series=>seriesControl(board,series)).join(""):'<div class="series-empty">검색한 단지의 ‘추가’ 버튼을 누르면 추가 순서에 맞는 색상으로 표시됩니다.</div>')+'</div>'+
    '<div class="timeline-guide" hidden aria-hidden="true"><span class="timeline-guide-date"></span><div class="timeline-guide-popup"></div></div>'+
    '<section class="stack-chart price-section"><div class="economic-title"><b>'+chartHeading+'</b><span>'+chartSubtitle+'</span></div>'+
    '<div class="graph-size-controls" aria-label="실거래 그래프 크기 조절">'+
      '<label>가로 <input id="graphWidth" type="range" min="100" max="200" step="10" value="'+board.chartWidth+'"><output id="graphWidthValue">'+board.chartWidth+'%</output></label>'+
      '<label>높이 <input id="graphHeight" type="range" min="260" max="720" step="10" value="'+shownChartHeight+'"><output id="graphHeightValue">'+shownChartHeight+'px</output></label>'+
      '<span class="graph-size-actions"><button id="alignEconomicCharts" type="button">경제지표 그래프 정렬</button><button id="resetAllGraphScales" type="button">그래프 배율 초기화</button></span></div>'+
    '<div class="price-chart-scroll"><div class="chart-wrap graph-chart-wrap" style="'+chartSizeStyle+'"><canvas class="price-chart" aria-label="'+esc(board.name)+' '+chartHeading+' 그래프"></canvas></div></div></section>'+
    '<p class="chart-help">그래프 위를 움직이거나 누르면 모든 지표의 같은 연월을 잇는 세로선이 표시됩니다. 숫자 세로선은 아래 주요 정책 발표 시점입니다.</p>'+
    '<div class="economic-stack stacked">'+
      '<section class="stack-chart economic-indicator"><div class="economic-title"><b>원·달러 환율</b><span>월평균 · 원/USD</span></div><div class="economic-chart"><canvas class="exchange-chart" aria-label="원달러 환율 그래프"></canvas></div><div class="indicator-description"><p><b>의미</b> 1달러를 사는 데 필요한 원화입니다.</p><p><b>해석</b> 상승하면 원화 약세로 수입물가 부담이 커질 수 있고, 하락하면 원화 강세로 외국인 자금과 수입비용에 유리할 수 있습니다.</p></div></section>'+
      '<section class="stack-chart economic-indicator"><div class="economic-title"><b>기준금리</b><span>한국·미국·일본 · %</span></div><div class="economic-chart"><canvas class="rate-chart" aria-label="한국 미국 일본 기준금리 비교 그래프"></canvas></div><div class="indicator-description"><p><b>의미</b> 각국 중앙은행 통화정책의 기준이 되는 금리입니다.</p><p><b>해석</b> 인상은 대출·부동산·주식 수요를 누르는 방향, 인하는 자금조달 부담을 낮추는 방향입니다. 국가 간 금리차는 환율에도 영향을 줍니다.</p></div></section>'+
      '<section class="stack-chart economic-indicator"><div class="economic-title"><b>통화량 M1·M2</b><span>한국 · 월평균 · 조원</span></div><div class="economic-chart"><canvas class="money-chart" aria-label="한국 통화량 M1 M2 그래프"></canvas></div><div class="indicator-description"><p><b>의미</b> M1은 바로 결제 가능한 돈, M2는 M1에 2년 미만 예·적금과 금융상품 등을 더한 넓은 통화량입니다.</p><p><b>해석</b> 증가 속도가 빨라지면 자산시장 유동성과 물가 상승 압력이 커질 수 있고, 둔화하면 소비·투자 여력이 약해질 수 있습니다.</p></div></section>'+
      '<section class="stack-chart economic-indicator"><div class="economic-title"><b>금·은·구리 시세</b><span>금·은 USD/온스 · 구리 USD/톤</span></div><div class="economic-chart"><canvas class="metal-chart" aria-label="금 은 구리 시세 그래프"></canvas></div><div class="indicator-description"><p><b>의미</b> 금은 안전자산·인플레이션 기대, 은과 구리는 산업 수요를 함께 반영합니다. 단위 차이 때문에 시작값 100으로 비교합니다.</p><p><b>해석</b> 금만 강하면 위험회피, 구리까지 함께 강하면 제조업·경기 회복 기대가 동반된 흐름인지 살펴볼 수 있습니다.</p></div></section>'+
      '<section class="stack-chart economic-indicator"><div class="economic-title"><b>원유가격</b><span>브렌트·WTI·두바이 · USD/배럴</span></div><div class="economic-chart oil-chart-wrap"><canvas class="oil-chart" aria-label="국제 원유가격 그래프"></canvas></div><div class="indicator-description"><p><b>의미</b> 유럽·미국·중동의 대표 원유 가격으로 세계 에너지 비용을 보여줍니다.</p><p><b>해석</b> 동반 상승은 물가와 운송·생산비 상승 요인이고, 급락은 수요 둔화 또는 공급 증가 신호일 수 있습니다.</p></div></section>'+
      '<section class="stack-chart economic-indicator"><div class="economic-title"><b>한국 채권금리</b><span>1년·10년·30년 · 월평균 %</span></div><div class="economic-chart"><canvas class="kr-bond-chart" aria-label="한국 채권금리 그래프"></canvas></div><div class="indicator-description"><p><b>의미</b> 만기별 국채 수익률은 시장이 보는 성장·물가·기준금리 경로를 반영합니다.</p><p><b>해석</b> 장기금리 상승은 주택담보대출과 자산가치 할인율 부담을 높입니다. 1년이 10·30년보다 높아지는 역전은 경기 둔화 우려로 해석되기도 합니다.</p></div></section>'+
      '<section class="stack-chart economic-indicator"><div class="economic-title"><b>미국 채권금리</b><span>1년·10년·30년 · 월평균 %</span></div><div class="economic-chart"><canvas class="us-bond-chart" aria-label="미국 채권금리 그래프"></canvas></div><div class="indicator-description"><p><b>의미</b> 세계 금융시장의 기준 할인율이며 달러와 글로벌 자금 흐름에 큰 영향을 줍니다.</p><p><b>해석</b> 전 구간 상승은 주식·가상자산·부동산의 할인율 부담, 하락은 금융여건 완화 요인입니다. 장단기 역전 여부도 함께 봅니다.</p></div></section>'+
      '<section class="stack-chart economic-indicator"><div class="economic-title"><b>일본 채권금리</b><span>1년·10년·30년 · 월평균 %</span></div><div class="economic-chart"><canvas class="jp-bond-chart" aria-label="일본 채권금리 그래프"></canvas></div><div class="indicator-description"><p><b>의미</b> 일본은행 정책 정상화와 엔화 자금조달 비용의 변화를 보여주는 일본 재무성 공식 만기별 수익률입니다.</p><p><b>해석</b> 상승하면 엔 캐리 자금 회수와 엔화 강세 압력이 커질 수 있습니다. 1·10·30년의 기울기로 단기 정책과 장기 물가 기대를 구분해 봅니다.</p></div></section>'+
      '<section class="stack-chart economic-indicator"><div class="economic-title"><b>주요 주식시장 비교</b><span>기간 시작값=100 · KOSPI·KOSDAQ·미국지수·반도체</span></div><div class="economic-chart market-chart-wrap"><canvas class="market-chart" aria-label="주요 주식시장 비교 그래프"></canvas></div><div class="indicator-description"><p><b>의미</b> 단위가 다른 주가지수를 선택 기간 첫 값 100으로 환산해 상승률을 비교합니다.</p><p><b>해석</b> 여러 지수가 함께 오르면 위험선호가 넓게 확산된 흐름이고, 반도체 등 일부 지수만 오르면 특정 업종 집중도가 높은 장세일 수 있습니다.</p></div></section>'+
      '<section class="stack-chart economic-indicator"><div class="economic-title"><b>비트코인</b><span>월말 · USD</span></div><div class="economic-chart"><canvas class="bitcoin-chart" aria-label="비트코인 가격 그래프"></canvas></div><div class="indicator-description"><p><b>의미</b> 대표 가상자산인 비트코인의 미국 달러 기준 월말 가격입니다.</p><p><b>해석</b> 유동성과 위험선호에 민감하지만 주식보다 변동성이 큽니다. 금리·달러·VIX와 함께 보고 단기 급등락을 일반 자산시장 흐름과 구분해야 합니다.</p></div></section>'+
      '<section class="stack-chart economic-indicator sentiment-indicator"><div class="economic-title"><b>시장 심리</b><span>VIX·공포탐욕지수(0~100)</span></div><div class="economic-chart"><canvas class="sentiment-chart" aria-label="VIX 공포탐욕지수 그래프"></canvas></div><div class="sentiment-reference-guide" aria-label="시장 심리 기준선 설명"><span class="vix"><b>VIX</b><em>20 안정·보통</em><em>30 공포</em><em>40 극단적 공포</em></span><span class="greed"><b>공포탐욕</b><em>25 극단적 공포</em><em>45 공포↔중립</em><em>55 중립↔탐욕</em><em>75 극단적 탐욕</em></span></div><div class="indicator-description"><p><b>의미</b> VIX는 미국 주식시장의 예상 변동성, 공포탐욕지수는 7개 심리지표를 0(극단적 공포)~100(극단적 탐욕)으로 합산한 값입니다.</p><p><b>해석</b> VIX 급등과 공포탐욕 하락이 겹치면 위험회피가 강해진 상태입니다. 극단값은 반전 가능성도 있지만 단독 매매 신호로 사용하면 안 됩니다.</p></div></section>'+
    '</div>'+
    '<div class="policy-panel"><div class="economic-title"><b>주요 정부 부동산 정책</b><span>번호를 누르면 아래에 상세 내용이 표시됩니다</span></div><ol class="policy-list"></ol><div class="policy-detail" aria-live="polite"><p>선택한 기간의 정책을 누르면 핵심 요약이 여기에 표시됩니다.</p></div></div>'+
    '<section class="tax-estimator" aria-labelledby="taxEstimatorTitle">'+
      '<div class="tax-estimator-head"><div><b id="taxEstimatorTitle">주택 세금 예상 계산</b><span>2023~2027년 · 현행 세율 기준 단순 추정</span></div><strong class="tax-current-total">—</strong></div>'+
      '<div class="tax-property-picker">'+
        '<label>아파트·단지 검색<small>단지와 평형을 고른 뒤 동·호별 공동주택 공시가격을 확인하세요.</small><input class="tax-property-search" type="search" placeholder="아파트명 또는 지역 입력" autocomplete="off"></label>'+
        '<div class="tax-property-results" hidden></div>'+
        '<div class="tax-property-selected" hidden><div><b class="tax-selected-name"></b><small class="tax-selected-address"></small></div><label>평형 선택<select class="tax-area-select"></select></label><label>동<input class="tax-building" type="text" inputmode="numeric" placeholder="예: 101"></label><label>호<input class="tax-unit" type="text" inputmode="numeric" placeholder="예: 1203"></label><a class="tax-official-link" href="https://www.realtyprice.kr/notice/m/gss/search.do" target="_blank" rel="noopener">공식 공시가격 조회 ↗</a><p class="tax-property-note"></p></div>'+
      '</div>'+
      '<div class="tax-form">'+
        '<label>주택 취득가액<small>취득세 계산 기준</small><span><input class="tax-purchase-price" type="number" min="0" max="10000" step="0.1" value="10"><em>억원</em></span></label>'+
        '<label>2026년 공동주택 공시가격<small>동·호별 공식값 · 보유주택 합계</small><span><input class="tax-official-price" type="number" min="0" max="10000" step="0.1" placeholder="공식값 입력"><em>억원</em></span></label>'+
        '<label>취득 후 주택 수<small>세대 기준</small><select class="tax-home-count"><option value="1">1주택</option><option value="2">2주택</option><option value="3">3주택</option><option value="4">4주택 이상</option></select></label>'+
        '<label>취득연도<small>취득세는 선택 연도만</small><select class="tax-acquisition-year"><option value="2022">2022년 이전</option><option value="2023">2023년</option><option value="2024">2024년</option><option value="2025">2025년</option><option value="2026">2026년</option><option value="2027">2027년</option></select></label>'+
        '<label class="tax-check"><input class="tax-adjusted-area" type="checkbox"><span><b>조정대상지역 취득</b><small>다주택 취득세 중과 판단</small></span></label>'+
        '<label class="tax-check"><input class="tax-urban-area" type="checkbox" checked><span><b>도시지역</b><small>도시지역분 재산세 포함</small></span></label>'+
      '</div>'+
      '<div class="tax-growth-control"><div><label for="taxGrowthRange">공시가격 연 증감률</label><button class="tax-growth-help" type="button" title="2026년 공시가격을 기준으로 이전 연도는 역산하고 2027년은 같은 비율로 예측합니다." aria-label="공시가격 증감률 계산 설명">?</button></div><div><input id="taxGrowthRange" class="tax-growth-range" type="range" min="-30" max="50" step="1" value="20"><input class="tax-growth-number" type="number" min="-30" max="50" step="1" value="20" aria-label="공시가격 연 증감률 숫자 입력"><output class="tax-growth-value">20%</output></div></div>'+
      '<div class="tax-summary" aria-live="polite"></div>'+
      '<div class="tax-table-wrap"><table class="tax-table"><thead><tr><th>연도</th><th>예상 공시가격</th><th>재산세</th><th>지방교육세</th><th>도시지역분</th><th>종합부동산세</th><th>농어촌특별세</th><th>보유세 합계</th><th>취득세</th></tr></thead><tbody></tbody></table></div>'+
      '<div class="tax-chart-wrap"><canvas class="tax-chart" aria-label="연도별 예상 보유세 그래프"></canvas></div>'+
      '<details class="tax-method"><summary>계산 기준과 꼭 확인할 점</summary><ul><li>아파트의 과세 기준은 토지의 공시지가가 아니라 동·호별 공동주택 공시가격입니다. 단지·평형 검색은 대상을 찾기 위한 기능이며, 공식 공시가격은 부동산공시가격 알리미에서 동·호까지 확인해 입력해야 합니다.</li><li>2023~2027년 공시가격은 입력한 2026년 값을 같은 증감률로 역산·예측합니다. 과거 실제 공시가격을 입력하는 방식이 아니므로 비교용입니다.</li><li>재산세, 지방교육세(재산세의 20%), 선택 시 도시지역분을 각각 계산합니다. 여러 주택의 합계 공시가격을 하나의 주택처럼 계산하므로 실제 고지액과 차이가 날 수 있습니다.</li><li>종합부동산세는 1주택 12억원·일반 9억원 기본공제와 공정시장가액비율 60%를 적용한 공제 전 추정치이며 농어촌특별세는 별도 항목으로 표시합니다. 재산세 중복분, 고령자·장기보유 세액공제, 공동명의·법인·특례는 반영하지 않습니다.</li><li>취득세는 본세만 표시하며 취득 관련 지방교육세·농어촌특별세, 생애최초·일시적 2주택·저가주택 등 감면과 예외는 주택 면적과 취득 사유가 더 필요해 계산에 포함하지 않습니다.</li></ul><p>이 결과는 세무 신고용이 아닌 모의 계산입니다. 실제 계약·신고 전에는 부동산공시가격 알리미의 공식 공시가격과 관할 지방자치단체 또는 세무 전문가의 계산을 확인하세요.</p></details>'+
    '</section>'+
    '<p class="economic-sources">출처: <a href="https://fred.stlouisfed.org/" target="_blank" rel="noopener">FRED</a> · <a href="https://ecos.bok.or.kr/" target="_blank" rel="noopener">한국은행 ECOS</a> · <a href="https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/" target="_blank" rel="noopener">일본 재무성</a> · <a href="https://finance.yahoo.com/markets/" target="_blank" rel="noopener">Yahoo Finance</a> · <a href="https://www.cnn.com/markets/fear-and-greed" target="_blank" rel="noopener">CNN Fear &amp; Greed</a> · 국토교통부·관계부처 발표자료. 월이 끝나지 않은 값은 잠정치이며, 대용 지표는 그래프 설명에 표시합니다.</p></article>';

  const nameInput=byId("graphName");
  nameInput.addEventListener("input",e=>{
    board.name=e.target.value.slice(0,30)||"이름 없는 그래프";
    const activeTab=byId("graphTabs").querySelector('[data-board-id="'+CSS.escape(board.id)+'"]');
    if(activeTab) activeTab.textContent=(graphBoards.indexOf(board)+1)+". "+board.name;
    markUnsaved("그래프 이름을 변경했습니다.");
  });
  byId("graphPeriod").addEventListener("change",e=>{
    board.periodYears=Number(e.target.value);
    renderGraphBoards();
    markUnsaved("그래프 표시 기간을 변경했습니다.");
  });
  byId("priceMode").addEventListener("change",e=>{
    board.priceMode=e.target.value==="pyeong"?"pyeong":"trade";
    renderGraphBoards();
    markUnsaved(board.priceMode==="pyeong"?"공급평당가 그래프로 전환했습니다. 공급면적을 확인해 주세요.":"실거래가 그래프로 전환했습니다.");
  });
  const graphWidthInput=byId("graphWidth"),graphHeightInput=byId("graphHeight"),graphChartWrap=byId("graphBoards").querySelector(".graph-chart-wrap");
  const resizePriceChart=()=>requestAnimationFrame(()=>charts.get(board.id+"-price")?.resize());
  graphWidthInput.addEventListener("input",e=>{
    board.chartWidth=Math.min(200,Math.max(100,Number(e.target.value)||100));
    graphChartWrap.style.width=board.chartWidth+"%";byId("graphWidthValue").textContent=board.chartWidth+"%";resizePriceChart();
  });
  graphWidthInput.addEventListener("change",()=>markUnsaved("실거래 그래프의 가로 크기를 변경했습니다."));
  graphHeightInput.addEventListener("input",e=>{
    board.chartHeight=Math.min(720,Math.max(260,Number(e.target.value)||defaultChartHeight));
    graphChartWrap.style.height=board.chartHeight+"px";byId("graphHeightValue").textContent=board.chartHeight+"px";resizePriceChart();
  });
  graphHeightInput.addEventListener("change",()=>markUnsaved("실거래 그래프의 높이를 변경했습니다."));
  byId("alignEconomicCharts").addEventListener("click",()=>{
    board.economicWidth=board.chartWidth;renderGraphBoards();markUnsaved("경제지표 그래프를 실거래 그래프의 가로 배율에 맞췄습니다.");
  });
  byId("resetAllGraphScales").addEventListener("click",()=>{
    graphBoards.forEach(item=>{item.chartWidth=100;item.chartHeight=0;item.economicWidth=100;});
    renderGraphBoards();markUnsaved("모든 그래프의 가로·높이·경제지표 배율을 기본값으로 되돌렸습니다.");
  });
  byId("graphBoards").querySelectorAll(".series-item").forEach(card=>{
    const series=board.series.find(item=>item.id===card.dataset.seriesId);
    card.querySelector(".area-select").addEventListener("change",e=>{
      series.area=Number(e.target.value);series.supplyPyeong=Math.max(1,defaultSupplyPyeong(series.area));renderGraphBoards();markUnsaved("평형을 변경했습니다. 공급면적 추정값을 확인해 주세요.");
      const group=apartmentGroups.find(g=>g.key===series.key);if(group)renderDetails(group,series.area);
    });
    const supplyInput=card.querySelector(".supply-input");
    if(supplyInput)supplyInput.addEventListener("change",e=>{series.supplyPyeong=Math.max(1,Number(e.target.value)||1);renderGraphBoards();markUnsaved("공급면적을 변경했습니다.");});
    card.querySelector(".color-select").addEventListener("change",e=>{
      series.color=e.target.value;renderGraphBoards();markUnsaved("그래프 색상을 변경했습니다.");
    });
    card.querySelector(".line-style-select").addEventListener("change",e=>{
      series.lineStyle=graphLineStyle(e.target.value).value;renderGraphBoards();markUnsaved("그래프 선 종류를 변경했습니다.");
    });
    card.querySelector(".remove-btn").addEventListener("click",()=>removeSeries(board.id,series.id));
  });
  renderBoardChart(board,byId("graphBoards").querySelector(".graph-board"));
  refreshResultButtons();
}

function seriesControl(board,series){
  const group=apartmentGroups.find(g=>g.key===series.key);
  if(!group) return "";
  const areaOptions=group.areas.length?group.areas.map(area=>'<option value="'+area+'" '+(Number(area)===Number(series.area)?"selected":"")+'>'+areaComparisonLabel(area,Number(area)===Number(series.area)?series.supplyPyeong:null)+'</option>').join(""):'<option value="0">평형 자료 없음</option>';
  const colorOptions=graphColors.map(color=>'<option value="'+color.value+'" '+(color.value===series.color?"selected":"")+'>'+color.name+'</option>').join("");
  const lineStyleOptions=graphLineStyles.map(style=>'<option value="'+style.value+'" '+(style.value===graphLineStyle(series.lineStyle).value?"selected":"")+'>'+style.name+'</option>').join("");
  const matchingSeries=board.series.filter(item=>item.key===series.key);
  const duplicateOrdinal=matchingSeries.findIndex(item=>item.id===series.id)+1;
  return '<div class="series-item" data-series-id="'+esc(series.id)+'"><i class="series-color" style="background:'+esc(series.color)+'"></i>'+
    '<div class="series-name"><b>'+esc(group.apt_name)+'</b><span>'+esc(group.region_name+" "+group.dong+" · 동일 단지 "+duplicateOrdinal+"번째 / "+matchingSeries.length+"개")+'</span></div>'+
    '<select class="area-select" aria-label="'+esc(group.apt_name)+' 평형 선택">'+areaOptions+'</select>'+
    '<select class="color-select" aria-label="'+esc(group.apt_name)+' 색상 선택">'+colorOptions+'</select>'+
    '<select class="line-style-select" aria-label="'+esc(group.apt_name)+' 선 종류 선택">'+lineStyleOptions+'</select>'+
    (board.priceMode==="pyeong"?'<label class="supply-control">공급면적(평)<input class="supply-input" type="number" min="1" step="0.1" value="'+fmt(Number(series.supplyPyeong)||Math.max(1,defaultSupplyPyeong(series.area)))+'" aria-label="'+esc(group.apt_name)+' 공급면적 평수"><small>최초값은 전용률 75% 추정</small></label>':"")+
    '<button class="remove-btn" type="button" aria-label="'+esc(group.apt_name)+' 그래프에서 삭제">삭제</button></div>';
}

function monthRange(start,end){
  if(!start||!end) return [];
  const months=[],cursor=new Date(start+"-01T00:00:00Z"),last=new Date(end+"-01T00:00:00Z");
  while(cursor<=last){months.push(cursor.toISOString().slice(0,7));cursor.setUTCMonth(cursor.getUTCMonth()+1);}
  return months;
}
function rateAtMonth(month){
  let value=null;
  for(const item of economicContext.base_rates||[]){if(String(item.date).slice(0,7)<=month)value=Number(item.rate);else break;}
  return value;
}
function valueMap(items,valueKey){
  return new Map((items||[]).map(item=>[String(item.month||item.date||"").slice(0,7),Number(item[valueKey])]));
}
function latestDatasetPoint(labels,dataset){
  const values=Array.isArray(dataset?.data)?dataset.data:[];
  for(let index=values.length-1;index>=0;index--){
    const raw=values[index];
    if(raw===null||raw===undefined||raw==="")continue;
    const value=Number(raw);
    if(Number.isFinite(value))return {index,value,date:String(labels[index]||"")};
  }
  return null;
}
function renderLatestValues(chart,valueFormatter,confirmedOn=""){
  const section=chart?.canvas?.closest?.(".stack-chart");
  if(!section)return;
  let row=section.querySelector(":scope > .latest-values");
  if(!row){
    row=document.createElement("div");
    row.className="latest-values";
    row.setAttribute("aria-label","그래프 최신값");
    const title=section.querySelector(":scope > .economic-title");
    if(title)title.insertAdjacentElement("afterend",row);else section.prepend(row);
  }
  const labels=chart.data?.labels||[];
  const chips=(chart.data?.datasets||[]).map(dataset=>{
    const point=latestDatasetPoint(labels,dataset);
    if(!point)return "";
    const color=Array.isArray(dataset.borderColor)?dataset.borderColor.at(-1):dataset.borderColor;
    const formatted=valueFormatter(point.value,dataset,point.index);
    const exactDate=String(dataset.observationDates?.[point.index]||confirmedOn||"").slice(0,10);
    const dateText="기준 "+point.date+(exactDate?" · 확인 "+exactDate:"");
    return '<span class="latest-value-chip" style="--latest-color:'+esc(String(color||"#475467"))+'">'+
      '<i aria-hidden="true"></i><b>'+esc(dataset.label||"지표")+'</b><strong>'+esc(formatted)+'</strong><small>'+esc(dateText)+'</small></span>';
  }).filter(Boolean);
  row.innerHTML='<span class="latest-values-label">최신값</span>'+(chips.length?chips.join(""):'<span class="latest-values-empty">표시할 최신 자료가 없습니다.</span>');
}
function policyRecord(item,index){
  if(typeof item==="string") return {date:"",title:item,summary:item,before:[],after:[],impact:"",url:"",sourceIndex:index};
  const date=String(item.date||""),detail=POLICY_DETAILS[date]||{};
  return {date,title:String(item.title||"정책 발표"),summary:String(item.summary||"공식 발표자료의 상세 내용을 확인해 주세요."),before:Array.isArray(detail.before)?detail.before:[],after:Array.isArray(detail.after)?detail.after:[],impact:String(detail.impact||""),url:String(detail.url||item.url||""),sourceIndex:index};
}
function periodBounds(board,seriesRows){
  const tradeMonths=seriesRows.flatMap(item=>item.points.map(point=>point.month));
  const economicMonths=[
    ...(economicContext.exchange_rates||[]).map(item=>String(item.month||"").slice(0,7)),
    ...(economicContext.us_policy_rates||[]).map(item=>String(item.month||"").slice(0,7)),
    ...(economicContext.japan_policy_rates||[]).map(item=>String(item.month||"").slice(0,7)),
    ...(economicContext.money_supply||[]).map(item=>String(item.month||"").slice(0,7)),
    ...(economicContext.metal_prices||[]).map(item=>String(item.month||"").slice(0,7)),
    ...(economicContext.bond_yields||[]).map(item=>String(item.month||"").slice(0,7)),
    ...(economicContext.oil_prices||[]).map(item=>String(item.month||"").slice(0,7)),
    ...(economicContext.market_indices||[]).map(item=>String(item.month||"").slice(0,7)),
    ...(economicContext.fear_greed||[]).map(item=>String(item.month||"").slice(0,7)),
    ...(economicContext.base_rates||[]).map(item=>String(item.date||"").slice(0,7))
  ].filter(Boolean);
  const allMonths=[...tradeMonths,...economicMonths].filter(Boolean).sort();
  if(!allMonths.length) return {start:"",end:""};
  const end=allMonths[allMonths.length-1];
  if(!Number(board.periodYears)) return {start:allMonths[0],end};
  const cursor=new Date(end+"-01T00:00:00Z");
  cursor.setUTCMonth(cursor.getUTCMonth()-(Number(board.periodYears)*12)+1);
  return {start:cursor.toISOString().slice(0,7),end};
}

const policyMarkerPlugin={
  id:"policyMarkers",
  afterDatasetsDraw(chart,args,options){
    const items=options.items||[];
    chart.$policyMarkers=[];
    if(!items.length||!chart.scales.x)return;
    const ctx=chart.ctx,area=chart.chartArea;
    ctx.save();
    items.forEach((item,index)=>{
      const labelIndex=chart.data.labels.indexOf(String(item.date).slice(0,7));
      if(labelIndex<0)return;
      const x=chart.scales.x.getPixelForValue(labelIndex);
      chart.$policyMarkers.push({item,index,x,y:area.top+8});
      ctx.strokeStyle="rgba(180,83,9,.5)";ctx.setLineDash([3,4]);ctx.lineWidth=.8;
      ctx.beginPath();ctx.moveTo(x,area.top);ctx.lineTo(x,area.bottom);ctx.stroke();
      ctx.setLineDash([]);ctx.fillStyle="#92400e";ctx.font="bold 8px system-ui";
      ctx.fillText(String(index+1),Math.min(x+2,area.right-11),area.top+10);
    });
    ctx.restore();
  }
};

const referenceLinesPlugin={
  id:"referenceLines",
  beforeDatasetsDraw(chart,args,options){
    const lines=options.lines||[],area=chart.chartArea,ctx=chart.ctx;
    if(!area||!lines.length)return;
    ctx.save();
    lines.forEach(line=>{
      const scale=chart.scales[line.axis||"y"];
      if(!scale)return;
      const y=scale.getPixelForValue(Number(line.value));
      if(!Number.isFinite(y)||y<area.top||y>area.bottom)return;
      ctx.strokeStyle=line.color||"rgba(71,84,103,.22)";
      ctx.lineWidth=line.width||1;
      ctx.setLineDash(line.dash||[4,4]);
      ctx.beginPath();ctx.moveTo(area.left,y);ctx.lineTo(area.right,y);ctx.stroke();
      ctx.setLineDash([]);
      if(line.label){
        const onRight=line.side==="right";
        ctx.font="600 9px system-ui";
        ctx.textAlign=onRight?"right":"left";ctx.textBaseline="bottom";
        ctx.fillStyle=line.textColor||"rgba(71,84,103,.62)";
        ctx.fillText(String(line.label),onRight?area.right-4:area.left+4,Math.max(area.top+10,y-3));
      }
    });
    ctx.restore();
  }
};
Chart.register(referenceLinesPlugin);

function policyHtml(items){
  if(!items.length)return '<li class="policy-empty">선택한 기간 안에 표시할 주요 정책이 없습니다.</li>';
  return items.map((item,index)=>'<li><button type="button" class="policy-item '+(index===0?'active':'')+'" data-policy-index="'+index+'" title="'+esc(item.date+' · '+item.title)+'" aria-label="'+(index+1)+'번 정책 '+esc(item.date)+' '+esc(item.title)+'"><span class="policy-number" aria-hidden="true">'+(index+1)+'</span></button></li>').join("");
}
function policyChangeColumn(title,items,className){
  return '<section class="policy-change '+className+'"><h4>'+esc(title)+'</h4><ul>'+items.map(text=>'<li>'+esc(text)+'</li>').join("")+'</ul></section>';
}
function policyDetailHtml(item,includeClose=false){
  if(!item)return "<p>선택한 기간의 정책을 누르면 핵심 요약이 여기에 표시됩니다.</p>";
  return (includeClose?'<button type="button" class="policy-popup-close" aria-label="정책 팝업 닫기">×</button>':"")+
    '<div class="policy-detail-head"><time>'+esc(item.date)+'</time><b>'+esc(item.title)+'</b></div>'+
    '<p class="policy-summary">'+esc(item.summary)+'</p>'+
    '<div class="policy-change-grid">'+policyChangeColumn("정책 이전",item.before,"before")+policyChangeColumn("정책 이후",item.after,"after")+'</div>'+
    (item.impact?'<p class="policy-impact"><strong>시장 해석</strong>'+esc(item.impact)+'</p>':"")+
    (item.url?'<a href="'+esc(item.url)+'" target="_blank" rel="noopener">공식 발표자료 보기</a>':"");
}
function showPolicyDetail(container,item){
  const detail=container.querySelector(".policy-detail");
  detail.innerHTML=policyDetailHtml(item);
}
let policyHoverTimer=null,policyHideTimer=null,policyPopupLocked=false;
function ensurePolicyPopup(){
  let popup=byId("policyPopup");
  if(popup)return popup;
  popup=document.createElement("aside");
  popup.id="policyPopup";popup.className="policy-popup";popup.hidden=true;
  popup.setAttribute("role","dialog");popup.setAttribute("aria-label","주요 부동산 정책 변경사항");
  popup.addEventListener("mouseenter",()=>clearTimeout(policyHideTimer));
  popup.addEventListener("mouseleave",()=>schedulePolicyPopupHide());
  document.body.appendChild(popup);
  return popup;
}
function positionPolicyPopup(popup,clientX,clientY){
  popup.style.left="12px";popup.style.top="12px";
  const rect=popup.getBoundingClientRect(),gap=14;
  const left=Math.max(12,Math.min(window.innerWidth-rect.width-12,clientX+gap));
  const top=Math.max(12,Math.min(window.innerHeight-rect.height-12,clientY+gap));
  popup.style.left=left+"px";popup.style.top=top+"px";
}
function showPolicyPopup(item,clientX,clientY,locked=false){
  clearTimeout(policyHideTimer);
  const popup=ensurePolicyPopup();
  policyPopupLocked=locked;
  popup.innerHTML=policyDetailHtml(item,true);
  popup.hidden=false;
  positionPolicyPopup(popup,clientX,clientY);
  popup.querySelector(".policy-popup-close").addEventListener("click",()=>hidePolicyPopup(true));
}
function hidePolicyPopup(force=false){
  if(policyPopupLocked&&!force)return;
  clearTimeout(policyHoverTimer);clearTimeout(policyHideTimer);
  const popup=byId("policyPopup");if(popup)popup.hidden=true;
  policyPopupLocked=false;
}
function schedulePolicyPopupHide(){
  clearTimeout(policyHideTimer);
  policyHideTimer=setTimeout(()=>hidePolicyPopup(false),260);
}
function bindPolicyMarkerHover(chart,container){
  const canvas=chart.canvas;
  let activeIndex=-1,lastClient={x:0,y:0};
  const markerAt=event=>{
    const rect=canvas.getBoundingClientRect();
    const x=(event.clientX-rect.left)*(chart.width/rect.width);
    const y=(event.clientY-rect.top)*(chart.height/rect.height);
    if(y<chart.chartArea.top-5||y>chart.chartArea.top+21)return null;
    return (chart.$policyMarkers||[]).reduce((best,marker)=>Math.abs(marker.x-x)<=11&&(!best||Math.abs(marker.x-x)<Math.abs(best.x-x))?marker:best,null);
  };
  const clearActive=()=>{
    activeIndex=-1;canvas.style.cursor="";clearTimeout(policyHoverTimer);
    schedulePolicyPopupHide();
  };
  canvas.addEventListener("mousemove",event=>{
    const marker=markerAt(event);lastClient={x:event.clientX,y:event.clientY};
    if(!marker){clearActive();return;}
    canvas.style.cursor="pointer";
    if(activeIndex===marker.index)return;
    activeIndex=marker.index;clearTimeout(policyHoverTimer);
    policyHoverTimer=setTimeout(()=>{
      showPolicyDetail(container,marker.item);
      showPolicyPopup(marker.item,lastClient.x,lastClient.y,false);
    },1000);
  });
  canvas.addEventListener("mouseleave",clearActive);
  canvas.addEventListener("click",event=>{
    const marker=markerAt(event);if(!marker)return;
    clearTimeout(policyHoverTimer);showPolicyDetail(container,marker.item);
    showPolicyPopup(marker.item,event.clientX,event.clientY,true);
  });
}

function bindTimelineGuide(container,timelineCharts,labels){
  const guide=container.querySelector(".timeline-guide"),label=guide?.querySelector(".timeline-guide-date"),popup=guide?.querySelector(".timeline-guide-popup");
  if(!guide||!labels.length||!timelineCharts.length)return;
  const indicatorValue=(chart,index,suffix,datasetIndex=0)=>{
    const value=Number(chart?.data?.datasets?.[datasetIndex]?.data?.[index]);
    return Number.isFinite(value)?fmt(value)+suffix:"—";
  };
  const popupHtml=index=>'<b>경제지표</b>'+
    '<span><em>원·달러</em><strong>'+indicatorValue(timelineCharts[1],index,"원")+'</strong></span>'+
    '<span><em>한·미·일 금리</em><strong>'+indicatorValue(timelineCharts[2],index,"%")+' · '+indicatorValue(timelineCharts[2],index,"%",1)+' · '+indicatorValue(timelineCharts[2],index,"%",2)+'</strong></span>'+
    '<span><em>M1·M2</em><strong>'+indicatorValue(timelineCharts[3],index,"조원")+' · '+indicatorValue(timelineCharts[3],index,"조원",1)+'</strong></span>'+
    '<span><em>10년 국고채</em><strong>'+indicatorValue(timelineCharts[4],index,"%")+'</strong></span>'+
    '<span><em>브렌트유</em><strong>'+indicatorValue(timelineCharts[5],index,"달러")+'</strong></span>';
  const hide=()=>{guide.hidden=true;};
  const show=(sourceChart,clientX)=>{
    const sourceRect=sourceChart.canvas.getBoundingClientRect();
    const sourceX=(clientX-sourceRect.left)*(sourceChart.width/sourceRect.width);
    if(sourceX<sourceChart.chartArea.left||sourceX>sourceChart.chartArea.right)return hide();
    const rawIndex=Number(sourceChart.scales.x.getValueForPixel(sourceX));
    const index=Math.max(0,Math.min(labels.length-1,Math.round(rawIndex)));
    const anchor=timelineCharts[0],last=timelineCharts[timelineCharts.length-1];
    const containerRect=container.getBoundingClientRect();
    const anchorRect=anchor.canvas.getBoundingClientRect(),firstEconomicRect=timelineCharts[1]?.canvas?.getBoundingClientRect(),lastRect=last.canvas.getBoundingClientRect();
    const anchorScaleX=anchorRect.width/anchor.width,anchorScaleY=anchorRect.height/anchor.height,lastScaleY=lastRect.height/last.height;
    const left=anchorRect.left-containerRect.left+anchor.scales.x.getPixelForValue(index)*anchorScaleX;
    const top=anchorRect.top-containerRect.top+anchor.chartArea.top*anchorScaleY;
    const bottom=lastRect.top-containerRect.top+last.chartArea.bottom*lastScaleY;
    guide.style.left=left+"px";guide.style.top=top+"px";guide.style.height=Math.max(0,bottom-top)+"px";
    label.textContent=labels[index];popup.innerHTML=popupHtml(index);
    const gapTop=(anchorRect.bottom-containerRect.top)+30;
    const gapBottom=firstEconomicRect?(firstEconomicRect.top-containerRect.top)-8:gapTop+110;
    const popupTop=Math.max(10,gapTop-top+Math.max(0,(gapBottom-gapTop-96)/2));
    guide.style.setProperty("--timeline-popup-top",popupTop+"px");
    guide.classList.remove("is-left");guide.hidden=false;
    popup.style.right="auto";
    const popupWidth=popup.getBoundingClientRect().width;
    const popupLeft=Math.max(8,Math.min(containerRect.width-popupWidth-8,left+10));
    popup.style.left=(popupLeft-left)+"px";
  };
  timelineCharts.forEach(chart=>{
    chart.canvas.addEventListener("mousemove",event=>show(chart,event.clientX));
    chart.canvas.addEventListener("touchstart",event=>{const touch=event.touches[0];if(touch)show(chart,touch.clientX);},{passive:true});
  });
  container.addEventListener("mouseleave",hide);
}

function bindEconomicChartAlignment(container,timelineCharts){
  const priceScroll=container.querySelector(".price-chart-scroll");
  const economicWraps=[...container.querySelectorAll(".economic-indicator .economic-chart")];
  if(!priceScroll||!economicWraps.length)return;
  const sync=()=>{
    const shift=Math.max(0,priceScroll.scrollLeft);
    economicWraps.forEach(wrap=>{wrap.style.transform="translateX("+(-shift)+"px)";});
  };
  priceScroll.addEventListener("scroll",sync,{passive:true});
  requestAnimationFrame(()=>{
    timelineCharts.slice(1).forEach(chart=>chart.resize());
    sync();
  });
}

function taxMarginalAmount(base,segments){
  let remaining=Math.max(0,base),previous=0,total=0;
  for(const [limit,rate] of segments){
    const ceiling=Number.isFinite(limit)?limit:Infinity;
    const taxable=Math.max(0,Math.min(remaining,ceiling-previous));
    total+=taxable*rate;remaining-=taxable;previous=ceiling;
    if(remaining<=0)break;
  }
  return Math.max(0,total);
}

function estimatedPropertyTax(officialPrice,homeCount,isUrban){
  const oneHome=homeCount===1;
  const ratio=oneHome?(officialPrice<=300000000?.43:officialPrice<=600000000?.44:.45):.60;
  const base=officialPrice*ratio;
  const general=[[60000000,.001],[150000000,.0015],[300000000,.0025],[Infinity,.004]];
  const special=[[60000000,.0005],[150000000,.001],[300000000,.002],[Infinity,.0035]];
  const main=taxMarginalAmount(base,oneHome&&officialPrice<=900000000?special:general);
  const localEducation=main*.20;
  const urban=isUrban?base*.0014:0;
  return {main,localEducation,urban,total:main+localEducation+urban,ratio};
}

function estimatedComprehensiveTax(officialPrice,homeCount){
  const deduction=(homeCount===1?12:9)*100000000;
  const base=Math.max(0,officialPrice-deduction)*.60;
  const normal=[[300000000,.005],[600000000,.007],[1200000000,.01],[2500000000,.013],[5000000000,.015],[9400000000,.02],[Infinity,.027]];
  const multi=[[300000000,.005],[600000000,.007],[1200000000,.01],[2500000000,.02],[5000000000,.03],[9400000000,.04],[Infinity,.05]];
  const main=taxMarginalAmount(base,homeCount>=3?multi:normal);
  const rural=main*.20;
  return {main,rural,total:main+rural,base,deduction};
}

function estimatedAcquisitionTax(price,homeCount,isAdjusted){
  const eok=price/100000000;
  let rate;
  if((isAdjusted&&homeCount===2)||(!isAdjusted&&homeCount===3))rate=.08;
  else if((isAdjusted&&homeCount>=3)||(!isAdjusted&&homeCount>=4))rate=.12;
  else if(eok<=6)rate=.01;
  else if(eok<=9)rate=(eok*2/3-3)/100;
  else rate=.03;
  return {rate,total:Math.max(0,price*rate)};
}

function taxWon(value){
  if(!Number.isFinite(value)||value<=0)return "없음";
  const man=Math.round(value/10000);
  return man>=10000?fmt(man/10000)+"억원":fmt(man)+"만원";
}

function bindTaxEstimator(board,container){
  const estimator=container.querySelector(".tax-estimator");
  if(!estimator)return;
  const purchase=estimator.querySelector(".tax-purchase-price"),official=estimator.querySelector(".tax-official-price");
  const homeCount=estimator.querySelector(".tax-home-count"),acquisitionYear=estimator.querySelector(".tax-acquisition-year");
  const adjusted=estimator.querySelector(".tax-adjusted-area"),urban=estimator.querySelector(".tax-urban-area");
  const growthRange=estimator.querySelector(".tax-growth-range"),growthNumber=estimator.querySelector(".tax-growth-number"),growthValue=estimator.querySelector(".tax-growth-value");
  const propertySearch=estimator.querySelector(".tax-property-search"),propertyResults=estimator.querySelector(".tax-property-results"),propertySelected=estimator.querySelector(".tax-property-selected"),areaSelect=estimator.querySelector(".tax-area-select"),propertyNote=estimator.querySelector(".tax-property-note");
  const clampGrowth=value=>Math.min(50,Math.max(-30,Number(value)||0));
  let selectedProperty=null;
  const latestAreaPrice=(group,area)=>{
    const trades=group.trades.filter(row=>Math.abs(Number(row.area_m2)-Number(area))<.01).sort((a,b)=>String(a.trade_date).localeCompare(String(b.trade_date)));
    if(trades.length)return Number(trades[trades.length-1].price_eok)||0;
    const history=group.history.filter(row=>Math.abs(Number(row.area_m2)-Number(area))<.01).sort((a,b)=>String(a.month).localeCompare(String(b.month)));
    return history.length?Number(history[history.length-1].median_price_eok)||0:0;
  };
  const applySelectedArea=()=>{
    if(!selectedProperty)return;
    const area=Number(areaSelect.value),latestPrice=latestAreaPrice(selectedProperty,area);
    if(latestPrice)purchase.value=latestPrice;
    official.value="";
    propertyNote.textContent=(latestPrice?"최근 실거래 "+fmt(latestPrice)+"억원을 취득가액에 넣었습니다. ":"")+"공시가격은 같은 평형이라도 동·호에 따라 다르므로 공식 조회 후 입력하세요.";
    render();
  };
  const chooseProperty=async key=>{
    const group=apartmentGroups.find(item=>item.key===key);
    if(!group)return;
    await hydrateGroup(group);selectedProperty=group;
    propertySearch.value=group.apt_name;propertyResults.hidden=true;propertyResults.innerHTML="";
    propertySelected.hidden=false;estimator.querySelector(".tax-selected-name").textContent=group.apt_name;estimator.querySelector(".tax-selected-address").textContent=searchAddressOf(group).value;
    const areas=group.areas.length?group.areas:[Number(group.latest?.area_m2)].filter(Boolean);
    areaSelect.innerHTML=areas.map(area=>'<option value="'+area+'">'+esc(areaComparisonLabel(area))+'</option>').join("")||'<option value="">평형 정보 없음</option>';
    applySelectedArea();
  };
  const showPropertyMatches=()=>{
    const query=propertySearch.value.trim();
    if(!query){propertyResults.hidden=true;propertyResults.innerHTML="";return;}
    const matches=matchingApartments(query,8);
    propertyResults.innerHTML=matches.length?matches.map(({group})=>{const address=searchAddressOf(group);return '<button type="button" data-key="'+esc(group.key)+'"><b>'+esc(group.apt_name)+'</b><small>'+esc(address.value)+'</small><span>'+(group.areas?.length?fmt(group.areas.length)+'개 평형':'평형 확인')+'</span></button>';}).join(""):'<p>검색되는 단지가 없습니다.</p>';
    propertyResults.hidden=false;
    propertyResults.querySelectorAll("button").forEach(button=>button.addEventListener("click",()=>chooseProperty(button.dataset.key)));
  };
  const render=()=>{
    const growth=clampGrowth(growthNumber.value)/100;
    const price=Math.max(0,Number(purchase.value)||0)*100000000;
    const currentOfficial=Math.max(0,Number(official.value)||0)*100000000;
    const homes=Math.max(1,Number(homeCount.value)||1),bought=Number(acquisitionYear.value)||2022;
    const acquisition=estimatedAcquisitionTax(price,homes,adjusted.checked);
    const key=board.id+"-tax";
    if(!currentOfficial){
      estimator.querySelector(".tax-current-total").textContent="공시가격 입력 필요";
      estimator.querySelector(".tax-summary").innerHTML='<b>—</b><span>동·호별 공동주택 공시가격을 입력하면 세목별 예상액을 계산합니다.</span><small>취득세 본세 예상 '+taxWon(acquisition.total)+'</small>';
      estimator.querySelector("tbody").innerHTML='<tr><td colspan="9">공식 공동주택 공시가격을 입력해 주세요.</td></tr>';
      charts.get(key)?.destroy();charts.delete(key);return;
    }
    const rows=[2023,2024,2025,2026,2027].map(year=>{
      const projected=currentOfficial*Math.pow(1+growth,year-TAX_BASE_YEAR);
      const held=bought<=year;
      const property=held?estimatedPropertyTax(projected,homes,urban.checked):{main:0,localEducation:0,urban:0,total:0};
      const comprehensive=held?estimatedComprehensiveTax(projected,homes):{main:0,rural:0,total:0};
      const holding=property.total+comprehensive.total;
      return {year,projected,property:property.main,localEducation:property.localEducation,urban:property.urban,comprehensive:comprehensive.main,rural:comprehensive.rural,holding,acquisition:year===bought?acquisition.total:0};
    });
    const current=rows.find(row=>row.year===TAX_BASE_YEAR),previous=rows.find(row=>row.year===TAX_BASE_YEAR-1);
    const difference=current.holding-previous.holding;
    estimator.querySelector(".tax-current-total").textContent="2026년 예상 보유세 "+taxWon(current.holding);
    const differenceLabel=difference===0?"전년 대비 변동 없음":"전년 대비 "+(difference>0?"+":"")+taxWon(Math.abs(difference))+(difference<0?" 감소":" 증가");
    estimator.querySelector(".tax-summary").innerHTML='<b>'+taxWon(current.holding)+'</b><span>재산세·지방교육세·도시지역분·종합부동산세·농어촌특별세 합계</span><em class="'+(difference>0?"up":difference<0?"down":"")+'">'+differenceLabel+'</em><small>취득세율 '+fmt(acquisition.rate*100)+'% · 취득세 본세 '+taxWon(acquisition.total)+'</small>';
    estimator.querySelector("tbody").innerHTML=rows.map(row=>'<tr class="'+(row.year===TAX_BASE_YEAR?"current":"")+'"><th>'+row.year+(row.year===2027?'<small>예측</small>':"")+'</th><td>'+fmt(row.projected/100000000)+'억원</td><td>'+taxWon(row.property)+'</td><td>'+taxWon(row.localEducation)+'</td><td>'+taxWon(row.urban)+'</td><td>'+taxWon(row.comprehensive)+'</td><td>'+taxWon(row.rural)+'</td><td><b>'+taxWon(row.holding)+'</b></td><td>'+taxWon(row.acquisition)+'</td></tr>').join("");
    charts.get(key)?.destroy();
    const chart=new Chart(estimator.querySelector(".tax-chart"),{data:{labels:rows.map(row=>row.year+"년"),datasets:[{type:"bar",label:"재산세",data:rows.map(row=>Math.round(row.property/10000)),backgroundColor:"#f97316",borderRadius:4,stack:"holding"},{type:"bar",label:"지방교육세",data:rows.map(row=>Math.round(row.localEducation/10000)),backgroundColor:"#fbbf24",borderRadius:4,stack:"holding"},{type:"bar",label:"도시지역분",data:rows.map(row=>Math.round(row.urban/10000)),backgroundColor:"#14b8a6",borderRadius:4,stack:"holding"},{type:"bar",label:"종합부동산세",data:rows.map(row=>Math.round(row.comprehensive/10000)),backgroundColor:"#5b4bdb",borderRadius:4,stack:"holding"},{type:"bar",label:"농어촌특별세",data:rows.map(row=>Math.round(row.rural/10000)),backgroundColor:"#a855f7",borderRadius:4,stack:"holding"},{type:"line",label:"보유세 합계",data:rows.map(row=>Math.round(row.holding/10000)),borderColor:"#dc2626",backgroundColor:"#dc2626",borderWidth:2,pointRadius:3,tension:.2,stack:"total"}]},options:{maintainAspectRatio:false,responsive:true,interaction:{mode:"index",intersect:false},scales:{x:{stacked:true},y:{beginAtZero:true,title:{display:true,text:"만원"},ticks:{callback:value=>fmt(value)+"만원"}}},plugins:{legend:{position:"bottom",labels:{usePointStyle:true,boxWidth:7}},tooltip:{callbacks:{label:item=>item.dataset.label+": "+fmt(item.raw)+"만원"}}}}});
    charts.set(key,chart);
  };
  propertySearch.addEventListener("input",showPropertyMatches);
  areaSelect.addEventListener("change",applySelectedArea);
  growthRange.addEventListener("input",()=>{growthNumber.value=growthRange.value;growthValue.value=growthRange.value+"%";render();});
  growthNumber.addEventListener("input",()=>{const value=clampGrowth(growthNumber.value);growthRange.value=value;growthValue.value=value+"%";render();});
  [purchase,official,homeCount,acquisitionYear,adjusted,urban].forEach(input=>input.addEventListener("input",render));
  render();
}

function renderBoardChart(board,container){
  const seriesRows=board.series.map(series=>{
    const group=apartmentGroups.find(g=>g.key===series.key);
    if(!group)return null;
    let points=group.history.filter(r=>Number(r.area_m2)===series.area).map(r=>({month:r.month,price:Number(r.median_price_eok),count:Number(r.trade_count||0)}));
    if(!points.length){
      const monthly=new Map();
      group.trades.filter(r=>Number(r.area_m2)===series.area).forEach(r=>{const month=String(r.trade_date).slice(0,7);if(!monthly.has(month))monthly.set(month,[]);monthly.get(month).push(r.price_eok);});
      points=[...monthly].map(([month,values])=>({month,price:median(values),count:values.length}));
    }
    series.supplyPyeong=Number(series.supplyPyeong)||Math.max(1,defaultSupplyPyeong(series.area));
    points.forEach(point=>{point.pyeongPrice=Number(point.price)*10000/series.supplyPyeong;});
    return {series,group,points};
  }).filter(Boolean);
  const bounds=periodBounds(board,seriesRows);
  const labels=monthRange(bounds.start,bounds.end);
  const isPyeong=board.priceMode==="pyeong";
  const datasets=seriesRows.map(item=>{
    const values=new Map(item.points.map(point=>[point.month,isPyeong?point.pyeongPrice:point.price]));
    const counts=new Map(item.points.map(point=>[point.month,point.count]));
    const observationDates=new Map();
    item.group.trades.filter(row=>Number(row.area_m2)===Number(item.series.area)).forEach(row=>{
      const date=String(row.trade_date||"").slice(0,10),month=date.slice(0,7);
      if(date&&(!observationDates.has(month)||date>observationDates.get(month)))observationDates.set(month,date);
    });
    const lineStyle=graphLineStyle(item.series.lineStyle);
    return {label:item.group.apt_name+" · "+(item.series.area?areaComparisonLabel(item.series.area,item.series.supplyPyeong):"평형 없음"),data:labels.map(month=>values.has(month)?values.get(month):null),tradeCounts:labels.map(month=>counts.get(month)||0),observationDates:labels.map(month=>observationDates.get(month)||""),borderColor:item.series.color,backgroundColor:item.series.color,pointRadius:1.15,pointHoverRadius:4,borderWidth:lineStyle.width,borderDash:lineStyle.dash,tension:.16,spanGaps:true};
  });
  const policies=(economicContext.policies||[]).map(policyRecord).filter(item=>item.date&&item.date.slice(0,7)>=bounds.start&&item.date.slice(0,7)<=bounds.end).sort((a,b)=>b.date.localeCompare(a.date));
  container.querySelector(".policy-list").innerHTML=policyHtml(policies);
  const selectPolicy=(button,item)=>{
    container.querySelectorAll(".policy-item").forEach(node=>node.classList.toggle("active",node===button));
    showPolicyDetail(container,item);
  };
  container.querySelectorAll(".policy-item").forEach(button=>{
    const item=policies[Number(button.dataset.policyIndex)];
    button.addEventListener("focus",()=>selectPolicy(button,item));
    button.addEventListener("click",()=>selectPolicy(button,item));
  });
  if(policies.length) showPolicyDetail(container,policies[0]);

  const alignTimelineYAxis=scale=>{scale.width=78;};
  const timelineTicks={display:true,autoSkip:true,maxTicksLimit:12,maxRotation:0,minRotation:0,callback:shortMonthTick};
  const priceChart=new Chart(container.querySelector(".price-chart"),{type:"line",data:{labels,datasets},plugins:[policyMarkerPlugin],options:{maintainAspectRatio:false,responsive:true,interaction:{mode:"nearest",intersect:true},scales:{x:{offset:false,title:{display:true,text:"거래월"},ticks:{...timelineTicks}},y:{afterFit:alignTimelineYAxis,title:{display:true,text:isPyeong?"월 중앙 공급평당가 (만원/평)":"월 중앙 실거래가 (억원)"},beginAtZero:false}},plugins:{policyMarkers:{items:policies},legend:{position:"bottom",labels:{usePointStyle:true,boxWidth:7}},tooltip:{displayColors:true,callbacks:{title:items=>items[0]?.label||"",label:c=>c.raw==null?c.dataset.label+": 거래 없음":c.dataset.label+": "+fmt(c.raw)+(isPyeong?"만원/평":"억원"),afterLabel:c=>c.raw==null?"":"해당 월 거래 "+fmt(c.dataset.tradeCounts[c.dataIndex])+"건의 중앙값"}}}}});
  bindPolicyMarkerHover(priceChart,container);
  const exchangeMap=valueMap(economicContext.exchange_rates,"krw_per_usd");
  const usRateMap=valueMap(economicContext.us_policy_rates,"rate");
  const japanRateMap=valueMap(economicContext.japan_policy_rates,"rate");
  const m1Map=valueMap(economicContext.money_supply,"m1_trillion_krw");
  const m2Map=valueMap(economicContext.money_supply,"m2_trillion_krw");
  const metricMap=(group,key)=>valueMap(economicContext[group]||[],key);
  const values=(map)=>labels.map(month=>map.get(month)??null);
  const normalized=(map)=>{const raw=values(map),base=raw.find(value=>Number.isFinite(value)&&value!==0);return raw.map(value=>Number.isFinite(value)&&base?value/base*100:null);};
  const hasData=data=>data.some(Number.isFinite);
  const commonOptions=(yTitle,callback,showTitle=false,showLegend=false,referenceLines=[])=>({maintainAspectRatio:false,responsive:true,interaction:{mode:"index",intersect:false},scales:{x:{offset:false,ticks:{...timelineTicks},grid:{display:false},title:{display:showTitle,text:"연월"}},y:{afterFit:alignTimelineYAxis,title:{display:true,text:yTitle},beginAtZero:false}},plugins:{referenceLines:{lines:referenceLines},legend:{display:showLegend,position:"bottom",labels:{usePointStyle:true,boxWidth:7}},tooltip:{callbacks:{title:items=>items[0]?.label||"",label:c=>c.raw==null?c.dataset.label+": 자료 없음":callback(c)}}}});
  const lineDataset=(label,data,color,extra={})=>({label,data,borderColor:color,backgroundColor:color,pointRadius:0,pointHoverRadius:3,borderWidth:1.25,tension:.18,spanGaps:true,...extra});
  const exchangeChart=new Chart(container.querySelector(".exchange-chart"),{type:"line",data:{labels,datasets:[lineDataset("원·달러 환율",labels.map(month=>exchangeMap.get(month)??null),"#0f766e")]},options:commonOptions("원/USD",c=>fmt(c.raw)+"원/USD")});
  const zeroRateLine=[{value:0,label:"0% 기준",color:"rgba(71,84,103,.18)"}];
  const rateChart=new Chart(container.querySelector(".rate-chart"),{type:"line",data:{labels,datasets:[lineDataset("한국(원)",labels.map(rateAtMonth),"#7c3aed",{stepped:true,spanGaps:false}),lineDataset("미국(달러)",labels.map(month=>usRateMap.get(month)??null),"#dc2626"),lineDataset("일본(엔)",labels.map(month=>japanRateMap.get(month)??null),"#2563eb")]},options:commonOptions("%",c=>c.dataset.label+": "+fmt(c.raw)+"%",false,true,zeroRateLine)});
  const moneyChart=new Chart(container.querySelector(".money-chart"),{type:"line",data:{labels,datasets:[lineDataset("M1 협의통화",labels.map(month=>m1Map.get(month)??null),"#0f766e"),lineDataset("M2 광의통화",labels.map(month=>m2Map.get(month)??null),"#b45309")]},options:commonOptions("조원",c=>c.dataset.label+": "+fmt(c.raw)+"조원",false,true)});
  const normalizedBaseline=[{value:100,label:"시작 기준 100",color:"rgba(71,84,103,.22)"}];
  const metalChart=new Chart(container.querySelector(".metal-chart"),{type:"line",data:{labels,datasets:[lineDataset("금",normalized(metricMap("metal_prices","gold_usd_oz")),"#d4a017"),lineDataset("은",normalized(metricMap("metal_prices","silver_usd_oz")),"#64748b"),lineDataset("구리",normalized(metricMap("metal_prices","copper_usd_ton")),"#b45309")]},options:commonOptions("시작값=100",c=>c.dataset.label+": "+fmt(c.raw),false,true,normalizedBaseline)});
  const oilChart=new Chart(container.querySelector(".oil-chart"),{type:"line",data:{labels,datasets:[lineDataset("브렌트",values(metricMap("oil_prices","brent_usd_barrel")),"#111827"),lineDataset("WTI",values(metricMap("oil_prices","wti_usd_barrel")),"#dc2626"),lineDataset("두바이",values(metricMap("oil_prices","dubai_usd_barrel")),"#2563eb")]},options:commonOptions("USD/배럴",c=>c.dataset.label+": "+fmt(c.raw)+" USD/배럴",false,true)});
  const bondData=(prefix,shortLabel)=>{
    const shortExact=values(metricMap("bond_yields",prefix+"_1y")),shortProxy=values(metricMap("bond_yields",prefix+"_short_proxy"));
    const rows=[lineDataset(hasData(shortExact)?"1년":shortLabel,hasData(shortExact)?shortExact:shortProxy,"#dc2626"),lineDataset("10년",values(metricMap("bond_yields",prefix+"_10y")),"#2563eb"),lineDataset("30년",values(metricMap("bond_yields",prefix+"_30y")),"#111827")];
    return rows.filter(row=>hasData(row.data));
  };
  const krBondChart=new Chart(container.querySelector(".kr-bond-chart"),{type:"line",data:{labels,datasets:bondData("kr","단기 대용")},options:commonOptions("%",c=>c.dataset.label+": "+fmt(c.raw)+"%",false,true,zeroRateLine)});
  const usBondChart=new Chart(container.querySelector(".us-bond-chart"),{type:"line",data:{labels,datasets:bondData("us","단기")},options:commonOptions("%",c=>c.dataset.label+": "+fmt(c.raw)+"%",false,true,zeroRateLine)});
  const jpBondChart=new Chart(container.querySelector(".jp-bond-chart"),{type:"line",data:{labels,datasets:bondData("jp","단기 대용")},options:commonOptions("%",c=>c.dataset.label+": "+fmt(c.raw)+"%",false,true,zeroRateLine)});
  const marketDefs=[["KOSPI","kospi","#1d4ed8"],["KOSDAQ","kosdaq","#06b6d4"],["S&P 500","sp500","#dc2626"],["나스닥","nasdaq","#7c3aed"],["다우","dow","#111827"],["필라델피아 반도체","sox","#16a34a"]];
  const marketChart=new Chart(container.querySelector(".market-chart"),{type:"line",data:{labels,datasets:marketDefs.map(([label,key,color])=>lineDataset(label,normalized(metricMap("market_indices",key)),color))},options:commonOptions("시작값=100",c=>c.dataset.label+": "+fmt(c.raw),false,true,normalizedBaseline)});
  const bitcoinChart=new Chart(container.querySelector(".bitcoin-chart"),{type:"line",data:{labels,datasets:[lineDataset("비트코인",values(metricMap("market_indices","bitcoin")),"#f59e0b")]},options:commonOptions("USD",c=>"비트코인: $"+fmt(c.raw),false,false)});
  const sentimentOptions=commonOptions("",c=>c.dataset.label+": "+fmt(c.raw),false,true);
  sentimentOptions.scales.y.title={display:false};
  sentimentOptions.scales.y1={position:"right",min:0,max:100,title:{display:false},grid:{drawOnChartArea:false}};
  sentimentOptions.plugins.referenceLines.lines=[
    {axis:"y",value:20,color:"rgba(220,38,38,.15)"},
    {axis:"y",value:30,color:"rgba(220,38,38,.22)"},
    {axis:"y",value:40,color:"rgba(220,38,38,.3)"},
    {axis:"y1",value:25,color:"rgba(37,99,235,.16)"},
    {axis:"y1",value:45,color:"rgba(37,99,235,.18)"},
    {axis:"y1",value:55,color:"rgba(37,99,235,.18)"},
    {axis:"y1",value:75,color:"rgba(37,99,235,.24)"}
  ];
  const sentimentChart=new Chart(container.querySelector(".sentiment-chart"),{type:"line",data:{labels,datasets:[lineDataset("VIX",values(metricMap("market_indices","vix")),"#dc2626"),lineDataset("공포탐욕지수",values(metricMap("fear_greed","score")),"#2563eb",{yAxisID:"y1"})]},options:sentimentOptions});
  renderLatestValues(priceChart,(value,dataset,index)=>fmt(value)+(isPyeong?"만원/평":"억원")+(dataset.tradeCounts?.[index]?" · "+fmt(dataset.tradeCounts[index])+"건":""));
  const economicConfirmedOn=String(economicContext.metadata?.updated_at||"").slice(0,10);
  renderLatestValues(exchangeChart,value=>fmt(value)+"원/USD",economicConfirmedOn);
  renderLatestValues(rateChart,value=>fmt(value)+"%",economicConfirmedOn);
  renderLatestValues(moneyChart,value=>fmt(value)+"조원",economicConfirmedOn);
  renderLatestValues(metalChart,value=>fmt(value)+" (시작=100)",economicConfirmedOn);
  renderLatestValues(oilChart,value=>fmt(value)+" USD/배럴",economicConfirmedOn);
  renderLatestValues(krBondChart,value=>fmt(value)+"%",economicConfirmedOn);
  renderLatestValues(usBondChart,value=>fmt(value)+"%",economicConfirmedOn);
  renderLatestValues(jpBondChart,value=>fmt(value)+"%",economicConfirmedOn);
  renderLatestValues(marketChart,value=>fmt(value)+" (시작=100)",economicConfirmedOn);
  renderLatestValues(bitcoinChart,value=>"$"+fmt(value),economicConfirmedOn);
  renderLatestValues(sentimentChart,value=>fmt(value),economicConfirmedOn);
  const timelineCharts=[priceChart,exchangeChart,rateChart,moneyChart,metalChart,oilChart,krBondChart,usBondChart,jpBondChart,marketChart,bitcoinChart,sentimentChart];
  bindEconomicChartAlignment(container,timelineCharts);
  bindTimelineGuide(container,timelineCharts,labels);

  charts.set(board.id+"-price",priceChart);
  charts.set(board.id+"-exchange",exchangeChart);
  charts.set(board.id+"-rate",rateChart);
  charts.set(board.id+"-money",moneyChart);
  charts.set(board.id+"-metal",metalChart);
  charts.set(board.id+"-oil",oilChart);
  charts.set(board.id+"-kr-bond",krBondChart);
  charts.set(board.id+"-us-bond",usBondChart);
  charts.set(board.id+"-jp-bond",jpBondChart);
  charts.set(board.id+"-market",marketChart);
  charts.set(board.id+"-bitcoin",bitcoinChart);
  charts.set(board.id+"-sentiment",sentimentChart);
  bindTaxEstimator(board,container);
}

async function renderDetails(group,area){
  if(localApi&&!group.hydrated) await hydrateGroup(group);
  if(!area&&group.areas.length) area=preferredArea(group);
  const rows=group.trades.filter(r=>Number(r.area_m2)===Number(area)).sort((a,b)=>b.trade_date.localeCompare(a.trade_date));
  const prices=rows.map(r=>r.price_eok), latest=rows[0];
  byId("metrics").innerHTML=[
    ["선택 단지",group.apt_name],["선택 평형",area?areaComparisonLabel(area):"거래 평형 없음"],["최근 실거래",latest?fmt(latest.price_eok)+"억원":"—"],["최근 상세 거래",fmt(rows.length)+"건"]
  ].map(x=>'<div class="metric"><span>'+esc(x[0])+'</span><b>'+esc(x[1])+"</b></div>").join("");
  const displayRows=rows.map(row=>({...row,supply_m2:Number(row.area_m2)/.75,supply_pyeong:estimatedSupplyPyeong(row.area_m2),exclusive_pyeong:Number(row.area_m2)/3.3058}));
  const cols=[["trade_date","거래일"],["apt_name","단지"],["dong","법정동"],["supply_m2","공급㎡(추정)"],["supply_pyeong","공급평(추정)"],["area_m2","전용㎡"],["exclusive_pyeong","전용평"],["floor","층"],["price_eok","억원"],["price_per_pyeong_manwon","전용평당만원"]];
  byId("trades").innerHTML="<thead><tr>"+cols.map(c=>"<th>"+c[1]+"</th>").join("")+"</tr></thead><tbody>"+displayRows.map(r=>"<tr>"+cols.map(c=>"<td>"+esc(typeof r[c[0]]==="number"?fmt(r[c[0]]):r[c[0]])+"</td>").join("")+"</tr>").join("")+"</tbody>";
}

function updateMarkerAvailability(){
  if(!map)return;
  const zoom=map.getZoom(),enabled=zoom>=MIN_MARKER_ZOOM,element=byId("markerAvailability");
  element.classList.toggle("enabled",enabled);
  element.classList.toggle("disabled",!enabled);
  element.textContent=enabled?"마커 생성 가능 · 배율 "+zoom:"마커 생성 안 함 · 배율 "+zoom+" (14 이상 필요)";
}

function initMap(){
  map=L.map("map",{zoomControl:true}).setView([36.5,127.8],7);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{
    maxZoom:19,
    attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'
  }).addTo(map);
  byId("mapState").textContent="무료 지도 연결됨";
  byId("mapState").classList.add("ready");
  updateMarkerAvailability();
  map.on("moveend",scheduleViewportMarkers);
  map.on("zoomend",()=>{updateMarkerAvailability();scheduleViewportMarkers();});
  map.on("click",event=>{
    const target=event.originalEvent?.target;
    if(target?.closest?.(".leaflet-marker-icon,.leaflet-popup"))return;
    map.closePopup();
  });
  scheduleViewportMarkers();
}

async function geocode(query){
  if(geoCache[query]) return geoCache[query];
  const elapsed=Date.now()-lastGeocodeAt;
  if(elapsed<1100) await new Promise(resolve=>setTimeout(resolve,1100-elapsed));
  lastGeocodeAt=Date.now();
  try{
    const url="/api/geocode?limit=1&q="+encodeURIComponent(query);
    const rows=await Promise.race([
      fetch(url).then(r=>{if(!r.ok) throw new Error("주소 검색 실패");return r.json();}),
      new Promise((_,reject)=>setTimeout(()=>reject(new Error("주소 검색 시간 초과")),10000))
    ]);
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

async function geocodeGroup(group,allowAddressFallback=true){
  const queries=[geocodeQueryOf(group),[addressOf(group),apartmentGeocodeName(group.apt_name)].filter(Boolean).join(" "),apartmentGeocodeName(group.directory_name||group.apt_name),apartmentGeocodeName(group.apt_name)].filter((value,index,items)=>value&&items.indexOf(value)===index);
  for(const query of queries){
    const coord=await geocode(query);
    if(coord)return coord;
  }
  return allowAddressFallback?await geocode(addressOf(group)):null;
}

async function focusGroup(group,knownCoord){
  if(localApi&&!group.hydrated) await hydrateGroup(group);
  renderDetails(group,activeBoard()?.series.find(s=>s.key===group.key)?.area||group.areas[0]);
  if(!map) return null;
  const coord=knownCoord||await geocodeGroup(group);
  if(!coord) return null;
  mapLocalityAnchor={coord,lawd_cd:group.lawd_cd,group};
  const marker=ensureMapMarker(group,coord);
  map.setView([coord.lat,coord.lng],16);
  marker.openPopup();
  refreshGraphAddButtons(group);
  return coord;
}

function haversine(a,b){
  const rad=x=>x*Math.PI/180,R=6371,dLat=rad(b.lat-a.lat),dLon=rad(b.lng-a.lng);
  const h=Math.sin(dLat/2)**2+Math.cos(rad(a.lat))*Math.cos(rad(b.lat))*Math.sin(dLon/2)**2;
  return 2*R*Math.asin(Math.sqrt(h));
}
function setStatus(message,error=false){byId("status").textContent=message;byId("status").style.color=error?"#b42318":"";}
async function refreshCatalogIfUpdated(){
  if(!localApi||catalogRefreshChecking||document.visibilityState==="hidden")return;
  const now=Date.now();
  if(now-lastCatalogRefreshCheck<30000)return;
  lastCatalogRefreshCheck=now;catalogRefreshChecking=true;
  try{
    const response=await fetch("/api/meta?refresh="+now,{cache:"no-store"});
    if(!response.ok)return;
    const nextMeta=await response.json();
    const currentCount=Number(localMeta.complex_count||apartmentGroups.length||0);
    const nextCount=Number(nextMeta.complex_count||0);
    const currentTrades=Number(localMeta.represented_trades||localMeta.transaction_rows||0);
    const nextTrades=Number(nextMeta.represented_trades||nextMeta.transaction_rows||0);
    if(nextCount&&((nextCount!==currentCount)||(nextTrades&&nextTrades!==currentTrades))){
      setStatus("새로 수집된 단지 자료를 자동 반영하는 중입니다…");
      setTimeout(()=>location.reload(),500);
    }
  }catch(_error){}finally{catalogRefreshChecking=false;}
}
byId("searchForm").addEventListener("submit",e=>{e.preventDefault();search();});
byId("searchInput").addEventListener("input",event=>{
  clearTimeout(searchSuggestionTimer);
  const query=event.currentTarget.value.trim();
  if(query.length<2){hideSearchSuggestions();return;}
  searchSuggestionTimer=setTimeout(()=>renderSearchSuggestions(matchingApartments(query,10),query),120);
});
byId("searchInput").addEventListener("focus",event=>{
  const query=event.currentTarget.value.trim();
  if(query.length>=2)renderSearchSuggestions(matchingApartments(query,10),query);
});
byId("searchInput").addEventListener("keydown",event=>{
  if(event.key==="Escape")hideSearchSuggestions();
  if(event.key==="ArrowDown"&&!byId("searchSuggestions").hidden){
    const first=byId("searchSuggestions").querySelector(".search-suggestion");
    if(first){event.preventDefault();first.focus();}
  }
});
document.addEventListener("click",event=>{if(!event.target.closest("#searchForm,#searchSuggestions"))hideSearchSuggestions();});
byId("addGraphBtn").addEventListener("click",addGraphBoard);
byId("removeGraphBtn").addEventListener("click",removeActiveGraphBoard);
byId("saveGraphsBtn").addEventListener("click",saveGraphBoards);
byId("map").addEventListener("click",async event=>{
  const button=event.target.closest?.(".map-popup-add");
  if(!button||button.disabled)return;
  event.preventDefault();event.stopPropagation();
  const group=apartmentGroups.find(item=>item.key===button.dataset.key);
  if(!group)return;
  button.disabled=true;button.classList.add("is-pressed");button.textContent="추가 중...";
  const added=await addSeries(group,Number(group.latest?.area_m2)||null);
  await new Promise(resolve=>setTimeout(resolve,180));
  if(!button.isConnected){refreshGraphAddButtons(group);return;}
  button.disabled=false;button.classList.remove("is-pressed");
  if(added){
    button.classList.add("is-added");button.textContent=sameSeriesCount(group)+"번째 추가됨";
    await new Promise(resolve=>setTimeout(resolve,450));
  }
  if(button.isConnected){button.classList.remove("is-added");button.textContent=graphAddLabel(group);}
  refreshGraphAddButtons(group);
});
load();
document.addEventListener("visibilitychange",()=>{if(document.visibilityState==="visible")refreshCatalogIfUpdated();});
window.addEventListener("focus",refreshCatalogIfUpdated);
setInterval(refreshCatalogIfUpdated,CATALOG_REFRESH_INTERVAL_MS);
