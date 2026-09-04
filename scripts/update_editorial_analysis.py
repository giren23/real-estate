from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
NEWS_DIR = ROOT / "web" / "content" / "news"
OUTPUT_DIR = ROOT / "web" / "content" / "analysis"
INDEX_PATH = OUTPUT_DIR / "index.json"
NUMBER_PATTERN = re.compile(r"(?<!\d)(\d[\d,.]*(?:\.\d+)?\s*(?:조원|억원|억|만원|만명|만호|만대|%|bp|건|척|호|명|대))", re.I)
USER_AGENT = "KoreanEconomicResearch/2.0"


COMPANIES = (
    {"name": "부-스타", "aliases": ("부-스타", "부스타"), "industry": "산업용 보일러", "business": "산업용 보일러의 수주·설치와 유지보수가 매출을 구성합니다.", "watch": ("수주잔고와 매출 전환", "원재료·공사 원가율", "배당과 순현금")},
    {"name": "가온전선", "aliases": ("가온전선",), "industry": "전선", "business": "전력·통신 케이블을 생산하며 구리 가격과 전력망 투자의 영향을 받습니다.", "watch": ("동 가격 전가", "수주잔고", "LS그룹 내부거래")},
    {"name": "알지노믹스", "aliases": ("알지노믹스",), "industry": "바이오", "business": "RNA 기반 유전자치료제를 개발하는 연구개발 중심 기업입니다.", "watch": ("임상 일정", "기술이전 계약", "현금 소진 속도")},
    {"name": "엠앤씨솔루션", "aliases": ("엠앤씨솔루션",), "industry": "방산", "business": "방산용 구동·제어장치를 공급해 수주와 납품 일정이 실적을 좌우합니다.", "watch": ("수주잔고", "수출 비중", "고객 집중도")},
    {"name": "비나우", "aliases": ("비나우",), "industry": "화장품", "business": "브랜드 화장품의 해외 유통과 마케팅 효율이 성장성을 결정합니다.", "watch": ("지역별 매출", "광고선전비", "재고 회전")},
    {"name": "오에스피", "aliases": ("오에스피",), "industry": "반려동물 식품", "business": "반려동물 식품 ODM과 자체 브랜드를 운영합니다.", "watch": ("ODM 가동률", "자체 브랜드 비중", "원재료 가격")},
    {"name": "이노스페이스", "aliases": ("이노스페이스",), "industry": "우주항공", "business": "소형위성 발사체를 개발하는 상용화 초기 단계 기업입니다.", "watch": ("시험발사 일정", "수주계약", "추가 자금조달")},
    {"name": "우진비앤지", "aliases": ("우진비앤지",), "industry": "동물의약품", "business": "동물용 의약품과 백신을 생산해 축산 경기와 수출의 영향을 받습니다.", "watch": ("수출 매출", "품목 허가", "매출채권 회수")},
    {"name": "코미코", "aliases": ("코미코",), "industry": "반도체 장비", "business": "반도체 공정 부품의 세정·코팅을 제공해 고객 가동률에 연동됩니다.", "watch": ("고객사 가동률", "해외법인 성장", "신규 코팅 매출")},
    {"name": "팜한농", "aliases": ("팜한농",), "industry": "농업", "business": "작물보호제·종자·비료를 공급하며 계절성과 원재료 가격의 영향을 받습니다.", "watch": ("작물보호제 점유율", "원재료 가격", "계열사 거래")},
)

