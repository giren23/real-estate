from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
NEWS_DIR = ROOT / "web" / "content" / "news"
INDEX_PATH = NEWS_DIR / "index.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KoreanEconomicNewsArchive/1.0"
FEED_QUERIES = (
    "경제 OR 금융 OR 증시 OR 환율 OR 금리 OR 반도체",
    "부동산 OR 주택 OR 전세 OR 아파트 OR 분양",
    "미국증시 OR 연준 OR 국제유가 OR 금값 OR 비트코인",
)
TAG_PATTERN = re.compile(r"<[^>]+>")
SPACE_PATTERN = re.compile(r"\s+")
TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z0-9]+")
STOPWORDS = {"관련", "대한", "이번", "오늘", "내일", "정부", "시장", "뉴스", "전망", "발표", "한국", "미국"}
NUMBER_PATTERN = re.compile(r"(?<!\d)(\d[\d,.]*(?:\.\d+)?\s*(?:조원|억원|억|만원|만명|만호|%|bp|건|척|호|명|대))", re.I)


CATEGORY_RULES = (
    ("부동산", ("부동산", "주택", "아파트", "전세", "월세", "분양", "재건축", "재개발")),
    ("금리·채권", ("금리", "국채", "채권", "연준", "한국은행", "기준금리")),
    ("가상자산", ("비트코인", "가상자산", "암호화폐", "이더리움")),
    ("원자재", ("유가", "원유", "금값", "은값", "구리", "원자재")),
    ("산업·기업", ("반도체", "기업", "실적", "수출", "자동차", "배터리", "조선")),
    ("증시", ("코스피", "코스닥", "나스닥", "다우", "S&P", "증시", "주가")),
)


MARKET_COMMENTS = {
    "부동산": "대출 여건, 지역별 공급과 입주 시차를 함께 확인해야 합니다. 서울 핵심지·수도권 외곽·지방은 수요와 미분양 여건이 달라 같은 방향으로 움직이지 않을 수 있습니다.",
    "금리·채권": "단기금리는 대출비용과 유동성에, 장기금리는 주택·주식의 할인율과 경기 기대에 영향을 줍니다. 한 번의 금리 움직임보다 1년·10년·30년 금리곡선의 방향을 함께 보는 것이 중요합니다.",
    "가상자산": "비트코인은 유동성과 위험선호에 민감하지만 주식·부동산과 항상 같은 방향으로 움직이지는 않습니다. 변동성이 커 단기 가격을 경제 전체의 방향으로 해석하면 안 됩니다.",
    "원자재": "유가 상승은 물가와 운송·생산비의 상방 요인이고, 구리는 산업수요의 보조지표입니다. 금·은은 실질금리와 안전자산 수요의 영향을 함께 받으므로 원인에 따라 해석이 달라집니다.",
    "산업·기업": "기업 실적과 수주는 고용·수출·설비투자에 연결됩니다. 발표 수치가 일회성인지, 실제 현금흐름과 다음 분기 실적으로 이어지는지를 확인해야 합니다.",
    "증시": "주가지수는 경기 기대와 유동성을 빠르게 반영하지만 실물경제보다 먼저 움직일 수 있습니다. 국내외 지수, 반도체지수, VIX를 함께 비교해야 위험선호 변화를 구분할 수 있습니다.",
    "거시경제": "한 개의 지표보다 금리·환율·물가·고용·소비가 같은 방향인지 확인해야 합니다. 발표치와 시장 기대의 차이가 단기 가격변동을 크게 만들 수 있습니다.",
}


def clean_text(value: str) -> str:
    return SPACE_PATTERN.sub(" ", html.unescape(TAG_PATTERN.sub(" ", value or ""))).strip()


def classify(text: str) -> str:
    for category, keywords in CATEGORY_RULES:
        if any(keyword.lower() in text.lower() for keyword in keywords):
            return category
    return "거시경제"


def feed_url(query: str, target: date) -> str:
    after = target.isoformat()
    before = (target + timedelta(days=1)).isoformat()
    scoped = f"({query}) after:{after} before:{before}"
    return f"https://news.google.com/rss/search?q={quote_plus(scoped)}&hl=ko&gl=KR&ceid=KR:ko"


