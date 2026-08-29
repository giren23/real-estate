from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "public" / "market_snapshot.json"
ECONOMIC_CONTEXT = ROOT / "data" / "public" / "economic_context.json"
USER_AGENT = "Mozilla/5.0 KoreanRealEstateMarketSnapshot/1.0"

ASSETS = {
    "global": [
        ("kospi", "🇰🇷 KOSPI", "^KS11", "pt", False),
        ("kosdaq", "🇰🇷 KOSDAQ", "^KQ11", "pt", False),
        ("sp500", "🇺🇸 S&P 500", "^GSPC", "pt", False),
        ("nasdaq", "🇺🇸 NASDAQ", "^IXIC", "pt", False),
        ("dow", "🇺🇸 DOW 30", "^DJI", "pt", False),
        ("nikkei", "🇯🇵 NIKKEI 225", "^N225", "pt", False),
        ("hangseng", "🇭🇰 HANG SENG", "^HSI", "pt", False),
        ("ftse", "🇬🇧 FTSE 100", "^FTSE", "pt", False),
    ],
    "fx": [
        ("krw_usd", "￦ 원/달러", "KRW=X", "원", False),
        ("jpy_usd", "￥ 엔/달러", "JPY=X", "엔", False),
        ("cny_usd", "¥ 위안/달러", "CNY=X", "위안", False),
        ("eur_usd", "€ 유로/달러", "EURUSD=X", "유로", True),
        ("gbp_usd", "£ 파운드/달러", "GBPUSD=X", "파운드", True),
    ],
    "commodities": [
        ("wti", "🛢️ WTI 원유", "CL=F", "달러/배럴", False),
        ("brent", "🛢️ 브렌트유", "BZ=F", "달러/배럴", False),
        ("gold", "🥇 금", "GC=F", "달러/온스", False),
        ("silver", "🥈 은", "SI=F", "달러/온스", False),
        ("copper", "🔧 구리", "HG=F", "달러/파운드", False),
        ("aluminum", "⚙️ 알루미늄", "ALI=F", "달러/톤", False),
    ],
    "rates": [
        ("us10y", "🇺🇸 미국 국채 10년", "^TNX", "%", False),
        ("us30y", "🇺🇸 미국 국채 30년", "^TYX", "%", False),
        ("us5y", "🇺🇸 미국 국채 5년", "^FVX", "%", False),
    ],
}

CATEGORY_META = {
    "global": ("🌍 글로벌 증시", "8개 주요 지수"),
    "fx": ("💱 환율 (대달러)", "달러 1단위에 대한 각 통화 값"),
    "commodities": ("🛢️ 원자재", "국제 선물시장 최근 종가"),
    "rates": ("📈 금리", "변화량은 bp(0.01%p)"),
}


def download_json(url: str) -> dict:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urlopen(request, timeout=40) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as error:
            last_error = error
            if attempt < 2:
                time.sleep(2**attempt)
    assert last_error is not None
    raise last_error


def fetch_yahoo(symbol: str, invert: bool = False) -> list[dict[str, object]]:
    now = int(time.time()) + 86400
    start = now - 620 * 86400
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{quote(symbol, safe='')}?period1={start}&period2={now}&interval=1d&events=history"
    )
    payload = download_json(url)
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    closes = result.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose")
    if not closes:
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close") or []
    rows = []
    for timestamp, close in zip(timestamps, closes):
        if close in (None, 0):
            continue
        value = 1 / float(close) if invert else float(close)
        rows.append(
            {
                "date": datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d"),
                "value": round(value, 6),
            }
        )
    if len(rows) < 2:
        raise ValueError(f"{symbol}: 유효 시세가 부족합니다.")
    return rows


def value_on_or_before(rows: list[dict[str, object]], target: datetime) -> float | None:
    target_text = target.strftime("%Y-%m-%d")
    for row in reversed(rows):
        if str(row["date"]) <= target_text:
            return float(row["value"])
    return None


def changes(rows: list[dict[str, object]], *, basis_points: bool = False) -> dict[str, float | None]:
    latest = float(rows[-1]["value"])
    latest_date = datetime.strptime(str(rows[-1]["date"]), "%Y-%m-%d")
    output: dict[str, float | None] = {}
    for key, days in (("day", 1), ("week", 7), ("month", 30), ("quarter", 90)):
        old = value_on_or_before(rows[:-1], latest_date - timedelta(days=days))
        if old is None:
            output[key] = None
        elif basis_points:
            output[key] = round((latest - old) * 100, 2)
        else:
            output[key] = round((latest / old - 1) * 100, 2)
    return output


