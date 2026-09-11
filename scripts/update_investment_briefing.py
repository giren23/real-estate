from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
MARKET_PATH = ROOT / "data" / "public" / "market_snapshot.json"
NEWS_INDEX_PATH = ROOT / "web" / "content" / "news" / "index.json"
NEWS_DIR = ROOT / "web" / "content" / "news"
OUTPUT_DIR = ROOT / "web" / "content" / "investment-briefing"
INDEX_PATH = OUTPUT_DIR / "index.json"
SEOUL = ZoneInfo("Asia/Seoul")
# The user requested a clean restart from this morning's report.
ARCHIVE_START_DATE = "2026-09-11"

INVESTMENT_TAGS = {"증시", "주식", "금리·채권", "환율", "원자재", "가상자산", "산업", "기업", "반도체", "경제정책"}
INVESTMENT_KEYWORDS = (
    "금리", "연준", "중앙은행", "증시", "코스피", "코스닥", "나스닥", "s&p", "다우",
    "주가", "주식", "채권", "국채", "환율", "달러", "원화", "엔화", "유가", "원유",
    "금값", "구리", "반도체", "비트코인", "etf", "실적", "수출", "물가", "고용",
    "gdp", "경기", "관세", "무역", "투자", "대출", "모기지",
)
NOISE_KEYWORDS = ("화재", "사망", "숨져", "대피", "홍수", "사고", "범죄", "실종")

# Wording contract for the no-AI briefing:
# - "체결·공시·발표" is reserved for a source that identifies the actor and
#   action; the related party, amount, product, and period are included only
#   when the source itself provides them.
# - Everything else is a monitoring condition, never an implied confirmation.
FACT_LANGUAGE_RULE = (
    "‘체결·공시·발표’는 원문에 주체와 행위가 명시된 사실에만 사용합니다. "
    "상대방·규모·품목·기간은 원문에 있는 경우에만 함께 적습니다. "
    "그 밖의 ‘수요·수주·가격·수급’은 확정 사실이 아니라 관찰할 지표로 표기합니다."
)


def read_json(path: Path, fallback: object) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return fallback


def number(value: object, digits: int = 2) -> str:
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def signed(value: object, unit: str = "%") -> str:
    try:
        return f"{float(value):+.2f}{unit}"
    except (TypeError, ValueError):
        return "—"


def item_map(market: dict) -> dict[str, dict]:
    return {
        str(item.get("key")): item
        for category in market.get("categories", [])
        for item in category.get("items", [])
        if item.get("key")
    }


def metric(item: dict | None, change_key: str = "day") -> dict:
    if not item:
        return {"label": "자료 준비 중", "value": "—", "change": "—", "date": "—", "tone": "flat"}
    changes = item.get("changes") or {}
    change = changes.get(change_key)
    try:
        tone = "up" if float(change) > 0 else "down" if float(change) < 0 else "flat"
    except (TypeError, ValueError):
        tone = "flat"
    return {
        "label": item.get("label", "—"),
        "value": f"{number(item.get('value'), 2)}{item.get('unit', '')}",
        "change": signed(change, item.get("change_unit", "%")),
        "date": item.get("date", "—"),
        "tone": tone,
    }