# Public filing figures reconstructed into an original, consistent report format.
# Values remain labelled by period/unit; prose from third-party articles is not stored.
COMPANY_FACTS = {
    "부-스타": {"date":"2026-07-08","code":"008470","basis":"2026년 1분기 연결","headline":"유지보수 매출의 방어력과 저PBR 재무체력","metrics":[("1Q 매출","253.3억","전년 대비 -12.2%"),("영업손익","-10.3억","적자 확대"),("부채비율","26.7%","자본 800억"),("A/S·부품 비중","60.2%","반복 매출")],"trend":[("1Q25 매출",288.4),("1Q26 매출",253.3),("1Q25 영업손익",-0.6),("1Q26 영업손익",-10.3)],"tables":[("1분기 손익(억원)",["항목","1Q26","1Q25","증감"],[["매출","253.3","288.4","-12.2%"],["매출총이익","31.7","39.0","-18.8%"],["판관비","42.0","39.6","+6.0%"],["영업손익","-10.3","-0.6","적자 확대"],["순손익","-0.97","4.2","적자 전환"]]),("제품별 가동률",["제품군","1Q26","2025"],[["관류보일러","69.9%","50.4%"],["진공·무압","39.3%","57.7%"],["히트펌프 등","2.3%","3.2%"]])],"drivers":["전국 A/S망에서 발생하는 반복 매출","노후 보일러 교체와 저NOx 규제","히트펌프 매출 현실화"],"risks":["설비투자·건설경기 둔화","내수 편중","신사업의 낮은 가동률"],"source":"https://gjbuffet.kr/companies/2026-07-08_boostar-analysis.html"},
    "가온전선": {"date":"2026-06-17","code":"000500","basis":"2026년 1분기 연결","headline":"전력망 투자와 특수케이블 확장","metrics":[("1Q 매출","7,636억","+19.4%"),("영업이익","278억","+27.2%"),("전력사업 비중","74.6%","사업부 합계 기준"),("부채비율","약 202%","전년말 185%")],"trend":[("1Q25 매출",6393),("1Q26 매출",7636),("1Q25 영업이익",219),("1Q26 영업이익",278)],"tables":[("사업부 매출 구성(억원)",["사업부","매출","비중"],[["전력","6,401","74.6%"],["특수케이블","1,607","18.7%"],["통신","496","5.8%"],["목드럼","72","0.8%"]]),("손익 요약(억원)",["항목","1Q26","1Q25","증감"],[["매출","7,636","6,393","+19.4%"],["매출총이익","738","524","+40.8%"],["영업이익","278","219","+27.2%"],["순이익","197","153","+28.3%"]]),("재무상태",["항목","1Q26","2025말"],[["자산","15,156억","13,779억"],["부채","10,145억","8,941억"],["자본","5,011억","4,838억"],["재고","3,507억","2,842억"]])],"drivers":["국내외 전력망 교체","자동차·특수케이블 비중 확대","미국 법인 매출 전환"],"risks":["구리 가격과 판가 전가 시차","부채·재고 증가","신규 자회사 수익성"],"source":"https://gjbuffet.kr/companies/2026-06-17_gaon-cable.html"},
    "알지노믹스": {"date":"2026-06-16","code":"251557","basis":"2026년 1분기 별도","headline":"RNA 편집 플랫폼의 계약가치와 현금 소진","metrics":[("릴리 계약 최대액","약 1.9조","USD 13.34억"),("영업수익","3.7억","1Q26"),("영업손실","-80.6억","1Q26"),("자본총계","517.5억","1Q26말")],"trend":[("1Q25 영업손실",-41.3),("1Q26 영업손실",-80.6),("1Q25 순손실",-52.6),("1Q26 순손실",-77.6)],"tables":[("릴리 라이선스 계약",["항목","내용"],[["대상","유전성 난청 RNA 편집 치료제"],["최대 계약규모","USD 13.34억(약 1.9조원)"],["수익 구조","연구비·마일스톤·경상로열티"],["역할","초기 R&D 후 릴리가 후기개발·상업화"]]),("1분기 재무(억원)",["항목","1Q26","1Q25"],[["영업수익","3.7","0"],["영업손실","-80.6","-41.3"],["순손실","-77.6","-52.6"],["자산","585.9","628.3"],["자본","517.5","588.8"]])],"drivers":["RNA 치환효소 플랫폼 확장","릴리 마일스톤 달성","주력 파이프라인 임상 진전"],"risks":["임상 실패","마일스톤 최대액과 실수령액의 차이","적자 지속에 따른 희석"],"source":"https://gjbuffet.kr/companies/2026-06-16_rznomics-analysis.html"},
    "엠앤씨솔루션": {"date":"2026-06-15","code":"283530","basis":"2026년 1분기 연결","headline":"K-방산 수출과 9,622억 수주잔고","metrics":[("2025 매출","4,033억","+42.6%"),("1Q 영업이익","80억","OPM 12.1%"),("수주잔고","9,622억","공시 기준"),("현금성자산","860억","1Q말")],"trend":[("2024 매출",2828),("2025 매출",4033),("2024 영업이익",348),("2025 영업이익",561)],"tables":[("손익 요약(억원)",["항목","2024","2025","1Q26"],[["매출","2,828","4,033","661"],["영업이익","348","561","80"],["순이익","270","456","61"],["영업이익률","12.3%","13.9%","12.1%"]]),("주요 수출계약(억원)",["계약","금액","상대방"],[["폴란드 K9PL EC2","495","한화에어로"],["폴란드 K2GF","419","현대로템"],["230mm 다련장 3차","237","한화에어로"],["K21 4차","199","한화에어로"],["천무 폴란드 2차","183","한화에어로"]]),("재무상태(억원)",["항목","2025말","1Q26"],[["현금성자산","862","860"],["부채","2,082","2,172"],["자본","1,947","1,780"],["부채비율","107%","122%"],["선수금","1,277","1,252"]])],"drivers":["폴란드·인도 등 방산 수출","수주잔고의 납품 전환","선수금 기반 운전자금"],"risks":["상위 고객 집중","납품시점별 실적 변동","PEF 지분 오버행"],"source":"https://gjbuffet.kr/companies/2026-06-15_mnc-solution.html"},
    "비나우": {"date":"2026-06-10","code":"비상장","basis":"2025년 연결 감사보고서","headline":"해외 매출 성장과 마케팅비 부담","metrics":[("매출","3,250억","+22.0%"),("영업이익","671억","-10.6%"),("해외 비중","55%","일본 성장 주도"),("현금","768억","사실상 무차입")],"trend":[("2024 매출",2664),("2025 매출",3250),("2024 영업이익",751),("2025 영업이익",671)],"tables":[("연결 손익(억원)",["항목","2025","2024","증감"],[["매출","3,250","2,664","+22.0%"],["매출총이익","2,140","1,807","+18.4%"],["판관비","1,442","1,040","+38.7%"],["영업이익","671","751","-10.6%"],["순이익","534","690","-22.6%"]]),("해외법인(억원)",["법인","매출","손익"],[["일본","775","+25.5"],["미국","25.5","-21.1"],["중국","-","-0.1"]]),("지배구조·자본배분",["항목","내용"],[["최대주주 2인","합산 66.9%"],["팀모먼트 인수","지분 90%·9.45억"],["배당","총 100억원"],["스톡옵션 비용","21.6억원"]])],"drivers":["일본 매출 확대","브랜드·채널 다변화","인수회사의 마케팅 시너지"],"risks":["판관비 증가","미국 법인 적자","비상장 정보 접근성"],"source":"https://gjbuffet.kr/companies/2026-06-10_benow-analysis.html"},
    "오에스피": {"date":"2026-06-05","code":"355150","basis":"2026년 1분기 연결","headline":"ODM 기반에서 자체브랜드로 이동","metrics":[("1Q 매출","71.95억","전년 64.21억"),("영업이익","4.54억","흑자전환"),("자본총계","434.56억","1Q말"),("PB 비중","36%","3%에서 확대")],"trend":[("1Q25 매출",64.21),("1Q26 매출",71.95),("1Q25 영업이익",-4.80),("1Q26 영업이익",4.54)],"tables":[("연결 손익(백만원)",["항목","1Q26","1Q25"],[["매출","7,195","6,421"],["매출총이익","2,429","1,807"],["판관비","1,975","2,288"],["영업이익","454","-480"],["순이익","-250","-392"]]),("재무상태(백만원)",["항목","1Q26","2025말"],[["유동자산","18,970","18,644"],["비유동자산","46,397","47,025"],["부채","21,911","22,087"],["자본","43,456","43,582"]])],"drivers":["인디고 등 자체브랜드 확대","ODM 가동률 회복","바우와우코리아 시너지"],"risks":["매출 성장과 순손실의 괴리","전환사채·금융비용","브랜드 마케팅 효율"],"source":"https://gjbuffet.kr/companies/2026-06-05_osp-petfood-analysis.html"},
    "이노스페이스": {"date":"2026-06-05","code":"462350","basis":"2026년 1분기 연결","headline":"첫 상업발사 전 현금 소진과 일정 위험","metrics":[("1Q 매출","14억","상업화 초기"),("영업손실","-124억","1Q26"),("현금성자산","82억","전년말 211억"),("누적 결손","-703억","1Q말")],"trend":[("2024 매출",0.1),("2025 매출",27),("1Q26 매출",14),("1Q26 영업손실",-124)],"tables":[("한빛 발사체",["모델","탑재량","단계"],[["한빛-나노","90kg","시장 진입"],["한빛-마이크로","170kg","확장"],["한빛 대형","1,300kg","장기 목표"]]),("손익(억원)",["항목","1Q26","2025","2024"],[["매출","14","27","0.1"],["영업손익","-124","-722","-329"],["순손익","-125","-751","-333"]]),("재무상태(억원)",["항목","1Q26","2025말"],[["자산","592","701"],["현금성자산","82","211"],["부채","181","180"],["자본","411","520"],["결손금","-703","-578"]])],"drivers":["한빛-나노 상업발사 성공","후속 발사 수주","하이브리드 엔진의 원가·안전성"],"risks":["발사 실패·지연","빠른 현금 소진","추가 자금조달과 희석"],"source":"https://gjbuffet.kr/companies/2026-06-05_innospace-analysis.html"},
    "우진비앤지": {"date":"2026-06-01","code":"079000","basis":"2026년 1분기 연결","headline":"동물약품 본업 흑자와 펫푸드 연결 부담","metrics":[("2025 별도 매출","302억","본체 기준"),("2025 별도 영업이익","21.9억","본업 흑자"),("1Q 연결 영업이익","7.1억","+66.4%"),("1Q 순손익","-1.6억","적자 전환")],"trend":[("1Q25 매출",143.2),("1Q26 매출",143.1),("1Q25 영업이익",4.2),("1Q26 영업이익",7.1)],"tables":[("2025 별도·연결(억원)",["항목","별도","연결"],[["매출","302","548"],["영업이익","21.9","3.2"],["순손익","18.7","-35.8"]]),("1분기 연결(억원)",["항목","1Q26","1Q25","증감"],[["매출","143.1","143.2","-0.1%"],["매출총이익","46.9","44.6","+5.1%"],["영업이익","7.1","4.2","+66.4%"],["순손익","-1.6","1.5","적자 전환"]])],"drivers":["동물약품 본업 수익성","백신·수출 품목 확대","펫푸드 자회사 정상화"],"risks":["연결 자회사 손실","축산경기·질병 변동","매출채권 회수"],"source":"https://gjbuffet.kr/companies/2026-06-01_woogenebng-analysis.html"},
    "코미코": {"date":"2026-05-13","code":"183300","basis":"2025년 연결","headline":"AI 반도체 가동률에 연동되는 세정·코팅","metrics":[("매출","6,041억","2025"),("영업이익","1,110억","OPM 18.4%"),("해외고객 비중","61.4%","2025"),("ROE","18.5%","지배 기준")],"trend":[("2022 매출",2884),("2023 매출",3073),("2024 매출",5071),("2025 매출",6041)],"tables":[("4개년 재무(억원)",["항목","2022","2023","2024","2025"],[["매출","2,884","3,073","5,071","6,041"],["영업이익","554","330","1,125","1,110"],["영업이익률","19.2%","10.7%","22.2%","18.4%"],["순이익","420","455","878","772"],["부채","1,301","3,059","4,246","6,604"]]),("고객 매출(억원)",["고객군","매출","비중"],[["국내 메모리사 등","2,147","35.5%"],["Intel·TSMC·Micron 등","3,708","61.4%"],["비반도체","186","3.1%"]]),("R&D·지식재산",["항목","2025말"],[["등록 특허","104건"],["R&D 인력","91명"],["연구개발 실적","세정 26건·코팅 45건"]])],"drivers":["AI·HBM 가동률 상승","미세공정 세정·코팅 횟수 증가","6개국 현지 서비스망"],"risks":["반도체 매출 96.9% 집중","부채와 투자현금흐름 부담","중국 내재화"],"source":"https://gjbuffet.kr/companies/2026-05-13_komico-analysis.html"},
    "팜한농": {"date":"2026-05-12","code":"비상장","basis":"2025년 연결","headline":"국내 1위 농자재와 친환경 전환 비용","metrics":[("매출","7,748억","2025"),("영업이익","376억","OPM 4.9%"),("작물보호 점유율","30%","국내 1위"),("자본총계","4,777억","2025말")],"trend":[("2023 매출",7824),("2024 매출",7621),("2025 매출",7748),("2025 영업이익",376)],"tables":[("3개년 재무(억원)",["항목","2023","2024","2025"],[["매출","7,824","7,621","7,748"],["영업이익","458","441","376"],["영업이익률","5.9%","5.8%","4.9%"],["순이익","-26","4","434"],["부채","6,538","6,607","6,089"],["자본","4,357","4,354","4,777"]]),("사업부 구조",["부문","주요 제품","핵심"],[["작물보호","테라도·큐라텔 등","국내 점유율 30%"],["비료","완효성·수용성 비료","친환경 전환"],["종자","흥농씨앗","70년 육종 기반"],["B2C","식물재배기 씨앗키트","신규 채널"]])],"drivers":["친환경 작물보호제","해외 파트너십","디지털 파밍·B2C"],"risks":["원재료 수입과 환율","중국 저가 경쟁","비료부문 수익성"],"source":"https://gjbuffet.kr/companies/2026-05-12_farmhannong-analysis.html"},
}

