from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
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
GLOBAL_FEEDS = (
    ("economy OR markets OR interest rates OR stocks", "en-US", "US", "US:en", "us"),
    ("site:nytimes.com (economy OR markets OR business OR interest rates)", "en-US", "US", "US:en", "us"),
    ("site:fortune.com (economy OR markets OR business OR stocks)", "en-US", "US", "US:en", "us"),
    ("(site:reuters.com OR site:ft.com OR site:bbc.com OR site:apnews.com) (economy OR markets OR rates OR stocks OR oil)", "en-GB", "GB", "GB:en", "global"),
    ("(site:economist.com OR site:asia.nikkei.com OR site:lemonde.fr) (economy OR markets OR rates OR trade)", "en-GB", "GB", "GB:en", "global"),
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
    ("환율", ("환율", "달러", "원화", "엔화", "위안화", "외환")),
    ("산업·기업", ("반도체", "기업", "실적", "수출", "자동차", "배터리", "조선")),
    ("증시", ("코스피", "코스닥", "나스닥", "다우", "S&P", "증시", "주가")),
)


MARKET_COMMENTS = {
    "부동산": "대출 여건, 지역별 공급과 입주 시차를 함께 확인해야 합니다. 서울 핵심지·수도권 외곽·지방은 수요와 미분양 여건이 달라 같은 방향으로 움직이지 않을 수 있습니다.",
    "금리·채권": "단기금리는 대출비용과 유동성에, 장기금리는 주택·주식의 할인율과 경기 기대에 영향을 줍니다. 한 번의 금리 움직임보다 1년·10년·30년 금리곡선의 방향을 함께 보는 것이 중요합니다.",
    "가상자산": "비트코인은 유동성과 위험선호에 민감하지만 주식·부동산과 항상 같은 방향으로 움직이지는 않습니다. 변동성이 커 단기 가격을 경제 전체의 방향으로 해석하면 안 됩니다.",
    "원자재": "유가 상승은 물가와 운송·생산비의 상방 요인이고, 구리는 산업수요의 보조지표입니다. 금·은은 실질금리와 안전자산 수요의 영향을 함께 받으므로 원인에 따라 해석이 달라집니다.",
    "환율": "환율은 외국인 자금 흐름, 수입물가, 수출기업의 원화 환산 실적에 영향을 줍니다. 하루 움직임보다 금리차와 무역수지, 위험선호가 같은 방향인지 함께 확인해야 합니다.",
    "산업·기업": "기업 실적과 수주는 고용·수출·설비투자에 연결됩니다. 발표 수치가 일회성인지, 실제 현금흐름과 다음 분기 실적으로 이어지는지를 확인해야 합니다.",
    "증시": "주가지수는 경기 기대와 유동성을 빠르게 반영하지만 실물경제보다 먼저 움직일 수 있습니다. 국내외 지수, 반도체지수, VIX를 함께 비교해야 위험선호 변화를 구분할 수 있습니다.",
    "거시경제": "한 개의 지표보다 금리·환율·물가·고용·소비가 같은 방향인지 확인해야 합니다. 발표치와 시장 기대의 차이가 단기 가격변동을 크게 만들 수 있습니다.",
}

CORE_MARKET_CATEGORIES = {"증시", "금리·채권", "환율", "원자재"}
TRUSTED_PUBLISHERS = ("연합뉴스", "한국은행", "기획재정부", "금융위원회", "한국거래소", "KBS", "MBC", "SBS", "로이터", "Reuters", "블룸버그", "Bloomberg", "한경", "매일경제", "서울경제", "이데일리", "The New York Times", "New York Times", "Fortune", "Financial Times", "The Wall Street Journal", "Wall Street Journal", "Associated Press", "AP News", "BBC", "CNBC", "The Economist", "Nikkei Asia", "The Washington Post")
US_PUBLISHERS = ("New York Times", "Fortune", "Wall Street Journal", "CNBC", "Bloomberg", "Associated Press", "AP News", "Washington Post", "MarketWatch", "Barron's", "CBS", "NBC", "ABC News", "CNN")
KOREAN_PUBLISHERS = ("연합뉴스", "한국은행", "기획재정부", "금융위원회", "한국거래소", "KBS", "MBC", "SBS", "한경", "한국경제", "매일경제", "서울경제", "이데일리", "조선일보", "중앙일보", "동아일보", "전자신문")
IMPACT_KEYWORDS = ("기준금리", "연준", "금리 인상", "금리 인하", "환율", "국채", "물가", "고용", "GDP", "관세", "수출", "실적", "코스피", "코스닥", "나스닥", "유가", "원유", "금값", "반도체", "부동산 정책", "대출 규제", "세제")
INVESTMENT_RELEVANCE = ("금리", "연준", "환율", "달러", "국채", "채권", "물가", "고용", "GDP", "관세", "무역", "수출", "실적", "코스피", "코스닥", "나스닥", "다우", "주가", "유가", "원유", "금값", "구리", "반도체", "비트코인", "ETF", "주택", "아파트", "대출", "분양", "재건축", "재개발", "공급", "세제", "세금")
NOISE_KEYWORDS = ("화재", "사망", "숨져", "대피", "홍수", "실종", "범죄", "교통사고", "연예", "Weverse", "TXT-LOG", "프라하하하", "[포토]", "시상식", "페스티벌")
RATE_DECISION_PATTERN = re.compile(r"(?:기준금리|정책금리|연준|한은|한국은행).{0,28}(?:인상|인하|동결|올렸|내렸)|(?:금리).{0,18}(?:인상 결정|인하 결정|동결 결정|올렸다|내렸다)", re.I)