def interpretation(items: dict[str, dict]) -> tuple[str, str, list[str]]:
    values = []
    for key in ("kospi", "sp500", "nasdaq"):
        try:
            values.append(float((items.get(key) or {}).get("changes", {}).get("day")))
        except (TypeError, ValueError):
            continue
    positive = sum(value > 0 for value in values)
    if values and positive >= 2:
        regime = "주요 지수의 위험선호가 비교적 넓게 이어지는 아침"
        stance = "추격 매수보다 상승 폭과 거래 확산을 확인하며 분할 접근할 구간입니다."
    elif values and positive == 0:
        regime = "주요 지수의 위험회피가 겹친 아침"
        stance = "신규 비중 확대보다 현금·손실 한도와 보유 종목의 지지선을 먼저 점검할 구간입니다."
    else:
        regime = "시장별 방향이 엇갈려 선별 확인이 필요한 아침"
        stance = "지수 방향보다 실적·수급이 확인되는 종목 중심으로 조건을 좁혀 볼 구간입니다."
    checks = [
        f"원·달러 {metric(items.get('krw_usd'))['value']} ({metric(items.get('krw_usd'))['change']}) — 원화 약세가 확대되면 외국인 수급 부담을 점검합니다.",
        f"미국 10년물 {metric(items.get('us10y'))['value']} ({metric(items.get('us10y'))['change']}) — 금리 상승 시 성장주 할인율 부담을 확인합니다.",
        f"금 {metric(items.get('gold'))['value']} ({metric(items.get('gold'))['change']}) — 주가와 금이 함께 강한지, 안전자산만 강한지 구분합니다.",
    ]
    return regime, stance, checks


def select_investment_news(rows: list[dict], limit: int = 6) -> list[dict]:
    scored: list[tuple[int, int, dict]] = []
    for position, row in enumerate(rows):
        title = str(row.get("title", ""))
        lowered = title.lower()
        score = min(6, sum(2 for keyword in INVESTMENT_KEYWORDS if keyword in lowered))
        if set(row.get("tags") or []) & INVESTMENT_TAGS:
            score += 2
        if any(keyword in lowered for keyword in NOISE_KEYWORDS):
            score -= 8
        if score >= 2:
            scored.append((score, -position, row))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    selected: list[dict] = []
    fingerprints: set[str] = set()
    for _, _, row in scored:
        fingerprint = "".join(ch for ch in str(row.get("title", "")).lower() if ch.isalnum())[:24]
        if not fingerprint or fingerprint in fingerprints:
            continue
        fingerprints.add(fingerprint)
        selected.append(row)
        if len(selected) == limit:
            break
    return selected


def news_rows(day: str) -> list[dict]:
    archive = read_json(NEWS_DIR / f"{day}.json", {})
    if isinstance(archive, dict) and isinstance(archive.get("items"), list):
        return [row for row in archive["items"] if isinstance(row, dict)]
    index = read_json(NEWS_INDEX_PATH, {})
    if isinstance(index, dict) and isinstance(index.get("items"), list):
        return [row for row in index["items"] if isinstance(row, dict) and row.get("date") == day]
    return []


def news_card(row: dict) -> dict:
    source = next((source for source in row.get("sources", []) if source.get("url")), {})
    article_summary = row.get("article_summary")
    if isinstance(article_summary, list):
        summary = next((str(text) for text in article_summary if str(text).strip()), "")
    else:
        summary = str(row.get("core_summary") or row.get("summary") or "")
    return {
        "title": str(row.get("title") or "제목 확인 필요"),
        "summary": summary,
        "publisher": str(row.get("publisher") or source.get("publisher") or "출처 미상"),
        "url": source.get("url") or row.get("url") or "",
        "important": bool(row.get("important")),
    }


def section_news(rows: list[dict], terms: tuple[str, ...], fallback_offset: int = 0) -> list[dict]:
    matching = [row for row in rows if any(term in str(row.get("title", "")).lower() for term in terms)]
    chosen = select_investment_news(matching, 3)
    if not chosen:
        chosen = select_investment_news(rows, 6)[fallback_offset:fallback_offset + 3]
    return [news_card(row) for row in chosen]


