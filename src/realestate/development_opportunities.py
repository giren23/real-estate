from __future__ import annotations

import hashlib
import html
import json
import os
import re
import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import requests


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KoreanRealEstateOfficialDevelopment/1.0"
KST = timezone(timedelta(hours=9))
SPACE_PATTERN = re.compile(r"\s+")
TAG_PATTERN = re.compile(r"<[^>]+>")
SENTENCE_PATTERN = re.compile(r"(?<=[.!?。])\s+")
NUMBER_PATTERN = re.compile(r"\d[\d,.]*(?:\s*(?:조원|억원|만원|원|km|m|㎡|%|개|곳|호|세대|년|월|일))?", re.I)
NOISE_PATTERN = re.compile(r"로그인|회원가입|개인정보처리방침|저작권|무단전재|메뉴|바로가기|검색어를 입력", re.I)

CATEGORY_TERMS = {
    "정비·주거": ("재개발", "재건축", "정비구역", "도시재생", "주택정비", "공공주택", "택지", "지구단위계획"),
    "교통": ("철도", "광역교통", "GTX", "도시철도", "지하철", "역세권", "환승", "도로", "IC", "개통"),
    "교육": ("학교", "초등학교", "중학교", "고등학교", "교육지원청", "학군", "도서관"),
    "생활·공공시설": ("공원", "병원", "의료원", "복지관", "체육", "문화시설", "공공시설", "복합개발", "청사"),
    "산업·일자리": ("산업단지", "업무지구", "기업유치", "연구개발", "첨단산업", "일자리", "테크노밸리"),
}
ALL_TERMS = tuple(dict.fromkeys(term for terms in CATEGORY_TERMS.values() for term in terms))
STAGE_RULES = (
    ("준공·개통", 6, re.compile(r"준공(?:했|됐|되었)|개통(?:했|됐|되었)|운영을?\s*시작|완료(?:했|됐|되었)")),
    ("착공·공사", 5, re.compile(r"착공(?:했|됐|되었)|첫\s*삽|공사(?:를|가)?\s*시작|공사\s*중|공사에\s*들어")),
    ("인허가·보상", 4, re.compile(r"사업시행인가|관리처분인가|실시계획인가|보상(?:계획|착수|공고)|토지\s*수용")),
    ("결정·고시/예산", 3, re.compile(r"결정\s*고시|지정\s*고시|고시(?:했|됐|되었)|예산\s*(?:반영|확정)|의결(?:했|됐|되었)|확정(?:했|됐|되었)")),
    ("계획 반영·추진", 2, re.compile(r"기본계획|계획에\s*반영|추진(?:한다|중|할)|사업\s*계획|정비구역\s*지정")),
    ("검토·용역", 1, re.compile(r"검토|용역|제안|건의|후보|타당성\s*조사")),
)
OFFICIAL_EXACT_HOSTS = {
    "korea.kr", "www.korea.kr", "eum.go.kr", "www.eum.go.kr", "data.go.kr", "www.data.go.kr",
    "schoolinfo.go.kr", "www.schoolinfo.go.kr", "kr.or.kr", "www.kr.or.kr", "lh.or.kr", "www.lh.or.kr",
    "gh.or.kr", "www.gh.or.kr", "i-sh.co.kr", "www.i-sh.co.kr", "korail.com", "www.korail.com",
}
OFFICIAL_SUFFIXES = (".go.kr", ".korea.kr", ".kr.or.kr", ".lh.or.kr", ".gh.or.kr")
BLOCKED_ARTICLE_HOSTS = {"news.google.com", "search.naver.com", "search.daum.net", "facebook.com", "www.facebook.com", "youtube.com", "www.youtube.com"}


def clean_text(value: str) -> str:
    return SPACE_PATTERN.sub(" ", html.unescape(TAG_PATTERN.sub(" ", value or ""))).strip()


def is_official_url(url: str) -> bool:
    parsed = urlparse(url or "")
    host = parsed.netloc.lower().split(":", 1)[0]
    return parsed.scheme in {"http", "https"} and (host in OFFICIAL_EXACT_HOSTS or host.endswith(OFFICIAL_SUFFIXES))