def clean_text(value: str) -> str:
    return SPACE_PATTERN.sub(" ", html.unescape(TAG_PATTERN.sub(" ", value or ""))).strip()


def classify(text: str) -> str:
    for category, keywords in CATEGORY_RULES:
        if any(keyword.lower() in text.lower() for keyword in keywords):
            return category
    return "거시경제"


def classify_region(publisher: str, hinted: str = "") -> str:
    if any(name.lower() in publisher.lower() for name in KOREAN_PUBLISHERS):
        return "domestic"
    if any(name.lower() in publisher.lower() for name in US_PUBLISHERS):
        return "us"
    return hinted if hinted in {"us", "global"} else "domestic"


def translate_to_korean(texts: list[str]) -> list[str] | None:
    """Translate only when an explicit DeepL key exists; never invent a Korean summary."""
    key = os.environ.get("DEEPL_API_KEY", "").strip()
    if not key or not texts:
        return None
    endpoint = os.environ.get("DEEPL_API_URL", "").strip() or ("https://api-free.deepl.com/v2/translate" if key.endswith(":fx") else "https://api.deepl.com/v2/translate")
    payload = json.dumps({"text": texts, "target_lang": "KO"}, ensure_ascii=False).encode("utf-8")
    request = Request(endpoint, data=payload, headers={"User-Agent": USER_AGENT, "Authorization": f"DeepL-Auth-Key {key}", "Content-Type": "application/json", "Accept": "application/json"}, method="POST")
    with urlopen(request, timeout=45) as response:
        rows = json.loads(response.read().decode("utf-8")).get("translations", [])
    translated = [clean_text(row.get("text", "")) for row in rows]
    return translated if len(translated) == len(texts) and all(translated) else None


def is_rate_decision(text: str) -> bool:
    return bool(RATE_DECISION_PATTERN.search(text or ""))


def representative_score(source: dict[str, str]) -> tuple[int, int, int, int]:
    publisher = source.get("publisher", "")
    title = source.get("title", "")
    description = source.get("description", "")
    authority = 1 if any(name.lower() in publisher.lower() for name in TRUSTED_PUBLISHERS) else 0
    return authority, 1 if NUMBER_PATTERN.search(f"{title} {description}") else 0, min(len(description), 300), min(len(title), 100)


def importance_details(item: dict[str, object]) -> dict[str, object]:
    title = str(item.get("title", ""))
    category = str(item.get("category") or ((item.get("tags") or ["거시경제"])[0]))
    metrics = item.get("metrics") or []
    related = int(item.get("related_reports") or 0)
    sources = int(item.get("source_count") or 0)
    if not related and metrics:
        match = re.search(r"\d+", str(metrics[0].get("value", "")))
        related = int(match.group()) if match else 1
    if not sources and len(metrics) > 1:
        match = re.search(r"\d+", str(metrics[1].get("value", "")))
        sources = int(match.group()) if match else 1
    related, sources = max(1, related), max(1, sources)
    publishers = " ".join(str(source.get("publisher", "")) for source in (item.get("sources") or []))
    coverage = min(32, related * 6 + sources * 5)
    market = 14 if category in CORE_MARKET_CATEGORIES else 10 if category in {"산업·기업", "거시경제", "부동산"} else 6
    impact = min(18, sum(3 for keyword in IMPACT_KEYWORDS if keyword.lower() in title.lower()))
    authority = 8 if any(name.lower() in publishers.lower() for name in TRUSTED_PUBLISHERS) else 0
    numeric = 3 if NUMBER_PATTERN.search(title) else 0
    rate_decision = is_rate_decision(title)
    decision_bonus = 30 if rate_decision else 0
    engagement = item.get("engagement") if isinstance(item.get("engagement"), dict) else {}
    actual_views = int(engagement.get("views") or 0)
    actual_reactions = int(engagement.get("reactions") or 0)
    popularity_rank = int(engagement.get("rank") or 0)
    engagement_bonus = min(24, int((actual_views + actual_reactions * 4) ** 0.25 * 2)) if actual_views or actual_reactions else max(0, 18 - popularity_rank) if popularity_rank else 0
    noise = 32 if any(keyword in title for keyword in NOISE_KEYWORDS) else 0
    relevant = category in CORE_MARKET_CATEGORIES or any(keyword.lower() in title.lower() for keyword in INVESTMENT_RELEVANCE)
    score = max(0, min(100, coverage + market + impact + authority + numeric + decision_bonus + engagement_bonus - noise))
    views_available = actual_views > 0
    if views_available or actual_reactions:
        response_basis = f"공개 조회 {actual_views:,}회 · 공개 반응 {actual_reactions:,}건"
    elif popularity_rank:
        response_basis = f"매체 공식 인기기사 순위 {popularity_rank}위 · 조회수 원수치는 비공개"
    else:
        response_basis = "조회·반응 수치 미제공 · 유사 보도 확산과 매체 다양성으로 대체"
    return {
        "score": score,
        "coverage_score": coverage,
        "market_impact_score": market + impact,
        "source_score": authority,
        "noise_penalty": noise,
        "attention_basis": f"유사 보도 {related}건 · 확인 매체 {sources}곳",
        "engagement_score": engagement_bonus,
        "views_available": views_available,
        "rate_decision": rate_decision,
        "response_proxy": response_basis,
        "investment_relevant": relevant and noise == 0,
    }