def build_payload(day: str) -> dict:
    observed = datetime.strptime(day, "%Y-%m-%d")
    weekdays = ("월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일")
    market = read_json(MARKET_PATH, {})
    market = market if isinstance(market, dict) else {}
    items = item_map(market)
    regime, stance, checks = interpretation(items)
    rows = news_rows(day)
    selected = select_investment_news(rows)

    def metrics(keys: tuple[str, ...]) -> list[dict]:
        return [metric(items.get(key)) for key in keys]

    sp500, kospi, kosdaq = metric(items.get("sp500")), metric(items.get("kospi")), metric(items.get("kosdaq"))
    # This mirrors the report order used in the "아침 저녁 투자 브리핑" chat.
    # Every statement is derived from the market snapshot or selected news; no
    # price target, ranking, or forecast is fabricated by this static job.
    us10y, wti, krw = metric(items.get("us10y")), metric(items.get("wti")), metric(items.get("krw_usd"))
    sections = [
        {
            "id": "verdict", "title": "1. 오늘 한 줄 결론", "subtitle": "아침 브리핑의 핵심 판단",
            "summary": f"{regime}. {stance}",
            "details": [
                f"간밤 S&P 500은 {sp500['value']} ({sp500['change']}), NASDAQ은 {metric(items.get('nasdaq'))['value']} ({metric(items.get('nasdaq'))['change']})로 마감했습니다.",
                f"국내 기준점인 KOSPI는 {kospi['value']} ({kospi['change']})입니다. 오늘은 지수보다 금리·유가·환율 변화가 업종별 방향을 가를 가능성을 먼저 점검합니다.",
            ],
            "metrics": metrics(("sp500", "kospi", "krw_usd", "us10y", "wti", "gold")), "checks": checks,
            "scenarios": [
                {"label": "상방", "title": "위험선호 확산", "body": "주요 지수 상승과 원화 안정이 함께 이어지는지 확인합니다."},
                {"label": "중립", "title": "지수별 차별화", "body": "지수보다 실적·수급이 강한 종목만 선별합니다."},
                {"label": "하방", "title": "금리·유가 부담", "body": "금리와 유가 동반 상승 시 변동성 확대에 대비합니다."},
            ], "news": [],
        },
        {
            "id": "us", "title": "2. 미국시장 핵심", "subtitle": "지수·금리·유가·물가 경로",
            "summary": "미국 주가지수만 보지 않고 장기금리와 원유 가격을 함께 읽습니다.",
            "details": [
                f"미국 10년물 국채금리는 {us10y['value']} ({us10y['change']})입니다. 금리가 오르면 미래 이익 비중이 큰 성장주의 할인율 부담이 커질 수 있습니다.",
                f"WTI 원유는 {wti['value']} ({wti['change']})입니다. 유가 변화는 물가와 미국 연방준비제도(Fed·연준)의 금리 경로에 연결되므로 단독으로 해석하지 않습니다.",
            ],
            "metrics": metrics(("sp500", "nasdaq", "dow", "us10y", "gold", "wti")),
            "checks": [checks[1], f"WTI {metric(items.get('wti'))['value']} ({metric(items.get('wti'))['change']}) — 유가 급등은 물가·금리 경로를 다시 자극할 수 있습니다."],
            "scenarios": [], "news": section_news(rows, ("미국", "연준", "fomc", "나스닥", "s&p", "금리"), 0)[:2],
        },
        {
            "id": "kr", "title": "3. 오늘 한국시장", "subtitle": "개장 전 환율·수급·업종 점검",
            "summary": f"KOSPI {kospi['value']} ({kospi['change']}), KOSDAQ {kosdaq['value']}입니다.",
            "details": [
                f"원·달러는 {krw['value']} ({krw['change']})입니다. 원화 약세가 이어지는지와 외국인 현물·선물 수급을 함께 확인합니다.",
                "개장 직후 등락만으로 결론을 내리지 않고, 반도체·수출주·금융 등 주요 업종으로 거래가 확산되는지 확인한 뒤 판단합니다.",
            ],
            "metrics": metrics(("kospi", "kosdaq", "krw_usd", "kr_10y")),
            "checks": [checks[0], "반도체·수출주 뉴스가 지수 상승을 실제 거래 확산으로 연결하는지 확인합니다."],
            "scenarios": [], "news": section_news(rows, ("한국", "코스피", "코스닥", "삼성", "하이닉스", "수출"), 3)[:2],
        },
        {
            "id": "sectors", "title": "4. 섹터·기업 체크", "subtitle": "사실과 관찰 항목을 구분한 업종별 촉매·위험",
            "summary": "기사의 확정 사실과 앞으로 관찰할 조건을 구분해 섹터의 촉매·위험을 정리합니다.",
            "details": [
                "반도체, 에너지, 금융 등은 같은 지수 안에서도 금리·유가·환율에 대한 민감도가 다릅니다. 기사 제목만으로 실적이나 목표주가를 추정하지 않습니다.",
                "기업이 등장할 때는 사업과 주력 제품을 함께 표기하고, HBM(고대역폭메모리)·CPI(미국 소비자물가지수)처럼 약어는 첫 등장 시 뜻을 풀어 씁니다.",
                FACT_LANGUAGE_RULE,
            ],
            "metrics": [], "checks": ["개별 기업 이슈는 ‘누가·무엇을·언제·얼마에·어떤 방식으로 했는지’가 원문 또는 공시에 나타난 경우에만 확정 사실로 읽습니다."],
            "scenarios": [], "news": [news_card(row) for row in selected[:3]],
        },
        {
            "id": "kr-top5", "title": "5. 한국장 관심종목 TOP 5", "subtitle": "AI 메모리·전력 인프라 중심의 일일 관찰 목록",
            "summary": "당일 매수 추천 순위가 아니라, 아침 브리핑에서 실적·수급·뉴스를 함께 확인할 한국 상장 핵심 종목입니다.",
            "details": ["순위는 자동매매 신호가 아니며, 개장 뒤 지수·환율·외국인 수급과 각 회사의 공시·실적을 확인해 해석합니다."],
            "rankings": [{"market": "한국", "items": [
                {"name": "SK하이닉스", "description": "메모리 반도체·SSD / 주력: HBM·DRAM", "reason": "관찰: AI 서버 출하·고객사 설비투자, HBM 공급량·계약가격"},
                {"name": "삼성전자", "description": "반도체·스마트폰·가전 / 주력: 메모리반도체", "reason": "관찰: 메모리 가격, HBM 제품 경쟁력, 외국인 순매수"},
                {"name": "한미반도체", "description": "반도체 장비 / 주력: HBM 후공정 장비", "reason": "관찰: 고객사의 HBM 증설 발표 후 장비 발주·수주 공시"},
                {"name": "HD현대일렉트릭", "description": "전력기기 / 주력: 변압기·송배전 장비", "reason": "관찰: 데이터센터·전력망 투자와 수주 공시의 상대방·금액·납기"},
                {"name": "두산에너빌리티", "description": "발전설비 / 주력: 원전·가스터빈", "reason": "관찰: 원전·가스터빈 수주의 발주처·품목·계약금액·기간 공시"}
            ]}], "metrics": [], "checks": ["각 종목은 일일 관심 목록입니다. 수요·수주가 ‘확정’으로 쓰일 때에는 계약 상대방, 품목, 금액·수량, 기간 중 원문에 공개된 항목을 함께 제시합니다."], "scenarios": [], "news": [],
        },
        {
            "id": "us-top5", "title": "6. 미국장 관심종목 TOP 5", "subtitle": "AI·반도체·전력 인프라 중심의 일일 관찰 목록",
            "summary": "미국 장에서는 실적, 장기금리, AI 설비투자 지속성의 세 가지를 함께 점검합니다.",
            "details": ["기업명마다 주력 사업을 함께 표시해, 종목의 테마가 아니라 실제 수익원과 연결해 읽을 수 있게 구성합니다."],
            "rankings": [{"market": "미국", "items": [
                {"name": "Microsoft", "description": "클라우드·소프트웨어·AI / 주력: Azure·Microsoft 365", "reason": "관찰: Azure AI 매출, 데이터센터 투자 발표, 자본지출"},
                {"name": "Broadcom", "description": "반도체·인프라 소프트웨어 / 주력: AI ASIC·네트워킹", "reason": "관찰: 고객사 AI ASIC 양산·주문과 네트워크 매출"},
                {"name": "GE Vernova", "description": "발전·전력망 장비 / 주력: 가스터빈·전력망 설비", "reason": "관찰: 데이터센터 전력 수요와 수주 발표의 발주처·금액·납기"},
                {"name": "ASML", "description": "반도체 장비 / 주력: EUV 노광장비", "reason": "관찰: 고객사의 첨단 반도체 설비투자와 장비 수주잔고"},
                {"name": "NVIDIA", "description": "AI·그래픽 반도체 / 주력: AI GPU", "reason": "관찰: AI 서버 주문·출하와 장기금리 변화에 따른 밸류에이션"}
            ]}], "metrics": [], "checks": ["달러 기준 종목은 환율 변동과 미국 장기금리 상승에 따른 밸류에이션 변화를 함께 확인합니다."], "scenarios": [], "news": [],
        },
        {
            "id": "hynix", "title": "7. SK하이닉스 별도 분석", "subtitle": "사용자 관심종목 · HBM·DRAM의 핵심 관찰 항목",
            "summary": "SK하이닉스(메모리 반도체·SSD / 주력: HBM·DRAM)는 AI 메모리 수요의 핵심 지표로 별도 추적합니다.",
            "details": [
                "긍정 요인은 HBM(고대역폭메모리) 공급 제약, AI 데이터센터 투자, 서버 DRAM 가격·출하 흐름입니다. 반대로 미국 장기금리 상승과 메모리 가격 둔화, 경쟁사의 HBM 공급 확대는 단기 위험입니다.",
                "매일 시가만 보지 않고 미국 반도체 흐름, 외국인 수급, HBM 관련 공시·고객 투자 뉴스가 같은 방향인지 확인합니다. 근거 없는 목표가나 매매 신호는 제시하지 않습니다.",
            ],
            "rankings": [{"market": "핵심 확인 순서", "items": [
                {"name": "① 미국 반도체", "description": "NASDAQ·반도체 지수·메모리 기업 흐름", "reason": "관찰: 한국 장 시작 전 글로벌 위험선호"},
                {"name": "② HBM 수요", "description": "AI 서버·고객사 CAPEX(설비투자)", "reason": "관찰: 고객사 투자 발표·서버 출하·메모리 주문"},
                {"name": "③ 외국인 수급", "description": "현물·선물 동향", "reason": "관찰: 단기 변동성과 추세"},
                {"name": "④ 메모리 가격", "description": "DRAM·NAND 현물·계약 가격", "reason": "관찰: 계약가격·출하량으로 보는 업황 전환"},
                {"name": "⑤ 경쟁 구도", "description": "삼성전자·Micron의 HBM 공급", "reason": "관찰: 공급량·고객 인증·점유율 변화"}
            ]}], "metrics": [], "checks": ["수요나 수주를 확정 사실로 표기하려면 고객사·제품·수량 또는 계약금액·기간이 공개된 공시·발표를 근거로 합니다. 그 전에는 관찰 항목입니다."], "scenarios": [], "news": section_news(rows, ("하이닉스", "hbm", "메모리", "dram"), 0)[:2],
        },
        {
            "id": "risk", "title": "8. 오늘 가장 중요한 위험", "subtitle": "우선순위대로 보는 경보 신호",
            "summary": "유가, 장기금리, 환율, 주요 경제지표 발표, 수급을 같은 순서로 추적합니다.",
            "details": [
                f"현재 수치에서는 유가 {wti['value']}, 미국 10년물 {us10y['value']}, 원·달러 {krw['value']}의 동반 변화를 우선 확인합니다.",
                "세 지표가 동시에 위험회피 방향으로 움직이면 고평가 성장주와 변동성이 큰 종목의 손실 한도를 먼저 점검합니다.",
            ],
            "metrics": metrics(("wti", "us10y", "krw_usd", "gold")),
            "checks": ["경제지표 발표 전후에는 가격 급변을 추격하지 않고, 실제 발표치와 시장 반응을 분리해서 확인합니다."],
            "scenarios": [], "news": [],
        },
        {
            "id": "action", "title": "9. 오늘의 실행 체크리스트", "subtitle": "브리핑을 매매 전 점검으로 바꾸는 순서",
            "summary": "예측보다 조건 확인을 우선합니다. 아래 항목은 투자 권유가 아닌 일일 점검 기준입니다.",
            "details": [
                "① 유가 → ② 미국 10년물 → ③ NASDAQ·반도체 지수 → ④ 원·달러 → ⑤ 외국인 수급 순서로 확인합니다.",
                "상방에서는 거래 확산과 환율 안정을, 하방에서는 금리·유가 동반 상승과 지지선 이탈을 확인합니다. 어느 경우에도 한 번의 장중 움직임만으로 비중을 크게 바꾸지 않습니다.",
            ],
            "metrics": [], "checks": ["보유 종목의 실적·공시·손실 한도를 먼저 확인합니다.", "원문이 미확인된 뉴스는 제목이나 2차 보도만으로 매매 근거로 사용하지 않습니다."],
            "scenarios": [], "news": [],
        },
    ]
    return {
        "schema_version": 4, "date": day,
        "generated_at": datetime.now(SEOUL).isoformat(timespec="seconds"),
        "title": f"{observed.year}년 {observed.month}월 {observed.day}일 {weekdays[observed.weekday()]} 아침 투자 브리핑",
        "format": "free-rule-based-morning",
        "summary": "공개 시장 수치·원문 접근 가능 뉴스·고정 점수 규칙으로 작성한 무료 자동 아침 투자 브리핑입니다. 사실은 공시·발표·체결처럼 행위와 근거가 있는 경우에만 확정 표현으로 쓰며, 나머지는 관찰 조건으로 표시합니다.",
        "sections": sections,
        "disclaimer": "공개 데이터의 기준일·시차에 따라 값이 다를 수 있습니다. 자동 생성 참고자료이며 투자 권유가 아닙니다.",
    }