THEMES = (
    {"name": "반도체·AI", "keywords": ("반도체", "HBM", "AI", "데이터센터", "파운드리"), "title": "반도체·AI 투자, 실적과 공급망을 함께 봐야 하는 이유", "path": "AI 투자 확대 → 반도체·전력 수요 증가 → 설비투자와 수출 → 기업 실적과 고용"},
    {"name": "금리·유동성", "keywords": ("금리", "연준", "한국은행", "국채", "채권", "유동성"), "title": "금리 방향이 주식·환율·부동산으로 번지는 경로", "path": "정책금리와 국채금리 → 대출·할인율 → 환율과 위험선호 → 소비·투자·주택수요"},
    {"name": "주택·공급", "keywords": ("부동산", "주택", "아파트", "분양", "재건축", "전세", "공급"), "title": "주택 공급 뉴스가 실제 가격에 반영되기까지", "path": "정책 발표 → 인허가 → 착공 → 준공·입주 → 지역별 매매·전월세 수급"},
    {"name": "원유·지정학", "keywords": ("유가", "원유", "호르무즈", "이란", "전쟁", "중동"), "title": "원유와 지정학 충격, 물가와 시장에 미치는 경로", "path": "공급 차질 우려 → 원유·운송비 → 소비자물가 → 금리 기대와 기업 마진"},
    {"name": "전력·인프라", "keywords": ("전력", "전력망", "변압기", "원전", "데이터센터", "에너지"), "title": "AI 시대 전력 인프라가 새로운 병목이 된 이유", "path": "AI 연산 수요 → 데이터센터 전력 소비 → 발전·송배전 투자 → 전력기기 수주"},
    {"name": "가상자산", "keywords": ("비트코인", "가상자산", "암호화폐", "이더리움"), "title": "비트코인 변동을 유동성과 위험선호로 읽는 법", "path": "달러 유동성·금리 → 위험선호와 레버리지 → 가상자산 자금 유입 → 변동성 확대"},
)


def load_news(days: int) -> list[dict[str, object]]:
    cutoff = date.today() - timedelta(days=days - 1)
    items: list[dict[str, object]] = []
    for path in sorted(NEWS_DIR.glob("20??-??-??.json"), reverse=True):
        if date.fromisoformat(path.stem) < cutoff:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        items.extend(payload.get("items", []))
    return items


def unique_sources(items: list[dict[str, object]], limit: int = 6) -> list[dict[str, str]]:
    seen: set[str] = set()
    sources: list[dict[str, str]] = []
    for item in sorted(items, key=lambda row: str(row.get("date", "")), reverse=True):
        for source in item.get("sources", []):
            key = f"{source.get('publisher')}|{source.get('title')}"
            if key in seen:
                continue
            seen.add(key)
            sources.append({key: str(source.get(key, "")) for key in ("publisher", "title", "url", "published_at")})
            if len(sources) >= limit:
                return sources
    return sources


def numbers_from(items: list[dict[str, object]], limit: int = 3) -> list[str]:
    values: list[str] = []
    for item in items:
        for value in NUMBER_PATTERN.findall(f"{item.get('title', '')} {item.get('summary', '')}"):
            value = re.sub(r"\s+", "", value)
            if value not in values:
                values.append(value)
            if len(values) >= limit:
                return values
    return values


def score(items: list[dict[str, object]], sources: list[dict[str, str]]) -> int:
    return min(100, len(items) * 8 + len({source["publisher"] for source in sources}) * 10 + len(numbers_from(items)) * 5)