def monthly_history(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    by_month: dict[str, dict[str, object]] = {}
    for row in rows:
        month = str(row["date"])[:7]
        by_month[month] = {"month": month, "value": row["value"]}
    return [by_month[key] for key in sorted(by_month)[-13:]]


def make_item(key: str, label: str, symbol: str, unit: str, invert: bool, rows: list[dict[str, object]]) -> dict:
    is_rate = key.endswith("y") and key[:2] in {"us", "kr", "jp"}
    computed_changes = changes(rows, basis_points=is_rate)
    if symbol == "official-monthly" or symbol.startswith("FRED-"):
        computed_changes["day"] = None
        computed_changes["week"] = None
    return {
        "key": key,
        "label": label,
        "symbol": symbol,
        "unit": unit,
        "date": rows[-1]["date"],
        "value": rows[-1]["value"],
        "changes": computed_changes,
        "change_unit": "bp" if is_rate else "%",
        "history": monthly_history(rows),
    }


def context_rate_items() -> list[dict]:
    if not ECONOMIC_CONTEXT.exists():
        return []
    context = json.loads(ECONOMIC_CONTEXT.read_text(encoding="utf-8"))
    rows = context.get("bond_yields") or []
    specs = [
        ("kr_1y", "🇰🇷 국고채 1년"),
        ("kr_10y", "🇰🇷 국고채 10년"),
        ("kr_30y", "🇰🇷 국고채 30년"),
        ("jp_10y", "🇯🇵 일본 국채 10년"),
    ]
    items = []
    for key, label in specs:
        series = [{"date": f"{row['month']}-28", "value": row[key]} for row in rows if key in row]
        if not series:
            continue
        items.append(make_item(key, label, "official-monthly", "%", False, series))
    return items


def context_commodity_items() -> list[dict]:
    if not ECONOMIC_CONTEXT.exists():
        return []
    context = json.loads(ECONOMIC_CONTEXT.read_text(encoding="utf-8"))
    rows = context.get("oil_prices") or []
    series = [
        {"date": f"{row['month']}-28", "value": row["dubai_usd_barrel"]}
        for row in rows
        if "dubai_usd_barrel" in row
    ]
    if not series:
        return []
    return [make_item("dubai", "🛢️ 두바이유", "FRED-POILDUBUSDM", "달러/배럴", False, series)]


def load_existing_items(existing: dict) -> dict[str, dict]:
    return {
        item["key"]: item
        for category in existing.get("categories", [])
        for item in category.get("items", [])
        if item.get("key")
    }


def insight(category_id: str, items: list[dict]) -> str:
    valid = [item for item in items if item.get("changes", {}).get("day") is not None]
    if not valid:
        return "현재 공개 데이터의 다음 갱신을 기다리고 있습니다."
    best = max(valid, key=lambda item: item["changes"]["day"])
    worst = min(valid, key=lambda item: item["changes"]["day"])
    if category_id == "rates":
        return f"전일 대비 {best['label']} {best['changes']['day']:+.1f}bp, {worst['label']} {worst['changes']['day']:+.1f}bp입니다."
    return f"전일 기준 상승 폭은 {best['label']} {best['changes']['day']:+.2f}%, 하락 폭은 {worst['label']} {worst['changes']['day']:+.2f}%입니다."


def main() -> None:
    existing = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
    existing_items = load_existing_items(existing)
    categories = []
    all_items: dict[str, dict] = {}
    failures = []
    for category_id, specs in ASSETS.items():
        items = []
        for key, label, symbol, unit, invert in specs:
            try:
                item = make_item(key, label, symbol, unit, invert, fetch_yahoo(symbol, invert))
            except Exception as error:
                item = existing_items.get(key)
                failures.append(f"{label}: {error}")
            if item:
                items.append(item)
                all_items[key] = item
        if category_id == "rates":
            for item in context_rate_items():
                if item["key"] not in all_items:
                    items.append(item)
                    all_items[item["key"]] = item
        if category_id == "commodities":
            for item in context_commodity_items():
                if item["key"] not in all_items:
                    items.append(item)
                    all_items[item["key"]] = item
        title, note = CATEGORY_META[category_id]
        categories.append({"id": category_id, "title": title, "note": note, "items": items, "insight": insight(category_id, items)})

    chart_keys = ["kospi", "sp500", "nikkei", "us10y", "krw_usd", "wti", "gold"]
    charts = [all_items[key] for key in chart_keys if key in all_items]
    market_dates = [str(item["date"]) for item in all_items.values() if item.get("date")]
    payload = {
        "schema_version": 1,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "market_date": max(market_dates) if market_dates else None,
        "categories": categories,
        "charts": charts,
        "domestic_data": {
            "status": "official_api_required",
            "title": "국내 증시 주변 자금·투자주체",
            "message": "고객예탁금·신용잔고·투자주체 순매수는 재배포 가능한 KRX 또는 금융투자협회 공식 API 연결 후 표시합니다.",
        },
        "sources": [
            {"name": "Yahoo Finance 공개 시세", "url": "https://finance.yahoo.com/markets/"},
            {"name": "한국은행 ECOS", "url": "https://ecos.bok.or.kr/"},
            {"name": "일본 재무성", "url": "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/"},
        ],
        "failures": failures,
        "method": "최근 종가를 기준으로 1·7·30·90일 전 또는 그 이전의 가장 가까운 거래일 종가와 비교합니다.",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"시장 한 컷 생성 완료: {len(all_items)}개 지표, {len(charts)}개 추세 차트, 실패 {len(failures)}개")


if __name__ == "__main__":
    main()
