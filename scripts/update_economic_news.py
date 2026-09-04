from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlparse
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
    ("site:nypost.com (business OR economy OR markets OR stocks OR Federal Reserve)", "en-US", "US", "US:en", "us"),
    ("(site:cnbc.com OR site:marketwatch.com OR site:barrons.com OR site:cnn.com) (economy OR markets OR rates OR stocks)", "en-US", "US", "US:en", "us"),
    ("(site:reuters.com OR site:ft.com OR site:bbc.com OR site:apnews.com) (economy OR markets OR rates OR stocks OR oil)", "en-GB", "GB", "GB:en", "global"),
    ("(site:economist.com OR site:asia.nikkei.com OR site:lemonde.fr OR site:theguardian.com OR site:dw.com OR site:aljazeera.com) (economy OR markets OR rates OR trade)", "en-GB", "GB", "GB:en", "global"),
)
DIRECT_RSS_FEEDS = (
    ("https://rss.blog.naver.com/dealsite.xml", "딜사이트", "domestic"),
    ("https://nypost.com/business/feed/", "New York Post", "us"),
    ("https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "The New York Times", "us"),
    ("https://feeds.bbci.co.uk/news/business/rss.xml", "BBC", "global"),
    ("https://www.theguardian.com/business/rss", "The Guardian", "global"),
    ("https://www.cnbc.com/id/10001147/device/rss/rss.html", "CNBC", "us"),
)
TAG_PATTERN = re.compile(r"<[^>]+>")
SPACE_PATTERN = re.compile(r"\s+")
TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z0-9]+")
STOPWORDS = {"관련", "대한", "이번", "오늘", "내일", "정부", "시장", "뉴스", "전망", "발표", "한국", "미국"}
NUMBER_PATTERN = re.compile(
    r"(?<![\w.])(?:[$€£¥]\s*)?\d[\d,.]*(?:\.\d+)?\s*(?:%p|%|bp|bps|basis\s+points?|조원|억원|억|만원|원|달러|엔|유로|trillion|billion|million|조|만|건|척|호|명|대|배럴|포인트|년|개월|월|분기|일)?",
    re.I,
)
SENTENCE_PATTERN = re.compile(r"(?<=[.!?。])\s+")
CAUSE_PATTERN = re.compile(r"때문|따라|영향|배경|이유|목적|위해|으로 인해|기인|전망|예상", re.I)
METHOD_PATTERN = re.compile(r"통해|활용|설정|계획|방식|구조|계약|조치|추진|검토|절차|대응", re.I)
TIME_PATTERN = re.compile(r"(?:\d{1,4}년|\d{1,2}월|\d{1,2}일|최근|현재|지난|올해|내년|상반기|하반기|분기|당시)")
ARTICLE_NOISE_PATTERN = re.compile(r"(?:무단전재|재배포|저작권|기자\s*[\w.@-]+|구독|로그인|댓글|공감|관련기사|ADVERTISEMENT|Copyright|All rights reserved)", re.I)


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
TRUSTED_PUBLISHERS = ("연합뉴스", "한국은행", "기획재정부", "금융위원회", "한국거래소", "KBS", "MBC", "SBS", "로이터", "Reuters", "블룸버그", "Bloomberg", "한경", "매일경제", "서울경제", "이데일리", "The New York Times", "New York Times", "New York Post", "Fortune", "Financial Times", "The Wall Street Journal", "Wall Street Journal", "Associated Press", "AP News", "BBC", "CNBC", "The Guardian", "The Economist", "Nikkei Asia", "The Washington Post")
US_PUBLISHERS = ("New York Times", "New York Post", "Fortune", "Wall Street Journal", "CNBC", "Bloomberg", "Associated Press", "AP News", "Washington Post", "MarketWatch", "Barron's", "CBS", "NBC", "ABC News", "CNN")
KOREAN_PUBLISHERS = ("연합뉴스", "한국은행", "기획재정부", "금융위원회", "한국거래소", "KBS", "MBC", "SBS", "한경", "한국경제", "매일경제", "서울경제", "이데일리", "조선일보", "중앙일보", "동아일보", "전자신문")
IMPACT_KEYWORDS = ("기준금리", "연준", "금리 인상", "금리 인하", "환율", "국채", "물가", "고용", "GDP", "관세", "수출", "실적", "코스피", "코스닥", "나스닥", "유가", "원유", "금값", "반도체", "부동산 정책", "대출 규제", "세제")
INVESTMENT_RELEVANCE = ("금리", "연준", "환율", "달러", "국채", "채권", "물가", "고용", "GDP", "관세", "무역", "수출", "실적", "코스피", "코스닥", "나스닥", "다우", "주가", "유가", "원유", "금값", "구리", "반도체", "비트코인", "ETF", "주택", "아파트", "대출", "분양", "재건축", "재개발", "공급", "세제", "세금")
MAX_HIGHLIGHT_TERMS = ("기준금리 인상", "기준금리 인하", "금리 인상", "금리 인하", "공급 중단", "대규모 감원", "법정관리", "부도", "디폴트")
HIGH_HIGHLIGHT_TERMS = ("연방준비제도", "연준", "한국은행", "기준금리", "국채", "환율", "관세", "물가", "고용", "GDP", "코스피", "코스닥", "나스닥", "반도체", "비트코인", "국토교통부", "공공주택", "재생에너지", "RE100")
NOISE_KEYWORDS = ("화재", "사망", "숨져", "대피", "홍수", "실종", "범죄", "교통사고", "연예", "Weverse", "TXT-LOG", "프라하하하", "[포토]", "시상식", "페스티벌")
RATE_DECISION_PATTERN = re.compile(r"(?:기준금리|정책금리|연준|한은|한국은행).{0,28}(?:인상|인하|동결|올렸|내렸)|(?:금리).{0,18}(?:인상 결정|인하 결정|동결 결정|올렸다|내렸다)", re.I)
US_ORIGIN_TERMS = ("미국", "연방준비제도", "연준", "Federal Reserve", "Fed ", "트럼프", "Trump", "백악관", "White House", "월가", "Wall Street", "나스닥", "NASDAQ", "S&P 500", "뉴욕증시")
GLOBAL_ORIGIN_TERMS = ("중국", "China", "일본", "Japan", "유럽", "European Union", "EU ", "영국", "독일", "프랑스", "러시아", "우크라이나", "중동", "OPEC", "IMF", "세계은행", "World Bank", "글로벌")
SUMMARY_SCHEMA_VERSION = 2
STRUCTURED_KEYS = ("summary_title", "article_summary", "core_summary", "six_w_one_h", "key_figures", "fact_status", "uncertainties")


