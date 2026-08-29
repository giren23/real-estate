from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
MARKET_PATH = ROOT / "data" / "public" / "market_snapshot.json"
NEWS_PATH = ROOT / "web" / "content" / "news" / "index.json"
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


def number(value: object, digits: int = 2) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{numeric:,.{digits}f}"


def signed(value: object, unit: str = "%") -> str:
    if value is None:
        return "—"
    numeric = float(value)
    return f"{numeric:+.2f}{unit}"


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
    change = item.get("changes", {}).get(change_key)
    tone = "up" if change is not None and change > 0 else "down" if change is not None and change < 0 else "flat"
    return {
        "label": item.get("label", "—"),
        "value": f"{number(item.get('value'), 2)}{item.get('unit', '')}",
        "change": signed(change, item.get("change_unit", "%")),
        "date": item.get("date", "—"),
        "tone": tone,
    }


def interpretation(items: dict[str, dict]) -> tuple[str, str, list[str]]:
    kospi = items.get("kospi", {})
    sp500 = items.get("sp500", {})
    nasdaq = items.get("nasdaq", {})
    usd = items.get("krw_usd", {})
    us10y = items.get("us10y", {})
    gold = items.get("gold", {})
    equity_changes = [row.get("changes", {}).get("day") for row in (kospi, sp500, nasdaq)]
    equity_changes = [float(value) for value in equity_changes if value is not None]
    positive = sum(value > 0 for value in equity_changes)
    if equity_changes and positive >= 2:
        regime = "주요 지수의 위험선호가 비교적 넓게 이어지는 아침"
        stance = "추격 매수보다 상승 폭과 거래 확산을 확인하며 분할 접근할 구간입니다."
    elif equity_changes and positive == 0:
        regime = "주요 지수의 위험회피가 겹친 아침"
        stance = "신규 비중 확대보다 현금·손실 한도와 보유 종목의 지지선을 먼저 점검할 구간입니다."
    else:
        regime = "시장별 방향이 엇갈려 선별 확인이 필요한 아침"
        stance = "지수 방향보다 실적·수급이 확인되는 종목 중심으로 조건을 좁혀 볼 구간입니다."
    checks = [
        f"원·달러 {metric(usd)['value']} ({metric(usd)['change']}) — 원화 약세가 확대되면 외국인 수급 부담을 점검합니다.",
        f"미국 10년물 {metric(us10y)['value']} ({metric(us10y)['change']}) — 금리 상승 시 성장주 할인율 부담을 확인합니다.",
        f"금 {metric(gold)['value']} ({metric(gold)['change']}) — 주가와 금이 함께 강한지, 안전자산만 강한지 구분합니다.",
    ]
    return regime, stance, checks


def select_investment_news(rows: list[dict], limit: int = 6) -> list[dict]:
    scored: list[tuple[int, int, dict]] = []
    for position, row in enumerate(rows):
        title = str(row.get("title", ""))
        lowered = title.lower()
        tags = set(row.get("tags") or [])
        score = min(6, sum(2 for keyword in INVESTMENT_KEYWORDS if keyword in lowered))
        if tags & INVESTMENT_TAGS:
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


def build_payload(day: str) -> dict:
    observed = datetime.strptime(day, "%Y-%m-%d")
    weekdays = ("월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일")
    title = f"{observed.year}년 {observed.month}월 {observed.day}일 {weekdays[observed.weekday()]} 아침 — 전수 스캔 투자 브리핑"
    return {
        "schema_version": 2,
        "date": day,
        "generated_at": datetime.now(SEOUL).isoformat(timespec="seconds"),
        "title": title,
        "format": "short-development",
        "sections": [
            {"id": "world", "title": "세계 정세 약식 총평", "subtitle": "세계 정세", "summary": ""},
            {"id": "us", "title": "미국장", "subtitle": "미국장 주요 핵심 총평", "summary": ""},
            {"id": "kr", "title": "한국장", "subtitle": "한국장 주요 핵심 총평", "summary": ""},
        ],
        "disclaimer": "현재 화면 구조를 개발 중이며, 완성 전까지 투자 판단에 사용할 내용을 제공하지 않습니다.",
    }


def rebuild_index() -> dict:
    files = sorted(OUTPUT_DIR.glob("????-??-??.json"), reverse=True)
    pages = []
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        pages.append({"date": payload["date"], "title": payload["title"], "file": path.name})
    index = {"schema_version": 1, "updated_at": datetime.now(SEOUL).isoformat(timespec="seconds"), "pages": pages}
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description="날짜별 읽기 전용 투자 브리핑 생성")
    parser.add_argument("--date", help="YYYY-MM-DD, 기본값은 한국시간 오늘")
    args = parser.parse_args()
    day = args.date or datetime.now(SEOUL).strftime("%Y-%m-%d")
    datetime.strptime(day, "%Y-%m-%d")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_payload(day)
    (OUTPUT_DIR / f"{day}.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    index = rebuild_index()
    print(f"오늘의 투자 브리핑 생성 완료: {day}, 보관 {len(index['pages'])}일")


if __name__ == "__main__":
    main()