def is_public_article_url(url: str) -> bool:
    parsed = urlparse(url or "")
    host = parsed.netloc.lower().split(":", 1)[0]
    if parsed.scheme not in {"http", "https"} or not host or host in BLOCKED_ARTICLE_HOSTS:
        return False
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or host.endswith((".local", ".internal")):
        return False
    return True


def location_terms(region_name: str, dong: str) -> list[str]:
    values = [token for token in re.findall(r"[가-힣A-Za-z0-9]+", f"{region_name} {dong}") if len(token) >= 2]
    root = re.sub(r"\d*(?:가|동|읍|면|리)$", "", dong)
    if len(root) >= 2:
        values.append(root)
    return list(dict.fromkeys(values))


def title_terms(value: str) -> set[str]:
    ignored = {"관련", "추진", "개최", "공개", "발표", "본격화", "된다", "위한"}
    return {token.lower() for token in re.findall(r"[가-힣A-Za-z0-9]+", clean_text(value)) if len(token) >= 2 and token not in ignored}


def same_event_title(left: str, right: str) -> bool:
    left_terms, right_terms = title_terms(left), title_terms(right)
    if not left_terms or not right_terms:
        return False
    return len(left_terms & right_terms) / min(len(left_terms), len(right_terms)) >= 0.72


def category_for(text: str) -> str:
    scored = [(sum(text.lower().count(term.lower()) for term in terms), name) for name, terms in CATEGORY_TERMS.items()]
    score, category = max(scored)
    return category if score else "기타 공식계획"


def stage_for(text: str) -> tuple[str, int]:
    for label, score, pattern in STAGE_RULES:
        if pattern.search(text):
            return label, score
    return "발표·공개", 0


class OfficialPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self.descriptions: list[str] = []
        self._capture = 0
        self._buffer: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() in {"script", "style", "svg", "noscript"}:
            self._skip += 1
            return
        if tag.lower() == "meta" and (attributes.get("name", "").lower() == "description" or attributes.get("property", "").lower() == "og:description"):
            value = clean_text(attributes.get("content", ""))
            if value:
                self.descriptions.append(value)
        if not self._skip and tag.lower() in {"p", "li", "h1", "h2", "h3"}:
            self._capture += 1
            if self._capture == 1:
                self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._capture and not self._skip:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "svg", "noscript"} and self._skip:
            self._skip -= 1
            return
        if tag.lower() in {"p", "li", "h1", "h2", "h3"} and self._capture:
            self._capture -= 1
            if self._capture == 0:
                value = clean_text(" ".join(self._buffer))
                if value:
                    self.blocks.append(value)


def _sentences(blocks: list[str]) -> list[str]:
    rows: list[str] = []
    for block in blocks:
        pieces = SENTENCE_PATTERN.split(clean_text(block))
        rows.extend(piece for piece in pieces if 24 <= len(piece) <= 500 and not NOISE_PATTERN.search(piece))
    return list(dict.fromkeys(rows))


def summarize_official_document(title: str, blocks: list[str], region_name: str, dong: str, apt_name: str) -> dict | None:
    title = clean_text(title)
    candidates = [row for row in _sentences(blocks) if row != title]
    locations = location_terms(region_name, dong)
    ranked: list[tuple[int, int, str]] = []
    for index, sentence in enumerate(candidates):
        score = 0
        score += 5 if apt_name and apt_name.replace(" ", "") in sentence.replace(" ", "") else 0
        score += min(4, sum(1 for term in locations if term in sentence))
        score += min(6, sum(2 for term in ALL_TERMS if term.lower() in sentence.lower()))
        score += 2 if NUMBER_PATTERN.search(sentence) else 0
        score += 1 if any(pattern.search(sentence) for _label, _weight, pattern in STAGE_RULES) else 0
        if score >= 4:
            ranked.append((score, index, sentence))
    chosen = sorted(sorted(ranked, reverse=True)[:3], key=lambda row: row[1])
    summary = " ".join(row[2] for row in chosen)
    if len(summary) < 70:
        return None
    evidence = f"{title} {summary}"
    stage, stage_score = stage_for(evidence)
    compact = summary[:700].rstrip()
    if len(summary) > 700:
        compact += "…"
    normalized_evidence = evidence.replace(" ", "")
    normalized_apt = apt_name.replace(" ", "")
    if normalized_apt and normalized_apt in normalized_evidence:
        scope = "선택 단지 직접 언급"
    elif dong and (dong in evidence or re.sub(r"\d*(?:가|동|읍|면|리)$", "", dong) in evidence):
        scope = "법정동 직접 언급"
    else:
        scope = "시·군·구 생활권 연관"
    return {
        "summary": compact,
        "category": category_for(evidence),
        "stage": stage,
        "stage_score": stage_score,
        "scope": scope,
        "body_status": "full_text",
    }