def clean_text(value: str) -> str:
    return SPACE_PATTERN.sub(" ", html.unescape(TAG_PATTERN.sub(" ", value or ""))).strip()


class ArticleParagraphParser(HTMLParser):
    """Collect public article paragraphs and articleBody JSON without site-specific dependencies."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[str] = []
        self._capture = 0
        self._buffer: list[str] = []
        self._json_ld = False
        self._json_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() in {"p", "article", "blockquote"}:
            self._capture += 1
            if self._capture == 1:
                self._buffer = []
        if tag.lower() == "script" and "ld+json" in attributes.get("type", "").lower():
            self._json_ld = True
            self._json_buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"p", "article", "blockquote"} and self._capture:
            self._capture -= 1
            if self._capture == 0:
                text = clean_text(" ".join(self._buffer))
                if text:
                    self.paragraphs.append(text)
        if tag.lower() == "script" and self._json_ld:
            self._json_ld = False
            raw = "".join(self._json_buffer).strip()
            try:
                self._collect_json(json.loads(raw))
            except (TypeError, ValueError, json.JSONDecodeError):
                pass

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buffer.append(data)
        if self._json_ld:
            self._json_buffer.append(data)

    def _collect_json(self, value: object) -> None:
        if isinstance(value, dict):
            body = value.get("articleBody")
            if isinstance(body, str):
                self.paragraphs.extend(part.strip() for part in body.splitlines() if part.strip())
            for child in value.values():
                if isinstance(child, (dict, list)):
                    self._collect_json(child)
        elif isinstance(value, list):
            for child in value:
                self._collect_json(child)


def article_sentences(page: str) -> list[str]:
    parser = ArticleParagraphParser()
    parser.feed(page)
    sentences: list[str] = []
    seen: set[str] = set()
    for paragraph in parser.paragraphs:
        for sentence in SENTENCE_PATTERN.split(clean_text(paragraph)):
            sentence = sentence.strip(" -•\t")
            normalized = SPACE_PATTERN.sub("", sentence).lower()
            if len(sentence) < 25 or len(sentence) > 700 or ARTICLE_NOISE_PATTERN.search(sentence) or normalized in seen:
                continue
            if sentence.count("#") >= 2:
                continue
            seen.add(normalized)
            sentences.append(sentence)
    return sentences


def fetch_article_sentences(url: str) -> tuple[list[str], str]:
    if "news.google.com" in urlparse(url).netloc.lower():
        try:
            from googlenewsdecoder import gnewsdecoder
            decoded = gnewsdecoder(url, interval=0)
            if decoded.get("status") and decoded.get("decoded_url"):
                url = str(decoded["decoded_url"])
        except Exception:
            pass
    parsed = urlparse(url)
    if parsed.netloc.lower() == "blog.naver.com":
        match = re.fullmatch(r"/([^/]+)/(\d+)", parsed.path.rstrip("/"))
        if match:
            url = f"https://blog.naver.com/PostView.naver?blogId={quote_plus(match.group(1))}&logNo={match.group(2)}"
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml", "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7"})
    with urlopen(request, timeout=18) as response:
        final_url = response.geturl()
        content_type = response.headers.get("Content-Type", "")
        if "html" not in content_type.lower():
            return [], final_url
        page = response.read(3_000_000).decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    return article_sentences(page), final_url


def sixw_summary_from_sentences(title: str, publisher: str, published_at: str, sentences: list[str]) -> dict[str, object]:
    """Build one evidence-bound 6W1H narrative and a matching core summary."""
    if not sentences:
        return {}
    title_tokens = {token.lower() for token in TOKEN_PATTERN.findall(title) if len(token) >= 2 and token not in STOPWORDS}
    article_start = next((index for index, sentence in enumerate(sentences) if len(title_tokens & {token.lower() for token in TOKEN_PATTERN.findall(sentence) if len(token) >= 2}) >= 2), 0)
    sentences = sentences[article_start:]
    ranked: list[tuple[int, int, str]] = []
    for index, sentence in enumerate(sentences):
        tokens = {token.lower() for token in TOKEN_PATTERN.findall(sentence) if len(token) >= 2}
        score = min(8, len(tokens & title_tokens) * 2)
        score += min(6, len(NUMBER_PATTERN.findall(sentence)) * 2)
        score += 3 if CAUSE_PATTERN.search(sentence) else 0
        score += 3 if METHOD_PATTERN.search(sentence) else 0
        score += 2 if TIME_PATTERN.search(sentence) else 0
        score += 4 if index < 3 else 0
        ranked.append((score, index, sentence))
    chosen_indices = {0}
    coverage_patterns = (TIME_PATTERN, CAUSE_PATTERN, METHOD_PATTERN, NUMBER_PATTERN)
    for pattern in coverage_patterns:
        match = next((row for row in ranked if pattern.search(row[2])), None)
        if match:
            chosen_indices.add(match[1])
    for _score, index, sentence in ranked:
        if NUMBER_PATTERN.search(sentence) or CAUSE_PATTERN.search(sentence) or METHOD_PATTERN.search(sentence):
            chosen_indices.add(index)
        if len(chosen_indices) >= 25:
            break
    for _score, index, _sentence in sorted(ranked, reverse=True):
        chosen_indices.add(index)
        if len(chosen_indices) >= 12:
            break
    chosen = [sentences[index] for index in sorted(chosen_indices)]
    while len(" ".join(chosen)) > 8000 and len(chosen) > 8:
        chosen.pop()
    lead = chosen[0]
    prefix = f"{publisher}는 {published_at} 공개한 기사에서 " if publisher or published_at else "기사에서는 "
    narrative = prefix + lead[0].lower() + lead[1:] if lead[:1].isascii() and lead[:1].isupper() else prefix + lead
    if not narrative.endswith((".", "다.", "요.")):
        narrative += "."
    if len(chosen) > 1:
        narrative += " " + " ".join(chosen[1:])
    core_candidates = [chosen[0]]
    for sentence in chosen[1:]:
        if (CAUSE_PATTERN.search(sentence) or METHOD_PATTERN.search(sentence) or NUMBER_PATTERN.search(sentence)) and sentence not in core_candidates:
            core_candidates.append(sentence)
        if len(core_candidates) >= 3:
            break
    core = " ".join(core_candidates)[:900]
    facts_source = [{"title": title, "description": narrative, "publisher": publisher, "published_at": published_at, "published_time": published_at}]
    fields = narrative_fields(facts_source, core)
    paragraph_count = max(3, min(7, (len(chosen) + 2) // 3))
    chunk_size = max(1, (len(chosen) + paragraph_count - 1) // paragraph_count)
    article_summary = [" ".join(chosen[index:index + chunk_size]) for index in range(0, len(chosen), chunk_size)][:7]
    fields.update(structured_summary_fields(title, publisher, published_at, article_summary, core))
    fields.update({
        "narrative_paragraphs": [narrative],
        "core_summary": core,
        "summary_basis": "공개 원문 본문",
        "article_body_status": "full_text",
        "publication_status": "detail",
        "article_body_sentence_count": len(sentences),
    })
    return fields


def extract_number_facts(sources: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep every distinct numeric statement available in public feed text, with context."""
    facts: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for source in sorted(sources, key=lambda item: item.get("published_time") or item.get("published_at") or ""):
        text = clean_text(f"{source.get('title', '')}. {source.get('description', '')}")
        sentences = [part.strip() for part in re.split(r"(?<=[.!?。])\s+", text) if part.strip()]
        for sentence in sentences:
            values = [SPACE_PATTERN.sub(" ", match.group(0)).strip() for match in NUMBER_PATTERN.finditer(sentence)]
            values = [value for value in values if re.search(r"\d", value)]
            for value in values:
                key = (value.lower(), sentence)
                if key in seen:
                    continue
                seen.add(key)
                facts.append({
                    "value": value,
                    "context": sentence[:1000],
                    "publisher": source.get("publisher", "원문"),
                    "published_time": source.get("published_time") or source.get("published_at", ""),
                })
    return facts