def coverage_charts(matches: list[dict[str, object]], sources: list[dict[str, str]]) -> list[dict[str, object]]:
    by_date = Counter(str(item.get("date", "")) for item in matches)
    by_publisher = Counter(source["publisher"] for source in sources)
    return [
        {
            "type": "bar",
            "title": "보도량 시간 흐름",
            "subtitle": "수집 기사 · 일자별",
            "rows": [
                {"label": label[5:].replace("-", "/"), "value": value, "display": f"{value}건"}
                for label, value in sorted(by_date.items())[-8:]
            ],
            "note": "기사 수는 관심도의 지표이며 실적이나 가격 방향을 뜻하지 않습니다.",
        },
        {
            "type": "donut",
            "title": "독립 출처 구성",
            "subtitle": "중복 제목 제거 후",
            "center": f"{len(sources)}건",
            "center_label": "검증 원문",
            "rows": [
                {"label": label, "value": value, "display": f"{value}건"}
                for label, value in by_publisher.most_common(5)
            ],
        },
    ]


def dart_corp_codes(api_key: str) -> dict[str, str]:
    """Download the official DART company-code table when a key is configured."""
    if not api_key:
        return {}
    request = Request("https://opendart.fss.or.kr/api/corpCode.xml?" + urlencode({"crtfc_key": api_key}), headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=40) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
        root = ET.fromstring(archive.read("CORPCODE.xml"))
    return {str(row.findtext("corp_name") or "").strip(): str(row.findtext("corp_code") or "").strip() for row in root.findall("list")}


