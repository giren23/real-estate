from __future__ import annotations

import argparse
import base64
import codecs
import gzip
import hashlib
import html
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import sys
import threading
import time
import uuid
import zlib
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlencode, urlunparse, quote, quote_plus, unquote, urljoin, urlparse
from urllib.error import URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPHandler, HTTPSHandler

try:  # Mozilla's root store; several Korean news sites chain to roots Windows' store lacks.
    import certifi
except Exception:  # pragma: no cover - the server's other Python may not ship it
    certifi = None

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
import news_quality as NQ  # noqa: E402  (network-free extraction/structuring rules)


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
    ("https://www.dt.co.kr/rss/rss_economy.html", "디지털타임스", "domestic"),
    ("https://rss.blog.naver.com/dealsite.xml", "딜사이트", "domestic"),
    ("https://nypost.com/business/feed/", "New York Post", "us"),
    ("https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "The New York Times", "us"),
    ("https://feeds.bbci.co.uk/news/business/rss.xml", "BBC", "global"),
    ("https://www.theguardian.com/business/rss", "The Guardian", "global"),
    ("https://www.cnbc.com/id/10001147/device/rss/rss.html", "CNBC", "us"),
)
# Public, publisher-owned listing pages used only after the feed URL and the
# two public news indexes could not verify an article.  This deliberately is a
# small allow-list: it is a normal daily archive read, not broad crawling or a
# way to evade a publisher's access controls.
PUBLISHER_DAILY_SECTIONS = {
    "benzinga": (
        ("publisher_archive_news", "https://kr.benzinga.com/news/"),
        ("publisher_archive_economy", "https://kr.benzinga.com/category/news/economy/"),
    ),
}
PUBLISHER_SEARCH_ENDPOINTS = {
    # The public magnifier/search page is the preferred publisher-owned path.
    # Section listings are only a fallback when this search page is absent or
    # cannot verify a matching article.
    "머니투데이": ("publisher_search_moneytoday", "https://www.mt.co.kr/search/{query}/news"),
    "글로벌이코노믹": ("publisher_search_global_economy", "https://news.g-enews.com/search.php?sn={query}"),
}
PUBLISHER_ALIASES = {
    "bloomingbit.io": "블루밍비트",
}
BLOOMINGBIT_SEARCH_API = "https://v3-gtw.bloomingbit.io/nexus/news/searches"
RECENT_ARTICLE_RETRY_HOURS = 3
RECENT_ARTICLE_DAYS = 2
TAG_PATTERN = re.compile(r"<[^>]+>")
SPACE_PATTERN = re.compile(r"\s+")
TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z0-9]+")
STOPWORDS = {"관련", "대한", "이번", "오늘", "내일", "정부", "시장", "뉴스", "전망", "발표", "한국", "미국"}
NUMBER_PATTERN = re.compile(
    r"(?<![\w.])(?:[$€£¥]\s*)?\d[\d,.]*(?:\.\d+)?\s*(?:%p|%|bp|bps|basis\s+points?|조원|억원|억|만원|원|달러|엔|유로|trillion|billion|million|조|만|건|척|호|명|대|배럴|포인트|년|개월|월|분기|일)?",
    re.I,
)
SENTENCE_PATTERN = re.compile(r"(?<=[.!?。])(?:\s+|(?=[가-힣A-Z][가-힣A-Za-z]))")
CAUSE_PATTERN = re.compile(r"때문|따라|영향|여파|압력|우려|배경|이유|목적|위해|으로 인해|기인|(?:부진|상승|하락|증가|감소)으로|그치면서|웃돌면서|밑돌면서", re.I)
METHOD_PATTERN = re.compile(r"통해|활용|발표|집계|조사|인용|설정|계획|방식|구조|계약|체결|조치|추진|투입|인수|매각|인상|인하|검토|절차|대응", re.I)
TIME_PATTERN = re.compile(r"(?:\d{1,4}년|\d{1,2}월|\d{1,2}일|최근|현재|지난|올해|내년|상반기|하반기|분기|당시)")
RESULT_PATTERN = re.compile(r"결과|이에|그에 따라|상승|하락|증가|감소|확대|축소|개선|악화|이어질|영향|전망|예상", re.I)
ACTION_PATTERN = re.compile(r"발표|결정|의결|체결|공시|출시|시행|공포|주문|수주|인상|인하|동결|급등|급락|증가|감소", re.I)
ARTICLE_NOISE_PATTERN = re.compile(
    r"(?:무단전재|재배포|저작권|기자\s*[\w.@-]+|구독|로그인|댓글|공감|관련기사|ADVERTISEMENT|Copyright|All rights reserved|"
    r"요약보기|자동요약|전체 맥락을 이해|음성으로 듣기|음성재생|음성 재생|글자 수|번역 설정|번역 beta|Translated by|"
    r"번역중|Now in translation|글씨크기|글자크기|닫기|인쇄하기|페이스북|Facebook|Twitter|LinkedIn|Pinterest|공유|"
    r"주소\s*:\s*서울특별시|일간신문등록번호|인터넷신문등록번호|등록\s*\(발행\)일자|발행\s*/\s*편집인|"
    r"(?:[가-힣]{2,5}\s+)?기자\s*(?:/|입력|수정)|입력\s*:\s*\d{4})", re.I)
# Body contract shared with docs/editorial-prompts.md and the web UI (index.json
# carries NQ.BODY_CONTRACT).  MIN_ARTICLE_BODY_CHARS is the floor for a
# verified excerpt; full_text needs NQ.FULL_TEXT_MIN_CHARS/SENTENCES.
MIN_ARTICLE_BODY_CHARS = NQ.EXCERPT_MIN_CHARS
FULL_TEXT_MIN_CHARS = NQ.FULL_TEXT_MIN_CHARS
PUBLISHABLE_BODY_STATUSES = {"fetched", "full_text", "verified_excerpt", "verified_reconstruction"}
BLOG_HOSTS = {"blog.naver.com", "m.blog.naver.com", "post.naver.com", "brunch.co.kr"}


CATEGORY_RULES = (
    ("부동산", ("부동산", "주택", "아파트", "전세", "월세", "분양", "재건축", "재개발")),
    ("금리·채권", ("금리", "국채", "채권", "연준", "한국은행", "기준금리")),
    ("가상자산", ("비트코인", "가상자산", "암호화폐", "이더리움")),
    ("원자재", ("유가", "원유", "기름값", "휘발유", "경유", "금값", "은값", "구리", "원자재")),
    ("환율", ("환율", "달러", "원화", "엔화", "위안화", "외환")),
    ("산업·기업", ("반도체", "기업", "실적", "수출", "자동차", "배터리", "조선")),
    ("증시", ("코스피", "코스닥", "나스닥", "다우", "S&P", "증시", "주가")),
)
PORTAL_HOSTS = {"v.daum.net", "news.daum.net", "news.naver.com", "n.news.naver.com"}
DISCOVERY_SEARCH_HOSTS = {"search.naver.com", "search.daum.net"}
DISCOVERY_LOCK = threading.Lock()
LAST_DISCOVERY_REQUEST_AT = 0.0
GOOGLE_NEWS_RESOLVE_LOCK = threading.Lock()
LAST_GOOGLE_NEWS_RESOLVE_AT = 0.0


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
TRUSTED_PUBLISHERS = ("연합뉴스", "뉴시스", "뉴스1", "한국은행", "기획재정부", "금융위원회", "한국거래소", "KBS", "MBC", "SBS", "로이터", "Reuters", "블룸버그", "Bloomberg", "한경", "매일경제", "서울경제", "이데일리", "The New York Times", "New York Times", "New York Post", "Fortune", "Financial Times", "The Wall Street Journal", "Wall Street Journal", "Associated Press", "AP News", "BBC", "CNBC", "The Guardian", "The Economist", "Nikkei Asia", "The Washington Post")
US_PUBLISHERS = ("New York Times", "New York Post", "Fortune", "Wall Street Journal", "CNBC", "Bloomberg", "Associated Press", "AP News", "Washington Post", "MarketWatch", "Barron's", "CBS", "NBC", "ABC News", "CNN")
KOREAN_PUBLISHERS = ("연합뉴스", "한국은행", "기획재정부", "금융위원회", "한국거래소", "KBS", "MBC", "SBS", "한경", "한국경제", "매일경제", "서울경제", "이데일리", "조선일보", "중앙일보", "동아일보", "전자신문")
IMPACT_KEYWORDS = ("기준금리", "연준", "금리 인상", "금리 인하", "환율", "국채", "물가", "고용", "GDP", "관세", "수출", "실적", "코스피", "코스닥", "나스닥", "유가", "원유", "기름값", "금값", "반도체", "부동산 정책", "대출 규제", "세제")
INVESTMENT_RELEVANCE = ("금리", "연준", "환율", "달러", "국채", "채권", "물가", "고용", "GDP", "관세", "무역", "수출", "실적", "코스피", "코스닥", "나스닥", "다우", "주가", "유가", "원유", "금값", "구리", "반도체", "비트코인", "ETF", "주택", "아파트", "대출", "분양", "재건축", "재개발", "공급", "세제", "세금")
MAX_HIGHLIGHT_TERMS = ("기준금리 인상", "기준금리 인하", "금리 인상", "금리 인하", "공급 중단", "대규모 감원", "법정관리", "부도", "디폴트")
HIGH_HIGHLIGHT_TERMS = ("연방준비제도", "연준", "한국은행", "기준금리", "국채", "환율", "관세", "물가", "고용", "GDP", "코스피", "코스닥", "나스닥", "반도체", "비트코인", "국토교통부", "공공주택", "재생에너지", "RE100")
NOISE_KEYWORDS = ("화재", "사망", "숨져", "대피", "홍수", "실종", "범죄", "교통사고", "연예", "Weverse", "TXT-LOG", "프라하하하", "[포토]", "[사진]", "AK포토", "[TVis]", "미우새", "시상식", "페스티벌", "위장전입", "부정청약")
NON_MARKET_EVENT_TERMS = ("시신", "살인", "살해", "용의자", "흉기", "강도", "납치", "성폭력", "실종")
MARKET_QUOTE_NOISE = ("check out", "stock price", "share price", "etf price", "price target")
NON_ARTICLE_TITLE_PATTERN = re.compile(
    r"(?:\bNet Asset Value\s*\(s\)|^About .{0,180}\b(?:ETF|fund)\b|"
    r"\bFuture(?:s)?\b.{0,100}\b(?:Overview|Continuous Contract)\b|"
    r"^Check out .{0,180}\b(?:stock|share|ETF) price\b|\bCompany Profile\s*$|\bFund Overview\s*$|"
    r"\|\s*Stock Price\s*&\s*Latest News\s*$)",
    re.I,
)
NON_MARKET_INCIDENT_PATTERN = re.compile(r"(?:화재|숨져|사망|시신|살인|폭행|교통사고|실종|범죄|침몰)")
MARKET_CONSEQUENCE_PATTERN = re.compile(r"(?:증시|주가|시장|경제|보험|공급망|생산|공장|유가|원자재|손실액|피해액|영업중단)")
ENTERTAINMENT_TITLE_PATTERN = re.compile(
    r"(?:^\s*\[(?:사진|포토|AK포토|TVis)\]|\b공항\s*화보\b|투모로우바이투게더|시상식|패션쇼|예능|가수|배우|방송인|아빠\s*노래|미우새|Emmys?|\d{1,2}세\s+[가-힣]{2,5}\s*[“\"])", re.I,
)
NON_MARKET_POLITICS_PATTERN = re.compile(r"금품수수|특검|검찰|재판|구속|탄핵|여야|국민의힘|민주당|국회의원|팩트대로")
POLICY_MARKET_PATTERN = re.compile(r"증시|주가|금리|환율|유가|경제|예산|세제|부동산\s*정책|주택\s*공급|대출\s*규제|무역|관세")
NON_MARKET_SECTION_PATTERN = re.compile(r"/(?:entertainment|sports?|culture|policy/politics)(?:/|$)", re.I)
CRYPTO_SINGLE_ACTOR_PATTERN = re.compile(r"고래|주요 계정|전량 매도|전량 매수|지정가 주문|평단가", re.I)
FEDERAL_RESERVE_CONTEXT_PATTERN = re.compile(r"금리|FOMC|Fed(?:eral Reserve)?|중앙은행|국채|물가|증시|달러|통화정책|경제|고용", re.I)
RATE_DECISION_PATTERN = re.compile(r"(?:기준금리|정책금리|연준|한은|한국은행).{0,28}(?:인상|인하|동결|올렸|내렸)|(?:금리).{0,18}(?:인상 결정|인하 결정|동결 결정|올렸다|내렸다)", re.I)
US_ORIGIN_TERMS = ("미국", "美 ", "연방준비제도", "연준", "Federal Reserve", "Fed ", "트럼프", "Trump", "백악관", "White House", "월가", "Wall Street", "나스닥", "NASDAQ", "S&P 500", "뉴욕증시")
GLOBAL_ORIGIN_TERMS = ("중국", "中 ", "China", "일본", "日 ", "Japan", "유럽", "European Union", "EU ", "영국", "독일", "프랑스", "러시아", "우크라이나", "중동", "G7", "OPEC", "IMF", "세계은행", "World Bank")
SUMMARY_SCHEMA_VERSION = 6
STRUCTURED_KEYS = ("summary_title", "article_summary", "core_summary", "six_w_one_h", "key_figures", "fact_status", "uncertainties")


def clean_text(value: str) -> str:
    return SPACE_PATTERN.sub(" ", html.unescape(TAG_PATTERN.sub(" ", value or ""))).strip()


WIRE_NAMES = (
    r"(?:연합뉴스|로이터(?:\s*통신)?|블룸버그(?:\s*통신)?|Bloomberg|Reuters|Associated Press|AP News|AP통신|디지털타임스|이데일리|"
    r"매일경제|한국경제|뉴스1|뉴시스|머니투데이|문화일보|조선비즈|Chosunbiz|연합인포맥스|CNBC|월스트리트저널|WSJ|파이낸셜타임스|FT|"
    r"니혼게이자이(?:신문)?|닛케이|뉴욕타임스|NYT|AFP(?:통신)?|다우존스)"
)
SUMMARY_PROVENANCE_PATTERN = re.compile(
    # Attribution phrases only.  A wire service/publisher that is the grammatical
    # actor ("로이터가 경제학자 101명을 조사했다") is a fact and is kept.
    r"(?:v\.daum\.net|news\.daum\.net|news\.naver\.com|n\.news\.naver\.com)"
    r"|(?:https?://\S+|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|net|org|co\.kr|kr|io|jp|cn|uk|news|tv)\b)"
    r"|(?:\b\d{4}[./-]\s*\d{1,2}[./-]\s*\d{1,2}\.?\s+\d{1,2}:\d{2}\b|\b\d{4}\.\s*\d{1,2}:\d{2}\b)"
    r"|(?:\b[가-힣]{2,4}\s*(?:기자|특파원)\s*(?:=|[\w.+-]+@[\w.-]+))"
    r"|(?:같은 사안을 다룬 관련 보도(?:에서는)?|보도에 따르면|기사에 따르면|통신에 따르면|신문에 따르면)", re.I)
UI_PHRASE_PATTERN = re.compile(
    r"요약보기|자동요약|전체 맥락을 이해|음성으로 듣기|음성재생|음성 재생|번역 설정|번역 beta|Translated by|번역중|Now in translation|"
    r"글씨크기|글자크기|인쇄하기|무단전재(?:\s*(?:및|·)?\s*재배포\s*금지)?|재배포\s*금지|All rights reserved|ADVERTISEMENT", re.I)