def fetch_feed(query: str, target: date) -> list[dict[str, str]]:
    request = Request(feed_url(query, target), headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml"})
    with urlopen(request, timeout=40) as response:
        root = ET.fromstring(response.read())
    rows: list[dict[str, str]] = []
    for item in root.findall("./channel/item"):
        title = clean_text(item.findtext("title") or "")
        link = clean_text(item.findtext("link") or "")
        description = clean_text(item.findtext("description") or "")
        source_node = item.find("source")
        publisher = clean_text(source_node.text if source_node is not None and source_node.text else "")
        published = item.findtext("pubDate") or ""
        if not title or not link:
            continue
        if publisher and title.endswith(f" - {publisher}"):
            title = title[: -(len(publisher) + 3)].strip()
        try:
            published_at = parsedate_to_datetime(published).astimezone(timezone(timedelta(hours=9)))
            published_date = published_at.date().isoformat()
        except (TypeError, ValueError):
            published_date = target.isoformat()
        rows.append({"title": title, "url": link, "publisher": publisher or "뉴스 원문", "description": description, "published_at": published_date})
    return rows


def headline_tokens(row: dict[str, str]) -> set[str]:
    return {token.lower() for token in TOKEN_PATTERN.findall(row["title"]) if len(token) >= 2 and token not in STOPWORDS and not token.isdigit()}


def cluster_rows(rows: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    clusters: list[list[dict[str, str]]] = []
    for row in rows:
        tokens = headline_tokens(row)
        best_index, best_score = -1, 0.0
        for index, cluster in enumerate(clusters):
            anchor = headline_tokens(cluster[0])
            similarity = len(tokens & anchor) / max(1, len(tokens | anchor))
            if similarity > best_score:
                best_index, best_score = index, similarity
        if best_index >= 0 and best_score >= 0.34:
            clusters[best_index].append(row)
        else:
            clusters.append([row])
    return clusters


def item_from_feed(row: dict[str, str], related: list[dict[str, str]] | None = None) -> dict[str, object]:
    related = related or [row]
    category = classify(f"{row['title']} {row['description']}")
    digest = hashlib.sha1(f"{row['url']}|{row['title']}".encode("utf-8")).hexdigest()[:14]
    description = row["description"]
    if not description or description == row["title"] or len(description) < 25:
        description = "제목에 담긴 핵심 이슈의 세부 수치와 전제조건은 연결된 원문에서 확인할 수 있습니다."
    description = description[:500]
    sources = []
    seen_publishers = set()
    for source in related:
        if source["publisher"] in seen_publishers:
            continue
        seen_publishers.add(source["publisher"])
        sources.append({"publisher": source["publisher"], "title": source["title"], "url": source["url"], "published_at": source["published_at"]})
    numbers = []
    for source in related:
        for value in NUMBER_PATTERN.findall(f"{source['title']} {source['description']}"):
            value = SPACE_PATTERN.sub("", value)
            if value not in numbers:
                numbers.append(value)
    metrics = [{"label": "관련 보도", "value": f"{len(related)}건", "note": "유사 제목 묶음"}, {"label": "확인 매체", "value": f"{len(sources)}곳", "note": "중복 매체 제외"}]
    metrics.extend({"label": f"기사 수치 {index}", "value": value, "note": "원문 제목·공개요약"} for index, value in enumerate(numbers[:2], 1))
    return {
        "id": f"news-{row['published_at'].replace('-', '')}-{digest}",
        "date": row["published_at"],
        "eyebrow": f"ECONOMY NEWS · {category}",
        "read_minutes": 2,
        "title": row["title"][:78],
        "summary": description[:160],
        "tags": [category, row["publisher"][:18]],
        "easy_explanation": description,
        "market_comment": MARKET_COMMENTS[category],
        "metrics": metrics,
        "sections": [
            {"heading": "한 줄로 이해하기", "paragraphs": [description], "bullets": []},
            {
                "heading": "여러 매체에서 확인된 보도",
                "paragraphs": [f"비슷한 제목의 보도 {len(related)}건을 묶었고, 서로 다른 매체 {len(sources)}곳의 원문을 연결했습니다."],
                "bullets": [source["title"] for source in sources[:5]],
            },
            {"heading": "시장 영향과 확인할 점", "paragraphs": [MARKET_COMMENTS[category]], "bullets": ["발표·전망과 실제 집행·실적을 구분", "기사 속 수치는 원문 기준기간과 단위를 재확인", "같은 기사의 단순 전재는 독립 근거로 계산하지 않음"]},
        ],
        "sources": sources,
        "disclaimer": "뉴스 제목과 공개 요약을 자동 정리한 정보이며 투자 권유가 아닙니다. 정확한 내용은 원문을 확인하세요.",
    }


def collect_day(target: date, limit: int) -> list[dict[str, object]]:
    unique: dict[str, dict[str, str]] = {}
    for query in FEED_QUERIES:
        try:
            for row in fetch_feed(query, target):
                key = SPACE_PATTERN.sub("", row["title"].lower())
                unique.setdefault(key, row)
        except Exception as error:
            print(f"{target} 뉴스 피드 일부 실패: {error}")
        time.sleep(0.2)
    clusters = cluster_rows(list(unique.values()))
    clusters.sort(key=lambda cluster: (len({row["publisher"] for row in cluster}), len(cluster), len(NUMBER_PATTERN.findall(" ".join(row["title"] for row in cluster)))), reverse=True)
    return [item_from_feed(cluster[0], cluster) for cluster in clusters[:limit]]


def write_day(target: date, items: list[dict[str, object]]) -> None:
    payload = {"schema_version": 1, "date": target.isoformat(), "count": len(items), "items": items}
    path = NEWS_DIR / f"{target.isoformat()}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def rebuild_index() -> None:
    archives: list[dict[str, object]] = []
    all_items: list[dict[str, object]] = []
    for path in sorted(NEWS_DIR.glob("20??-??-??.json"), reverse=True):
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("items", [])
        archives.append({"date": payload.get("date"), "count": len(items), "file": path.name})
        all_items.extend(items)
    index = {
        "schema_version": 1,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "archive_days": len(archives),
        "total_articles": len(all_items),
        "latest_items": all_items[:12],
        # Keep the first load light on mobile. Older days load on demand.
        "items": all_items[:600],
        "archives": archives,
    }
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="경제·금융·산업·부동산 뉴스 RSS를 날짜별로 보관합니다.")
    parser.add_argument("--backfill-days", type=int, default=1)
    parser.add_argument("--limit-per-day", type=int, default=24)
    args = parser.parse_args()
    days = max(1, min(args.backfill_days, 365))
    limit = max(6, min(args.limit_per_day, 60))
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today()
    for offset in range(days - 1, -1, -1):
        target = today - timedelta(days=offset)
        items = collect_day(target, limit)
        if items:
            write_day(target, items)
            print(f"{target}: {len(items)}건 저장")
    rebuild_index()
    print(f"경제뉴스 인덱스 생성 완료: {INDEX_PATH}")


if __name__ == "__main__":
    main()