def rebuild_index() -> dict:
    files = sorted((path for path in OUTPUT_DIR.glob("????-??-??.json") if path.stem >= ARCHIVE_START_DATE), reverse=True)
    pages = []
    for path in files:
        payload = read_json(path, {})
        if isinstance(payload, dict) and payload.get("date"):
            pages.append({"date": payload["date"], "title": payload.get("title", path.stem), "file": path.name})
    index = {"schema_version": 1, "updated_at": datetime.now(SEOUL).isoformat(timespec="seconds"), "pages": pages}
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return index


def prune_old_archives() -> int:
    """Keep the user-requested briefing history only from the archive start."""
    removed = 0
    for path in OUTPUT_DIR.glob("????-??-??.json"):
        if path.stem < ARCHIVE_START_DATE:
            path.unlink()
            removed += 1
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description="무료 규칙형 날짜별 오전 투자 브리핑 생성")
    parser.add_argument("--date", help="YYYY-MM-DD, 기본값은 한국시간 오늘")
    args = parser.parse_args()
    day = args.date or datetime.now(SEOUL).strftime("%Y-%m-%d")
    datetime.strptime(day, "%Y-%m-%d")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    removed = prune_old_archives()
    payload = build_payload(day)
    (OUTPUT_DIR / f"{day}.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    index = rebuild_index()
    print(f"오늘의 투자 브리핑 생성 완료: {day}, 보관 {len(index['pages'])}일, 이전 보관 정리 {removed}개, GPT 호출 없음")


if __name__ == "__main__":
    main()