class DevelopmentOpportunityStore:
    def __init__(self, root: Path, cache_hours: int | None = None) -> None:
        self.cache_path = root / "data" / "local" / "development_opportunities.json"
        self.cache_seconds = max(1, cache_hours or int(os.environ.get("DEVELOPMENT_CACHE_HOURS", "12"))) * 3600
        self._lock = threading.Lock()
        self._cache: dict[str, dict] | None = None

    def _read_cache(self) -> dict[str, dict]:
        with self._lock:
            if self._cache is None:
                try:
                    self._cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    self._cache = {}
            return self._cache

    def _write_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._cache or {}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temporary.replace(self.cache_path)

    @staticmethod
    def _cache_key(region_name: str, dong: str, apt_name: str) -> str:
        return f"v2|{clean_text(region_name)}|{clean_text(dong)}|{clean_text(apt_name)}"

    def get(self, region_name: str, dong: str, apt_name: str) -> dict:
        key = self._cache_key(region_name, dong, apt_name)
        cached = self._read_cache().get(key)
        now = datetime.now(KST)
        if cached:
            try:
                age = (now - datetime.fromisoformat(str(cached["generated_at"]))).total_seconds()
            except (KeyError, ValueError):
                age = self.cache_seconds + 1
            if age <= self.cache_seconds:
                return {**cached, "scope_apt_name": apt_name, "cached": True}
        try:
            result = self._collect(region_name, dong, apt_name)
        except Exception as error:
            if cached:
                return {**cached, "scope_apt_name": apt_name, "cached": True, "status": "stale", "message": "공식 자료 갱신이 지연되어 마지막 확인 결과를 표시함"}
            return {
                "status": "error", "message": "공식 자료 자동 조회에 실패함", "reason": str(error)[:160],
                "generated_at": now.isoformat(timespec="seconds"), "scope_apt_name": apt_name, "items": [],
            }
        with self._lock:
            assert self._cache is not None
            self._cache[key] = result
            self._write_cache()
        return {**result, "scope_apt_name": apt_name, "cached": False}

    def _feed_candidates(self, region_name: str, dong: str) -> list[dict]:
        terms = " OR ".join(ALL_TERMS)
        query = f'("{region_name}" OR "{dong}") ({terms}) (site:go.kr OR site:korea.kr OR site:kr.or.kr OR site:lh.or.kr) when:5y'
        url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=ko&gl=KR&ceid=KR:ko"
        response = requests.get(url, timeout=12, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml,application/xml"})
        response.raise_for_status()
        root = ET.fromstring(response.content)
        locations = location_terms(region_name, dong)
        rows: list[dict] = []
        for item in root.findall("./channel/item"):
            title = clean_text(item.findtext("title") or "")
            link = clean_text(item.findtext("link") or "")
            if not title or not link or not any(term.lower() in title.lower() for term in ALL_TERMS):
                continue
            if not any(term in title for term in locations):
                continue
            source = item.find("source")
            publisher = clean_text(source.text if source is not None and source.text else "공식기관")
            source_home = clean_text(source.get("url") if source is not None else "")
            published = item.findtext("pubDate") or ""
            try:
                published_at = parsedate_to_datetime(published).astimezone(KST).date().isoformat()
            except (TypeError, ValueError):
                published_at = ""
            rows.append({"title": title.rsplit(f" - {publisher}", 1)[0], "google_url": link, "publisher": publisher, "source_home": source_home, "official_hint": is_official_url(source_home), "published_at": published_at})
        rows.sort(key=lambda row: (row["official_hint"], row["published_at"]), reverse=True)
        return rows[:48]

    @staticmethod
    def _decode(row: dict) -> dict | None:
        try:
            from googlenewsdecoder import gnewsdecoder

            result = gnewsdecoder(row["google_url"], interval=0)
            url = str(result.get("decoded_url") or "") if result.get("status") else ""
        except Exception:
            return None
        if not is_public_article_url(url):
            return None
        return {**row, "url": url, "official": is_official_url(url)}

    @staticmethod
    def _fetch_document(row: dict, region_name: str, dong: str, apt_name: str) -> dict | None:
        try:
            response = requests.get(row["url"], timeout=8, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
            response.raise_for_status()
            if not is_public_article_url(response.url) or "html" not in response.headers.get("Content-Type", "").lower():
                return None
            response.encoding = response.apparent_encoding or response.encoding
            parser = OfficialPageParser()
            parser.feed(response.text[:2_000_000])
            summary = summarize_official_document(row["title"], parser.descriptions + parser.blocks, region_name, dong, apt_name)
            if not summary:
                return None
            url = response.url.split("#", 1)[0]
            return {
                "id": hashlib.sha256(url.encode("utf-8")).hexdigest()[:16], "title": row["title"][:220],
                "publisher": row["publisher"][:80], "published_at": row["published_at"], "url": url,
                "source_type": "공식기관 원문" if is_official_url(url) else "언론 공개 본문",
                "official": is_official_url(url), **summary,
            }
        except (requests.RequestException, ValueError, UnicodeError):
            return None

    def _collect(self, region_name: str, dong: str, apt_name: str) -> dict:
        candidates = self._feed_candidates(region_name, dong)
        decoded: list[dict] = []
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(self._decode, row) for row in candidates[:36]]
            for future in as_completed(futures):
                value = future.result()
                if value:
                    decoded.append(value)
        documents: list[dict] = []
        seen: set[str] = set()
        decoded.sort(key=lambda row: (row.get("official", False), row.get("published_at", "")), reverse=True)
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(self._fetch_document, row, region_name, dong, apt_name) for row in decoded[:20]]
            for future in as_completed(futures):
                value = future.result()
                if value and value["id"] not in seen:
                    seen.add(value["id"])
                    documents.append(value)
        documents.sort(key=lambda row: (row.get("official", False), row["scope"] == "선택 단지 직접 언급", row["stage_score"], row["published_at"]), reverse=True)
        unique_documents: list[dict] = []
        seen_titles: list[str] = []
        for document in documents:
            title_key = re.sub(r"[^가-힣A-Za-z0-9]", "", document["title"]).lower()
            if title_key in seen_titles or any(same_event_title(document["title"], row["title"]) for row in unique_documents):
                continue
            seen_titles.append(title_key)
            unique_documents.append(document)
        items = unique_documents[:8]
        now = datetime.now(KST).isoformat(timespec="seconds")
        return {
            "status": "ok" if items else "empty",
            "message": "공식기관 원문을 우선하고 공개 전문이 확보된 보도를 보조자료로 정리함" if items else "최근 5년 공개 검색 범위에서 본문까지 확인된 개발·생활권 자료가 없음",
            "generated_at": now, "region_name": region_name, "dong": dong, "items": items,
            "method": "공식기관 공개 원문을 최우선으로 수집하고, 부족할 때만 공개 전문이 확보된 보도를 보조자료로 사용해 사업 단계와 단지 연관 범위를 규칙 기반으로 분류",
            "caution": "‘언론 공개 본문’은 공식 확정 자료가 아니며, 법정동·시군구 연관 자료는 단지 경계나 출입구까지의 실제 거리 및 소음·혼잡 같은 반대 영향을 별도로 확인해야 함.",
        }