def dart_latest_sources(company_name: str, corp_code: str, api_key: str) -> list[dict[str, str]]:
    if not api_key or not corp_code:
        return []
    params = {"crtfc_key": api_key, "corp_code": corp_code, "bgn_de": (date.today()-timedelta(days=550)).strftime("%Y%m%d"), "page_count": 100}
    request = Request("https://opendart.fss.or.kr/api/list.json?" + urlencode(params), headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    rows = [row for row in payload.get("list", []) if any(token in str(row.get("report_nm", "")) for token in ("사업보고서", "반기보고서", "분기보고서", "감사보고서"))]
    return [{"publisher":"금융감독원 DART", "title":str(row.get("report_nm") or company_name), "url":f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={row.get('rcept_no')}", "published_at":str(row.get("rcept_dt") or ""), "source_type":"공시", "source_id":f"dart-{row.get('rcept_no')}"} for row in rows[:4]]


def source_contract(sources: list[dict[str, object]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, source in enumerate(sources):
        url = str(source.get("url") or "")
        key = url or f"{source.get('publisher')}|{source.get('title')}"
        if key in seen:
            continue
        seen.add(key)
        publisher = str(source.get("publisher") or "원문")
        source_type = str(source.get("source_type") or ("공시" if "DART" in publisher else "거래소" if "거래소" in publisher or "KRX" in publisher else "언론"))
        result.append({"source_id":str(source.get("source_id") or f"source-{index+1}"), "publisher":publisher, "document":str(source.get("document") or source.get("title") or "원문"), "title":str(source.get("title") or source.get("document") or "원문"), "published_at":str(source.get("published_at") or ""), "url":url, "source_type":source_type, "accessed_at":date.today().isoformat()})
    return result


def research_contract(item: dict[str, object], report_type: str) -> dict[str, object]:
    """Attach the strict, source-traceable report schema while retaining legacy rendering fields."""
    sources = source_contract(list(item.get("sources") or []))
    item["sources"] = sources
    source_id = sources[0]["source_id"] if sources else "source-required"
    charts = []
    for index, chart in enumerate(item.get("charts") or []):
        rows = list(chart.get("rows") or [])
        charts.append({**chart, "chart_id":str(chart.get("chart_id") or f"chart-{index+1}"), "purpose":str(chart.get("purpose") or "본문의 수치 비교를 검증"), "unit":str(chart.get("unit") or chart.get("subtitle") or "원자료 표기"), "basis":str(chart.get("basis") or "출처별 기준 확인"), "as_of":str(item.get("date") or ""), "source":[{"source_id":source_id}], "series":[{"name":str(chart.get("title") or "지표"), "data":[{"label":str(row.get("label") or ""), "value":row.get("value")} for row in rows]}], "annotation":[], "interpretation":str(chart.get("note") or "그래프에 표시된 값의 상대적 흐름을 비교함."), "caution":"단위·기간·연결/별도 기준이 같은 값만 직접 비교해야 함."})
    sections = []
    for index, section in enumerate(item.get("sections") or []):
        paragraphs = list(section.get("paragraphs") or [])
        sections.append({**section, "id":str(section.get("id") or f"section-{index+1}"), "number":index+1, "title":str(section.get("title") or section.get("heading") or ""), "summary":str(section.get("summary") or (paragraphs[0] if paragraphs else "")), "chart_ids":[str(row.get("chart_id") or f"section-{index+1}-chart-{chart_index+1}") for chart_index,row in enumerate(section.get("charts") or [])], "fact_or_analysis":str(section.get("fact_or_analysis") or "mixed")})
    tags = list(item.get("tags") or [])
    item.update({"type":report_type, "subtitle":str(item.get("summary") or ""), "as_of":str(item.get("date") or ""), "ticker":str(tags[1] if report_type=="company_analysis" and len(tags)>1 else ""), "reading_minutes":int(item.get("read_minutes") or 0), "key_message":str(item.get("easy_explanation") or item.get("summary") or ""), "key_metrics":[{"label":str(row.get("label") or ""), "value":str(row.get("value") or ""), "comparison":str(row.get("note") or ""), "basis":"보고서 표기 기준", "source_id":source_id} for row in item.get("metrics") or []], "toc":[section["title"] for section in sections], "sections":sections, "charts":charts, "scenarios":[scenario for section in sections for scenario in section.get("scenarios") or []], "risks":[{"risk":str(value), "probability":"판단불가", "impact":"판단불가", "warning_indicator":"후속 공식 공시·통계 확인", "source_id":source_id} for section in sections if "위험" in section["title"] for value in section.get("bullets") or []], "calendar":[], "uncertainties":["원자료에서 확인되지 않는 값은 자료 미확인으로 처리함"], "verification_status":"official_verified" if any(source["source_type"] in {"공시","정부통계","중앙은행통계","거래소"} and "main.do?rcpNo=" in source["url"] for source in sources) else "official_source_review_required"})
    return item


def daily_company_selection(company_items: list[dict[str, object]], previous: dict[str, object] | None = None) -> dict[str, object]:
    """Publish at most one newly verified company per day; never fill gaps with weak data."""
    today = date.today().isoformat()
    previous = previous or {}
    prior = dict(previous.get("daily_company_selection") or {})
    history = list(previous.get("daily_company_history") or [])
    if prior.get("date") == today:
        return {"selection": prior, "history": history}
    published_ids = {str(row.get("company_id") or "") for row in history if row.get("status") == "published"}
    eligible = [item for item in company_items if item.get("verification_status") == "official_verified" and str(item.get("id") or "") not in published_ids]
    if not eligible:
        selection = {"date":today, "status":"no_eligible_company", "message":"오늘은 검증 조건을 통과한 신규 기업이 없음", "company_id":""}
    else:
        chosen = max(eligible, key=lambda item: (int(item.get("issue_score") or 0), str(item.get("date") or "")))
        selection = {"date":today, "status":"published", "message":f"오늘의 검증 기업: {chosen.get('title', '')}", "company_id":str(chosen.get("id") or ""), "title":str(chosen.get("title") or ""), "verification_status":"official_verified"}
    history = ([selection] + history)[:365]
    return {"selection": selection, "history": history}


def company_item(company: dict[str, object], matches: list[dict[str, object]]) -> dict[str, object]:
    sources = unique_sources(matches)
    metrics = [{"label": "관련 기사", "value": f"{len(matches)}건", "note": "최근 수집 기간"}, {"label": "확인 매체", "value": f"{len({s['publisher'] for s in sources})}곳", "note": "중복 제외"}]
    metrics.extend({"label": f"기사 수치 {index}", "value": value, "note": "원문 제목·공개요약 언급값"} for index, value in enumerate(numbers_from(matches), 1))
    newest = max((str(item.get("date", "")) for item in matches), default=date.today().isoformat())
    issue_titles = [source["title"] for source in sources[:4]]
    digest = hashlib.sha1(f"{company['name']}|{newest}|{'|'.join(issue_titles)}".encode()).hexdigest()[:10]
    return {
        "id": f"company-auto-{newest.replace('-', '')}-{digest}", "date": newest,
        "eyebrow": f"COMPANY WATCH · {company['industry']}", "read_minutes": 5,
        "title": f"{company['name']} — 최근 주요 이슈와 다음 확인값",
        "summary": f"기업의 사업구조와 최근 {len(matches)}건의 보도를 바탕으로 실적 동인, 위험요인과 다음 공시 확인값을 정리했습니다.",
        "tags": [str(company["industry"]), "주요이슈", "공시확인"], "longform": True,
        "causal_path": ["뉴스·공시 발생", "수주·판매 조건 변화", "매출·원가 반영", "현금흐름·기업가치 검증"],
        "charts": coverage_charts(matches, sources) if matches else [],
        "methodology": "최근 기사에서 기업 별칭을 검색해 사건을 묶고, 발행처·제목 중복을 제거했습니다. 기사 속 숫자는 공시 숫자와 섞지 않고 별도 표시하며, 실제 사업 영향은 다음 DART 정기·주요사항 공시에서 재검증하도록 구성했습니다.",
        "easy_explanation": f"{company['business']} 최근 뉴스가 실제 매출과 현금흐름으로 이어지는지는 다음 공시에서 확인해야 합니다.",
        "market_comment": "기사의 관심도와 기업가치는 같은 말이 아닙니다. 호재는 매출 인식 시점과 비용을, 악재는 일회성 여부와 재무 여력을 함께 봐야 합니다. 주택·건설 관련 기업은 수도권과 지방 사업 비중, PF와 미분양 노출도도 구분해야 합니다.",
        "metrics": metrics[:5],
        "sections": [
            {"heading": "한 줄로 이해하기 — 어떤 회사인가", "paragraphs": [str(company["business"])], "bullets": []},
            {"heading": "최근 주요 이슈 — 여러 매체로 교차 확인", "paragraphs": ["아래 항목은 원문 제목과 공개요약에서 확인된 최근 관심사입니다. 같은 사건을 반복 보도한 경우 매체 수를 별도로 확인했습니다."], "bullets": issue_titles},
            {"heading": "숫자로 보기 — 기사 수치와 공시 수치를 구분", "paragraphs": ["기사에 숫자가 있더라도 계약 총액, 실제 매출, 영업이익은 서로 다릅니다. 아래 값은 기사에서 언급된 값이며 다음 정기공시에서 연결·별도 기준과 인식 시점을 다시 확인해야 합니다."], "bullets": numbers_from(matches) or ["공개 제목·요약에서 검증 가능한 핵심 숫자가 부족합니다."]},
            {"heading": "기회·기본·위험 시나리오", "paragraphs": ["방향을 예측하기보다 어떤 조건에서 해석이 달라지는지 나눕니다."], "bullets": [], "scenarios": [
                {"label": "기회", "title": "실적 전환", "body": "관련 수요가 실제 수주·출하·현금유입으로 전환"},
                {"label": "기본", "title": "점진 반영", "body": "관심은 높지만 기존 사업 범위 안에서 단계적으로 반영"},
                {"label": "위험", "title": "기대 이탈", "body": "비용·경쟁·규제 또는 일정 지연으로 기대와 실적이 벌어짐"},
            ]},
            {"heading": "다음 공시에서 확인할 것", "paragraphs": ["뉴스를 실적으로 검증하기 위한 체크리스트입니다."], "bullets": list(company["watch"]) + ["금융감독원 DART 정기·주요사항 공시 원문"]},
        ],
        "sources": sources + [
            {"publisher": "금융감독원 DART", "title": f"{company['name']} 공시검색", "url": "https://dart.fss.or.kr/dsab002/main.do", "published_at": newest},
            {"publisher": "한국거래소 KIND", "title": f"{company['name']} 상장공시·기업정보 확인", "url": "https://kind.krx.co.kr/", "published_at": newest},
            {"publisher": "KRX 정보데이터시스템", "title": f"{company['name']} 시장·종목 기초정보 확인", "url": "https://data.krx.co.kr/", "published_at": newest},
        ],
        "disclaimer": "뉴스 원문과 DART 공시를 교차 확인하기 위한 자동 이슈 브리핑이며 투자 권유가 아닙니다. 재무수치는 반드시 최신 공시 원문에서 다시 확인하세요.",
        "issue_score": score(matches, sources),
    }


def curated_company_item(company: dict[str, object], matches: list[dict[str, object]]) -> dict[str, object]:
    facts = COMPANY_FACTS[str(company["name"])]
    news_sources = unique_sources(matches, 4)
    tables = [
        {"title": title, "headers": headers, "rows": rows}
        for title, headers, rows in facts["tables"]
    ]
    trend_rows = [
        {"label": label, "value": value, "display": f"{value:g}"}
        for label, value in facts["trend"]
    ]
    return {
        "id": f"company-curated-{facts['code']}-{facts['date'].replace('-', '')}",
        "date": facts["date"], "eyebrow": f"COMPANY · {company['industry']} · {facts['code']}",
        "read_minutes": 8, "title": f"{company['name']} — {facts['headline']}",
        "summary": f"{facts['basis']} 공개 수치를 사업구조, 손익, 재무체력, 성장동력과 위험요인으로 나눠 검증했습니다.",
        "tags": [str(company["industry"]), str(facts["code"]), "공시분석"], "longform": True,
        "issue_score": 90, "causal_path": ["사업·수요 변화", "판매량·가격·수주", "매출·원가", "현금흐름·재무", "다음 공시 검증"],
        "metrics": [{"label": label, "value": value, "note": note} for label, value, note in facts["metrics"]],
        "charts": [{"type":"bar","title":"핵심 실적 흐름","subtitle":facts["basis"],"rows":trend_rows,"note":"서로 다른 기간·손익 항목이 함께 있을 수 있어 방향 비교용으로 읽어야 합니다."}],
        "easy_explanation": f"{company['business']} 이번 분석의 핵심은 ‘{facts['headline']}’이 실제 손익과 현금흐름으로 이어지는지 확인하는 것입니다.",
        "market_comment": "매출 성장만으로 기업가치를 판단하지 않습니다. 영업이익, 부채·현금, 일회성 요인과 다음 분기의 재현 가능성을 함께 비교했습니다.",
        "methodology": f"{facts['basis']} 기준으로 수집된 수치를 구조화했습니다. 정확한 DART 접수번호가 연결되면 원문과 자동 교차검증하며, 연결 전에는 공식 원문 재확인이 필요한 참고값으로 표시합니다. 외부 사이트의 문장과 그래픽은 복제하지 않습니다.",
        "sections": [
            {"heading":"기업과 사업구조 — 무엇으로 돈을 버나","paragraphs":[str(company["business"])],"bullets":list(facts["drivers"]),"tables":tables[:1]},
            {"heading":"핵심 실적 — 성장의 질을 숫자로 확인","paragraphs":[f"기준은 {facts['basis']}입니다. 매출과 영업이익의 방향이 같은지, 비용 증가가 성장을 상쇄하는지 구분합니다."],"bullets":[],"charts":[{"type":"bar","title":"공시 수치 비교","subtitle":facts["basis"],"rows":trend_rows}]},
            {"heading":"세부 근거표 — 기간과 단위를 함께 보기","paragraphs":["금액과 비율은 표에 표시된 기준기간·단위를 따릅니다. 전망치가 아니라 해당 공시 또는 감사보고서의 공개값을 우선했습니다."],"bullets":[],"tables":tables[1:] or tables},
            {"heading":"성장동력 — 숫자로 전환될 조건","paragraphs":["사업 설명보다 다음 공시에서 매출·수주·마진으로 확인될 조건을 추렸습니다."],"bullets":list(facts["drivers"])},
            {"heading":"상·기본·하방 시나리오","paragraphs":["특정 목표가를 제시하지 않고 실적을 바꿀 조건을 구분합니다."],"bullets":[],"scenarios":[{"label":"상방","title":"성장동력의 실적 전환","body":f"{facts['drivers'][0]}이 매출과 영업현금흐름에서 확인"},{"label":"기본","title":"현재 추세 유지","body":"외형과 수익성이 최근 공시 범위에서 점진적으로 움직임"},{"label":"하방","title":"위험요인 현실화","body":f"{facts['risks'][0]}이 비용·수요·자금조달에 반영"}]},
            {"heading":"위험요인과 다음 공시 체크리스트","paragraphs":["위험의 존재보다 실제 지표가 악화되는지를 확인합니다."],"bullets":list(facts["risks"])+list(company["watch"])}
        ],
        "sources": news_sources + [
            {"publisher":"금융감독원 DART","title":f"{company['name']} 정기·주요사항 공시","url":"https://dart.fss.or.kr/dsab002/main.do","published_at":facts["date"]},
            {"publisher":"한국거래소 KIND","title":f"{company['name']} 상장공시·기업정보","url":"https://kind.krx.co.kr/","published_at":facts["date"]},
            {"publisher":"KRX 정보데이터시스템","title":f"{company['name']} 시장·종목 기초정보","url":"https://data.krx.co.kr/","published_at":facts["date"]},
        ],
        "disclaimer":"공개 공시와 감사보고서 수치를 교육·분석 목적으로 재구성한 자료이며 투자 권유가 아닙니다. 최신 정정공시 여부를 원문에서 확인하세요."
    }


def memory_comparison_item() -> dict[str, object]:
    """Citi 전망치를 사실 표로 분리해 재구성한 삼성전자·SK하이닉스 비교판."""
    return {
        "id": "company-memory-citi-20260514", "date": "2026-05-14",
        "eyebrow": "COMPANY · MEMORY COMPARISON", "read_minutes": 12,
        "title": "삼성전자·SK하이닉스 — Citi 메모리 전망 비교",
        "summary": "Citi의 2026년 메모리 가격·실적 가정을 양사의 수익구조, 목표가 산식, 시나리오와 위험요인으로 나눠 비교합니다.",
        "tags": ["삼성전자", "SK하이닉스", "HBM"], "longform": True, "issue_score": 100,
        "easy_explanation": "같은 메모리 호황을 보더라도 SK하이닉스는 HBM 중심의 실적 민감도가 크고, 삼성전자는 사업 다각화와 메모리 이익 집중이 동시에 나타납니다.",
        "market_comment": "아래 값은 2026년 5월 Citi 전망치이지 확정 실적이 아닙니다. 목표가·ASP·이익 전망은 메모리 수요와 공급 가정이 달라지면 크게 변할 수 있으므로 실제 공시와 구분해 읽어야 합니다.",
        "methodology": "Citi Research(2026-05-11)를 인용해 공개된 전망 수치를 항목별로 구조화했습니다. 계산 가능한 비율은 원자료 수치로 교차 계산하고, 기업의 실제 실적은 DART 정기공시에서 별도로 확인하도록 전망과 사실을 분리했습니다.",
        "causal_path": ["AI 추론·토큰 사용 증가", "HBM·서버 DRAM 수요", "메모리 ASP 상승", "매출·영업이익 확대", "밸류에이션 재평가"],
        "metrics": [
            {"label":"SK하이닉스 목표가","value":"310만원","note":"Citi · 기존 170만원"},
            {"label":"삼성전자 목표가","value":"46만원","note":"Citi · 기존 30만원"},
            {"label":"4Q26 HBM 가격","value":"+30%","note":"QoQ 전망"},
            {"label":"2026E DRAM ASP","value":"+200%","note":"YoY · 기존 +190%"}
        ],
        "charts": [
            {"type":"bar","title":"Citi 목표주가 변경","subtitle":"만원 · 2026-05-11 전망","rows":[{"label":"SK하이닉스 기존","value":170,"display":"170만원"},{"label":"SK하이닉스 신규","value":310,"display":"310만원"},{"label":"삼성전자 기존","value":30,"display":"30만원"},{"label":"삼성전자 신규","value":46,"display":"46만원"}],"note":"현재가가 아닌 Citi 목표주가 비교입니다."},
            {"type":"bar","title":"2026E 수익성 비교","subtitle":"% · Citi 전망","rows":[{"label":"SK하이닉스 OPM","value":77.9,"display":"77.9%"},{"label":"삼성전자 OPM","value":46.4,"display":"46.4%"},{"label":"SK하이닉스 ROE","value":94.7,"display":"94.7%"},{"label":"삼성전자 ROE","value":45.2,"display":"45.2%"}]}
        ],
        "sections": [
            {"heading":"전망의 핵심 — 무엇이 바뀌었나","paragraphs":["Citi는 AI 추론용 메모리 수요와 하반기 가격 강세를 근거로 양사 목표가를 함께 올렸습니다. 삼성전자에는 별도로 90일 상승 촉매 관찰 의견을 제시했습니다."],"bullets":["DRAM 연간 ASP +190% → +200%", "NAND 연간 ASP +172% → +186%", "서버 DDR5 ASP +308% → +329%", "4Q26 DRAM QoQ +4% → +11%"],"tables":[{"title":"가격 전망 변경","headers":["항목","5월 전망","4월 전망"],"rows":[["DRAM 연간 ASP","+200%","+190%"],["NAND 연간 ASP","+186%","+172%"],["서버 DDR5 ASP","+329%","+308%"],["SSD ASP","+267%","+242%"],["64GB DDR5 4Q26","$1,586","$1,444"]]}]},
            {"heading":"SK하이닉스 — HBM 중심 이익 레버리지","paragraphs":["Citi 가정에서는 매출보다 영업이익이 더 빠르게 증가합니다. 분기 후반으로 갈수록 DRAM 영업이익률이 높아지는 구조입니다."],"bullets":[],"charts":[{"type":"bar","title":"SK하이닉스 2026E 분기 영업이익","subtitle":"조원 · Citi 전망","rows":[{"label":"1Q26","value":37.6,"display":"37.6조"},{"label":"2Q26E","value":58.9,"display":"58.9조"},{"label":"3Q26E","value":72.3,"display":"72.3조"},{"label":"4Q26E","value":82.4,"display":"82.4조"}]}],"tables":[{"title":"분기별 손익 전망","headers":["분기","총매출","DRAM","NAND","영업이익","DRAM OPM"],"rows":[["1Q26","52.6","41.8","12.0","37.6","76%"],["2Q26E","76.4","56.8","19.4","58.9","81%"],["3Q26E","90.7","67.6","23.0","72.3","83%"],["4Q26E","101.5","76.8","24.5","82.4","84%"]]},{"title":"SOTP 목표가 산식","headers":["사업부","EBITDA","배수","지분가치"],"rows":[["HBM","28.3조","9.5배","269조"],["Commodity 외","238.3조","7.7배","1,835조"],["합산+순현금","-","-","2,239조"],["주당 목표가","-","-","310만원"]]}]},
            {"heading":"삼성전자 — 메모리 이익 집중과 다각화","paragraphs":["Citi 전망상 2026년 전사 영업이익 대부분이 메모리에서 발생합니다. 다각화된 매출 구조와 달리 이익은 메모리 사이클에 민감하다는 뜻입니다."],"bullets":[],"charts":[{"type":"bar","title":"삼성전자 2026E 사업부 영업이익","subtitle":"조원 · Citi 전망","rows":[{"label":"메모리","value":327,"display":"327.0조"},{"label":"시스템 LSI","value":-4.4,"display":"-4.4조"},{"label":"디스플레이","value":2.5,"display":"2.5조"},{"label":"모바일","value":5.4,"display":"5.4조"},{"label":"가전","value":0.04,"display":"0.04조"}]}],"tables":[{"title":"사업부별 손익 전망","headers":["사업부","매출","영업이익","OPM"],"rows":[["반도체","477.8","322.7","67.5%"],["메모리","448.0","327.0","73.0%"],["시스템 LSI","30.8","-4.4","-14.2%"],["디스플레이","33.8","2.5","7.3%"],["모바일","158.7","5.4","3.4%"],["가전","59.7","0.04","0.1%"],["전사","713.5","331.0","46.4%"]]}]},
            {"heading":"양사 비교 — 성장 민감도와 방어력","paragraphs":["SK하이닉스는 HBM과 메모리 가격 상승에 대한 실적 민감도가 더 크고, 삼성전자는 절대 이익 규모와 사업 다각화가 특징입니다. 어느 쪽도 전망치가 확정 실적을 뜻하지 않습니다."],"bullets":[],"tables":[{"title":"2026E 핵심 지표","headers":["지표","SK하이닉스","삼성전자"],"rows":[["기대 수익률","+83.9%","+61.7%"],["P/E","6.0배","7.7배"],["P/B","3.9배","2.8배"],["ROE","94.7%","45.2%"],["영업이익","251조","331조"],["OPM","77.9%","46.4%"],["단기 촉매 관찰","없음","90일 Upside"]]}]},
            {"heading":"상·기본·하방 시나리오","paragraphs":["목표가는 메모리 ASP와 제품 믹스 가정에 따라 크게 달라집니다."],"bullets":[],"scenarios":[{"label":"상방","title":"SK 380만원 · 삼성 54만원","body":"AI 메모리 수요와 가격 강세가 예상보다 오래 지속"},{"label":"기본","title":"SK 310만원 · 삼성 46만원","body":"Citi의 기준 ASP와 제품 믹스 가정"},{"label":"하방","title":"SK 140만원 · 삼성 20만원","body":"업사이클 조기 종료와 경쟁 공급 확대"}]},
            {"heading":"위험요인과 검증 체크리스트","paragraphs":["가장 중요한 가정은 AI 서비스의 사용량 증가가 실제 메모리 구매로 이어지는지입니다."],"bullets":["AI 투자·토큰 수요 둔화", "Micron·중국 업체의 공급 확대", "원화 강세에 따른 환산 실적 감소", "스마트폰·PC 수요 둔화", "분기별 HBM 출하·가격과 재고일수 확인"],"tables":[{"title":"위험 강도","headers":["위험","강도","확인값"],"rows":[["AI 수요 둔화","매우 높음","데이터센터 CAPEX·HBM 주문"],["업사이클 조기 종료","높음","재고·공급 증가율"],["환율","중간","원/달러와 환헤지"],["중국 메모리","중간","증설·시장점유율"],["경기 둔화","중간","PC·모바일 출하량"]]}]}
        ],
        "sources": [
            {"publisher":"Citi Research","title":"Memory sector research (2026-05-11) — 공개 인용 전망치","url":"https://gjbuffet.kr/companies/2026-05-14_samsung-skhynix-citi.html","published_at":"2026-05-11"},
            {"publisher":"삼성전자 IR","title":"삼성전자 실적발표·사업보고서","url":"https://www.samsung.com/global/ir/","published_at":"2026-05-14"},
            {"publisher":"SK하이닉스 IR","title":"SK하이닉스 실적발표·사업보고서","url":"https://news.skhynix.co.kr/ir/","published_at":"2026-05-14"},
            {"publisher":"금융감독원 DART","title":"삼성전자·SK하이닉스 정기공시 확인","url":"https://dart.fss.or.kr/dsab002/main.do","published_at":"2026-05-14"}
        ],
        "disclaimer":"Citi 전망치를 교육·비교 목적으로 재구성한 자료이며 투자 권유가 아닙니다. 전망치와 실제 공시 실적을 반드시 구분하세요."
    }


def analysis_item(theme: dict[str, object], matches: list[dict[str, object]]) -> dict[str, object]:
    sources = unique_sources(matches, 8)
    newest = max(str(item.get("date", "")) for item in matches)
    publishers = len({source["publisher"] for source in sources})
    issue_titles = [source["title"] for source in sources[:5]]
    digest = hashlib.sha1(f"{theme['name']}|{newest}|{'|'.join(issue_titles)}".encode()).hexdigest()[:10]
    return {
        "id": f"analysis-auto-{newest.replace('-', '')}-{digest}", "date": newest,
        "eyebrow": f"DEEP DIVE · {theme['name']}", "read_minutes": 7,
        "title": str(theme["title"]),
        "summary": f"최근 {len(matches)}건·{publishers}개 매체의 보도를 한 주제로 묶어 원인, 전파경로, 반대 시나리오를 나눴습니다.",
        "tags": [str(theme["name"]), "이슈클러스터", "시나리오"], "longform": True,
        "causal_path": [part.strip() for part in str(theme["path"]).split("→")],
        "charts": coverage_charts(matches, sources),
        "methodology": "최근 뉴스에서 주제 핵심어를 검색해 사건 단위로 묶고, 발행처와 제목의 중복을 줄였습니다. 보도량·출처 구성은 사실 확인의 폭을 보여주며, 방향 전망은 공식 통계와 기업 공시로 검증할 조건부 시나리오로 분리했습니다.",
        "easy_explanation": f"핵심 흐름은 ‘{theme['path']}’입니다. 중간 단계가 실제 데이터로 확인되지 않으면 첫 뉴스가 커도 최종 영향은 제한될 수 있습니다.",
        "market_comment": "한두 개 기사보다 여러 매체가 같은 사실을 독립적으로 확인하는지 봐야 합니다. 단기 시장가격은 기대에 먼저 움직이고 실물경제와 기업실적은 늦게 반영됩니다. 부동산은 서울 핵심지, 수도권 외곽, 지방의 공급·대출·일자리 조건이 달라 같은 결론을 적용하면 안 됩니다.",
        "metrics": [{"label": "관련 기사", "value": f"{len(matches)}건", "note": "최근 수집 기간"}, {"label": "확인 매체", "value": f"{publishers}곳", "note": "중복 제외"}, {"label": "이슈 점수", "value": f"{score(matches, sources)}/100", "note": "빈도·매체·수치 기반"}],
        "sections": [
            {"heading": "한 줄로 이해하기 — 지금 왜 중요한가", "paragraphs": [f"{theme['name']} 관련 보도가 여러 매체에서 반복되고 있습니다. 기사 수보다 실제 정책·공시·통계가 같은 방향인지 확인하는 것이 핵심입니다."], "bullets": []},
            {"heading": "무슨 일이 있었나 — 핵심 보도 묶음", "paragraphs": ["동일 사건의 단순 전재를 줄이고 서로 다른 매체·관점의 제목을 우선했습니다."], "bullets": issue_titles},
            {"heading": "어떻게 시장으로 전달되나", "paragraphs": [str(theme["path"])], "bullets": ["뉴스와 기대가 먼저 가격에 반영", "정책·수주·투자가 실제 집행되는지 확인", "매출·물가·고용·주택수급 같은 후행 데이터로 검증"]},
            {"heading": "자산과 지역별 영향 — 같은 뉴스도 결과는 다르다", "paragraphs": ["주식은 기대와 할인율에 먼저 반응하고, 채권·환율은 금리와 자금 흐름을 반영합니다. 부동산은 거래량과 대출 여건을 거쳐 늦게 움직입니다."], "bullets": ["서울 핵심지: 희소성과 고가주택 대출·세제 변화", "수도권 외곽: 입주물량·교통·실수요 대출", "지방: 일자리·미분양·지역별 공급 부담을 별도로 확인"]},
            {"heading": "상승·중립·하락 시나리오", "paragraphs": ["조건별로 결론이 달라질 수 있습니다."], "bullets": [], "scenarios": [
                {"label": "상방", "title": "수요와 실적 동행", "body": "수요 증가와 공급 제약이 공식 통계·실적에서 동시에 확인"},
                {"label": "중립", "title": "집행 지연", "body": "발표는 크지만 집행·수주·착공이 늦어 실제 영향은 제한"},
                {"label": "하방", "title": "비용·수요 역풍", "body": "비용 상승, 수요 둔화 또는 정책 변경이 기대를 상쇄"},
            ]},
            {"heading": "앞으로 확인할 데이터", "paragraphs": ["다음 순서로 확인하면 기사와 실제 변화를 구분하기 쉽습니다."], "bullets": ["정부·중앙은행·거래소의 공식 발표", "기업 DART 공시와 현금흐름", "이 사이트의 금리·환율·원자재·주가지수", "부동산 주제는 거래량·입주물량·지역별 가격"]},
        ],
        "sources": sources,
        "disclaimer": "여러 공개 뉴스의 제목·요약을 주제별로 재구성한 자동 심층 브리핑이며 투자 권유가 아닙니다. 세부 수치와 발언은 연결된 원문을 확인하세요.",
        "issue_score": score(matches, sources),
    }


def build(days: int, company_limit: int, analysis_limit: int) -> dict[str, object]:
    news = load_news(days)
    dart_key = os.environ.get("DART_API_KEY", "").strip()
    try:
        corp_codes = dart_corp_codes(dart_key)
    except Exception as error:
        print(f"DART 기업코드 수집 실패: {error}")
        corp_codes = {}
    company_items = [memory_comparison_item()]
    for company in COMPANIES:
        matches = [item for item in news if any(alias.lower() in f"{item.get('title', '')} {item.get('summary', '')}".lower() for alias in company["aliases"])]
        report = curated_company_item(company, matches) if company["name"] in COMPANY_FACTS else company_item(company, matches)
        try:
            report["sources"] = dart_latest_sources(str(company["name"]), corp_codes.get(str(company["name"]), ""), dart_key) + list(report.get("sources") or [])
        except Exception as error:
            print(f"{company['name']} DART 공시 수집 실패: {error}")
        company_items.append(report)
    analysis_items = []
    for theme in THEMES:
        matches = [item for item in news if any(keyword.lower() in f"{item.get('title', '')} {item.get('summary', '')}".lower() for keyword in theme["keywords"])]
        if len(matches) >= 4 and len(unique_sources(matches)) >= 3:
            analysis_items.append(analysis_item(theme, matches))
    company_items.sort(key=lambda item: (item["issue_score"], item["date"]), reverse=True)
    analysis_items.sort(key=lambda item: (item["date"], item["issue_score"]), reverse=True)
    company_items = [research_contract(item, "company_analysis") for item in company_items[:company_limit]]
    analysis_items = [research_contract(item, "deep_dive") for item in analysis_items[:analysis_limit]]
    try:
        previous = json.loads(INDEX_PATH.read_text(encoding="utf-8")) if INDEX_PATH.exists() else {}
    except (OSError, ValueError, json.JSONDecodeError):
        previous = {}
    daily = daily_company_selection(company_items, previous)
    return {"schema_version": 2, "generation_policy":"공개 원자료 우선 · 타 사이트 문장/그래픽 비복제 · 사실/분석 분리", "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"), "lookback_days": days, "daily_company_selection":daily["selection"], "daily_company_history":daily["history"], "company_items": company_items, "analysis_items": analysis_items}


def main() -> None:
    parser = argparse.ArgumentParser(description="수집된 경제뉴스에서 주요 기업·심층 이슈 브리핑을 생성합니다.")
    parser.add_argument("--lookback-days", type=int, default=45)
    parser.add_argument("--company-limit", type=int, default=20)
    parser.add_argument("--analysis-limit", type=int, default=20)
    args = parser.parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build(max(7, min(args.lookback_days, 365)), max(3, min(args.company_limit, 50)), max(3, min(args.analysis_limit, 50)))
    INDEX_PATH.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"자동 분석 생성 완료: 기업 {len(payload['company_items'])}건, 심층 {len(payload['analysis_items'])}건")


if __name__ == "__main__":
    main()