def clean_summary_provenance(value: str) -> str:
    """Remove datelines, attribution and UI boilerplate while preserving actors and facts."""
    text = clean_evidence_sentence(value)
    text = re.sub(r"가장\s*빠른\s*뉴스가\s*있고.{0,100}다음뉴스를\s*만나보세요[.!]?", "", text)
    # Wire name immediately followed by a byline ("연합뉴스 홍길동 기자") is a credit line.
    text = re.sub(WIRE_NAMES + r"\s+(?=[가-힣]{2,4}\s*(?:기자|특파원)\b)", " ", text, flags=re.I)
    text = re.sub(r"(?:^|(?<=\s))[가-힣]{2,4}\s*(?:기자|특파원)(?=\s|$|=|,)", " ", text)
    # Only pure attribution is removed: "[서울=연합뉴스]", "(사진=AFP)",
    # "로이터통신에 따르면", "블룸버그 보도에 따르면".  A source that is the
    # subject of a fact or claim ("로이터가 …를 조사했다", "FT는 관계자를 인용해",
    # "AP통신 보도가 나오자") stays, because removing it breaks the sentence or
    # hides who made the claim.
    text = re.sub(WIRE_NAMES + r"\s*(?:통신)?\s*(?:의\s*)?(?:보도(?:에|에서)\s*)?(?:에\s*)?따르면\s*,?", " ", text, flags=re.I)
    text = re.sub(r"[(\[]\s*(?:[가-힣]{2,10}\s*=\s*" + WIRE_NAMES + r"|(?:사진|그래픽|자료|영상)\s*=\s*[^)\]]{1,30})\s*[)\]]", " ", text, flags=re.I)
    text = SUMMARY_PROVENANCE_PATTERN.sub(" ", text)
    text = UI_PHRASE_PATTERN.sub(" ", text)
    # Repair an already-sanitized archive sentence where a removed wire name
    # left only its Korean subject/topic particle, e.g. "(현지시간) 가 지난".
    text = re.sub(r"(?<=\))\s+[이가은는]\s+(?=(?:지난|올해|이번|오는|경제학자|시장|정부|미국|한국))", " ", text)
    text = re.sub(r"\b\d{1,2}:\d{2}\b", " ", text)
    text = re.sub(r"(?:^|\s)(?:\d{4}-\d{2}-\d{2}\s+)?[^,.]{1,40}\s+(?:보도에 따르면|기사에 따르면|전하면),?\s*", " ", text)
    text = re.sub(r"\s+([,.。;:])", r"\1", text)
    return SPACE_PATTERN.sub(" ", text).strip(" ,.;:·")


def strip_summary_provenance(item: dict[str, object]) -> dict[str, object]:
    """Sanitize all user-facing summary prose; source URLs remain in metadata."""
    prose_keys = {"summary", "easy_explanation", "core_summary", "article_summary", "narrative_paragraphs", "uncertainties", "fact_status", "six_w_one_h", "key_figures", "news_charts", "metrics"}
    preserve_keys = {"value", "period", "status", "type", "importance", "wiki_query"}

    def walk(value: object, key: str = "") -> object:
        if isinstance(value, str):
            if key in preserve_keys:
                return value
            cleaned = clean_summary_provenance(value)
            publishers = {str(item.get("publisher") or "")}
            publishers.update(str(source.get("publisher") or "") for source in item.get("sources") or [] if isinstance(source, dict))
            for publisher in sorted((token.strip() for token in publishers), key=len, reverse=True):
                if len(publisher) >= 2:
                    # Remove the publisher only where it is attribution, never
                    # where it is the subject of the event (e.g. 한국은행).
                    escaped = re.escape(publisher)
                    cleaned = re.sub(escaped + r"\s*(?:에|의)?\s*(?:따르면|보도(?:에|에서)?\s*(?:따르면)?)\s*,?", " ", cleaned, flags=re.I)
                    cleaned = re.sub(r"[(\[]\s*[가-힣]{2,10}\s*=\s*" + escaped + r"\s*[)\]]", " ", cleaned, flags=re.I)
                    cleaned = re.sub(escaped + r"\s*(?:은|는)?\s*(?:\d{4}-\d{2}-\d{2}\s+)?공개한 기사에서", " ", cleaned, flags=re.I)
            cleaned = re.sub(r"(?:[A-Za-z0-9가-힣._-]{2,40})(?:은|는)?\s*(?:\d{4}-\d{2}-\d{2}\s+)?공개한 기사에서", " ", cleaned)
            cleaned = re.sub(r"^\s*(?:은|는)\s+", "", cleaned)
            return SPACE_PATTERN.sub(" ", cleaned).strip(" ,.;:·")
        if isinstance(value, list):
            return [walk(row, key) for row in value]
        if isinstance(value, dict):
            return {name: (child if name in preserve_keys else walk(child, name)) for name, child in value.items()}
        return value

    for key in prose_keys:
        if key in item:
            item[key] = walk(item[key], key)
    return item


def is_probably_foreign(text: str) -> bool:
    """Detect source language from text, not the publisher's region label."""
    sample = clean_text(text)
    korean = len(re.findall(r"[가-힣]", sample))
    latin = len(re.findall(r"[A-Za-z]", sample))
    return latin >= 24 and latin > max(12, korean * 1.25)


class ArticleParagraphParser(HTMLParser):
    """Collect public article paragraphs and articleBody JSON without site-specific dependencies."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[str] = []
        self._capture = 0
        self._buffer: list[str] = []
        self._json_ld = False
        self._json_buffer: list[str] = []
        self._article_container_depth = 0
        self._article_container_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): value or "" for key, value in attrs}
        lowered_tag = tag.lower()
        if self._article_container_depth:
            if lowered_tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
                self._article_container_depth += 1
        elif lowered_tag in {"article", "main", "section", "div"}:
            marker = f"{attributes.get('id', '')} {attributes.get('class', '')}".lower()
            if re.search(
                r"(?:article|news|story)[-_ ]?(?:body|content|text|txt|view|detail)|"
                r"newsct_article|(?:view|news)[-_ ]?(?:content|cont|body|article)|content[-_ ]?view",
                marker,
            ):
                self._article_container_depth = 1
                self._article_container_buffer = []
        if lowered_tag == "meta":
            marker = f"{attributes.get('name', '')} {attributes.get('property', '')}".lower()
            if marker.strip() in {"description", "og:description", "twitter:description"}:
                description = clean_text(attributes.get("content", ""))
                if description:
                    self.paragraphs.append(description)
        if lowered_tag in {"p", "blockquote"}:
            self._capture += 1
            if self._capture == 1:
                self._buffer = []
        if tag.lower() == "script" and "ld+json" in attributes.get("type", "").lower():
            self._json_ld = True
            self._json_buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"p", "blockquote"} and self._capture:
            self._capture -= 1
            if self._capture == 0:
                text = clean_text(" ".join(self._buffer))
                if text:
                    self.paragraphs.append(text)
        if self._article_container_depth:
            self._article_container_depth -= 1
            if self._article_container_depth == 0:
                text = clean_text(" ".join(self._article_container_buffer))
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
        if self._article_container_depth:
            self._article_container_buffer.append(data)

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


def sentences_from_paragraphs(paragraphs: list[str]) -> list[str]:
    sentences: list[str] = []
    seen: set[str] = set()
    for paragraph in paragraphs:
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


def extract_article_page(page: str, title: str = "") -> NQ.Extraction:
    """Extract ONE body source with diagnostics (see news_quality.extract_article).

    The legacy ArticleParagraphParser merged meta descriptions, every <p>, whole
    containers (including inline <script> text) and JSON-LD into one list, which
    produced duplicated titles, UI text and code inside summaries.  It is kept
    only for backward-compatible imports.
    """
    # 매일경제의 refId 문단은 실제 기사 본문 경계다. 이후에 붙는 종목
    # 카드·AI 해설·푸터는 같은 p 태그를 쓰므로 일반 파서에 맡기면 섞인다.
    mk_body = [clean_text(part) for part in re.findall(r"<p\b[^>]*\brefId\s*=\s*['\"]?\d+['\"]?[^>]*>(.*?)</p>", page, re.I | re.S)]
    if len(mk_body) >= 2:
        extraction = NQ.extract_article(page, title)
        paragraphs = [" ".join(NQ.paragraph_sentences(row)) for row in mk_body]
        extraction.paragraphs = [row for row in paragraphs if row]
        extraction.path = "publisher_refid"
        extraction.boundary_closed = True
        return extraction
    return NQ.extract_article(page, title)


def article_sentences(page: str, title: str = "") -> list[str]:
    return extract_article_page(page, title).sentences


def source_role_for_url(url: str) -> str:
    """Distinguish a publisher page from portal/blog republications.

    ``full_text`` is the historical value for "publisher page" and is kept for
    stored-data compatibility; the UI labels it as 발행사 페이지.
    """
    host = urlparse(url).netloc.lower().split(":", 1)[0]
    if host in PORTAL_HOSTS:
        return "portal_republication"
    if host in BLOG_HOSTS:
        return "publisher_blog_republication"
    return "full_text"


class PublicLinkParser(HTMLParser):
    """Collect public HTTP(S) links from a search-result page without scripts."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href") or ""
        if href:
            self.links.append(html.unescape(href))