def structured_summary_fields(title: str, publisher: str, published_at: str, paragraphs: list[str], core: str) -> dict[str, object]:
    """Create the stable, LLM-free JSON contract used by every new article."""
    paragraphs = [clean_text(row) for row in paragraphs if clean_text(row)][:7]
    if len(paragraphs) < 3:
        paragraphs.append("공개된 기사 범위에서 확인되는 배경·실행 방법·적용 대상은 원문 링크에서 추가 확인이 필요함.")
    if len(paragraphs) < 3:
        paragraphs.append("공개 원문에서 확정되지 않은 수치·일정·시장 영향은 임의로 추정하지 않음.")
    full_text = " ".join(paragraphs)
    sentence_rows = [row.strip() for paragraph in paragraphs for row in SENTENCE_PATTERN.split(paragraph) if row.strip()]
    first = sentence_rows[0] if sentence_rows else core
    times = list(dict.fromkeys(match.group(0) for match in TIME_PATTERN.finditer(full_text)))[:8]
    locations = list(dict.fromkeys(re.findall(r"(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)[가-힣\s]{0,18}", full_text)))[:5]
    causes = [row for row in sentence_rows if CAUSE_PATTERN.search(row)][:3]
    methods = [row for row in sentence_rows if METHOD_PATTERN.search(row)][:3]
    number_sources = [{"title": title, "description": full_text, "publisher": publisher, "published_at": published_at, "published_time": published_at}]
    key_figures = [{"value": row["value"], "meaning": row["context"][:240], "basis": "기사 원문", "period": row["published_time"] or published_at} for row in extract_number_facts(number_sources)[:30]]
    status_rules = (("확정", "확정"), ("시행", "시행"), ("의결", "의결"), ("공포", "공포"), ("건의", "건의"), ("검토", "검토"), ("계획", "계획"), ("전망", "전망"), ("주장", "주장"))
    fact_status = []
    for row in sentence_rows:
        status = next((label for token, label in status_rules if token in row), "보도된 사실")
        fact_status.append({"statement": row[:500], "status": status})
        if len(fact_status) >= 12:
            break
    uncertain = [row for row in sentence_rows if re.search(r"미정|미확정|검토|예정|계획|전망|가능성|추정|주장|필요", row)][:5]
    return {
        "summary_title": re.sub(r"\s*[-|·:]\s*[^-|·:]{1,30}$", "", clean_text(title)).strip() or clean_text(title),
        "article_summary": paragraphs,
        "core_summary": core,
        "six_w_one_h": {
            "who": [publisher] if publisher else [],
            "when": times or ([published_at] if published_at else []),
            "where": locations,
            "what": [first[:500]] if first else [],
            "why": causes,
            "how": methods,
            "result": [sentence_rows[-1][:500]] if sentence_rows else [],
        },
        "key_figures": key_figures,
        "fact_status": fact_status,
        "uncertainties": uncertain or ["기사 원문에서 별도로 확인할 중대한 불확실성 없음"],
    }