def mark_important(items: list[dict[str, object]], limit: int = 8) -> list[dict[str, object]]:
    for item in items:
        item["category"] = str(item.get("category") or ((item.get("tags") or ["거시경제"])[0]))
        item["publisher"] = str(item.get("publisher") or (((item.get("sources") or [{}])[0]).get("publisher", "원문")))
        item["region"] = str(item.get("region") or classify_region(str(item["publisher"])))
        item["importance"] = importance_details(item)
        item["importance_score"] = item["importance"]["score"]
        item["important"] = False
    ranked = sorted(items, key=lambda row: (bool(row["importance"].get("rate_decision")), int(row.get("importance_score", 0)), str(row.get("date", ""))), reverse=True)
    category_counts: dict[str, int] = {}
    selected = 0
    for region in ("domestic", "us", "global"):
        candidate = next((row for row in ranked if row.get("region") == region and row["importance"].get("investment_relevant")), None)
        if candidate and selected < limit:
            candidate["important"] = True
            category = str(candidate.get("category", "거시경제"))
            category_counts[category] = category_counts.get(category, 0) + 1
            selected += 1
    for item in ranked:
        if item.get("important"):
            continue
        if (int(item.get("importance_score", 0)) < 28 and not item["importance"].get("rate_decision")) or not item["importance"].get("investment_relevant") or selected >= limit:
            continue
        category = str(item.get("category", "거시경제"))
        if category_counts.get(category, 0) >= 3:
            continue
        item["important"] = True
        category_counts[category] = category_counts.get(category, 0) + 1
        selected += 1
    return items


def feed_url(query: str, target: date, language: str = "ko", country: str = "KR", edition: str = "KR:ko") -> str:
    after = target.isoformat()
    before = (target + timedelta(days=1)).isoformat()
    scoped = f"({query}) after:{after} before:{before}"
    return f"https://news.google.com/rss/search?q={quote_plus(scoped)}&hl={language}&gl={country}&ceid={edition}"


def fetch_feed(query: str, target: date, language: str = "ko", country: str = "KR", edition: str = "KR:ko", region: str = "domestic") -> list[dict[str, str]]:
    request = Request(feed_url(query, target, language, country, edition), headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml"})
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
        rows.append({"title": title, "url": link, "publisher": publisher or "뉴스 원문", "description": description, "published_at": published_date, "region": classify_region(publisher, region)})
    return rows


def fetch_nyt_most_popular(target: date) -> list[dict[str, object]]:
    key = os.environ.get("NYT_API_KEY", "").strip()
    if not key:
        return []
    request = Request(f"https://api.nytimes.com/svc/mostpopular/v2/viewed/1.json?api-key={quote_plus(key)}", headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=40) as response:
        results = json.loads(response.read().decode("utf-8")).get("results", [])
    rows = []
    for rank, item in enumerate(results, 1):
        published = str(item.get("published_date") or target.isoformat())[:10]
        if published != target.isoformat():
            continue
        title, description, link = clean_text(item.get("title", "")), clean_text(item.get("abstract", "")), clean_text(item.get("url", ""))
        if title and link:
            rows.append({"title": title, "url": link, "publisher": "The New York Times", "description": description, "published_at": published, "region": "us", "engagement": {"rank": rank, "metric": "NYT most viewed"}})
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
    related = sorted(related, key=representative_score, reverse=True)
    row = related[0]
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
        source_entry = {"publisher": source["publisher"], "title": source["title"], "url": source["url"], "published_at": source["published_at"], "region": source.get("region", "domestic")}
        if source.get("region") in {"us", "global"}:
            source_entry.update({"summary_original": source["description"][:500], "translation_status": "translation_api_key_required"})
        sources.append(source_entry)
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
        "category": category,
        "publisher": row["publisher"][:40],
        "region": row.get("region", "domestic"),
        "engagement": row.get("engagement", {}),
        "related_reports": len(related),
        "source_count": len(sources),
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
        "disclaimer": "뉴스 제목과 공개 요약을 자동 정리한 정보이며 투자 권유가 아닙니다. 실제 조회수·좋아요는 제공되지 않아 유사 보도 확산과 매체 다양성을 호응도의 대체지표로 사용합니다. 정확한 내용은 원문을 확인하세요.",
    }