class PublisherListingParser(HTMLParser):
    """Collect visible article labels from a publisher's public daily listing."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self._href = dict(attrs).get("href") or ""
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            label = clean_text(" ".join(self._text))
            if label:
                self.links.append((label, html.unescape(self._href)))
            self._href = ""
            self._text = []


def _paced_public_request(url: str, *, accept: str = "text/html,application/xhtml+xml", headers: dict[str, str] | None = None) -> str:
    """Request public search pages slowly; this is reliability/rate etiquette, not bypassing access controls."""
    global LAST_DISCOVERY_REQUEST_AT
    with DISCOVERY_LOCK:
        elapsed = time.monotonic() - LAST_DISCOVERY_REQUEST_AT
        if elapsed < 1.2:
            time.sleep(1.2 - elapsed)
        request_headers = {"User-Agent": USER_AGENT, "Accept": accept, "Accept-Language": "ko-KR,ko;q=0.9"}
        request_headers.update(headers or {})
        request = Request(url, headers=request_headers)
        with urlopen(request, timeout=18) as response:
            page = response.read(1_500_000).decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        LAST_DISCOVERY_REQUEST_AT = time.monotonic()
    return page


def _unwrap_search_url(url: str, base_url: str) -> str:
    candidate = urljoin(base_url, url)
    parsed = urlparse(candidate)
    if parsed.netloc.lower().split(":", 1)[0] == "search.naver.com":
        values = parse_qs(parsed.query)
        for key in ("u", "url", "redirect"):
            if values.get(key):
                candidate = unquote(values[key][0])
                break
    return candidate


def is_article_candidate_url(url: str) -> bool:
    """Reject portal navigation/search pages that repeat the query but are not articles."""
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":", 1)[0]
    path = parsed.path.lower()
    query = parse_qs(parsed.query)
    if host in {"www.melon.com", "map.kakao.com", "shoppinghow.kakao.com", "search.shopping.naver.com"}:
        return False
    if any(segment in path for segment in ("/search", "/total", "/shopping", "/map")):
        return False
    if path in {"", "/"} or path.endswith(("/index.do", "/index.html", "/index.htm")):
        return False
    return not any(key in query for key in ("q", "query", "search"))


def is_news_article_candidate(item: dict[str, object]) -> bool:
    """Keep real investment news; reject quote/product pages and unrelated incidents."""
    title = clean_text(str(item.get("title") or ""))
    source_urls = " ".join(
        str(value or "")
        for value in [
            item.get("article_source_url"), item.get("canonical_source_url"),
            *[source.get("url") for source in (item.get("sources") or []) if isinstance(source, dict)],
        ]
    )
    if not title or NON_ARTICLE_TITLE_PATTERN.search(title):
        return False
    if NON_MARKET_SECTION_PATTERN.search(source_urls) and not POLICY_MARKET_PATTERN.search(title):
        return False
    if ENTERTAINMENT_TITLE_PATTERN.search(title):
        return False
    if NON_MARKET_POLITICS_PATTERN.search(title) and not POLICY_MARKET_PATTERN.search(title):
        return False
    # '연준'은 연방준비제도와 연예인 이름으로 모두 쓰인다. 금융 문맥이 없으면
    # 금리·시장 뉴스로 인식하지 않는다.
    if "연준" in title and not FEDERAL_RESERVE_CONTEXT_PATTERN.search(title):
        return False
    if NON_MARKET_INCIDENT_PATTERN.search(title) and not MARKET_CONSEQUENCE_PATTERN.search(title):
        return False
    return True


def recovery_search_links(title: str, publisher: str) -> list[dict[str, str]]:
    """Human-verifiable search paths saved when automatic full-text recovery fails."""
    query = clean_text(title)[:240]
    rows: list[dict[str, str]] = []
    publisher_key = clean_text(publisher).lower()
    for key, (method, template) in PUBLISHER_SEARCH_ENDPOINTS.items():
        if key.lower() in publisher_key:
            rows.append({"label": "발행사 검색", "method": method, "url": template.format(query=quote(query, safe=""))})
            break
    rows.extend([
        {"label": "네이버 뉴스 제목 검색", "method": "naver_search", "url": f"https://search.naver.com/search.naver?where=news&query={quote_plus(query)}"},
        {"label": "다음 뉴스 제목 검색", "method": "daum_search", "url": f"https://search.daum.net/search?w=news&q={quote_plus(query)}"},
        {"label": "Bing 뉴스 제목 검색", "method": "bing_news_search", "url": f"https://www.bing.com/news/search?q={quote_plus(query)}"},
    ])
    return rows


def is_publishable_detail(item: dict[str, object]) -> bool:
    """Single publication rule; the web UI mirrors it through ``detail_visible``."""
    gate = item.get("quality_gate")
    return (
        item.get("publication_status") == "detail"
        and item.get("article_body_status") in PUBLISHABLE_BODY_STATUSES
        and not (isinstance(gate, dict) and gate.get("passed") is False)
    )


def search_public_article_urls(title: str, publisher: str) -> list[tuple[str, str]]:
    """Find candidate publisher/portal URLs using public Naver and Daum search pages."""
    # The title is the stable identifier. Adding a publisher string can hide
    # valid results when the portal labels that publisher differently.
    query = clean_text(title)[:240]
    endpoints = (
        ("naver_search", f"https://search.naver.com/search.naver?where=news&query={quote_plus(query)}"),
        ("daum_search", f"https://search.daum.net/search?w=news&q={quote_plus(query)}"),
    )
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for discovery_method, endpoint in endpoints:
        try:
            parser = PublicLinkParser()
            parser.feed(_paced_public_request(endpoint))
        except Exception:
            continue
        for raw_url in parser.links:
            candidate = _unwrap_search_url(raw_url, endpoint)
            parsed = urlparse(candidate)
            host = parsed.netloc.lower().split(":", 1)[0]
            naver_internal = host.endswith(".naver.com") and host not in {"news.naver.com", "n.news.naver.com", "blog.naver.com"}
            daum_internal = host.endswith(".daum.net") and host not in PORTAL_HOSTS
            navigation_host = host in {"www.navercorp.com", "map.kakao.com", "shoppinghow.kakao.com"}
            if parsed.scheme not in {"http", "https"} or not host or host in DISCOVERY_SEARCH_HOSTS or host == "news.google.com" or naver_internal or daum_internal or navigation_host or not is_article_candidate_url(candidate):
                continue
            normalized = candidate.split("#", 1)[0]
            if normalized in seen:
                continue
            seen.add(normalized)
            candidates.append((discovery_method, normalized))
    publisher_host = clean_text(publisher).lower()
    candidates.sort(key=lambda row: (publisher_host not in row[1].lower(), source_role_for_url(row[1]) != "full_text"))
    # A title search can expose many navigation/related links.  Checking a
    # small ordered set keeps archive repair bounded and respectful of hosts.
    return candidates[:2]


def search_bing_news_article_urls(title: str) -> list[tuple[str, str]]:
    """Last-resort public news index used after publisher and Korean portal search."""
    endpoint = f"https://www.bing.com/news/search?q={quote_plus(clean_text(title)[:240])}&format=rss"
    try:
        page = _paced_public_request(endpoint, accept="application/rss+xml,application/xml,text/xml")
        root = ET.fromstring(page)
    except Exception:
        return []
    rows: list[tuple[float, str, str]] = []
    seen: set[str] = set()
    for item in root.findall(".//item"):
        candidate_title = clean_text(item.findtext("title") or "")
        raw_url = clean_text(item.findtext("link") or "")
        parsed = urlparse(raw_url)
        if parsed.netloc.lower().endswith("bing.com"):
            redirected = parse_qs(parsed.query).get("url") or parse_qs(parsed.query).get("u")
            if redirected:
                raw_url = unquote(redirected[0])
        candidate_url = raw_url.split("#", 1)[0]
        score = title_similarity(title, candidate_title)
        if score < 0.5 or candidate_url in seen or not is_article_candidate_url(candidate_url):
            continue
        seen.add(candidate_url)
        rows.append((score, candidate_title, candidate_url))
    rows.sort(key=lambda row: row[0], reverse=True)
    return [("bing_news_search", candidate_url) for _score, _candidate_title, candidate_url in rows[:4]]


def title_matches_sentences(title: str, sentences: list[str]) -> bool:
    title_tokens = {token.lower() for token in TOKEN_PATTERN.findall(title) if len(token) >= 2 and token.lower() not in STOPWORDS}
    if not title_tokens:
        return False
    body_tokens = {token.lower() for token in TOKEN_PATTERN.findall(" ".join(sentences[:12])) if len(token) >= 2}
    required = 1 if len(title_tokens) <= 2 else 2
    matches = {
        title_token for title_token in title_tokens
        if any(title_token == body_token or title_token.startswith(body_token) or body_token.startswith(title_token) for body_token in body_tokens)
    }
    return len(matches) >= required


def title_similarity(title: str, candidate_title: str) -> float:
    """Conservative lexical similarity for same-day publisher-listing repair."""
    left = {token.lower() for token in TOKEN_PATTERN.findall(title) if len(token) >= 2 and token.lower() not in STOPWORDS}
    right = {token.lower() for token in TOKEN_PATTERN.findall(candidate_title) if len(token) >= 2 and token.lower() not in STOPWORDS}
    if not left or not right:
        return 0.0
    overlap = len(left & right)
    ratio = overlap / min(len(left), len(right))
    left_numbers = {re.sub(r"[^0-9.]", "", value) for value in NUMBER_PATTERN.findall(title)} - {""}
    right_numbers = {re.sub(r"[^0-9.]", "", value) for value in NUMBER_PATTERN.findall(candidate_title)} - {""}
    # A changed key number (for example CPI versus PPI) is not a safe repair.
    required_numbers = 2 if len(left_numbers) >= 2 else 1
    if left_numbers and len(left_numbers & right_numbers) < required_numbers:
        return 0.0
    return ratio if overlap >= 2 else 0.0


def publisher_daily_candidates(title: str, publisher: str, target_day: str) -> list[tuple[str, str, str]]:
    """Read allow-listed public publisher sections and rank same-day-like titles.

    A refusal (403), changed layout, or unavailable archive simply produces no
    candidate.  The caller must never attempt to bypass that restriction.
    """
    publisher_key = clean_text(publisher).lower()
    sections: tuple[tuple[str, str], ...] = ()
    for key, values in PUBLISHER_DAILY_SECTIONS.items():
        if key in publisher_key:
            sections = values
            break
    ranked: list[tuple[float, str, str, str]] = []
    seen: set[str] = set()
    for method, listing_url in sections:
        try:
            parser = PublisherListingParser()
            parser.feed(_paced_public_request(listing_url))
        except Exception:
            continue
        for candidate_title, raw_url in parser.links:
            candidate_url = urljoin(listing_url, raw_url).split("#", 1)[0]
            if candidate_url in seen or not is_article_candidate_url(candidate_url):
                continue
            score = title_similarity(title, candidate_title)
            if score < 0.5:
                continue
            seen.add(candidate_url)
            ranked.append((score, candidate_title, candidate_url, method))
    ranked.sort(key=lambda row: row[0], reverse=True)
    return [(candidate_title, candidate_url, method) for _score, candidate_title, candidate_url, method in ranked[:4]]


def bloomingbit_search_candidates(title: str) -> list[tuple[str, str, str]]:
    """Use the public API behind Bloomingbit's magnifier search UI."""
    encoded_keyword = base64.b64encode(quote(clean_text(title)[:240], safe="").encode("ascii")).decode("ascii")
    endpoint = (
        f"{BLOOMINGBIT_SEARCH_API}?limit=20&type=infinite"
        f"&keyword={quote_plus(encoded_keyword)}"
    )
    try:
        payload = json.loads(_paced_public_request(
            endpoint,
            accept="application/json",
            headers={"bloomingbit-language": "ko"},
        ))
    except (OSError, ValueError, TypeError, KeyError):
        return []
    data = payload.get("data") if isinstance(payload, dict) else None
    rows = data.get("content", []) if isinstance(data, dict) else []
    ranked: list[tuple[float, str, str, str]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        candidate_title = clean_text(str(row.get("title") or ""))
        sequence = str(row.get("seq") or "").strip()
        score = title_similarity(title, candidate_title)
        if not sequence.isdigit() or score < 0.5:
            continue
        ranked.append((score, candidate_title, f"https://bloomingbit.io/feed/news/{sequence}", "publisher_search_bloomingbit"))
    ranked.sort(key=lambda row: row[0], reverse=True)
    return [(candidate_title, candidate_url, method) for _score, candidate_title, candidate_url, method in ranked[:4]]


def publisher_search_candidates(title: str, publisher: str) -> list[tuple[str, str, str]]:
    """Search a publisher's own public search UI before scanning its sections."""
    publisher_key = clean_text(publisher).lower()
    if "블루밍비트" in publisher_key or "bloomingbit" in publisher_key:
        return bloomingbit_search_candidates(title)
    endpoint: tuple[str, str] | None = None
    for key, value in PUBLISHER_SEARCH_ENDPOINTS.items():
        if key.lower() in publisher_key:
            endpoint = value
            break
    if not endpoint:
        return []
    method, template = endpoint
    try:
        parser = PublisherListingParser()
        parser.feed(_paced_public_request(template.format(query=quote(clean_text(title)[:240], safe=""))))
    except Exception:
        return []
    ranked: list[tuple[float, str, str, str]] = []
    seen: set[str] = set()
    for candidate_title, raw_url in parser.links:
        candidate_url = urljoin(template, raw_url).split("#", 1)[0]
        if candidate_url in seen or not is_article_candidate_url(candidate_url):
            continue
        score = title_similarity(title, candidate_title)
        if score < 0.5:
            continue
        seen.add(candidate_url)
        ranked.append((score, candidate_title, candidate_url, method))
    ranked.sort(key=lambda row: row[0], reverse=True)
    return [(candidate_title, candidate_url, method) for _score, candidate_title, candidate_url, method in ranked[:4]]


def _discovered_candidate_ok(title: str, candidate_title: str, extraction: NQ.Extraction, target_day: str) -> tuple[bool, dict[str, object]]:
    """A searched page must be the SAME article: topic, key numbers, page title and date."""
    sentences = extraction.sentences
    identity = NQ.verify_identity(title, sentences, extraction.meta, expected_date=target_day, strict=True)
    status, _completeness = NQ.body_status(sentences, boundary_closed=extraction.boundary_closed, path=extraction.path, identity_ok=bool(identity["ok"]))
    if candidate_title and clean_text(candidate_title) != clean_text(title) and title_similarity(title, candidate_title) < 0.5:
        identity = {**identity, "ok": False, "reasons": [*identity["reasons"], "검색 결과 제목 유사도 부족"]}
    return bool(identity["ok"]) and status != "unavailable", identity


def discover_article_body(title: str, publisher: str, target_day: str = "") -> tuple[list[str], str, str, str] | None:
    """Use public publisher/portal search only when the feed URL did not yield a usable body.

    Returns (sentences, final_url, method, verified_title); the extraction with
    diagnostics is available from ``discover_article_extraction``.
    """
    found = discover_article_extraction(title, publisher, target_day)
    if not found:
        return None
    extraction, final_url, method, candidate_title, _identity = found
    return extraction.sentences, final_url, method, candidate_title


def discover_article_extraction(title: str, publisher: str, target_day: str = "") -> tuple[NQ.Extraction, str, str, str, dict[str, object]] | None:
    def attempts():
        for candidate_title, candidate_url, discovery_method in publisher_search_candidates(title, publisher):
            yield candidate_title, candidate_url, discovery_method
        for discovery_method, candidate_url in search_public_article_urls(title, publisher):
            yield "", candidate_url, discovery_method
        # Search indexes can miss a just-published or retitled article.  In
        # that case inspect the publisher's normal public section list.
        for candidate_title, candidate_url, discovery_method in publisher_daily_candidates(title, publisher, target_day):
            yield candidate_title, candidate_url, discovery_method
        for discovery_method, candidate_url in search_bing_news_article_urls(title):
            yield "", candidate_url, discovery_method

    for candidate_title, candidate_url, discovery_method in attempts():
        try:
            extraction, final_url = fetch_article(candidate_url, candidate_title or title)
        except Exception:
            continue
        ok, identity = _discovered_candidate_ok(title, candidate_title, extraction, target_day)
        if ok:
            return extraction, final_url, discovery_method, candidate_title or title, identity
    return None


def resolve_article_url(url: str) -> str:
    """Resolve a Google News relay slowly so concurrent enrichment does not trigger throttling."""
    if "news.google.com" not in urlparse(url).netloc.lower():
        return url
    global LAST_GOOGLE_NEWS_RESOLVE_AT
    with GOOGLE_NEWS_RESOLVE_LOCK:
        elapsed = time.monotonic() - LAST_GOOGLE_NEWS_RESOLVE_AT
        if elapsed < 1.5:
            time.sleep(1.5 - elapsed)
        resolved = url
        try:
            from googlenewsdecoder import gnewsdecoder
            decoded = gnewsdecoder(url, interval=0)
            if decoded.get("status") and decoded.get("decoded_url"):
                resolved = str(decoded["decoded_url"])
        finally:
            LAST_GOOGLE_NEWS_RESOLVE_AT = time.monotonic()
    return resolved


class AccessRestricted(Exception):
    """A paywall/login/CAPTCHA/refusal page.  It is recorded, never bypassed."""


class ArticleGone(Exception):
    """The publisher says the article no longer exists (deleted or moved)."""


class NotAnArticlePage(Exception):
    """A market-data/quote page, not a news article."""


ACCESS_RESTRICTION_PATTERN = re.compile(
    r"captcha|are you a robot|unusual traffic|access denied|subscribe to continue|subscription required|"
    r"로그인\s*후\s*(?:이용|열람)|유료\s*회원|구독자\s*전용|회원\s*전용\s*기사", re.I)
# Bot-check interstitials (Sucuri/Cloudflare JS challenges) are refusals too.
BOT_CHALLENGE_PATTERN = re.compile(r"sucuri_cloudproxy|Javascript is required\. Please enable javascript|cf-browser-verification|challenge-platform", re.I)
# Tiny "no such article" pages that only alert() and go back (ndsoft CMS).
GONE_PAGE_PATTERN = re.compile(r"존재하지\s*않는\s*(?:링크|기사|페이지)|삭제된\s*기사|기사가\s*존재하지\s*않|article (?:has been )?(?:removed|not found)", re.I)
NON_ARTICLE_URL = re.compile(
    r"^https?://(?:markets\.ft\.com/data/(?:etfs|funds|equities|indices|announce)/|(?:www\.)?cnbc\.com/quotes/|"
    r"(?:www\.)?morningstar\.com/(?:etfs|funds|stocks|cefs)/|(?:www\.)?reuters\.com/markets/quote/|"
    r"(?:[a-z]{2,3}\.)?investing\.com/(?:etfs|funds|equities|indices|currencies|commodities|rates-bonds|crypto)/)", re.I)

MAX_PAGE_BYTES = 3_000_000
PAGE_READ_SECONDS = 45
_page_metrics: dict[str, int] = {}
_page_metrics_lock = threading.Lock()
_enrichment_metrics: list[dict[str, object]] = []


def validate_public_url(url: str) -> None:
    """Reject non-web, credential-bearing and non-public destinations at each hop."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("공개 HTTP/HTTPS 주소만 허용함")
    if parsed.port not in {None, 80, 443}:
        raise ValueError("공개 웹 포트만 허용함")
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global or ipaddress.ip_address(row[4][0]).is_multicast for row in addresses):
        raise ValueError("사설·로컬·예약 IP로의 요청을 차단함")


class PublicRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _public_connection(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
    # Pin the connection to the addresses checked here, not a second DNS lookup.
    # TLS still uses the original hostname for SNI and certificate validation.
    infos = socket.getaddrinfo(address[0], address[1], type=socket.SOCK_STREAM)
    if not infos or any(not ipaddress.ip_address(row[4][0]).is_global or ipaddress.ip_address(row[4][0]).is_multicast for row in infos):
        raise ValueError("연결 대상이 사설·로컬·예약 IP임")
    last_error = None
    for family, kind, proto, _canon, sockaddr in infos:
        connection = socket.socket(family, kind, proto)
        try:
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                connection.settimeout(timeout)
            if source_address:
                connection.bind(source_address)
            connection.connect(sockaddr)
            return connection
        except OSError as error:
            connection.close()
            last_error = error
    raise last_error or OSError("공개 서버에 연결할 수 없음")


class PublicHTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _public_connection


class PublicHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _public_connection


class PublicHTTPHandler(HTTPHandler):
    def http_open(self, req):
        return self.do_open(PublicHTTPConnection, req)


class PublicHTTPSHandler(HTTPSHandler):
    def https_open(self, req):
        return self.do_open(PublicHTTPSConnection, req, context=self._context)


def urlopen(request, timeout=12, context=None):
    """All collector requests, including redirect/AMP/relay destinations, share policy."""
    url = request.full_url if isinstance(request, Request) else str(request)
    validate_public_url(url)
    opener = build_opener(PublicRedirectHandler(), PublicHTTPHandler(), PublicHTTPSHandler(context=context or _tls_context()))
    return opener.open(request, timeout=timeout)


def _page_metric(name: str) -> None:
    with _page_metrics_lock:
        _page_metrics[name] = _page_metrics.get(name, 0) + 1


def _read_page_prefix(response, limit: int) -> bytes:
    if not hasattr(response, "read1"):
        return response.read(limit + 1)
    deadline = time.monotonic() + PAGE_READ_SECONDS
    chunks, size = [], 0
    while size <= limit:
        assert_run_ownership()
        if time.monotonic() > deadline:
            raise TimeoutError("페이지 읽기 시간 상한 초과")
        chunk = response.read1(min(65_536, limit + 1 - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
    return b"".join(chunks)


def _tls_context() -> ssl.SSLContext:
    """Fully verifying context: the OS store plus Mozilla roots (certifi)."""
    context = ssl.create_default_context()
    if certifi is not None:
        try:
            context.load_verify_locations(cafile=certifi.where())
        except OSError:
            pass
    return context


def _decode_page(raw: bytes, headers: object) -> str:
    """Decode a bounded page; try declared charsets without silently corrupting text."""
    encoding = str(getattr(headers, "get", lambda *_: "")("Content-Encoding") or "").lower()
    if raw[:2] == b"\x1f\x8b" or "gzip" in encoding or "deflate" in encoding:
        windows = (16 + zlib.MAX_WBITS,) if raw[:2] == b"\x1f\x8b" or "gzip" in encoding else (zlib.MAX_WBITS, -zlib.MAX_WBITS)
        for window in windows:
            try:
                decoder = zlib.decompressobj(window)
                decoded = decoder.decompress(raw, MAX_PAGE_BYTES + 1)
            except zlib.error:
                if window == windows[-1]:
                    raise ValueError("페이지 압축을 해제할 수 없음")
                continue
            if len(decoded) > MAX_PAGE_BYTES or decoder.unconsumed_tail:
                _page_metric("decompressed_limit_exceeded")
                raise ValueError("페이지 압축 해제 크기 제한 초과")
            if not decoder.eof:
                raise ValueError("페이지 압축 데이터가 잘림")
            raw = decoded
            break
    if len(raw) > MAX_PAGE_BYTES:
        raise ValueError("페이지 크기 제한 초과")
    candidates = []
    if hasattr(headers, "get_content_charset"):
        candidates += [token.strip() for token in str(headers.get_content_charset() or "").split(",")]  # "utf-8,gbk"
    meta = re.search(rb"<meta[^>]{0,80}charset\s*=\s*[\"']?([A-Za-z0-9_-]+)", raw[:4096], re.I)
    if meta:
        candidates.append(meta.group(1).decode("ascii", "ignore"))
    candidates.append("utf-8")
    for name in candidates:
        try:
            codecs.lookup(name)
            return raw.decode(name, errors="strict")
        except (LookupError, TypeError, UnicodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def _download_page(url: str, accept: str, limit: int = 3_000_000) -> tuple[str, str, str]:
    """GET one public page → (text, final_url, content_type).

    Verify TLS against configured OS/Mozilla roots, with one slower timeout
    retry. Never add certificates advertised by an unauthenticated peer to
    the trust store. 401/402/403/429/451 and bot-check pages raise
    AccessRestricted; nothing is bypassed.
    """
    request_headers = {"User-Agent": USER_AGENT, "Accept": accept, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7"}
    last_error: Exception | None = None
    for timeout in (12, 30):
        try:
            assert_run_ownership()
            response_context = urlopen(Request(url, headers=request_headers), timeout=timeout, context=_tls_context())
            with response_context as response:
                raw = _read_page_prefix(response, limit)
                if len(raw) > limit:
                    _page_metric("oversized_responses")
                    encoding = str(response.headers.get("Content-Encoding") or "").lower()
                    if raw[:2] == b"\x1f\x8b" or encoding in {"gzip", "deflate"}:
                        raise ValueError("압축 페이지 크기 제한 초과")
                    _page_metric("bounded_prefix_reads")
                    return _decode_page(raw[:limit], response.headers), response.geturl(), response.headers.get("Content-Type", "") + "; x-news-prefix=1"
                return _decode_page(raw, response.headers), response.geturl(), response.headers.get("Content-Type", "")
        except Exception as error:
            code = getattr(error, "code", None)
            if code in {401, 402, 403, 429, 451}:
                raise AccessRestricted(f"접근 제한 HTTP {code}") from error
            if code in {301, 302, 303, 307, 308}:
                try:
                    body = error.read(4000).decode("utf-8", "ignore")  # type: ignore[attr-defined]
                except Exception:
                    body = ""
                if BOT_CHALLENGE_PATTERN.search(body):
                    raise AccessRestricted("접근 제한(자바스크립트 봇 확인 페이지)") from error
            if code in {404, 410}:
                raise ArticleGone(f"원문 삭제·이동(HTTP {code})") from error
            timed_out = isinstance(error, (TimeoutError, socket.timeout)) or "timed out" in str(error).lower()
            if not timed_out:
                raise
            last_error = error
    raise last_error if last_error else OSError("원문 요청 실패")


def fetch_article(url: str, title: str = "") -> tuple[NQ.Extraction, str]:
    """Download one public page and return (extraction, final_url).

    HTTP 401/403/429 and paywall/CAPTCHA markers raise AccessRestricted so the
    caller records the reason and schedules a normal retry; nothing is bypassed.
    """
    if "news.google.com" in urlparse(url).netloc.lower():
        try:
            url = resolve_article_url(url)
        except Exception:
            pass
    parsed = urlparse(url)
    if parsed.netloc.lower() == "blog.naver.com":
        match = re.fullmatch(r"/([^/]+)/(\d+)", parsed.path.rstrip("/"))
        if match:
            url = f"https://blog.naver.com/PostView.naver?blogId={quote_plus(match.group(1))}&logNo={match.group(2)}"
    if NON_ARTICLE_URL.search(url):
        raise NotAnArticlePage("기사 아님(시세·펀드 데이터 페이지)")
    page, final_url, content_type = _download_page(url, "text/html,application/xhtml+xml")
    extraction, final_url = read_article_page(page, title, final_url, content_type)
    # A successful public JavaScript shell may link its static AMP rendition.
    # Follow only that page's explicit same-host link; never use it after a
    # refusal, paywall notice or HTTP access error.
    amp = urljoin(final_url, str(extraction.meta.get("amphtml") or ""))
    if (len(extraction.sentences) < NQ.EXCERPT_MIN_SENTENCES
            and extraction.meta.get("amphtml") and amp != final_url
            and urlparse(amp).scheme in {"http", "https"}
            and urlparse(amp).hostname == urlparse(final_url).hostname
            and not ACCESS_RESTRICTION_PATTERN.search(page)):
        amp_page, amp_final, amp_type = _download_page(amp, "text/html,application/xhtml+xml")
        alternate, amp_final = read_article_page(amp_page, title, amp_final, amp_type)
        if len(alternate.sentences) > len(extraction.sentences):
            alternate.note("public_amp_rendition", "공개 페이지가 명시한 동일 매체 AMP 본문 사용")
            return alternate, amp_final
    return extraction, final_url


def read_article_page(page: str, title: str = "", final_url: str = "", content_type: str = "text/html") -> tuple[NQ.Extraction, str]:
    """Classify and extract one downloaded page (network-free; shared by tests)."""
    if "html" not in content_type.lower():
        return NQ.Extraction(path="non_html"), final_url
    if len(page) < 2000 and GONE_PAGE_PATTERN.search(page):
        raise ArticleGone("원문 삭제(존재하지 않는 기사 안내 페이지)")
    if len(page) < 20_000 and BOT_CHALLENGE_PATTERN.search(page):
        raise AccessRestricted("접근 제한(자바스크립트 봇 확인 페이지)")
    extraction = extract_article_page(page, title)
    weak_reading = bool(extraction.removed.get("weak_container_fallback"))
    if (len(extraction.sentences) < NQ.EXCERPT_MIN_SENTENCES or weak_reading) and ACCESS_RESTRICTION_PATTERN.search(page[:200_000]):
        # A paywall page's leftover notices ("중앙일보로 이동합니다") must not be
        # read as a body through the loose paragraph reading.
        raise AccessRestricted("유료벽·로그인·CAPTCHA 등 접근 제한 페이지")
    if extraction.path in NQ.PAGE_DATA_PATHS and ACCESS_RESTRICTION_PATTERN.search(page):
        # Text embedded in page data is never read from a page that shows a
        # paywall/login wall to readers.
        raise AccessRestricted("유료·회원 전용 표시가 있는 페이지(페이지 데이터 본문 사용 안 함)")
    if "x-news-prefix=1" in content_type:
        # Apply only after the original extraction path's access-control checks.
        extraction.path = "bounded_prefix"
        extraction.boundary_closed = False
        extraction.note("bounded_prefix", "페이지 크기 상한 내 앞부분만 읽음: 전체 본문 여부 미확인")
    return extraction, final_url


def fetch_article_sentences(url: str) -> tuple[list[str], str]:
    """Backward-compatible wrapper returning only cleaned body sentences."""
    extraction, final_url = fetch_article(url)
    return extraction.sentences, final_url


def _sentence_title_overlap(title: str, sentence: str) -> int:
    title_tokens = {token.lower() for token in TOKEN_PATTERN.findall(title) if len(token) >= 2 and token.lower() not in STOPWORDS}
    sentence_tokens = {token.lower() for token in TOKEN_PATTERN.findall(sentence) if len(token) >= 2}
    return len(title_tokens & sentence_tokens)


def clean_evidence_sentence(value: str) -> str:
    """Remove datelines/byline markers without rewriting the article's factual prose."""
    value = clean_text(value)
    value = re.sub(r"^\s*\[[^\]]{1,60}\]\s*(?:=|[-–—])?\s*", "", value)
    # "(서울=연합인포맥스) 이윤구 기자 = …", "(베이징=뉴스1) 김철수 기자 = …"
    value = re.sub(r"^\s*\([^()]{1,40}=[^()]{1,40}\)\s*(?:=|[-–—])?\s*", "", value)
    value = re.sub(r"^\s*[가-힣]{2,4}\s*(?:기자|특파원|객원기자|선임기자|인턴기자)\s*=\s*", "", value)
    value = re.sub(r"^\s*[가-힣]{2,10}\s*=\s*", "", value)
    return value.lstrip("=·-–— ").strip()


def extract_article_actors(sentences: list[str], title: str = "") -> list[str]:
    """Actors that the article itself names as subject or speaker; empty when unsupported.

    The previous version matched ``[A-Z]{2,10}`` with re.I (any English word) and
    the bare suffix ``부`` (so "2023년부터" became "2023년부").  Candidates now
    need a subject/speaker position after particle stripping plus an entity signal.
    """
    return [row["name"] for row in NQ.extract_actors([clean_evidence_sentence(row) for row in sentences], title)]


def highlight_keywords(text: str) -> list[dict[str, str]]:
    keywords: list[dict[str, str]] = []
    lowered = text.lower()
    for term in MAX_HIGHLIGHT_TERMS:
        if term.lower() in lowered:
            keywords.append({"term": term, "importance": "max", "wiki_query": term})
    for term in HIGH_HIGHLIGHT_TERMS:
        if term.lower() in lowered and not any(row["term"] == term for row in keywords):
            keywords.append({"term": term, "importance": "high", "wiki_query": term})
    return keywords


def sixw_summary_from_sentences(title: str, publisher: str, published_at: str, sentences: list[str], paragraph_of: list[int] | None = None) -> dict[str, object]:
    """Build an evidence-bound extractive summary from cleaned body sentences.

    * The lead is the first body sentence.  Only standalone headline/subtitle
      lines among the first three rows are skipped; a later sentence that
      resembles the title never causes earlier sentences to be discarded.
    * Sentence selection follows news_quality.select_summary_sentences (lead,
      new amounts/ratios, decisions/conditions, speakers, informative ending).
    * No synthetic "publisher said in an article" prefix is added.
    """
    rows: list[str] = []
    paragraphs_of_rows: list[int] = []
    for index, sentence in enumerate(sentences):
        cleaned = clean_evidence_sentence(sentence)
        if cleaned:
            rows.append(cleaned)
            paragraphs_of_rows.append(paragraph_of[index] if paragraph_of and index < len(paragraph_of) else index)
    if not rows:
        return {}
    start = 0
    while start < min(3, len(rows) - 1) and (NQ._title_like(rows[start], [title]) or not NQ.is_sentence_like(rows[start])):
        start += 1
    rows, paragraphs_of_rows = rows[start:], paragraphs_of_rows[start:]
    actors = NQ.extract_actors(rows, title)
    figures = NQ.extract_figures(rows, actors)
    indices = NQ.select_summary_sentences(rows, figures, actors, title)
    article_summary = NQ.group_paragraphs(indices, rows, paragraphs_of_rows)
    core = NQ.core_summary(rows, indices, figures)
    narrative = " ".join(rows[index] for index in indices)
    fields: dict[str, object] = {"highlight_keywords": highlight_keywords(narrative)}
    fields.update(structured_summary_fields(title, publisher, published_at, article_summary, core, body_sentences=rows))
    fields.update({
        "narrative_paragraphs": [narrative],
        "core_summary": core,
        "summary_basis": "공개 원문 본문",
        "summary_method": "extractive_v2",
        "summary_sentence_indices": indices,
        "article_body_status": "full_text",
        "publication_status": "detail",
        "article_body_sentence_count": len(rows),
        "skipped_leading_lines": start,
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


CAUSE_STRICT_PATTERN = re.compile(r"때문|이유는|이유로|배경(?:은|으로|에는|이다|입니다)|위해|목적|여파로|영향으로|으로\s*인해|로\s*인해|탓|덕분|덕에|감안해|고려해|에\s*따른|(?:부진|상승|하락|증가|감소)으로")
METHOD_STRICT_PATTERN = re.compile(r"통해|방식으로|활용해|절차를\s*거쳐|거쳐|형태로|구조로|계약을\s*체결|투입해|조달해|매각해|인수해|발행해|의결을|공시를|입찰|공모")
RESULT_STRICT_PATTERN = re.compile(r"그\s*결과|이에\s*따라|결과적으로|(?:늘었|줄었|증가했|감소했|상승했|하락했|개선됐|악화됐|확대됐|축소됐|도달했|기록했|마감했|그쳤|넘어섰|돌파했)")
LOCATION_PATTERN = re.compile(
    r"(?:미국|중국|일본|한국|유럽연합|유럽|영국|독일|프랑스|러시아|우크라이나|중동|뉴욕|워싱턴|"
    r"서울(?:특별시)?|부산(?:광역시)?|대구(?:광역시)?|인천(?:광역시)?|광주(?:광역시)?|"
    r"대전(?:광역시)?|울산(?:광역시)?|세종(?:특별자치시)?|경기(?:도)?|강원(?:특별자치도|도)?|"
    r"충북|충남|전북|전남|경북|경남|제주(?:특별자치도|도)?|수도권|지방)"
    r"(?=(?:에서|내|의|으로|로|발|현지|[\s,.;:]))"
)


def _quality_assessment(title: str, paragraphs: list[str], core: str, body_rows: list[str], figures: list[dict[str, object]]) -> dict[str, object]:
    """Score verification checks; filling 6W slots earns nothing by itself."""
    summary_text = " ".join(paragraphs)
    identity = NQ.verify_identity(title, body_rows)
    coverage = NQ.figure_coverage(figures, f"{summary_text} {core}")
    unsupported = NQ.unsupported_numbers(f"{summary_text} {core}", " ".join(body_rows))
    contaminated = [row for row in NQ.split_sentences(summary_text) if NQ.CODE_LINE.search(row) or NQ.STRONG_UI.search(row)]
    title_key = NQ.normalized(re.sub(r"^\s*\[[^\]]{1,40}\]\s*", "", title))[:16]
    title_glued = bool(title_key) and len(title_key) >= 8 and (title_key in NQ.normalized(core)[:40] or bool(paragraphs) and title_key in NQ.normalized(paragraphs[0])[:40])
    lead_preserved = bool(paragraphs) and bool(body_rows) and NQ.normalized(paragraphs[0]).startswith(NQ.normalized(body_rows[0])[:20])
    total = int(coverage["important_total"])
    ratio = 1.0 if not total else int(coverage["important_in_summary"]) / total
    score = 100
    deductions: list[str] = []
    if not identity["ok"]:
        score -= 40
        deductions.append("제목·본문 불일치")
    if contaminated:
        score -= 30
        deductions.append("본문 UI·코드 혼입")
    if title_glued:
        score -= 15
        deductions.append("요약이 제목을 반복")
    if unsupported:
        score -= min(30, 10 * len(unsupported))
        deductions.append(f"원문에서 찾지 못한 수치 {len(unsupported)}개")
    if ratio < 0.8:
        score -= 15
        deductions.append(f"핵심 수치 요약 반영 {round(ratio * 100)}%")
    if not lead_preserved:
        score -= 10
        deductions.append("요약 첫 문장이 본문 도입부가 아님")
    score = max(0, score)
    return {
        "score": score,
        "grade": "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D",
        "basis": "검증 항목 감점제(육하원칙 채움률은 점수에 반영하지 않음)",
        "deductions": deductions,
        "title_body_match": bool(identity["ok"]),
        "body_characters": len(" ".join(body_rows)),
        "summary_characters": len(summary_text),
        "figure_coverage_percent": round(ratio * 100),
        "unsupported_numbers": unsupported[:10],
        "contaminated_sentences": [row[:120] for row in contaminated[:3]],
        "title_glued": title_glued,
        "lead_preserved": lead_preserved,
    }


def structured_summary_fields(
    title: str,
    publisher: str,
    published_at: str,
    paragraphs: list[str],
    core: str,
    *,
    body_sentences: list[str] | None = None,
) -> dict[str, object]:
    """Create an evidence-bound 6W1H contract without filling absent facts.

    ``body_sentences`` (when available) is the full cleaned article body, so
    actors, dates, figures and uncertainty come from the whole article, not
    only from the sentences that made it into the summary.
    """
    paragraphs = [clean_evidence_sentence(row) for row in paragraphs if clean_evidence_sentence(row)][:7]
    core = clean_evidence_sentence(core)
    summary_rows = [clean_evidence_sentence(row) for paragraph in paragraphs for row in NQ.split_sentences(paragraph) if clean_evidence_sentence(row)]
    body_rows = [clean_evidence_sentence(row) for row in (body_sentences or summary_rows) if clean_evidence_sentence(row)]
    language = NQ.language_of(" ".join(body_rows))
    actors = NQ.extract_actors(body_rows, title)
    date_facts = NQ.extract_date_facts(body_rows, published_at)
    figures = NQ.extract_figures(body_rows, actors)
    what_row = next(
        (row for row in body_rows[:4] if NQ.STATUS_ACTION.search(row) or _sentence_title_overlap(title, row) >= 2),
        body_rows[0] if body_rows else core,
    )
    locations: list[tuple[str, str]] = []
    for row in body_rows:
        for match in LOCATION_PATTERN.finditer(row):
            if match.group(0) not in {name for name, _row in locations}:
                locations.append((match.group(0), row))
    causes = [row for row in body_rows if CAUSE_STRICT_PATTERN.search(row)][:3]
    methods = [row for row in body_rows if METHOD_STRICT_PATTERN.search(row) and row != what_row][:3]
    results = [row for row in body_rows if RESULT_STRICT_PATTERN.search(row) and row != what_row][:3]
    when_rows = []
    for row in date_facts:
        if row["resolved"]:
            when_rows.append(f"{row['text']} → {row['resolved']}")
        elif row["basis"] not in {"기간 표현"}:
            when_rows.append(f"{row['text']} (날짜 미확정: {row['basis']})")
        else:
            when_rows.append(str(row["text"]))
    if not when_rows and published_at:
        when_rows = [f"기사 발행일 {published_at} (본문에 사건 날짜 명시 없음)"]
    six_w = {
        "who": [row["name"] for row in actors],
        "when": when_rows[:8],
        "where": [name for name, _row in locations][:5],
        "what": [what_row[:500]] if what_row else [],
        "why": causes,
        "how": methods,
        "result": results,
    }
    evidence = {
        "who": [{"value": row["name"], "role": row["role"], "evidence": row["evidence"]} for row in actors],
        "when": [{"value": row["text"], "resolved": row["resolved"], "basis": row["basis"], "evidence": row["evidence"]} for row in date_facts[:8]],
        "where": [{"value": name, "evidence": row[:240]} for name, row in locations[:5]],
        "what": [{"value": what_row[:240], "evidence": what_row[:240]}] if what_row else [],
        "why": [{"value": row[:240], "evidence": row[:240]} for row in causes],
        "how": [{"value": row[:240], "evidence": row[:240]} for row in methods],
        "result": [{"value": row[:240], "evidence": row[:240]} for row in results],
    }
    covered = sum(bool(value) for value in six_w.values())
    missing = [key for key, value in six_w.items() if not value]
    key_figures = [{
        "value": row["value"],
        "meaning": str(row["context"])[:240],
        "basis": "기사 원문",
        "period": published_at,
        "unit": row["unit"],
        "kind": row["kind"],
        "label": row["label"],
        "direction": row["direction"],
        "qualifier": row["qualifier"],
        "subject": row["subject"],
        "negative": row["negative"],
    } for row in figures[:40]]
    status_rows = summary_rows or body_rows
    fact_status = [{"statement": row[:500], "status": NQ.classify_statement(row)} for row in status_rows[:14]]
    quality = _quality_assessment(title, paragraphs, core, body_rows, figures)
    return {
        "summary_title": re.sub(r"\s*[-|·:]\s*[^-|·:]{1,30}$", "", clean_text(title)).strip() or clean_text(title),
        "article_summary": paragraphs,
        "core_summary": core,
        "six_w_one_h": six_w,
        "six_w_one_h_evidence": evidence,
        "six_w_one_h_meta": {
            "covered": covered,
            "total": 7,
            "coverage_percent": round(covered / 7 * 100),
            "missing": missing,
            "missing_note": "빈 칸은 원문에서 근거를 찾지 못한 항목이며 추정해 채우지 않음",
            "evidence_bound": True,
            "source_publisher": publisher,
            "language": language,
        },
        "date_facts": date_facts,
        "summary_quality": quality,
        "figure_coverage": NQ.figure_coverage(figures, f"{' '.join(paragraphs)} {core}"),
        "key_figures": key_figures,
        "fact_status": fact_status,
        "uncertainties": NQ.uncertainty_rows(body_rows),
        "summary_language": language,
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


UNAVAILABLE_NOTE = "공개 원문 본문을 확인하지 못해 상세 요약을 보류했습니다."


def upgrade_existing_item(item: dict[str, object]) -> dict[str, object]:
    """Migrate archived cards to the single narrative format without network or GPT."""
    if item.get("discovery_method") and not is_article_candidate_url(str(item.get("article_source_url") or "")):
        item["article_body_status"] = "unavailable"
        item["article_body_error"] = "기사 URL 형식 불일치"
        item["next_body_retry_at"] = date.today().isoformat()
    # rebuild_index() calls this for every archived item on every run.  Prose
    # of items already on the current schema is NOT re-cleaned here: a change
    # to the cleaner would otherwise silently rewrite the whole archive.  Use
    # scripts/reprocess_news.py (dry-run first) for deliberate re-processing.
    needs_migration = int(item.get("summary_schema_version") or 0) < SUMMARY_SCHEMA_VERSION
    if needs_migration:
        strip_summary_provenance(item)
    if item.get("article_body_status") == "unavailable":
        # Never present contaminated portal/RSS text as an article summary when
        # the representative source could not be opened. Keep the card visible
        # for statistics and schedule a later retry instead of inventing prose.
        stored = [str(row).rstrip(". ") for row in item.get("article_summary") or []]
        if not needs_migration and stored == [UNAVAILABLE_NOTE.rstrip(". ")] and item.get("publication_status") == "statistics_only":
            return item  # already converted; keep the stored text stable
        title = clean_text(str(item.get("title") or "제목 미확인"))
        item.update({
            "summary": title,
            "summary_title": title,
            "core_summary": title,
            "article_summary": ["공개 원문 본문을 확인하지 못해 상세 요약을 보류했습니다."],
            "narrative_paragraphs": ["공개 원문 본문을 확인하지 못해 상세 요약을 보류했습니다."],
            "easy_explanation": "원문 링크가 확인되면 본문을 다시 수집해 상세 요약으로 전환합니다.",
            "six_w_one_h": {"who": [], "when": [str(item.get("date") or "")], "where": [], "what": [title], "why": [], "how": [], "result": []},
            "key_figures": [],
            "fact_status": [{"statement": "공개 원문 본문 미확인", "status": "미확인"}],
            "uncertainties": ["원문 본문 확인 전에는 세부 수치와 인과관계를 확정할 수 없습니다."],
            "news_charts": [],
            "metrics": [],
            "publication_status": "statistics_only",
            "summary_basis": "제목·공개요약(원문 미확인)",
            "summary_schema_version": SUMMARY_SCHEMA_VERSION,
            "recovery_status": "retry_scheduled",
            "recovery_search_links": recovery_search_links(title, str(item.get("publisher") or "")),
        })
        strip_summary_provenance(item)
        return item
    if item.get("article_body_status") == "fetched":
        item["article_body_status"] = "full_text"
    gate = item.get("quality_gate")
    if isinstance(gate, dict) and gate.get("passed") is False:
        # A body was read but failed verification (identity, contamination,
        # untraceable numbers).  Keep it for statistics; never promote it.
        item["publication_status"] = "statistics_only"
        return item
    if not item.get("article_body_status") and has_verified_legacy_summary(item):
        item["article_body_status"] = "verified_reconstruction"
        if not item.get("narrative_paragraphs") and item.get("article_summary"):
            item["narrative_paragraphs"] = list(item["article_summary"])
    if (
        item.get("article_body_status") in PUBLISHABLE_BODY_STATUSES
        and item.get("narrative_paragraphs") and item.get("core_summary")
        and all(key in item for key in STRUCTURED_KEYS)
        and int(item.get("summary_schema_version") or 0) >= SUMMARY_SCHEMA_VERSION
    ):
        item["publication_status"] = "detail"
        for obsolete in ("sections", "expert_analysis", "timeline", "fact_ledger", "coverage_status", "coverage_note", "causal_path"):
            item.pop(obsolete, None)
        return item
    if item.get("article_body_status") in PUBLISHABLE_BODY_STATUSES and (item.get("article_summary") or item.get("narrative_paragraphs")):
        paragraphs = [str(row) for row in (item.get("article_summary") or item.get("narrative_paragraphs") or []) if str(row).strip()]
        item.update(structured_summary_fields(str(item.get("title", "")), str(item.get("publisher", "원문")), str(item.get("date", "")), paragraphs, str(item.get("core_summary") or item.get("summary") or "")))
        item["summary_schema_version"] = SUMMARY_SCHEMA_VERSION
        item["publication_status"] = "detail"
        strip_summary_provenance(item)
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
    strip_summary_provenance(item)
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
    """Translate without an LLM or paid service.

    Prefer an optional locally installed Argos Translate model.  The existing
    keyless GoogleTranslator fallback is retained for machines that do not
    have the offline model yet; it is bounded, one request per text, and its
    result is explicitly marked as machine-translated.
    """
    if not texts:
        return None
    try:
        import argostranslate.translate as argos_translate
        languages = argos_translate.get_installed_languages()
        source = next((language for language in languages if language.code == "en"), None)
        target = next((language for language in languages if language.code == "ko"), None)
        if source and target:
            translator = source.get_translation(target)
            translated = [clean_text(translator.translate(text[:4500])) for text in texts]
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


def translate_summary_fields(fields: dict[str, object], published_at: str = "") -> dict[str, object]:
    """Translate a foreign-language summary and verify it before calling it translated.

    The original-language summary is always preserved in ``original_summary``.
    Missing segments, non-Korean output or changed numbers keep the original
    text and set translation_status to translation_unavailable /
    translation_unverified instead of "translated".
    """
    paragraphs = [str(row) for row in fields.get("article_summary") or fields.get("narrative_paragraphs") or []]
    texts = [str(fields.get("summary_title") or ""), *paragraphs, str(fields.get("core_summary") or "")]
    fields["original_summary"] = {"summary_title": texts[0], "article_summary": paragraphs, "core_summary": texts[-1], "language": NQ.language_of(" ".join(paragraphs))}
    try:
        translated = translate_to_korean(texts)
    except Exception:
        translated = None
    if not translated:
        fields["translation_status"] = "translation_unavailable"
        fields["translation_check"] = {"ok": False, "problems": ["번역기 응답 없음"]}
        return fields
    check = NQ.translation_check(texts, translated)
    fields["translation_check"] = check
    if not check["ok"]:
        fields["translation_status"] = "translation_unverified"
        return fields
    title, core = translated[0], translated[-1]
    korean_paragraphs = translated[1:-1]
    rebuilt = structured_summary_fields(title, "번역 원문", published_at, korean_paragraphs, core)
    fields.update(rebuilt)
    fields.update({"summary_title": title, "article_summary": korean_paragraphs, "narrative_paragraphs": korean_paragraphs, "core_summary": core, "translation_status": "translated", "summary_language": "ko"})
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


def importance_details(item: dict[str, object], active_macro_alert: set[str] | None = None) -> dict[str, object]:
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
    action_bonus = 8 if ACTION_PATTERN.search(title) else 0
    engagement = item.get("engagement") if isinstance(item.get("engagement"), dict) else {}
    actual_views = int(engagement.get("views") or 0)
    actual_reactions = int(engagement.get("reactions") or 0)
    popularity_rank = int(engagement.get("rank") or 0)
    engagement_bonus = min(24, int((actual_views + actual_reactions * 4) ** 0.25 * 2)) if actual_views or actual_reactions else max(0, 18 - popularity_rank) if popularity_rank else 0
    title_lower = title.lower()
    noise = 32 if any(keyword in title for keyword in NOISE_KEYWORDS) else 0
    if any(keyword in title_lower for keyword in MARKET_QUOTE_NOISE):
        noise = max(noise, 60)
    single_actor_crypto = bool(CRYPTO_SINGLE_ACTOR_PATTERN.search(title) and re.search(r"비트코인|이더리움|코인|가상자산", title))
    if single_actor_crypto:
        noise = max(noise, 12)
    non_market_event = any(keyword in title for keyword in NON_MARKET_EVENT_TERMS)
    relevant = (category in CORE_MARKET_CATEGORIES or any(keyword.lower() in title.lower() for keyword in INVESTMENT_RELEVANCE)) and not non_market_event
    body_status = str(item.get("article_body_status") or "")
    publication_status = str(item.get("publication_status") or "")
    verification_score = 12 if body_status in {"fetched", "full_text", "verified_reconstruction"} else 6 if body_status == "verified_excerpt" else -50 if body_status == "unavailable" or publication_status == "statistics_only" else 0
    eligible = relevant and noise == 0 and body_status != "unavailable" and publication_status != "statistics_only"
    summary_quality = item.get("summary_quality") if isinstance(item.get("summary_quality"), dict) else {}
    quality_score = int(summary_quality.get("score") or 0)
    independently_supported = sources >= 2 or related >= 2 or authority > 0 or engagement_bonus > 0 or rate_decision or (quality_score >= 80 and (impact > 0 or action_bonus > 0))
    major_news_eligible = eligible and independently_supported and (not single_actor_crypto or sources >= 3 or engagement_bonus > 0)
    item_signals = macro_signals(item_market_text(item))
    linked_macro_signals = item_signals & (active_macro_alert or set())
    macro_alert_bonus = 18 if macro_signals(title) and any(pair <= linked_macro_signals for pair in MACRO_ALERT_PAIRS) else 0
    featured = bool(engagement.get("featured") or engagement.get("editor_pick") or engagement.get("top_story"))
    editorial_bonus = 10 if featured else 0
    score = max(0, min(100, coverage + market + impact + authority + numeric + decision_bonus + action_bonus + engagement_bonus + verification_score + macro_alert_bonus + editorial_bonus - noise))
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
        "verification_score": verification_score,
        "verified_body": body_status in PUBLISHABLE_BODY_STATUSES,
        "decisive_action_score": action_bonus,
        "noise_penalty": max(noise, 60 if non_market_event else 0),
        "attention_basis": f"유사 보도 {related}건 · 확인 매체 {sources}곳",
        "engagement_score": engagement_bonus,
        "editorial_priority_score": editorial_bonus,
        "macro_alert_score": macro_alert_bonus,
        "macro_alert_signals": sorted(linked_macro_signals),
        "views_available": views_available,
        "rate_decision": rate_decision,
        "response_proxy": response_basis,
        "investment_relevant": relevant and noise == 0,
        "eligible_for_important": eligible,
        "independently_supported": independently_supported,
        "summary_quality_score": quality_score,
        "major_news_eligible": major_news_eligible,
        "single_actor_crypto": single_actor_crypto,
    }


def same_important_event(left: dict[str, object], right: dict[str, object]) -> bool:
    """Avoid filling the major-news row with several headlines about one event."""
    common_noise = STOPWORDS | {"종합", "속보", "기사", "오늘", "이번", "가능성", "전망"}
    left_tokens = {token.lower() for token in TOKEN_PATTERN.findall(str(left.get("title") or "")) if len(token) >= 2 and token.lower() not in common_noise}
    right_tokens = {token.lower() for token in TOKEN_PATTERN.findall(str(right.get("title") or "")) if len(token) >= 2 and token.lower() not in common_noise}
    if not left_tokens or not right_tokens:
        return False
    overlap = left_tokens & right_tokens
    return len(overlap) >= 3 and len(overlap) / min(len(left_tokens), len(right_tokens)) >= 0.42


def mark_important(items: list[dict[str, object]], limit: int = 8) -> list[dict[str, object]]:
    active_macro_alert = macro_market_alert([item for item in items if item.get("publication_status") != "statistics_only" and item.get("article_body_status") != "unavailable"])
    for item in items:
        item["category"] = str(item.get("category") or ((item.get("tags") or ["거시경제"])[0]))
        item["publisher"] = str(item.get("publisher") or (((item.get("sources") or [{}])[0]).get("publisher", "원문")))
        region_text = f"{item.get('title', '')} {item.get('core_summary', '')}"
        item["region"] = classify_topic_region(region_text, item.get("sources") or [])
        item["importance"] = importance_details(item, active_macro_alert)
        item["importance_score"] = item["importance"]["score"]
        item["important"] = False
    ranked = sorted(items, key=lambda row: (bool(row["importance"].get("rate_decision")), int(row.get("importance_score", 0)), str(row.get("date", ""))), reverse=True)
    category_counts: dict[str, int] = {}
    selected_rows: list[dict[str, object]] = []
    selected = 0
    for region in ("domestic", "us", "global"):
        candidate = next((
            row for row in ranked
            if row.get("region") == region
            and row["importance"].get("major_news_eligible")
            and (int(row.get("importance_score", 0)) >= 36 or row["importance"].get("rate_decision"))
            and not any(same_important_event(row, chosen) for chosen in selected_rows)
        ), None)
        if candidate and selected < limit:
            candidate["important"] = True
            selected_rows.append(candidate)
            category = str(candidate.get("category", "거시경제"))
            category_counts[category] = category_counts.get(category, 0) + 1
            selected += 1
    for item in ranked:
        if item.get("important"):
            continue
        if (int(item.get("importance_score", 0)) < 36 and not item["importance"].get("rate_decision")) or not item["importance"].get("major_news_eligible") or selected >= limit:
            continue
        if any(same_important_event(item, chosen) for chosen in selected_rows):
            continue
        category = str(item.get("category", "거시경제"))
        if category_counts.get(category, 0) >= 3:
            continue
        item["important"] = True
        selected_rows.append(item)
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
        publisher = PUBLISHER_ALIASES.get(publisher.lower(), publisher)
        try:
            published_at = parsedate_to_datetime(published).astimezone(timezone(timedelta(hours=9)))
            published_date = published_at.date().isoformat()
            published_time = published_at.isoformat(timespec="minutes")
        except (TypeError, ValueError):
            published_date = target.isoformat()
            published_time = published_date
        row = {"title": title, "url": link, "publisher": publisher or "뉴스 원문", "description": description, "published_at": published_date, "published_time": published_time, "region": classify_region(publisher, region)}
        if not is_non_editorial_notice(row):
            rows.append(row)
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
        row = {"title": title, "url": link, "publisher": publisher, "description": description, "published_at": published_date, "published_time": published_time, "region": region}
        if title and link and published_date == target.isoformat() and not is_non_editorial_notice(row):
            rows.append(row)
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
        "published_time": row.get("published_time", row["published_at"]),
        "summary": description[:500],
        "tags": [category, row["publisher"][:18]],
        "category": category,
        "publisher": row["publisher"][:40],
        "region": topic_region,
        "engagement": aggregate_engagement(related),
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
            if not is_probably_foreign(f"{title} {summary}"):
                continue
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


def _build_verified_fields(
    title: str,
    publisher: str,
    published_at: str,
    extraction: NQ.Extraction,
    final_url: str,
    identity: dict[str, object],
) -> dict[str, object]:
    """Summary + provenance + body-contract status for one verified extraction."""
    sentences = extraction.sentences
    fields = sixw_summary_from_sentences(title, publisher, published_at, sentences, extraction.paragraph_of_sentence)
    status, completeness = NQ.body_status(sentences, boundary_closed=extraction.boundary_closed, path=extraction.path, identity_ok=bool(identity.get("ok")))
    fields["article_body_status"] = status
    fields["body_completeness"] = completeness
    fields["summary_basis"] = {
        "full_text": "공개 원문 본문",
        "verified_excerpt": "공개 본문 일부 또는 짧은 기사(전체 본문 여부 미확인)" if completeness == "boundary_unconfirmed" else "공개 본문(짧은 기사)",
    }.get(status, "제목·RSS 공개요약")
    # Translation is decided by the language of the body text, never by region.
    if NQ.language_of(" ".join(sentences)) == "en":
        fields = translate_summary_fields(fields, published_at)
    else:
        fields["translation_status"] = "not_needed"
    quality = fields.get("summary_quality")
    if isinstance(quality, dict) and identity.get("ok") and not quality.get("title_body_match"):
        # The page-level identity check (headline, page title, date) passed; the
        # body-keyword-only check inside the score must not contradict it
        # (English headline over a Korean body, reworded headlines).
        quality["deductions"] = [row for row in quality.get("deductions") or [] if row != "제목·본문 불일치"]
        quality["score"] = min(100, int(quality.get("score") or 0) + 40)
        quality["grade"] = "A" if quality["score"] >= 85 else "B" if quality["score"] >= 70 else "C" if quality["score"] >= 55 else "D"
        quality["title_body_match"] = True
    canonical = str(extraction.meta.get("canonical") or extraction.meta.get("og:url") or "")
    if not canonical.startswith(("http://", "https://")):
        canonical = final_url
    source_role = source_role_for_url(final_url)
    fields.update({
        "article_source_url": final_url,
        "fetched_url": final_url,
        "body_source_publisher": str(extraction.meta.get("publisher") or urlparse(final_url).hostname or publisher),
        "body_published_at": str(extraction.meta.get("article:published_time") or extraction.meta.get("datePublished") or ""),
        "canonical_source_url": canonical,
        "primary_source_role": source_role,
        "identity_check": identity,
        "extraction_diagnostics": extraction.diagnostics(),
        "extraction_version": NQ.EXTRACTION_VERSION,
        "article_body_checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "summary_schema_version": SUMMARY_SCHEMA_VERSION,
        "next_body_retry_at": "",
        "recovery_status": "verified",
        "recovery_search_links": [],
    })
    if source_role == "portal_republication":
        fields["summary_basis"] = f"{fields['summary_basis']} · 포털 재전재본"
    elif source_role == "publisher_blog_republication":
        fields["summary_basis"] = f"{fields['summary_basis']} · 발행사 운영 블로그 게시본"
    fields["quality_gate"] = quality_gate(fields)
    if not fields["quality_gate"]["passed"]:
        fields["publication_status"] = "statistics_only"
    return fields


def quality_gate(fields: dict[str, object]) -> dict[str, object]:
    """Publication gate shared by collection, re-processing and index building."""
    failures: list[str] = []
    status = str(fields.get("article_body_status") or "")
    if status not in PUBLISHABLE_BODY_STATUSES:
        failures.append("본문 계약 미충족")
    identity = fields.get("identity_check") if isinstance(fields.get("identity_check"), dict) else {}
    if identity and not identity.get("ok"):
        failures.append("제목·본문 동일성 미확인: " + ", ".join(identity.get("reasons") or []))
    quality = fields.get("summary_quality") if isinstance(fields.get("summary_quality"), dict) else {}
    if quality.get("contaminated_sentences"):
        failures.append("요약에 UI·코드 문장 혼입")
    if quality.get("unsupported_numbers"):
        failures.append("원문에서 역추적되지 않은 수치")
    text = " ".join(str(row) for row in fields.get("article_summary") or [])
    if re.search(r"[�]|����", text):
        failures.append("인코딩 오류 문자")
    return {"passed": not failures, "failures": failures, "checked_at": datetime.now().astimezone().isoformat(timespec="seconds")}


def recovery_source_urls(item: dict[str, object]) -> list[str]:
    """Own feed addresses first; related reports cannot identify this story."""
    sources = [row for row in item.get("sources") or [] if isinstance(row, dict)]
    primary = sources[0] if sources else {}
    values = [primary.get(key) for key in ("resolved_url", "discovery_url", "url")]
    values.extend(item.get(key) for key in ("fetched_url", "article_source_url", "canonical_source_url"))
    return list(dict.fromkeys(str(value) for value in values if value
                             and str(value).startswith(("http://", "https://"))
                             and "news.google.com" not in (urlparse(str(value)).hostname or "").lower()
                             and is_article_candidate_url(str(value))))


def recovered_source_fields(item: dict[str, object], extraction: NQ.Extraction, final_url: str,
                            *, allow_date_correction: bool = False) -> tuple[dict[str, object] | None, str]:
    """Keyless source repair shared by scheduled collection and manual review.

    Dates can change only with the same full headline and publisher metadata.
    All other identity, body and numeric-quality checks still have to pass.
    """
    title = str(item.get("title") or "")
    expected_date = str(item.get("date") or "")
    published = str(extraction.meta.get("article:published_time") or extraction.meta.get("datePublished") or "")
    page_title = str(extraction.meta.get("og:title") or extraction.meta.get("headline") or "")
    key, page_key = NQ.normalized(title), NQ.normalized(page_title)
    exact = len(key) >= 12 and (key == page_key or key in page_key and len(page_key) - len(key) <= 24)
    identity = NQ.verify_identity(title, extraction.sentences, extraction.meta, expected_date=expected_date, strict=True)
    correction = None
    if allow_date_correction and identity.get("date_consistent") is False and exact and published:
        try:
            parsed = datetime.fromisoformat(published.replace("Z", "+00:00"))
        except ValueError:
            return None, "원문 발행일을 해석할 수 없음"
        new_date = parsed.date().isoformat()
        if new_date > datetime.now().astimezone().date().isoformat():
            return None, "원문 발행일이 현재보다 미래임"
        identity = NQ.verify_identity(title, extraction.sentences, extraction.meta, expected_date=new_date, strict=True)
        correction = {"previous_date": expected_date, "verified_date": new_date, "source_url": final_url,
                      "reason": "동일 제목의 원문 발행 메타데이터로 날짜 정정"}
        expected_date = new_date
    if not identity.get("ok"):
        return None, "제목·본문 검증 실패: " + ", ".join(str(x) for x in identity.get("reasons") or [])
    status, _ = NQ.body_status(extraction.sentences, boundary_closed=extraction.boundary_closed,
                              path=extraction.path, identity_ok=True)
    if status == "unavailable":
        return None, "복구 원문 본문 분량 부족"
    fields = _build_verified_fields(title, str(item.get("publisher") or "원문"), expected_date,
                                    extraction, final_url, identity)
    if not is_publishable_detail(fields):
        return None, "복구 요약 품질 미달: " + ", ".join(fields.get("quality_gate", {}).get("failures") or [])
    if correction:
        fields.update({"date": expected_date, "published_time": published,
                       "feed_date": str(item.get("feed_date") or item.get("date") or ""), "date_correction": correction})
    sources = [row for row in item.get("sources") or [] if isinstance(row, dict)]
    primary = dict(sources[0]) if sources else {}
    previous = {name: item.get(name) for name in ("article_source_url", "canonical_source_url", "fetched_url")}
    previous["primary_source_url"] = primary.get("url")
    fields["source_corrections"] = [*(item.get("source_corrections") or []), {
        "previous": previous, "verified_url": final_url,
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds")}]
    if primary.get("url") and primary["url"] != final_url:
        primary.setdefault("discovery_url", primary["url"])
    primary.update({"url": final_url, "resolved_url": final_url, "title": title,
                    "published_at": expected_date, "published_time": published or expected_date})
    if extraction.meta.get("publisher"):
        primary["publisher"] = extraction.meta["publisher"]
    fields["sources"] = [primary, *sources[1:]]
    fields["discovery_method"] = "verified_source_recovery"
    return fields, ""


def _article_enrichment(item: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    sources = [row for row in item.get("sources") or [] if isinstance(row, dict)]
    primary = sources[0] if sources else {}
    # Bound requests as before, but never let a related report outrank the
    # original feed page. A stored discovery can have pointed at another story.
    candidates = [(dict(primary, url=url, resolved_url=url), True) for url in recovery_source_urls(item)]
    if primary and "news.google.com" in str(primary.get("resolved_url") or primary.get("url") or ""):
        candidates.append((dict(primary), True))
    related = sorted(sources[1:], key=lambda source: ("news.google.com" in str(source.get("url", "")), -representative_score(source)[0]))
    candidates.extend((dict(source), False) for source in related)
    title = str(item.get("title", ""))
    last_error = ""
    failure_kind = ""
    for source, own_source in candidates[:3]:
        original_url = str(source.get("url", ""))
        url = str(source.get("resolved_url") or original_url)
        if not url or not is_article_candidate_url(url):
            last_error, failure_kind = "기사 URL 형식 불일치", "url_invalid"
            continue
        if "news.google.com" in urlparse(url).netloc.lower() and int(item.get("article_body_attempts") or 0) >= 2:
            last_error, failure_kind = "Google 뉴스 중계 주소 재해석 생략 · 공개 검색으로 원문 재확인", "relay_unresolved"
            continue
        if "news.google.com" in urlparse(url).netloc.lower():
            try:
                resolved_url = resolve_article_url(url)
                if resolved_url != url:
                    source["discovery_url"] = original_url
                    source["resolved_url"] = resolved_url
                    url = resolved_url
                else:
                    last_error, failure_kind = "Google 뉴스 중계 주소에서 출판사 원문 주소를 확인하지 못함", "relay_unresolved"
                    continue
            except Exception as error:
                last_error, failure_kind = f"Google 뉴스 원문 주소 확인 실패: {str(error)[:120]}", "relay_unresolved"
                continue
        try:
            extraction, final_url = fetch_article(url, title)
        except AccessRestricted as error:
            last_error, failure_kind = str(error), "access_restricted"
            continue
        except NotAnArticlePage as error:
            last_error, failure_kind = str(error), "not_an_article"
            continue
        except ArticleGone as error:
            last_error, failure_kind = str(error), "article_gone"
            continue
        except Exception as error:
            last_error, failure_kind = str(error)[:160], "fetch_error"
            continue
        sentences = extraction.sentences
        if own_source:
            # Automatic date repair is deliberately narrower than an explicit
            # manual repair: a feed-owned host and at most a 31-day drift.
            published = str(extraction.meta.get("article:published_time") or extraction.meta.get("datePublished") or "")
            primary_hosts = {urlparse(str(primary.get(key) or "")).hostname for key in ("resolved_url", "discovery_url", "url")}
            try:
                small_date_drift = abs((date.fromisoformat(published[:10]) - date.fromisoformat(str(item.get("date") or "")[:10])).days) <= 31
            except ValueError:
                small_date_drift = False
            fields, error = recovered_source_fields(item, extraction, final_url,
                allow_date_correction=small_date_drift and urlparse(final_url).hostname in primary_hosts)
            if fields:
                fields["statistics_only_source_count"] = max(0, len(sources) - 1)
                fields["article_body_attempts"] = int(item.get("article_body_attempts") or 0) + 1
                return item, fields
            last_error = error
            failure_kind = "body_too_short" if "분량 부족" in error else "quality_gate" if "품질 미달" in error else "title_mismatch"
            continue
        identity = NQ.verify_identity(title, sentences, extraction.meta, expected_date=str(source.get("published_at") or item.get("date") or ""))
        status, _completeness = NQ.body_status(sentences, boundary_closed=extraction.boundary_closed, path=extraction.path, identity_ok=bool(identity["ok"]))
        if not identity["ok"]:
            last_error, failure_kind = "기사 제목과 본문 불일치: " + ", ".join(identity["reasons"]), "title_mismatch"
            continue
        if status == "unavailable":
            last_error, failure_kind = f"공개 본문 분량 부족({len(sentences)}문장·{len(' '.join(sentences))}자)", "body_too_short"
            continue
        fields = _build_verified_fields(
            title, str(source.get("publisher") or item.get("publisher") or "원문"),
            str(source.get("published_at") or item.get("date") or ""), extraction, final_url, identity,
        )
        fields["title"] = str(source.get("title_ko") or source.get("title") or item.get("title") or "")[:78]
        fields["publisher"] = str(source.get("publisher") or item.get("publisher") or "원문")[:40]
        fields["statistics_only_source_count"] = max(0, len(sources) - 1)
        fields["article_body_attempts"] = int(item.get("article_body_attempts") or 0) + 1
        return item, fields
    discovered = discover_article_extraction(title, str(item.get("publisher", "")), str(item.get("date", "")))
    if discovered:
        extraction, final_url, discovery_method, discovered_title, identity = discovered
        fields = _build_verified_fields(discovered_title, str(item.get("publisher") or "원문"), str(item.get("date") or ""), extraction, final_url, identity)
        fields.update({
            "discovery_method": discovery_method,
            "statistics_only_source_count": max(0, len(sources) - 1),
            "article_body_attempts": int(item.get("article_body_attempts") or 0) + 1,
        })
        if clean_text(discovered_title) != clean_text(title):
            # Preserve the feed label for auditability; the verified publisher
            # title is shown with a 유사기사 badge, never as an exact match.
            fields["feed_title"] = title
            fields["title"] = discovered_title[:160]
            fields["title_match_status"] = "similar_article_verified"
        return item, fields
    if not failure_kind:
        failure_kind = "no_source"
    return item, {
        "article_body_status": "unavailable",
        "publication_status": "statistics_only",
        "article_body_error": last_error or "공개 원문 본문을 확보하지 못함",
        "article_body_failure_kind": failure_kind,
        "article_body_checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "summary_basis": "제목·RSS 공개요약",
        "article_body_attempts": int(item.get("article_body_attempts") or 0) + 1,
        "summary_schema_version": SUMMARY_SCHEMA_VERSION,
        "next_body_retry_at": next_body_retry_at(item, failure_kind=failure_kind),
        "recovery_status": "statistics_only_" + failure_kind if failure_kind in {"not_an_article", "article_gone"} else "retry_scheduled",
        "recovery_search_links": recovery_search_links(title, str(item.get("publisher", ""))),
    }


def next_body_retry_at(item: dict[str, object], now: datetime | None = None, *, failure_kind: str = "") -> str:
    """Retry fresh failures quickly, then back off so old archives stay bounded."""
    current = now or datetime.now().astimezone()
    if failure_kind in {"not_an_article", "article_gone"}:
        return ""
    if failure_kind == "access_restricted":
        return (current + timedelta(days=7)).isoformat(timespec="seconds")
    raw_day = str(item.get("date") or item.get("published_time") or "")[:10]
    try:
        article_day = date.fromisoformat(raw_day)
    except ValueError:
        article_day = current.date()
    attempts = int(item.get("article_body_attempts") or 0) + 1
    age_days = (current.date() - article_day).days
    if 0 <= age_days <= RECENT_ARTICLE_DAYS and attempts <= 4:
        return (current + timedelta(hours=RECENT_ARTICLE_RETRY_HOURS)).isoformat(timespec="seconds")
    if attempts <= 7:
        return (current + timedelta(days=1)).isoformat(timespec="seconds")
    return (current + timedelta(days=7)).isoformat(timespec="seconds")


def article_retry_due(item: dict[str, object], now: datetime | None = None) -> bool:
    if item.get("article_body_failure_kind") in {"not_an_article", "article_gone"} or NON_ARTICLE_TITLE_PATTERN.search(str(item.get("title") or "")):
        return False
    if item.get("manual_verified") and item.get("editorial_verification") and is_publishable_detail(item):
        return False  # editorial reconstruction is not a failed machine extraction
    gate_failed = isinstance(item.get("quality_gate"), dict) and item["quality_gate"].get("passed") is False
    if (item.get("article_body_status") in PUBLISHABLE_BODY_STATUSES
            and int(item.get("summary_schema_version") or 0) >= SUMMARY_SCHEMA_VERSION
            and not gate_failed):
        return False
    restricted = item.get("article_body_failure_kind") == "access_restricted"
    if int(item.get("summary_schema_version") or 0) < SUMMARY_SCHEMA_VERSION and not restricted:
        return True
    retry_at = str(item.get("next_body_retry_at") or "")
    if not retry_at:
        return gate_failed
    current = now or datetime.now().astimezone()
    raw_day = str(item.get("date") or item.get("published_time") or "")[:10]
    try:
        article_day = date.fromisoformat(raw_day)
    except ValueError:
        article_day = current.date()
    age_days = (current.date() - article_day).days
    attempts = int(item.get("article_body_attempts") or 0)
    checked_at = str(item.get("article_body_checked_at") or "")
    if not restricted and 0 <= age_days <= RECENT_ARTICLE_DAYS and attempts <= 4 and checked_at:
        try:
            checked = datetime.fromisoformat(checked_at)
            if checked.tzinfo is None:
                checked = checked.replace(tzinfo=current.tzinfo)
            # Older payloads stored a seven-day cooldown. Override it for a
            # fresh article so a newly indexed publisher page is found soon.
            if checked + timedelta(hours=RECENT_ARTICLE_RETRY_HOURS) <= current:
                return True
        except ValueError:
            pass
    try:
        scheduled = datetime.fromisoformat(retry_at)
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=current.tzinfo)
        return scheduled <= current
    except ValueError:
        return retry_at[:10] <= current.date().isoformat()


def apply_enrichment(item: dict[str, object], fields: dict[str, object]) -> str:
    """Merge one enrichment result without letting a failure erase a good summary.

    Returns "updated" or "kept_existing".  A previously publishable item keeps
    its content when the new attempt failed or did not pass the quality gate;
    the attempt is recorded in ``last_refresh`` for diagnosis and retry.
    """
    was_publishable = is_publishable_detail(item)
    new_publishable = is_publishable_detail(fields)
    editorial = was_publishable and item.get("manual_verified") and item.get("editorial_verification")
    if was_publishable and (not new_publishable or editorial):
        gate = fields.get("quality_gate") if isinstance(fields.get("quality_gate"), dict) else {}
        item["last_refresh"] = {
            "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "result": "kept_existing",
            "error": "편집 검수 요약은 자동 재수집으로 교체하지 않음" if editorial else fields.get("article_body_error") or "; ".join(gate.get("failures") or []) or "새 처리 결과가 발행 기준 미달",
            "failure_kind": fields.get("article_body_failure_kind") or ("quality_gate" if gate else ""),
        }
        return "kept_existing"
    item.update(fields)
    item["detail_visible"] = is_publishable_detail(item)
    if item["detail_visible"]:
        item.pop("article_body_error", None)
        item.pop("article_body_failure_kind", None)
    item.pop("last_refresh", None)
    return "updated"


def enrich_article_bodies(items: list[dict[str, object]], limit: int | None = None, workers: int = 6, force_retry: bool = False) -> None:
    """Fetch representative public bodies concurrently, then replace feed-only summaries."""
    pending = [item for item in items if force_retry or article_retry_due(item)]
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
            _enrichment_metrics.append({"id": item.get("id"), "publisher": item.get("publisher"),
                                        "success": is_publishable_detail(fields),
                                        "failure_kind": fields.get("article_body_failure_kind"),
                                        "date_corrected": bool(fields.get("date_correction"))})
            if apply_enrichment(item, fields) == "kept_existing":
                continue
            if fields.get("article_body_status") in PUBLISHABLE_BODY_STATUSES and fields.get("publication_status") != "statistics_only":
                if fields.get("article_source_url"):
                    for source in item.get("sources") or []:
                        if source.get("url") and "news.google.com" in str(source.get("url")):
                            source["discovery_url"] = source["url"]
                            source["url"] = fields["article_source_url"]
                        source["canonical_url"] = fields.get("canonical_source_url", fields.get("article_source_url"))
                item["summary"] = str(fields.get("core_summary", item.get("summary", "")))[:900]
                item["easy_explanation"] = str(fields.get("narrative_paragraphs", [item.get("summary", "")])[0])
                prepared = [{"title": str(item.get("title", "")), "description": str(item.get("easy_explanation", "")), "publisher": str(item.get("publisher", "원문")), "published_at": str(item.get("date", "")), "published_time": str(item.get("date", ""))}]
                item["news_charts"] = numeric_charts(extract_number_facts(prepared))
            strip_summary_provenance(item)


def enrich_archived_bodies(limit: int, force_retry: bool = False) -> int:
    """Gradually migrate past archives so each scheduled run makes bounded progress."""
    if limit <= 0:
        return 0
    targets: list[tuple[Path, dict[str, object], dict[str, object]]] = []
    payloads: dict[Path, dict[str, object]] = {}
    for path in sorted(NEWS_DIR.glob("20??-??-??.json"), reverse=True):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payloads[path] = payload
        for item in payload.get("items", []):
            stale_discovery = bool(item.get("discovery_method")) and not is_article_candidate_url(str(item.get("article_source_url") or ""))
            should_retry = (item.get("article_body_status") == "unavailable" or stale_discovery) if force_retry else article_retry_due(item)
            if should_retry:
                targets.append((path, payload, item))
                if len(targets) >= limit:
                    break
        if len(targets) >= limit:
            break
    if not targets:
        return 0
    enrich_article_bodies([item for _path, _payload, item in targets], workers=6, force_retry=force_retry)
    touched = {path for path, _payload, _item in targets}
    for path in touched:
        atomic_write_json(path, payloads[path])
    return len(targets)


def atomic_write_json(path: Path, payload: object, *, only_if_changed: bool = False) -> bool:
    """Write JSON through a temp file + os.replace so readers never see half a file."""
    assert_run_ownership()
    if path.parent == NEWS_DIR and re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", path.name):
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ValueError("뉴스 날짜 파일의 items 배열이 잘못됨")
        ids = []
        for item in payload["items"]:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
                raise ValueError("뉴스 기사의 ID가 잘못됨")
            ids.append(item["id"])
            if "detail_visible" in item and item["detail_visible"] != is_publishable_detail(item):
                raise ValueError("뉴스 상세 노출 상태가 검증 결과와 다름")
        if len(set(ids)) != len(ids):
            raise ValueError("같은 날짜 파일 안의 기사 ID 중복")
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if only_if_changed and path.exists():
        try:
            if path.read_text(encoding="utf-8") == text:
                return False
        except OSError:
            pass
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8")
    for attempt in range(6):
        try:
            assert_run_ownership()
            os.replace(temporary, path)
            return True
        except PermissionError:
            # Windows refuses replace while another process holds the file open.
            if attempt == 5:
                temporary.unlink(missing_ok=True)
                raise
            time.sleep(0.25 * (attempt + 1))
    return True


def _title_key(item: dict[str, object]) -> str:
    return NQ.normalized(re.sub(r"^\s*\[[^\]]{1,40}\]\s*", "", str(item.get("feed_title") or item.get("title") or "")))


def normalize_article_url(url: str) -> str:
    parsed = urlparse(url)
    tracking = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}
    if (parsed.hostname or "").endswith(".yna.co.kr"):
        tracking.add("input")
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key.lower() not in tracking]
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.params, urlencode(query), ""))


def _source_urls(item: dict[str, object]) -> set[str]:
    """The article's OWN addresses: its page and its primary feed row.

    ``sources[1:]`` are related reports by other publishers (the feed
    cluster); two different articles can share them, so they never identify
    an article (2026-11-28: an MBC report was merged into an MBN one).
    """
    urls = {str(item.get(key) or "") for key in ("article_source_url", "canonical_source_url", "fetched_url")}
    sources = [source for source in item.get("sources") or [] if isinstance(source, dict)]
    if sources:
        urls.update(str(sources[0].get(key) or "") for key in ("url", "resolved_url", "canonical_url"))
    return {normalize_article_url(url) for url in urls
            if url.startswith(("http://", "https://")) and is_article_candidate_url(url)}


def merge_day_items(existing: list[dict[str, object]], fresh: list[dict[str, object]]) -> list[dict[str, object]]:
    """Merge a new collection into the stored day without losing verified work.

    * Same article (id, title or any source URL) keeps the stored id, so ids
      stay stable across runs.
    * A stored publishable summary is never replaced by a failed/unpublishable
      fresh attempt.
    * Previously stored articles that the latest feed no longer returns are kept.
    """
    by_id = {str(item.get("id")): item for item in existing}
    by_title = {_title_key(item): item for item in existing if _title_key(item)}
    by_url: dict[str, dict[str, object]] = {}
    for item in existing:
        for url in _source_urls(item):
            by_url.setdefault(url, item)
    used: set[int] = set()
    merged: list[dict[str, object]] = []
    for item in fresh:
        old = by_id.get(str(item.get("id"))) or by_title.get(_title_key(item)) or next((by_url[url] for url in _source_urls(item) if url in by_url), None)
        if old is not None and id(old) not in used:
            used.add(id(old))
            item["id"] = old.get("id", item.get("id"))
            editorial = old.get("manual_verified") and old.get("editorial_verification")
            if is_publishable_detail(old) and (not is_publishable_detail(item) or editorial):
                kept = dict(old)
                kept["last_refresh"] = {
                    "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "result": "kept_existing",
                    "error": "편집 검수 요약은 자동 재수집으로 교체하지 않음" if editorial else item.get("article_body_error") or "새 수집본이 발행 기준 미달",
                    "failure_kind": item.get("article_body_failure_kind") or "",
                }
                for key in ("related_reports", "source_count", "engagement"):
                    if item.get(key):
                        kept[key] = item[key]
                merged.append(kept)
                continue
        merged.append(item)
    merged.extend(item for item in existing if id(item) not in used)
    seen_ids: set[str] = set()
    unique: list[dict[str, object]] = []
    for item in merged:
        key = str(item.get("id"))
        if key in seen_ids:
            continue
        seen_ids.add(key)
        unique.append(item)
    return unique


def collect_day(target: date, limit: int) -> list[dict[str, object]]:
    unique: dict[str, dict[str, str]] = {}
    for query in FEED_QUERIES:
        try:
            for row in fetch_feed(query, target):
                if is_non_editorial_notice(row):
                    continue
                key = SPACE_PATTERN.sub("", row["title"].lower())
                unique.setdefault(key, row)
        except Exception as error:
            print(f"{target} 뉴스 피드 일부 실패: {error}")
        time.sleep(0.2)
    for query, language, country, edition, region in GLOBAL_FEEDS:
        try:
            for row in fetch_feed(query, target, language, country, edition, region):
                if is_non_editorial_notice(row):
                    continue
                key = SPACE_PATTERN.sub("", row["title"].lower())
                unique.setdefault(key, row)
        except Exception as error:
            print(f"{target} 해외 뉴스 피드 일부 실패: {error}")
        time.sleep(0.2)
    for url, publisher, region in DIRECT_RSS_FEEDS:
        try:
            for row in fetch_direct_feed(url, publisher, region, target):
                if is_non_editorial_notice(row):
                    continue
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
    candidates = [item for item in candidates if is_news_article_candidate(item)]
    candidates = [item for item in candidates if item.get("category") != "거시경제" or any(keyword.lower() in f"{item.get('title', '')} {item.get('summary', '')}".lower() for keyword in INVESTMENT_RELEVANCE)]
    quotas = {"domestic": max(1, round(limit * 0.55)), "us": max(1, round(limit * 0.25))}
    quotas["global"] = max(1, limit - quotas["domestic"] - quotas["us"])
    items = []
    for region in ("domestic", "us", "global"):
        items.extend([item for item in candidates if item.get("region") == region][:quotas[region]])
    if len(items) < limit:
        selected_ids = {str(item.get("id")) for item in items}
        items.extend(item for item in candidates if str(item.get("id")) not in selected_ids and len(items) < limit)
    items, already_stored = drop_stored_in_neighbour_days(target, items)
    if already_stored:
        print(f"{target}: 인접 날짜 파일에 이미 저장된 기사 {already_stored}건은 다시 저장하지 않음")
    items = reuse_verified_items(target, items)
    translate_foreign_sources([item for item in items if not item.get("extraction_version")])
    enrich_article_bodies(items)
    enrich_video_news(items)
    mark_important(items)
    return sorted(items, key=lambda row: int(row.get("importance_score", 0)), reverse=True)


def _load_day(target: date) -> list[dict[str, object]]:
    path = NEWS_DIR / f"{target.isoformat()}.json"
    if not path.exists():
        return []
    try:
        return [row for row in json.loads(path.read_text(encoding="utf-8")).get("items", []) if isinstance(row, dict)]
    except (OSError, ValueError):
        return []


def _same_article(left: dict[str, object], right: dict[str, object]) -> bool:
    if str(left.get("id")) == str(right.get("id")):
        return True
    if _title_key(left) and _title_key(left) == _title_key(right):
        return True
    return bool(_source_urls(left) & _source_urls(right))


def drop_stored_in_neighbour_days(target: date, items: list[dict[str, object]]) -> tuple[list[dict[str, object]], int]:
    """An article is stored once: in the first day file that saved it.

    Day files follow the feed's collection window, and a feed's item date
    (Google's pubDate of the cluster representative) can change between
    runs, so the same article is returned for two adjacent windows.  It is
    kept where it already is (same id or same own URL) instead of being
    written again.  A recurring headline on another day has a different URL
    and is not affected.
    """
    stored = [row for day in (target - timedelta(days=1), target + timedelta(days=1)) for row in _load_day(day)]
    if not stored:
        return items, 0
    ids = {str(row.get("id")) for row in stored}
    urls = {url for row in stored for url in _source_urls(row)}
    kept = [item for item in items if str(item.get("id")) not in ids and not (_source_urls(item) & urls)]
    return kept, len(items) - len(kept)


def reuse_verified_items(target: date, items: list[dict[str, object]]) -> list[dict[str, object]]:
    """Skip re-fetching articles already verified by the current extractor."""
    existing = _load_day(target)
    if not existing:
        return items
    by_id = {str(row.get("id")): row for row in existing}
    by_title = {_title_key(row): row for row in existing if _title_key(row)}
    rows: list[dict[str, object]] = []
    for item in items:
        old = by_id.get(str(item.get("id"))) or by_title.get(_title_key(item))
        if old and is_publishable_detail(old) and (int(old.get("extraction_version") or 0) >= NQ.EXTRACTION_VERSION
                                                   or old.get("manual_verified") and old.get("editorial_verification")):
            reused = dict(old)
            for key in ("related_reports", "source_count", "engagement"):
                if item.get(key):
                    reused[key] = item[key]
            rows.append(reused)
            continue
        if old:
            item["id"] = old.get("id", item.get("id"))
            item["article_body_attempts"] = int(old.get("article_body_attempts") or 0)
        rows.append(item)
    return rows


def write_day(target: date, items: list[dict[str, object]]) -> None:
    merged = merge_day_items(_load_day(target), items)
    if not merged:
        return  # an empty day file becomes the news page's first (blank) archive
    merged = sorted(mark_important(merged), key=lambda row: int(row.get("importance_score", 0)), reverse=True)
    payload = {"schema_version": 1, "date": target.isoformat(), "count": len(merged), "items": merged}
    atomic_write_json(NEWS_DIR / f"{target.isoformat()}.json", payload)


def rebuild_index() -> None:
    archives: list[dict[str, object]] = []
    all_items: list[dict[str, object]] = []
    latest_archive_items: list[dict[str, object]] = []
    for path in sorted(NEWS_DIR.glob("20??-??-??.json"), reverse=True):
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = []
        for item in payload.get("items", []):
            if is_news_article_candidate(item):
                item = upgrade_existing_item(item)
            else:
                # Eligibility is a publication decision, never permission to
                # erase an archived record when classification rules change.
                item["publication_status"] = "statistics_only"
                item["detail_visible"] = False
                item["article_body_failure_kind"] = "not_an_article"
                item["recovery_status"] = "statistics_only_not_article"
            items.append(item)
        items = mark_important(items)
        for item in items:
            item["detail_visible"] = is_publishable_detail(item)
        payload["items"] = items
        payload["count"] = len(items)
        atomic_write_json(path, payload, only_if_changed=True)
        archives.append({"date": payload.get("date"), "count": len(items), "file": path.name})
        if not latest_archive_items:
            latest_archive_items = items
        all_items.extend(items)
    publishable_items = [item for item in all_items if is_publishable_detail(item)]
    important_items = sorted(
        [item for item in latest_archive_items if item.get("important") and is_publishable_detail(item)],
        key=lambda row: int(row.get("importance_score", 0)),
        reverse=True,
    )[:8]
    recovery_queue = [
        {
            "id": item.get("id"),
            "date": item.get("date"),
            "title": item.get("title"),
            "publisher": item.get("publisher"),
            "error": item.get("article_body_error"),
            "attempts": item.get("article_body_attempts", 0),
            "next_retry_at": item.get("next_body_retry_at"),
            "search_links": item.get("recovery_search_links") or recovery_search_links(str(item.get("title", "")), str(item.get("publisher", ""))),
        }
        for item in all_items
        if not is_publishable_detail(item) and (item.get("article_body_status") == "unavailable"
                                                or item.get("recovery_status") == "retry_scheduled")
    ][:100]
    index = {
        "schema_version": 1,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "archive_days": len(archives),
        "total_articles": len(all_items),
        "latest_items": publishable_items[:12],
        "important_items": important_items,
        "importance_method": "원문 본문 확인을 필수로 하고, 시장 영향도·금리 결정·확정 발표·유사 보도 확산·매체 다양성·출처 신뢰도·공개 조회·반응을 종합해 산정. 연예·포토·비시장성 사건은 제외",
        # Keep the first load light on mobile. Older days load on demand.
        "items": all_items[:600],
        "detailed_articles": len(publishable_items),
        "body_verified_articles": sum(item.get("article_body_status") in PUBLISHABLE_BODY_STATUSES for item in all_items),
        "statistics_only_articles": len(all_items) - len(publishable_items),
        "recovery_queue_count": len(recovery_queue),
        "recovery_queue": recovery_queue,
        "archives": archives,
        # One body/publication contract for backend, docs and the web UI.
        "body_contract": NQ.BODY_CONTRACT,
    }
    atomic_write_json(INDEX_PATH, index)


LOCK_PATH = NEWS_DIR / ".update-economic-news.lock"
LOCK_STALE_SECONDS = 45 * 60
LOCK_MAX_RUN_SECONDS = 3 * 60 * 60
_run_lock_token: str | None = None
_run_lock_guard = None
_run_lock_started = 0.0
_run_lock_stop: threading.Event | None = None
_run_lock_thread: threading.Thread | None = None
_collector_self_exit_enabled = False


def _process_identity(pid: int) -> str | None:
    """Process creation identity, so a recycled PID never owns an old lease."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = (wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4))
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            if kernel.GetProcessTimes(handle, *(ctypes.byref(row) for row in times)):
                return str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
        finally:
            kernel.CloseHandle(handle)
    else:
        try:
            return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
        except (OSError, IndexError):
            pass
    return None


def _guard_lock():
    # Kernel-owned guard is released on exit/crash; never unlink this file.
    handle = LOCK_PATH.with_suffix(LOCK_PATH.suffix + ".guard").open("a+b")
    try:
        if os.name == "nt":
            import msvcrt
            if handle.seek(0, 2) == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def _record_lock_skip(reason: str) -> None:
    state_path = LOCK_PATH.with_suffix(LOCK_PATH.suffix + ".status.json")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        state.update({"consecutive_skips": int(state.get("consecutive_skips") or 0) + 1,
                      "last_skip_at": datetime.now().astimezone().isoformat(timespec="seconds"), "reason": reason})
        atomic_write_json(state_path, state)
        print(f"뉴스 잠금 건너뜀 {state['consecutive_skips']}회: {reason}")
    except (OSError, ValueError, TypeError):
        pass


def assert_run_ownership() -> None:
    """Fence writes and network work after lease loss or the runtime deadline."""
    if not _run_lock_token:
        return
    owner = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if owner.get("token") != _run_lock_token:
        raise RuntimeError("뉴스 실행 잠금 소유권 변경: 저장을 중단함")
    if time.monotonic() - _run_lock_started > LOCK_MAX_RUN_SECONDS:
        raise RuntimeError("뉴스 실행 3시간 상한 초과: 저장을 중단함")


def _heartbeat(stop: threading.Event) -> None:
    while not stop.wait(30):
        try:
            if _collector_self_exit_enabled and time.monotonic() - _run_lock_started > LOCK_MAX_RUN_SECONDS:
                _abort_expired_collector()
                return
            assert_run_ownership()
            os.utime(LOCK_PATH, None)
        except (OSError, ValueError, RuntimeError):
            return


def _abort_expired_collector() -> None:
    """Only main() opts in: exit its own stuck collector, never its parent server.

    Releasing a live writer's lock would allow concurrent corrupting writes.
    Exiting this collector instead lets the OS release its guard atomically.
    """
    if not _collector_self_exit_enabled:
        return
    try:
        owner = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        if owner.get("token") != _run_lock_token:
            return
        path = LOCK_PATH.with_suffix(LOCK_PATH.suffix + ".status.json")
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps({"reason": "collector_runtime_exceeded", "pid": os.getpid(),
                                        "expired_at": datetime.now().astimezone().isoformat(timespec="seconds")}), encoding="utf-8")
        os.replace(temporary, path)
    except (OSError, ValueError):
        pass
    os._exit(124)


def _process_is_running(pid: int) -> bool:
    """Probe liveness without terminating a process; uncertainty keeps the lock."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() != 87  # ERROR_INVALID_PARAMETER: no such PID
        try:
            code = wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def acquire_run_lock() -> bool:
    """One writer at a time (two local servers can schedule the same slot)."""
    global _run_lock_token, _run_lock_guard, _run_lock_started, _run_lock_stop, _run_lock_thread
    if _run_lock_token:
        return False
    guard = _guard_lock()
    if guard is None:
        _record_lock_skip("다른 수집 프로세스가 OS 잠금을 보유 중")
        return False
    acquired = False
    try:
        acquired = _acquire_metadata_lock()
        if not acquired:
            return False
        _run_lock_guard = guard
        _run_lock_started = time.monotonic()
        _run_lock_stop = threading.Event()
        _run_lock_thread = threading.Thread(target=_heartbeat, args=(_run_lock_stop,), daemon=True)
        _run_lock_thread.start()
        atomic_write_json(LOCK_PATH.with_suffix(LOCK_PATH.suffix + ".status.json"), {"consecutive_skips": 0, "acquired_at": datetime.now().astimezone().isoformat(timespec="seconds")})
        return True
    finally:
        if not acquired:
            guard.close()


def _acquire_metadata_lock() -> bool:
    global _run_lock_token
    for _attempt in range(2):
        try:
            handle = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(handle, "w", encoding="utf-8") as output:
                token = uuid.uuid4().hex
                output.write(json.dumps({"pid": os.getpid(), "process_identity": _process_identity(os.getpid()),
                                         "token": token, "started_at": datetime.now().astimezone().isoformat(timespec="seconds")}))
            _run_lock_token = token
            return True
        except FileExistsError:
            try:
                age = time.time() - LOCK_PATH.stat().st_mtime
            except OSError:
                continue
            try:
                owner = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
                pid = int(owner.get("pid") or 0)
                identity = _process_identity(pid)
                reused_pid = owner.get("process_identity") and identity and owner["process_identity"] != identity
                if _process_is_running(pid) and not reused_pid:
                    _record_lock_skip("기존 수집 프로세스가 실행 중이거나 소유권 확인이 불확실함")
                    return False  # a long live collection is not a stale writer
            except (OSError, ValueError, TypeError):
                if age > LOCK_STALE_SECONDS:
                    LOCK_PATH.unlink(missing_ok=True)  # crashed during metadata creation; OS guard is free
                    continue
                _record_lock_skip("잠금 메타데이터를 확인할 수 없음")
                return False
            LOCK_PATH.unlink(missing_ok=True)
    return False


def release_run_lock() -> None:
    global _run_lock_token, _run_lock_guard, _run_lock_stop, _run_lock_thread
    if _run_lock_stop:
        _run_lock_stop.set()
    if _run_lock_thread:
        _run_lock_thread.join(timeout=1)
    try:
        owner = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        if _run_lock_token and owner.get("token") == _run_lock_token:
            LOCK_PATH.unlink(missing_ok=True)
    except (OSError, ValueError, TypeError):
        pass
    finally:
        _run_lock_token = None
        if _run_lock_guard:
            _run_lock_guard.close()
        _run_lock_guard = _run_lock_stop = _run_lock_thread = None


def main() -> None:
    global _collector_self_exit_enabled
    parser = argparse.ArgumentParser(description="경제·금융·산업·부동산 뉴스 RSS를 날짜별로 보관합니다.")
    parser.add_argument("--backfill-days", type=int, default=1)
    parser.add_argument("--limit-per-day", type=int, default=24)
    parser.add_argument("--archive-enrich-limit", type=int, default=60, help="한 실행에서 과거 원문 본문을 다시 처리할 최대 기사 수")
    parser.add_argument("--archive-only", action="store_true", help="새 뉴스 수집 없이 과거 기사 구조화만 실행")
    parser.add_argument("--force-retry-unavailable", action="store_true", help="원문 미확인 기사도 즉시 다시 원문 경로를 확인")
    args = parser.parse_args()
    days = max(1, min(args.backfill_days, 365))
    limit = max(6, min(args.limit_per_day, 60))
    archive_limit = max(0, min(args.archive_enrich_limit, 120))
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    if not acquire_run_lock():
        print(f"다른 뉴스 갱신이 실행 중이라 이번 실행을 건너뜁니다: {LOCK_PATH}")
        return
    run_started = time.monotonic()
    _collector_self_exit_enabled = True
    _page_metrics.clear()
    _enrichment_metrics.clear()
    def inventory():
        rows = [row for path in NEWS_DIR.glob("20??-??-??.json")
                for row in json.loads(path.read_text(encoding="utf-8")).get("items", [])]
        return {"total": len(rows), "visible": sum(is_publishable_detail(row) for row in rows)}
    metrics = {"started_at": datetime.now().astimezone().isoformat(timespec="seconds")}
    try:
        metrics["before"] = inventory()
        today = date.today()
        if not args.archive_only:
            for offset in range(days - 1, -1, -1):
                target = today - timedelta(days=offset)
                # Day files keep the collection window (the archive's existing
                # convention).  Each item shows its own KST "date"; re-filing by
                # that date was tried on 2026-11-28 and duplicated articles,
                # because the feed date of a cluster changes between runs.
                items = collect_day(target, limit)
                if items:  # right after midnight the new day's feed is empty; never publish an empty day page
                    write_day(target, items)
                    print(f"{target}: {len(items)}건 저장")
        enriched = enrich_archived_bodies(archive_limit, force_retry=args.force_retry_unavailable)
        if enriched:
            print(f"과거 기사 원문 본문 재처리: {enriched}건")
        rebuild_index()
        print(f"경제뉴스 인덱스 생성 완료: {INDEX_PATH}")
    except Exception as error:
        metrics["error"] = f"{type(error).__name__}: {str(error)[:240]}"
        raise
    finally:
        try:
            metrics.update({"after": inventory(), "duration_seconds": round(time.monotonic() - run_started, 2),
                            "page_reads": dict(_page_metrics), "enrichment_attempts": len(_enrichment_metrics),
                            "enrichment_successes": sum(bool(row["success"]) for row in _enrichment_metrics),
                            "date_corrections": sum(bool(row["date_corrected"]) for row in _enrichment_metrics),
                            "results": _enrichment_metrics})
            out = ROOT / "data" / "local" / "news-run-metrics"
            out.mkdir(parents=True, exist_ok=True)
            destination = out / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{os.getpid()}.json"
            destination.write_text(json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8")
        finally:
            _collector_self_exit_enabled = False
            release_run_lock()


NON_EDITORIAL_NOTICE_PATTERN = re.compile(
    r"\b(?:net\s+asset\s+value(?:\(s\))?|nav\s+per\s+share|"
    r"dealing\s+date|ucits\s+etf|regulatory\s+announcement)\b",
    re.I,
)

MACRO_MARKET_SIGNALS = {
    # "유가증권" 같은 금융상품 명칭은 국제유가 충격이 아니므로, 유가라는
    # 단독 낱말 대신 원유·배럴·WTI·브렌트 등 오인 가능성이 낮은 표현만 쓴다.
    "유가": ("유가", "원유", "WTI", "브렌트", "두바이유", "배럴당"),
    "물가": ("소비자물가", "생산자물가", "CPI", "PPI", "인플레이션"),
    "금리": ("국채", "10년물", "국채금리", "수익률", "장기금리", "기준금리"),
    "통화정책": ("연준", "Federal Reserve", "FOMC", "금리 인상", "금리 인하"),
    "주식시장": ("뉴욕증시", "코스피", "코스닥", "나스닥", "S&P", "주가", "증시"),
}

MACRO_ALERT_PAIRS = (
    frozenset({"유가", "물가"}), frozenset({"유가", "금리"}), frozenset({"유가", "통화정책"}), frozenset({"유가", "주식시장"}),
    frozenset({"물가", "금리"}), frozenset({"물가", "통화정책"}), frozenset({"물가", "주식시장"}),
    frozenset({"금리", "통화정책"}), frozenset({"금리", "주식시장"}),
)

def is_non_editorial_notice(row: dict[str, object]) -> bool:
    """Exclude repetitive fund NAV and regulatory administration notices."""
    title = clean_text(str(row.get("title") or ""))
    description = clean_text(str(row.get("description") or ""))
    return bool(NON_EDITORIAL_NOTICE_PATTERN.search(title) or NON_EDITORIAL_NOTICE_PATTERN.search(description))

def aggregate_engagement(related: list[dict[str, object]]) -> dict[str, object]:
    """Keep only public, source-supplied popularity/editorial signals.

    We never infer clicks from a headline or a publisher name.  When a duplicate
    group contains multiple official ranks, the best rank is retained; views and
    reactions are summed only when they are explicitly exposed by a source.
    """
    views = reactions = 0
    ranks: list[int] = []
    metrics: list[str] = []
    featured = False
    for source in related:
        engagement = source.get("engagement") if isinstance(source.get("engagement"), dict) else {}
        views += max(0, int(engagement.get("views") or 0))
        reactions += max(0, int(engagement.get("reactions") or 0))
        rank = int(engagement.get("rank") or 0)
        if rank > 0:
            ranks.append(rank)
        metric = clean_text(str(engagement.get("metric") or ""))
        if metric and metric not in metrics:
            metrics.append(metric[:80])
        featured = featured or bool(engagement.get("featured") or engagement.get("editor_pick") or engagement.get("top_story"))
    result: dict[str, object] = {}
    if views:
        result["views"] = views
    if reactions:
        result["reactions"] = reactions
    if ranks:
        result["rank"] = min(ranks)
    if metrics:
        result["metric"] = " · ".join(metrics[:2])
    if featured:
        result["featured"] = True
    return result

def item_market_text(item: dict[str, object]) -> str:
    sources = item.get("sources") if isinstance(item.get("sources"), list) else []
    source_text = " ".join(f"{source.get('title', '')} {source.get('description', '')}" for source in sources if isinstance(source, dict))
    return " ".join(str(item.get(key) or "") for key in ("title", "summary", "easy_explanation", "core_summary")) + " " + source_text

def macro_signals(text: str) -> set[str]:
    # "유가증권"은 국내 주식시장 용어라 국제유가 신호에서 제외한다.
    lowered = text.lower().replace("유가증권", "")
    return {label for label, keywords in MACRO_MARKET_SIGNALS.items() if any(keyword.lower() in lowered for keyword in keywords)}

def macro_market_alert(items: list[dict[str, object]]) -> set[str]:
    """Return verified cross-market signals only when a same-day shock is corroborated.

    A single headline never creates an alert.  Two linked groups must appear and at
    least one article must directly connect the groups, preventing unrelated daily
    headlines from being promoted merely because they share broad keywords.
    """
    per_item = [macro_signals(item_market_text(item)) for item in items]
    present = set().union(*per_item) if per_item else set()
    confirmed = set().union(*(pair for pair in MACRO_ALERT_PAIRS if pair <= present))
    linked = any(any(pair <= signals for pair in MACRO_ALERT_PAIRS if pair <= confirmed) for signals in per_item)
    return confirmed if linked else set()

if __name__ == "__main__":
    main()