def narrative_fields(related: list[dict[str, str]], fallback: str) -> dict[str, object]:
    """Create a deterministic 6W1H evidence flow without an LLM."""
    ordered = sorted(related, key=lambda item: item.get("published_time") or item.get("published_at") or "")
    paragraphs: list[str] = []
    seen: set[str] = set()
    for index, source in enumerate(ordered):
        detail = clean_text(source.get("description", ""))
        if not detail or detail == source.get("title") or len(detail) < 25:
            detail = clean_text(source.get("title", ""))
        if not detail or detail in seen:
            continue
        seen.add(detail)
        lead = "보도에 따르면" if index == 0 else "같은 사안을 다룬 관련 보도에서는"
        paragraphs.append(f"{source.get('published_at', '')} {source.get('publisher', '원문')} {lead}, {detail.rstrip('.')}.")
    if not paragraphs:
        paragraphs = [fallback]
    full_text = " ".join(paragraphs)
    keywords: list[dict[str, str]] = []
    for term in MAX_HIGHLIGHT_TERMS:
        if term.lower() in full_text.lower():
            keywords.append({"term": term, "importance": "max", "wiki_query": term})
    for term in HIGH_HIGHLIGHT_TERMS:
        if term.lower() in full_text.lower() and not any(row["term"] == term for row in keywords):
            keywords.append({"term": term, "importance": "high", "wiki_query": term})
    primary = ordered[0] if ordered else {}
    structured = structured_summary_fields(str(primary.get("title") or fallback), str(primary.get("publisher") or ""), str(primary.get("published_at") or ""), paragraphs, fallback)
    structured.update({"narrative_paragraphs": paragraphs, "core_summary": fallback, "highlight_keywords": keywords})
    return structured


def classify_topic_region(text: str, sources: list[dict[str, str]] | None = None) -> str:
    """Classify by where the event started, not by the language of the article."""
    lowered = text.lower()
    if any(term.lower() in lowered for term in US_ORIGIN_TERMS):
        return "us"
    if any(term.lower() in lowered for term in GLOBAL_ORIGIN_TERMS):
        return "global"
    source_regions = [source.get("region") for source in (sources or []) if source.get("region") in {"us", "global"}]
    if source_regions:
        return max(set(source_regions), key=source_regions.count)
    return "domestic"


def numeric_charts(facts: list[dict[str, str]]) -> list[dict[str, object]]:
    groups: dict[str, list[dict[str, object]]] = {}
    allowed = {"%", "%p", "bp", "bps", "원", "달러", "엔", "유로", "억원", "억", "조원", "포인트", "배럴", "명", "건", "호"}
    for fact in facts:
        raw = str(fact.get("value", "")).replace(",", "").strip()
        number_match = re.search(r"[-+]?\d+(?:\.\d+)?", raw)
        unit = re.sub(r"[-+]?\d+(?:\.\d+)?", "", raw).strip()
        if not number_match or unit not in allowed:
            continue
        groups.setdefault(unit, []).append({"label": str(fact.get("context", ""))[:34], "value": float(number_match.group()), "display": fact.get("value", "")})
    candidates = [(unit, rows) for unit, rows in groups.items() if 2 <= len(rows) <= 10]
    if not candidates:
        return []
    unit, rows = max(candidates, key=lambda pair: len(pair[1]))
    return [{"type": "bar", "title": "기사에서 확인된 비교 수치", "subtitle": f"동일 단위 · {unit}", "rows": rows, "note": "서로 같은 단위인 공개 수치만 자동 비교했습니다. 기준기간과 대상은 각 문장을 확인하세요."}]


def has_verified_legacy_summary(item: dict[str, object]) -> bool:
    """Recognize substantive hand-edited archives without admitting title/RSS stubs."""
    paragraphs = item.get("article_summary") or item.get("narrative_paragraphs") or []
    paragraphs = [str(row).strip() for row in paragraphs if str(row).strip()]
    sources = item.get("sources") or []
    six_w = item.get("six_w_one_h") or {}
    return (
        len(paragraphs) >= 3
        and sum(map(len, paragraphs)) >= 250
        and len(str(item.get("core_summary") or "").strip()) >= 80
        and any(str(source.get("url") or "").startswith(("http://", "https://")) for source in sources)
        and all(isinstance(six_w.get(key), list) and six_w[key] for key in ("who", "when", "what", "why", "how"))
    )