def translate_foreign_sources(items: list[dict[str, object]]) -> None:
    pending: list[tuple[dict[str, object], str, str]] = []
    texts: list[str] = []
    for item in items:
        for source in item.get("sources") or []:
            if source.get("region") not in {"us", "global"}:
                continue
            title, summary = str(source.get("title", "")), str(source.get("summary_original", ""))
            pending.append((source, title, summary))
            texts.extend([title, summary or title])
    if not texts:
        return
    try:
        translated = translate_to_korean(texts)
    except Exception as error:
        print(f"해외 기사 번역 실패: {error}")
        translated = None
    if not translated:
        return
    for index, (source, _title, _summary) in enumerate(pending):
        source.update({"title_ko": translated[index * 2], "summary_ko": translated[index * 2 + 1], "translation_status": "translated", "translation_provider": "DeepL"})


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
    for query, language, country, edition, region in GLOBAL_FEEDS:
        try:
            for row in fetch_feed(query, target, language, country, edition, region):
                key = SPACE_PATTERN.sub("", row["title"].lower())
                unique.setdefault(key, row)
        except Exception as error:
            print(f"{target} 해외 뉴스 피드 일부 실패: {error}")
        time.sleep(0.2)
    try:
        for row in fetch_nyt_most_popular(target):
            key = SPACE_PATTERN.sub("", str(row["title"]).lower())
            unique[key] = row
    except Exception as error:
        print(f"{target} NYT 인기기사 API 실패: {error}")
    clusters = cluster_rows(list(unique.values()))
    clusters.sort(key=lambda cluster: (len({row["publisher"] for row in cluster}), len(cluster), len(NUMBER_PATTERN.findall(" ".join(row["title"] for row in cluster)))), reverse=True)
    candidates = [item_from_feed(cluster[0], cluster) for cluster in clusters]
    candidates = [item for item in candidates if item.get("category") != "거시경제" or any(keyword.lower() in f"{item.get('title', '')} {item.get('summary', '')}".lower() for keyword in INVESTMENT_RELEVANCE)]
    quotas = {"domestic": max(1, round(limit * 0.55)), "us": max(1, round(limit * 0.25))}
    quotas["global"] = max(1, limit - quotas["domestic"] - quotas["us"])
    items = []
    for region in ("domestic", "us", "global"):
        items.extend([item for item in candidates if item.get("region") == region][:quotas[region]])
    if len(items) < limit:
        selected_ids = {str(item.get("id")) for item in items}
        items.extend(item for item in candidates if str(item.get("id")) not in selected_ids and len(items) < limit)
    translate_foreign_sources(items)
    mark_important(items)
    return sorted(items, key=lambda row: int(row.get("importance_score", 0)), reverse=True)


def write_day(target: date, items: list[dict[str, object]]) -> None:
    payload = {"schema_version": 1, "date": target.isoformat(), "count": len(items), "items": items}
    path = NEWS_DIR / f"{target.isoformat()}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def rebuild_index() -> None:
    archives: list[dict[str, object]] = []
    all_items: list[dict[str, object]] = []
    latest_archive_items: list[dict[str, object]] = []
    for path in sorted(NEWS_DIR.glob("20??-??-??.json"), reverse=True):
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = mark_important(payload.get("items", []))
        payload["items"] = items
        path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        archives.append({"date": payload.get("date"), "count": len(items), "file": path.name})
        if not latest_archive_items:
            latest_archive_items = items
        all_items.extend(items)
    important_items = sorted(
        [item for item in latest_archive_items if item.get("important")],
        key=lambda row: int(row.get("importance_score", 0)),
        reverse=True,
    )[:8]
    index = {
        "schema_version": 1,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "archive_days": len(archives),
        "total_articles": len(all_items),
        "latest_items": all_items[:12],
        "important_items": important_items,
        "importance_method": "실제 조회수·좋아요 미제공 · 유사 보도 확산, 매체 다양성, 대표 기사 품질, 출처 신뢰도, 금리 결정 등 시장 영향도로 산정",
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
