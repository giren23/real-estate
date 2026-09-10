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

INVESTMENT_TAGS = {"증시", "주식", "금리·채권", "환율", "원자재", "가상자산", "산업", "기업", "반도체", "경제정책"}
INVESTMENT_KEYWORDS = (
    "금리", "연준", "중앙은행", "증시", "코스피", "코스닥", "나스닥", "s&p", "다우",
    "주가", "주식", "채권", "국채", "환율", "달러", "원화", "엔화", "유가", "원유",
    "금값", "구리", "반도체", "비트코인", "etf", "실적", "수출", "물가", "고용",
    "gdp", "경기", "관세", "무역", "투자", "대출", "모기지",
)
NOISE_KEYWORDS = ("화재", "사망", "숨져", "대피", "홍수", "사고", "범죄", "실종")


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
    sections = [
        {
            "id": "world", "title": "세계 정세 약식 총평", "subtitle": "위험선호·환율·원자재 동시 점검",
            "summary": f"{regime}. 미국 S&P 500은 {sp500['value']} ({sp500['change']}), KOSPI는 {kospi['value']} ({kospi['change']})로 확인됩니다.",
            "metrics": metrics(("sp500", "kospi", "krw_usd", "us10y", "wti", "gold")), "checks": checks,
            "scenarios": [
                {"label": "상방", "title": "위험선호 확산", "body": "주요 지수 상승과 원화 안정이 함께 이어지는지 확인합니다."},
                {"label": "중립", "title": "지수별 차별화", "body": "지수보다 실적·수급이 강한 종목만 선별합니다."},
                {"label": "하방", "title": "금리·유가 부담", "body": "금리와 유가 동반 상승 시 변동성 확대에 대비합니다."},
            ], "news": [news_card(row) for row in selected[:4]],
        },
        {
            "id": "us", "title": "미국장", "subtitle": "미국장 주요 핵심 총평",
            "summary": f"S&P 500과 NASDAQ의 전일 방향, 미국 10년물 금리와 유가를 함께 확인합니다. {stance}",
            "metrics": metrics(("sp500", "nasdaq", "dow", "us10y", "gold", "wti")),
            "checks": [checks[1], f"WTI {metric(items.get('wti'))['value']} ({metric(items.get('wti'))['change']}) — 유가 급등은 물가·금리 경로를 다시 자극할 수 있습니다."],
            "scenarios": [], "news": section_news(rows, ("미국", "연준", "fomc", "나스닥", "s&p", "금리"), 0),
        },
        {
            "id": "kr", "title": "한국장", "subtitle": "한국장 주요 핵심 총평",
            "summary": f"KOSPI {kospi['value']} ({kospi['change']}), KOSDAQ {kosdaq['value']} — 원·달러와 외국인 수급을 함께 점검합니다.",
            "metrics": metrics(("kospi", "kosdaq", "krw_usd", "kr_10y")),
            "checks": [checks[0], "반도체·수출주 뉴스가 지수 상승을 실제 거래 확산으로 연결하는지 확인합니다."],
            "scenarios": [], "news": section_news(rows, ("한국", "코스피", "코스닥", "삼성", "하이닉스", "수출"), 3),
        },
    ]
    return {
        "schema_version": 3, "date": day,
        "generated_at": datetime.now(SEOUL).isoformat(timespec="seconds"),
        "title": f"{observed.year}년 {observed.month}월 {observed.day}일 {weekdays[observed.weekday()]} 아침 — 전수 스캔 투자 브리핑",
        "format": "deterministic-morning",
        "summary": "시장 스냅샷과 당일 뉴스 보관본을 규칙 기반으로 결합한 오전 브리핑입니다. 생성 과정에 GPT 호출을 사용하지 않습니다.",
        "sections": sections,
        "disclaimer": "공개 데이터의 기준일·시차에 따라 값이 다를 수 있습니다. 자동 생성 참고자료이며 투자 권유가 아닙니다.",
    }


def rebuild_index() -> dict:
    files = sorted(OUTPUT_DIR.glob("????-??-??.json"), reverse=True)
    pages = []
    for path in files:
        payload = read_json(path, {})
        if isinstance(payload, dict) and payload.get("date"):
            pages.append({"date": payload["date"], "title": payload.get("title", path.stem), "file": path.name})
    index = {"schema_version": 1, "updated_at": datetime.now(SEOUL).isoformat(timespec="seconds"), "pages": pages}
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description="GPT 호출 없이 날짜별 오전 투자 브리핑 생성")
    parser.add_argument("--date", help="YYYY-MM-DD, 기본값은 한국시간 오늘")
    args = parser.parse_args()
    day = args.date or datetime.now(SEOUL).strftime("%Y-%m-%d")
    datetime.strptime(day, "%Y-%m-%d")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_payload(day)
    (OUTPUT_DIR / f"{day}.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    index = rebuild_index()
    print(f"오늘의 투자 브리핑 생성 완료: {day}, 보관 {len(index['pages'])}일, GPT 호출 없음")


if __name__ == "__main__":
    main()