def upgrade_existing_item(item: dict[str, object]) -> dict[str, object]:
    """Migrate archived cards to the single narrative format without network or GPT."""
    if item.get("article_body_status") == "fetched":
        item["article_body_status"] = "full_text"
    if not item.get("article_body_status") and has_verified_legacy_summary(item):
        item["article_body_status"] = "verified_reconstruction"
        if not item.get("narrative_paragraphs") and item.get("article_summary"):
            item["narrative_paragraphs"] = list(item["article_summary"])
    if item.get("article_body_status") in {"full_text", "verified_reconstruction"} and item.get("narrative_paragraphs") and item.get("core_summary") and all(key in item for key in STRUCTURED_KEYS):
        item["publication_status"] = "detail"
        for obsolete in ("sections", "expert_analysis", "timeline", "fact_ledger", "coverage_status", "coverage_note", "causal_path"):
            item.pop(obsolete, None)
        return item
    if item.get("article_body_status") in {"full_text", "verified_reconstruction"} and item.get("narrative_paragraphs"):
        paragraphs = [str(row) for row in item.get("narrative_paragraphs") or [] if str(row).strip()]
        item.update(structured_summary_fields(str(item.get("title", "")), str(item.get("publisher", "원문")), str(item.get("date", "")), paragraphs, str(item.get("core_summary") or item.get("summary") or "")))
        item["summary_schema_version"] = SUMMARY_SCHEMA_VERSION
        item["publication_status"] = "detail"
        return item
    sources = item.get("sources") or []
    prepared: list[dict[str, str]] = []
    for index, source in enumerate(sources):
        prepared.append({
            **source,
            "title": str(source.get("title_ko") or source.get("title") or item.get("title", "")),
            "description": str(source.get("summary_ko") or source.get("description") or source.get("summary_original") or (item.get("easy_explanation") if index == 0 else "") or ""),
            "published_at": str(source.get("published_at") or item.get("date", "")),
            "published_time": str(source.get("published_time") or source.get("published_at") or item.get("date", "")),
            "publisher": str(source.get("publisher") or item.get("publisher") or "원문"),
            "region": str(source.get("region") or item.get("region") or "domestic"),
        })
    if not prepared:
        prepared = [{"title": str(item.get("title", "")), "description": str(item.get("easy_explanation") or item.get("summary") or item.get("title", "")), "published_at": str(item.get("date", "")), "published_time": str(item.get("date", "")), "publisher": str(item.get("publisher") or "원문"), "region": str(item.get("region") or "domestic")}]
    fallback = str(item.get("easy_explanation") or item.get("summary") or item.get("title", ""))
    facts = extract_number_facts(prepared)
    item.update(narrative_fields(prepared, fallback))
    item["news_charts"] = numeric_charts(facts)
    item["publication_status"] = "statistics_only"
    item["region"] = classify_topic_region(" ".join(f"{row.get('title', '')} {row.get('description', '')}" for row in prepared), prepared)
    for obsolete in ("sections", "expert_analysis", "timeline", "fact_ledger", "coverage_status", "coverage_note", "causal_path"):
        item.pop(obsolete, None)
    return item


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
    """Translate with DeepL, then a keyless fallback; never invent missing content."""
    key = os.environ.get("DEEPL_API_KEY", "").strip()
    if not texts:
        return None
    if key:
        try:
            endpoint = os.environ.get("DEEPL_API_URL", "").strip() or ("https://api-free.deepl.com/v2/translate" if key.endswith(":fx") else "https://api.deepl.com/v2/translate")
            payload = json.dumps({"text": texts, "target_lang": "KO"}, ensure_ascii=False).encode("utf-8")
            request = Request(endpoint, data=payload, headers={"User-Agent": USER_AGENT, "Authorization": f"DeepL-Auth-Key {key}", "Content-Type": "application/json", "Accept": "application/json"}, method="POST")
            with urlopen(request, timeout=45) as response:
                rows = json.loads(response.read().decode("utf-8")).get("translations", [])
            translated = [clean_text(row.get("text", "")) for row in rows]
            if len(translated) == len(texts) and all(translated):
                return translated
        except Exception:
            pass
    try:
        from deep_translator import GoogleTranslator
        translated = [clean_text(GoogleTranslator(source="auto", target="ko").translate(text[:4500])) for text in texts]
        return translated if len(translated) == len(texts) and all(translated) else None
    except Exception:
        return None


def translate_summary_fields(fields: dict[str, object]) -> dict[str, object]:
    paragraphs = [str(row) for row in fields.get("article_summary") or fields.get("narrative_paragraphs") or []]
    texts = [str(fields.get("summary_title") or ""), *paragraphs, str(fields.get("core_summary") or "")]
    translated = translate_to_korean(texts)
    if not translated:
        fields["translation_status"] = "translation_unavailable"
        return fields
    title, core = translated[0], translated[-1]
    korean_paragraphs = translated[1:-1]
    rebuilt = structured_summary_fields(title, "번역 원문", "", korean_paragraphs, core)
    fields.update(rebuilt)
    fields.update({"summary_title": title, "article_summary": korean_paragraphs, "narrative_paragraphs": korean_paragraphs, "core_summary": core, "translation_status": "translated"})
    return fields


VIDEO_TITLE_PATTERN = re.compile(r"(?:\[영상\]|\[동영상\]|\bvideo\b|\bwatch\b)", re.I)
YOUTUBE_EMBED_PATTERN = re.compile(r"(?:youtube(?:-nocookie)?\.com/(?:watch\?(?:[^\"'<> ]*&)?v=|embed/|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})", re.I)
CAPTION_SIGNAL_PATTERN = re.compile(r"\b(?:fed|federal reserve|rate|inflation|economy|market|stock|bond|yield|dollar|oil|gold|trade|tariff|earnings|recession|growth|jobs?|unemployment|housing|mortgage|bitcoin)\b|\d", re.I)


def youtube_video_id(url: str) -> str:
    """Return a validated YouTube id from common public URL forms."""
    try:
        parsed = urlparse(html.unescape(url or ""))
    except ValueError:
        return ""
    host = parsed.netloc.lower().split(":", 1)[0]
    if host.endswith("youtu.be"):
        candidate = parsed.path.strip("/").split("/", 1)[0]
    elif host.endswith("youtube.com") or host.endswith("youtube-nocookie.com"):
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith(("/embed/", "/shorts/", "/live/")):
            candidate = parsed.path.strip("/").split("/", 1)[1].split("/", 1)[0]
        else:
            candidate = ""
    else:
        candidate = ""
    return candidate if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate or "") else ""


def discover_youtube_url(source_url: str) -> str:
    """Find an embedded YouTube video on a public article page without executing scripts."""
    direct_id = youtube_video_id(source_url)
    if direct_id:
        return f"https://www.youtube.com/watch?v={direct_id}"
    parsed = urlparse(source_url or "")
    if parsed.scheme not in {"http", "https"} or "news.google.com" in parsed.netloc.lower():
        return ""
    request = Request(source_url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urlopen(request, timeout=25) as response:
        page = response.read(2_000_000).decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    match = YOUTUBE_EMBED_PATTERN.search(html.unescape(page).replace("\\/", "/"))
    return f"https://www.youtube.com/watch?v={match.group(1)}" if match else ""


def select_caption_excerpts(events: list[dict[str, object]], limit: int = 8, word_limit: int = 150) -> list[dict[str, object]]:
    """Select short, investment-relevant caption passages and keep their chronology."""
    candidates: list[tuple[int, int, dict[str, object]]] = []
    for index, event in enumerate(events):
        text = clean_text(str(event.get("text", ""))).replace("♪", "").strip()
        words = text.split()
        if len(words) < 4 or text.startswith("["):
            continue
        score = min(6, len(CAPTION_SIGNAL_PATTERN.findall(text))) + (2 if index < 8 else 0)
        candidates.append((score, index, {"start_seconds": round(float(event.get("start_seconds") or 0), 1), "original": text}))
    selected = sorted(candidates, key=lambda row: (row[0], -row[1]), reverse=True)[: limit * 2]
    selected.sort(key=lambda row: float(row[2].get("start_seconds") or 0))
    output: list[dict[str, object]] = []
    used_words = 0
    for _score, _index, row in selected:
        words = str(row["original"]).split()
        remaining = word_limit - used_words
        if remaining < 4:
            break
        if len(words) > remaining:
            words = words[:remaining]
            row["original"] = " ".join(words) + "…"
        seconds = int(float(row["start_seconds"]))
        row["time"] = f"{seconds // 60:02d}:{seconds % 60:02d}"
        output.append(row)
        used_words += len(words)
        if len(output) >= limit:
            break
    return output


def fetch_youtube_captions(video_url: str) -> dict[str, object]:
    """Fetch key excerpts from YouTube's publicly exposed English caption track."""
    video_id = youtube_video_id(video_url)
    if not video_id:
        raise ValueError("지원하지 않는 유튜브 주소")
    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    request = Request(watch_url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    with urlopen(request, timeout=30) as response:
        page = response.read(4_000_000).decode("utf-8", errors="replace")
    marker = '\"captionTracks\":'
    start = page.find(marker)
    if start < 0:
        raise LookupError("공개 자막 없음")
    tracks, _ = json.JSONDecoder().raw_decode(page, start + len(marker))
    english = [track for track in tracks if str(track.get("languageCode", "")).lower().startswith("en")]
    if not english:
        raise LookupError("공개 영어 자막 없음")
    track = sorted(english, key=lambda row: row.get("kind") == "asr")[0]
    caption_url = html.unescape(str(track.get("baseUrl", "")))
    request = Request(caption_url + ("&" if "?" in caption_url else "?") + "fmt=json3", headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    events = []
    for event in payload.get("events", []):
        text = "".join(str(segment.get("utf8", "")) for segment in event.get("segs", []))
        if clean_text(text):
            events.append({"start_seconds": float(event.get("tStartMs", 0)) / 1000, "text": text})
    excerpts = select_caption_excerpts(events)
    if not excerpts:
        raise LookupError("표시할 수 있는 공개 영어 자막 없음")
    originals = [str(row["original"]) for row in excerpts]
    translated = translate_to_korean(originals)
    for index, row in enumerate(excerpts):
        row["translation"] = translated[index] if translated else ""
    return {
        "video_id": video_id, "source_url": watch_url, "language": "en",
        "caption_kind": "auto" if track.get("kind") == "asr" else "manual",
        "summary": " ".join((translated or originals)[:3])[:900],
        "translation_status": "translated" if translated else "translation_unavailable",
        "excerpts": excerpts,
        "excerpt_policy": "투자 판단 관련 주요 구간만 시간순으로 발췌",
    }


def enrich_video_news(items: list[dict[str, object]], page_budget: int = 6) -> None:
    """Attach captions to selected video news; never infer dialogue when captions are absent."""
    inspected = 0
    for item in items:
        sources = item.get("sources") or []
        direct = next((str(source.get("url", "")) for source in sources if youtube_video_id(str(source.get("url", "")))), "")
        if not direct and not VIDEO_TITLE_PATTERN.search(str(item.get("title", ""))):
            continue
        video_url = direct
        if not video_url and inspected < page_budget:
            inspected += 1
            for source in sources[:2]:
                try:
                    video_url = discover_youtube_url(str(source.get("url", "")))
                except Exception:
                    video_url = ""
                if video_url:
                    break
        if not video_url:
            item["video_transcript"] = {"status": "captions_unavailable", "message": "기사에서 공개 영어 자막이 있는 영상 주소를 확인하지 못했습니다."}
            continue
        try:
            item["video_transcript"] = {"status": "available", **fetch_youtube_captions(video_url)}
            transcript = item["video_transcript"]
            translated_paragraphs = [str(row.get("translation", "")) for row in transcript.get("excerpts", []) if row.get("translation")]
            if translated_paragraphs:
                fields = structured_summary_fields(str(item.get("title", "")), str(item.get("publisher", "영상 원문")), str(item.get("date", "")), translated_paragraphs, str(transcript.get("summary", "")))
                fields.update({"narrative_paragraphs": translated_paragraphs, "summary_basis": "공개 동영상 자막 번역", "summary_schema_version": SUMMARY_SCHEMA_VERSION})
                item.update(fields)
                item["summary"] = str(fields.get("core_summary", ""))[:900]
        except Exception as error:
            item["video_transcript"] = {"status": "captions_unavailable", "source_url": video_url, "message": str(error)[:180]}


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
            published_time = published_at.isoformat(timespec="minutes")
        except (TypeError, ValueError):
            published_date = target.isoformat()
            published_time = published_date
        rows.append({"title": title, "url": link, "publisher": publisher or "뉴스 원문", "description": description, "published_at": published_date, "published_time": published_time, "region": classify_region(publisher, region)})
    return rows


def fetch_direct_feed(url: str, publisher: str, region: str, target: date) -> list[dict[str, str]]:
    """Read publisher RSS directly so related links point to the original article."""
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml"})
    with urlopen(request, timeout=40) as response:
        root = ET.fromstring(response.read())
    rows: list[dict[str, str]] = []
    nodes = root.findall("./channel/item")
    for item in nodes:
        title = clean_text(item.findtext("title") or "")
        link = clean_text(item.findtext("link") or "")
        description = clean_text(item.findtext("description") or "")
        published = item.findtext("pubDate") or item.findtext("{http://purl.org/dc/elements/1.1/}date") or ""
        try:
            published_at = parsedate_to_datetime(published).astimezone(timezone(timedelta(hours=9)))
            published_date, published_time = published_at.date().isoformat(), published_at.isoformat(timespec="minutes")
        except (TypeError, ValueError):
            published_date, published_time = target.isoformat(), target.isoformat()
        if title and link and published_date == target.isoformat():
            rows.append({"title": title, "url": link, "publisher": publisher, "description": description, "published_at": published_date, "published_time": published_time, "region": region})
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
            rows.append({"title": title, "url": link, "publisher": "The New York Times", "description": description, "published_at": published, "published_time": published, "region": "us", "engagement": {"rank": rank, "metric": "NYT most viewed"}})
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
        description = row["title"]
    description = description[:4000]
    sources = []
    seen_publishers = set()
    for source in related:
        if source["publisher"] in seen_publishers:
            continue
        seen_publishers.add(source["publisher"])
        source_entry = {"publisher": source["publisher"], "title": source["title"], "url": source["url"], "published_at": source["published_at"], "published_time": source.get("published_time", source["published_at"]), "description": source.get("description", "")[:4000], "region": source.get("region", "domestic")}
        if source.get("region") in {"us", "global"}:
            source_entry.update({"summary_original": source["description"][:4000], "translation_status": "translation_api_key_required"})
        sources.append(source_entry)
    fact_ledger = extract_number_facts(related)
    numbers = list(dict.fromkeys(fact["value"] for fact in fact_ledger))
    metrics = [{"label": "관련 보도", "value": f"{len(related)}건", "note": "유사 제목 묶음"}, {"label": "확인 매체", "value": f"{len(sources)}곳", "note": "중복 매체 제외"}]
    metrics.extend({"label": f"기사 수치 {index}", "value": value, "note": "원문 제목·공개요약"} for index, value in enumerate(numbers, 1))
    timeline = [{
        "published_time": source.get("published_time", source.get("published_at", "")),
        "publisher": source.get("publisher", "원문"),
        "title": source.get("title", ""),
        "summary": source.get("description", "") or "공개 피드에는 제목 외 요약이 제공되지 않았습니다.",
        "region": source.get("region", "domestic"),
    } for source in sorted(related, key=lambda item: item.get("published_time") or item.get("published_at") or "")]
    has_public_summaries = sum(bool(source.get("description") and len(source.get("description", "")) >= 25) for source in related)
    narrative = narrative_fields(related, description)
    topic_region = classify_topic_region(" ".join(f"{source.get('title', '')} {source.get('description', '')}" for source in related), related)
    return {
        "id": f"news-{row['published_at'].replace('-', '')}-{digest}",
        "date": row["published_at"],
        "eyebrow": f"ECONOMY NEWS · {category}",
        "read_minutes": max(3, min(15, 2 + len(timeline) + len(fact_ledger) // 4)),
        "title": row["title"][:78],
        "summary": description[:500],
        "tags": [category, row["publisher"][:18]],
        "category": category,
        "publisher": row["publisher"][:40],
        "region": topic_region,
        "engagement": row.get("engagement", {}),
        "related_reports": len(related),
        "source_count": len(sources),
        "easy_explanation": description,
        "market_comment": MARKET_COMMENTS[category],
        **narrative,
        "news_charts": numeric_charts(fact_ledger),
        "metrics": metrics,
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
        source.update({"title_ko": translated[index * 2], "summary_ko": translated[index * 2 + 1], "translation_status": "translated", "translation_provider": "자동 번역"})
    for item in items:
        translated_by_title = {str(source.get("title")): source for source in item.get("sources") or []}
        for event in item.get("timeline") or []:
            translated_source = translated_by_title.get(str(event.get("title")))
            if translated_source and translated_source.get("summary_ko"):
                event["title_ko"] = translated_source.get("title_ko")
                event["summary_ko"] = translated_source.get("summary_ko")
        narrative_sources = []
        for source in item.get("sources") or []:
            narrative_sources.append({**source, "title": source.get("title_ko") or source.get("title", ""), "description": source.get("summary_ko") or source.get("description", "")})
        if narrative_sources:
            item.update(narrative_fields(narrative_sources, narrative_sources[0].get("description") or narrative_sources[0].get("title", "")))


def _article_enrichment(item: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    sources = list(item.get("sources") or [])
    sources.sort(key=lambda source: ("news.google.com" in str(source.get("url", "")), -representative_score(source)[0]))
    last_error = ""
    for source in sources[:3]:
        url = str(source.get("url", ""))
        if not url:
            continue
        try:
            sentences, final_url = fetch_article_sentences(url)
        except Exception as error:
            last_error = str(error)[:160]
            continue
        if len(sentences) < 3 or len(" ".join(sentences)) < 350:
            last_error = "공개 본문 분량 부족"
            continue
        fields = sixw_summary_from_sentences(
            str(item.get("title", "")), str(source.get("publisher") or item.get("publisher") or "원문"),
            str(source.get("published_at") or item.get("date") or ""), sentences,
        )
        if item.get("region") in {"us", "global"}:
            fields = translate_summary_fields(fields)
        fields["article_source_url"] = final_url
        fields["title"] = str(source.get("title_ko") or source.get("title") or item.get("title") or "")[:78]
        fields["publisher"] = str(source.get("publisher") or item.get("publisher") or "원문")[:40]
        fields["primary_source_role"] = "full_text"
        fields["statistics_only_source_count"] = max(0, len(sources) - 1)
        fields["article_body_checked_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        fields["article_body_attempts"] = int(item.get("article_body_attempts") or 0) + 1
        fields["summary_schema_version"] = SUMMARY_SCHEMA_VERSION
        fields["next_body_retry_at"] = ""
        return item, fields
    return item, {
        "article_body_status": "unavailable",
        "publication_status": "statistics_only",
        "article_body_error": last_error or "공개 원문 본문을 확보하지 못함",
        "article_body_checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "summary_basis": "제목·RSS 공개요약",
        "article_body_attempts": int(item.get("article_body_attempts") or 0) + 1,
        "summary_schema_version": SUMMARY_SCHEMA_VERSION,
        "next_body_retry_at": (date.today() + timedelta(days=7)).isoformat(),
    }


def article_retry_due(item: dict[str, object]) -> bool:
    if item.get("article_body_status") in {"fetched", "full_text", "verified_reconstruction"}:
        return False
    if int(item.get("summary_schema_version") or 0) < SUMMARY_SCHEMA_VERSION:
        return True
    retry_at = str(item.get("next_body_retry_at") or "")
    return bool(retry_at and retry_at <= date.today().isoformat())


def enrich_article_bodies(items: list[dict[str, object]], limit: int | None = None, workers: int = 6) -> None:
    """Fetch representative public bodies concurrently, then replace feed-only summaries."""
    pending = [item for item in items if article_retry_due(item)]
    if limit is not None:
        pending = pending[: max(0, limit)]
    if not pending:
        return
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as executor:
        futures = [executor.submit(_article_enrichment, item) for item in pending]
        for future in as_completed(futures):
            try:
                item, fields = future.result()
            except Exception as error:
                print(f"기사 원문 본문 처리 실패: {error}")
                continue
            item.update(fields)
            if fields.get("article_body_status") in {"full_text", "verified_reconstruction"}:
                item["summary"] = str(fields.get("core_summary", item.get("summary", "")))[:900]
                item["easy_explanation"] = str(fields.get("narrative_paragraphs", [item.get("summary", "")])[0])
                prepared = [{"title": str(item.get("title", "")), "description": str(item.get("easy_explanation", "")), "publisher": str(item.get("publisher", "원문")), "published_at": str(item.get("date", "")), "published_time": str(item.get("date", ""))}]
                item["news_charts"] = numeric_charts(extract_number_facts(prepared))


def enrich_archived_bodies(limit: int) -> int:
    """Gradually migrate past archives so each scheduled run makes bounded progress."""
    if limit <= 0:
        return 0
    targets: list[tuple[Path, dict[str, object], dict[str, object]]] = []
    payloads: dict[Path, dict[str, object]] = {}
    for path in sorted(NEWS_DIR.glob("20??-??-??.json"), reverse=True):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payloads[path] = payload
        for item in payload.get("items", []):
            if article_retry_due(item):
                targets.append((path, payload, item))
                if len(targets) >= limit:
                    break
        if len(targets) >= limit:
            break
    if not targets:
        return 0
    enrich_article_bodies([item for _path, _payload, item in targets], workers=6)
    touched = {path for path, _payload, _item in targets}
    for path in touched:
        path.write_text(json.dumps(payloads[path], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(targets)


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
    for url, publisher, region in DIRECT_RSS_FEEDS:
        try:
            for row in fetch_direct_feed(url, publisher, region, target):
                key = SPACE_PATTERN.sub("", row["title"].lower())
                unique.setdefault(key, row)
        except Exception as error:
            print(f"{target} {publisher} 직접 RSS 일부 실패: {error}")
        time.sleep(0.15)
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
    enrich_article_bodies(items)
    enrich_video_news(items)
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
        items = mark_important([upgrade_existing_item(item) for item in payload.get("items", [])])
        payload["items"] = items
        path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        archives.append({"date": payload.get("date"), "count": len(items), "file": path.name})
        detailed_items = [item for item in items if item.get("article_body_status") in {"full_text", "verified_reconstruction"}]
        if not latest_archive_items:
            latest_archive_items = detailed_items
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
        "latest_items": [item for item in all_items if item.get("article_body_status") in {"full_text", "verified_reconstruction"}][:12],
        "important_items": important_items,
        "importance_method": "실제 조회수·좋아요 미제공 · 유사 보도 확산, 매체 다양성, 대표 기사 품질, 출처 신뢰도, 금리 결정 등 시장 영향도로 산정",
        # Keep the first load light on mobile. Older days load on demand.
        "items": all_items[:600],
        "detailed_articles": sum(item.get("article_body_status") in {"full_text", "verified_reconstruction"} for item in all_items),
        "statistics_only_articles": sum(item.get("article_body_status") not in {"full_text", "verified_reconstruction"} for item in all_items),
        "archives": archives,
    }
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="경제·금융·산업·부동산 뉴스 RSS를 날짜별로 보관합니다.")
    parser.add_argument("--backfill-days", type=int, default=1)
    parser.add_argument("--limit-per-day", type=int, default=24)
    parser.add_argument("--archive-enrich-limit", type=int, default=60, help="한 실행에서 과거 원문 본문을 다시 처리할 최대 기사 수")
    parser.add_argument("--archive-only", action="store_true", help="새 뉴스 수집 없이 과거 기사 구조화만 실행")
    args = parser.parse_args()
    days = max(1, min(args.backfill_days, 365))
    limit = max(6, min(args.limit_per_day, 60))
    archive_limit = max(0, min(args.archive_enrich_limit, 120))
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today()
    if not args.archive_only:
        for offset in range(days - 1, -1, -1):
            target = today - timedelta(days=offset)
            items = collect_day(target, limit)
            if items:
                write_day(target, items)
                print(f"{target}: {len(items)}건 저장")
    enriched = enrich_archived_bodies(archive_limit)
    if enriched:
        print(f"과거 기사 원문 본문 재처리: {enriched}건")
    rebuild_index()
    print(f"경제뉴스 인덱스 생성 완료: {INDEX_PATH}")


if __name__ == "__main__":
    main()
