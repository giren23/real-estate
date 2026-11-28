"""Evidence-bound article extraction and structuring rules for the news archive.

This module is deliberately network-free.  ``update_economic_news.py`` fetches
public pages and calls these functions; tests exercise them with fixed HTML.

Contract summary (also written to ``index.json`` as ``body_contract``):

* ``full_text``        – a dedicated article-body region (JSON-LD articleBody,
  a recognised body container or an ``<article>`` element, or paragraph text
  closed by a byline/copyright boundary) that matches the headline and holds
  at least 3 sentences and 350 characters.
* ``verified_excerpt`` – the headline matches and at least 2 sentences /
  120 characters were read, but the full-text rule is not met (a short but
  complete wire item, or an unconfirmed body boundary).  The UI must say so.
* ``unavailable``      – anything else.  Titles, subtitles, captions, meta
  descriptions and RSS snippets never count toward body length.
"""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from typing import Iterable

EXTRACTION_VERSION = 2

BODY_CONTRACT: dict[str, object] = {
    "version": 1,
    "statuses": {
        "full_text": {
            "min_sentences": 3,
            "min_chars": 350,
            "requires": ["dedicated_body_region_or_closed_boundary", "title_body_match"],
            "label": "원문 본문 확보",
        },
        "verified_excerpt": {
            "min_sentences": 2,
            "min_chars": 120,
            "requires": ["title_body_match"],
            "label": "본문 일부 또는 짧은 기사 확인",
        },
        "verified_reconstruction": {
            "requires": ["manual_editorial_record"],
            "label": "수동 검수 요약",
        },
        "unavailable": {"label": "원문 본문 미확보"},
    },
    "publishable_statuses": ["full_text", "verified_excerpt", "verified_reconstruction"],
    "excluded_from_body_length": ["title", "subtitle", "caption", "meta_description", "rss_description", "ui", "code", "after_boundary"],
}
FULL_TEXT_MIN_SENTENCES = 3
FULL_TEXT_MIN_CHARS = 350
EXCERPT_MIN_SENTENCES = 2
EXCERPT_MIN_CHARS = 120
PUBLISHABLE_STATUSES = frozenset(BODY_CONTRACT["publishable_statuses"])  # type: ignore[arg-type]

SPACE = re.compile(r"\s+")
TAG = re.compile(r"<[^>]+>")
TOKEN = re.compile(r"[가-힣A-Za-z0-9]+")
STOPWORDS = {"관련", "대한", "이번", "오늘", "내일", "정부", "시장", "뉴스", "전망", "발표", "한국", "미국", "종합", "속보", "단독"}
# Split after terminal punctuation.  "다" endings without a period are common in
# Korean copy, so a closing "다" followed by whitespace and a new sentence start
# is also treated as a boundary.
SENTENCE_SPLIT = re.compile(r"(?<=[.!?。])(?:\s+|(?=[가-힣A-Z“\"'‘\[][가-힣A-Za-z]))")
SENTENCE_END = re.compile(r"(?:[다요음함임됨]|니다|습니다)\s*[.!?。]?[”\"’')\]]*\s*$|[.!?。][”\"’')\]]*\s*$")

CONTAINER_MARKER = re.compile(
    r"(?:article|news|story|post|entry)[-_ ]?(?:body|content|text|txt|view|detail|cont)\b|"
    r"newsct_article|(?:view|news)[-_ ]?(?:content|cont|body|article|text)|content[-_ ]?view|"
    r"se-main-container|postviewarea|articlebody|article_view|art_txt|news_body_area|dic_area|"
    r"article-view-content-div|news-article-body|story-body|caas-body|article__content|entry-content|"
    r"CmAdContent|(?:^|\s)paragraph(?:\s|$)|article_content|articletxt|news_text|view_con|story-news|article-text|"
    r"detail[-_ ]?cont|(?:^|\s)vtxt(?:\s|$)|(?:^|\s)textinput(?:\s|$)",
    re.I,
)
EXCLUDED_ZONE_MARKER = re.compile(
    r"(?:^|[-_ ])(?:related|relate|recommend|recom|popular|ranking|rank|reporter|byline|copyright|"
    r"sns|share|social|comment|reply|footer|aside|banner|advert|ads?|adsense|tag-?list|hashtag|"
    r"subscribe|newsletter|breadcrumb|gnb|lnb|menu|navigation|nav|promo|sponsor|outbrain|taboola|"
    r"most-?read|more-?news|other-?news|series-?list|keyword|toolbar|util|font-?size|print|"
    r"tts|audio|player|summary-?ai|ai-?summary|paywall|regwall|modal|popup|layer-?pop)(?:$|[-_ ])",
    re.I,
)
CAPTION_MARKER = re.compile(r"caption|photo[-_ ]?desc|img[-_ ]?desc|image[-_ ]?desc|figcaption|pic[-_ ]?txt|photo[-_ ]?text|se-caption", re.I)
# <form> is not skipped: some CMS pages wrap the whole article in one form
# (gnews.gg.go.kr).  Its controls (input/select/textarea/button) still are.
SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "iframe", "button", "select", "option", "textarea", "video", "audio", "canvas"}
EXCLUDED_TAGS = {"nav", "aside", "footer"}
BLOCK_TAGS = {"p", "div", "li", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "figcaption", "section", "article", "main", "header", "dd", "dt", "pre", "table", "tr", "ul", "ol", "figure"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

CAPTION_LINE = re.compile(
    r"\((?:사진|그래픽|자료|출처|이미지|영상|제공|일러스트|표)\s*[=:]|^\(?(?:사진|그래픽|자료|출처|이미지|일러스트)\s*[=:]|"
    r"/\s*(?:사진|그래픽)\s*=|=\s*(?:연합뉴스|뉴시스|뉴스1)\s*\)?\s*$|For Use Only in the Republic of Korea|"
    r"(?:사진|자료|그래픽)\s*제공\s*[=:]?\s*[가-힣A-Za-z]+\s*$|^\[(?:사진|그래픽|표)\]",
    re.I,
)
BYLINE_LINE = re.compile(
    r"^(?:[가-힣]{2,4}\s*)?(?:[가-힣]{2,4}\s+)?(?:기자|특파원|객원기자|선임기자|인턴기자|에디터|통신원)\b.{0,60}$|"
    r"^[가-힣]{2,4}\s*(?:기자|특파원)\s*[\w.+-]+@[\w.-]+|[\w.+-]+@[\w-]+\.[\w.-]+\s*$",
)
BROADCAST_CUE = re.compile(r"(?:다|요|까)[.!?](?:\s|$)|(?:기자|특파원)\s*[!?]")
COPYRIGHT_LINE = re.compile(r"ⓒ|©|무단\s*전재|재배포\s*금지|무단\s*복제|Copyright|All rights reserved|저작권자|^\((?:Reporting|Writing|Additional reporting) by\b", re.I)
# A standalone list label inside a body container ("주요뉴스" followed by other
# headlines on edaily) closes the article once the body has started.
RELATED_LABEL = re.compile(
    r"(?:이\s*시각\s*|오늘의\s*)?(?:주요\s*뉴스|관련\s*(?:기사|뉴스)|많이\s*본\s*(?:기사|뉴스)|인기\s*(?:기사|뉴스)|추천\s*(?:기사|뉴스)|"
    r"최신\s*(?:기사|뉴스)|랭킹\s*뉴스|함께\s*(?:보면|볼만한)\s*좋은\s*(?:기사|뉴스)|Related\s*(?:articles|news|stories)|Most\s*read)\s*[:：]?",
    re.I,
)
ATTACHMENT_LINE = re.compile(r"\.(?:hwpx?|pdf|docx?|xlsx?|pptx?|png|jpe?g|gif|zip)\b(?:\s|$)", re.I)
AI_SUMMARY_START = re.compile(r"^(?:주요\s*요약|핵심\s*요약|AI\s*요약|3줄\s*요약|세\s*줄\s*요약|Key\s*Points?|Summary)\s*[:：]?\s*$", re.I)
STRONG_UI = re.compile(
    r"가장\s*빠른\s*뉴스가\s*있고.{0,100}다음뉴스를\s*만나보세요|"
    r"아래\s*텍스트는\s*실제\s*방송\s*내용과\s*차이|"
    r"요약보기|자동\s*요약|AI가\s*요약|음성으로\s*듣기|음성\s*재생|기사를\s*읽어|글자\s*크기|글씨\s*크기|번역\s*beta|Translated by|"
    r"번역중|Now in translation|기사\s*저장|스크랩|URL\s*복사|링크\s*복사|인쇄하기|공유하기|구독하기|좋아요|추천해요|"
    r"로그인(?:이|을)?\s*필요|댓글(?:을)?\s*(?:입력|작성|쓰기|보기)|이\s*기사를\s*추천|기사\s*제보|"
    r"주소\s*:\s*서울특별시|일간신문등록번호|인터넷신문등록번호|등록\s*\(발행\)일자|발행\s*/\s*편집인|청소년보호책임자|"
    r"블로그\s*(?:주소|아이디)|이웃(?:을)?\s*맺|이웃새글|네이버\s*고객센터|악성코드|비밀번호(?:를)?\s*확인|"
    r"게시물\s*등록이|스팸\s*게시물|이용제한\s*파일|\{FILENAME\}|\{ALERTMESSAGE\}|이\s*블로그의\s*저작물|"
    r"이\s*포스트는\s*네이버\s*블로그|네이버\s*여행\s*서비스|글보내기\s*기능|주제\s*분류\s*기능|공감수|"
    r"멤버는\s*매월\s*\d+\s*개|누구에게나\s*선물할\s*수|계정/결제\s*관리를\s*위해|구독자\s*전용\s*콘텐츠|새\s*창을\s*닫으면|"
    r"browser\s+(?:doesn't|does\s+not)\s+support\s+HTML5|오류가\s*있을\s*수\s*있으며\s*정확한\s*정보는|특정\s*종목에\s*대한\s*투자\s*권유가\s*아닙니다",
    re.I,
)
SHORT_UI_WORDS = re.compile(r"공유|구독|로그인|댓글|공감|닫기|인쇄|페이스북|Facebook|트위터|Twitter|카카오톡|LinkedIn|Pinterest|URL|목록|이전\s*기사|다음\s*기사|전체\s*메뉴|검색", re.I)
CODE_LINE = re.compile(
    r"function\s*\(|googletag|window\.|document\.|\bvar\s+\w+\s*=|\bconst\s+\w+\s*=|\blet\s+\w+\s*=|=>|cmd\.push|adsbygoogle|"
    # "return" alone is ordinary English ("a return to growth"); only a return
    # statement closed by ";" is code.
    r"\$\(|jQuery|\{\s*[\w-]+\s*:\s*[^}]{0,40}\}|\b\d+px\b|<\/?[a-z][\w-]*[^>]*>|setTimeout|addEventListener|\bif\s*\(|\breturn\s+[^;\n]{0,60};",
    re.I,
)
HASHTAG_LINE = re.compile(r"(?:^|\s)#[^\s#]{1,30}(?:\s+#[^\s#]{1,30})+")
DATELINE = re.compile(r"^\s*(?:\[[^\]]{1,60}\]|\([^)]{1,40}=[^)]{1,30}\))\s*(?:=|[-–—])?\s*|^\s*[가-힣]{2,10}\s*=\s*[가-힣A-Za-z]{0,10}\s*(?:[가-힣]{2,4}\s*(?:기자|특파원)\s*=)?\s*")


ATOMIC_CLASS_CHARS = re.compile(r"[\[\]:&()!%#]")
TRUNCATED_END = re.compile(r"(?:\.{2,}|…)[”\"’')\]]*\s*$")


def marker_text(attributes: dict[str, str]) -> str:
    """id + class for marker matching, without utility-CSS tokens.

    Tailwind/Panda pages carry selector-like classes such as
    "[&_figcaption]:fs_14px" or "[&>:first-child]:!mt-0" on the body wrapper;
    matching "figcaption" inside them turned whole articles into captions.
    """
    tokens = [token for token in attributes.get("class", "").split() if not ATOMIC_CLASS_CHARS.search(token)]
    return f"{attributes.get('id', '')} {' '.join(tokens)}"


def clean_text(value: str) -> str:
    return SPACE.sub(" ", html.unescape(TAG.sub(" ", value or ""))).replace("​", "").strip()


DEBRIS_TAIL = re.compile(
    r"\(?\s*(?:adsbygoogle|googletag)|\(?제공\s*=\s*[^)]*NAVER\s*MEDIA\s*API|"
    r"NAVER\s*MEDIA\s*API|이\s*블로그의\s*저작물|블로그\s*마켓\s*판매자|"
    r"발행인\s*(?:및|/|·)\s*편집인|청소년\s*보호\s*책임자|(?:회장|부회장)\s*[:：]|"
    r"ⓒ|©|All rights reserved|무단\s*전재|재배포\s*금지|"
    r"Market News and Data brought to you by|Data is a real[- ]time snapshot", re.I)
BROADCAST_NOTICE = re.compile(r"\*?\s*아래\s*텍스트는\s*실제\s*방송\s*내용과\s*차이.{0,180}?방송으로\s*확인하시(?:기|기를)\s*바랍니다[.!]?\s*")


def clean_article_text(value: str) -> str:
    """Remove unmistakable inline UI while retaining the factual part of a line."""
    value = clean_text(value)
    value = BROADCAST_NOTICE.sub("", value)
    value = re.sub(r"인용\s*시\s*\[YTN[^\]]*\]\s*명시해주시기\s*바랍니다[.!]?\s*", "", value)
    value = re.sub(r"정확한\s*정보\s*파악을\s*위해\s*전체\s*본문을\s*확인하시길\s*권장합니다[.!]?\s*", "", value)
    value = re.sub(r"\(\s*▶\s*바로가기\s*\)", "", value)
    tail = DEBRIS_TAIL.search(value)
    if tail:
        value = value[:tail.start()].rstrip(" ([*")
    return SPACE.sub(" ", value).strip()


def normalized(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", clean_text(value).lower())


def title_tokens(title: str) -> set[str]:
    return {token.lower() for token in TOKEN.findall(clean_text(title)) if len(token) >= 2 and token.lower() not in STOPWORDS}


def is_sentence_like(text: str) -> bool:
    return bool(SENTENCE_END.search(clean_text(text)))


def split_sentences(text: str) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    parts = [part.strip(" -•\t") for part in SENTENCE_SPLIT.split(text)]
    return [part for part in parts if part]


def strip_dateline(sentence: str) -> str:
    value = clean_text(sentence)
    value = DATELINE.sub("", value, count=1)
    value = re.sub(r"^\s*[가-힣]{2,4}\s*(?:기자|특파원|객원기자|선임기자|인턴기자)\s*=\s*", "", value)
    return value.lstrip("=·-–— ").strip()


# ---------------------------------------------------------------------------
# HTML extraction
# ---------------------------------------------------------------------------
@dataclass
class Block:
    text: str
    tag: str
    container: int
    in_article: bool
    excluded: bool
    caption: bool
    heading: bool
    # Inside a body container and excluded only because an ancestor carries a
    # layout class ("aside_left", "print_wrap"), never by <aside>/<nav>/<footer>.
    layout_only: bool = False
    link_only: bool = False


class ArticleBlockParser(HTMLParser):
    """Collect block-level text with its page context; never executes scripts."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self.meta: dict[str, str] = {}
        self.json_ld: list[object] = []
        # tag, skip, excluded, caption, heading, body_marker (body container class or <article>)
        self._stack: list[tuple[str, bool, bool, bool, bool, bool]] = []
        self._container_stack: list[int] = []
        self._container_tags: list[str] = []
        self._container_count = 0
        self._article_depth = 0
        self._buffer: list[str] = []
        self._buffer_has_nonlink_text = False
        self._json_ld_active = False
        self._json_buffer: list[str] = []
        self._skip_depth = 0
        self._excluded_depth = 0
        self._caption_depth = 0
        self._heading_depth = 0
        self.title_tag_text = ""
        self._in_title = False

    # -- helpers -----------------------------------------------------------
    def _flush(self, tag: str = "") -> None:
        text = clean_text(" ".join(self._buffer))
        self._buffer = []
        link_only = not self._buffer_has_nonlink_text
        self._buffer_has_nonlink_text = False
        if not text:
            return
        # Excluded only by layout classes OUTSIDE the innermost body marker
        # ("div.inner_aside" around donga's section.news_view, "section.news
        # menu" around TV조선's <article>): nothing inside the body is excluded
        # and no <aside>/<nav>/<footer> tag wraps it.
        layout_only = False
        if self._excluded_depth > 0:
            anchor = max((index for index, row in enumerate(self._stack) if row[5]), default=-1)
            layout_only = (anchor >= 0 and not any(row[2] for row in self._stack[anchor + 1:])
                           and not any(row[0] in EXCLUDED_TAGS for row in self._stack[: anchor + 1]))
        self.blocks.append(Block(
            text=text,
            tag=tag or (self._stack[-1][0] if self._stack else ""),
            container=self._container_stack[0] if self._container_stack else 0,
            in_article=self._article_depth > 0,
            excluded=self._excluded_depth > 0,
            caption=self._caption_depth > 0,
            heading=self._heading_depth > 0,
            layout_only=layout_only,
            link_only=link_only,
        ))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attributes = {key.lower(): value or "" for key, value in attrs}
        if tag == "meta":
            key = (attributes.get("property") or attributes.get("name") or attributes.get("itemprop") or "").lower()
            if key in {"og:title", "twitter:title", "og:description", "description", "twitter:description", "article:published_time",
                       "og:site_name", "og:url", "pubdate", "datepublished", "article:modified_time", "og:locale"}:
                self.meta.setdefault(key, clean_text(attributes.get("content", "")))
            return
        if tag == "link" and "canonical" in attributes.get("rel", "").lower():
            self.meta.setdefault("canonical", attributes.get("href", ""))
            return
        if tag == "link" and attributes.get("rel", "").lower() == "amphtml":
            self.meta.setdefault("amphtml", attributes.get("href", ""))
            return
        if tag == "html" and attributes.get("lang"):
            self.meta.setdefault("lang", attributes["lang"])
        if tag == "title":
            self._in_title = True
        if tag == "script" and "ld+json" in attributes.get("type", "").lower():
            self._json_ld_active = True
            self._json_buffer = []
        if tag in VOID_TAGS:
            if tag == "br":
                self._flush()
            return
        marker = marker_text(attributes)
        # schema.org microdata names the body directly (mk.co.kr MAI pages).
        body_itemprop = attributes.get("itemprop", "").strip().lower() == "articlebody"
        skip = tag in SKIP_TAGS or attributes.get("aria-hidden") == "true" and tag not in BLOCK_TAGS
        excluded = tag in EXCLUDED_TAGS or bool(EXCLUDED_ZONE_MARKER.search(marker)) and not CONTAINER_MARKER.search(marker) and not body_itemprop
        caption = tag == "figcaption" or bool(CAPTION_MARKER.search(marker))
        heading = tag in {"h1", "h2", "h3", "h4", "h5", "h6"} or (tag == "header")
        container_tag = tag in {"div", "section", "main", "td"} and (bool(CONTAINER_MARKER.search(marker)) or body_itemprop)
        body_marker = tag == "article" or container_tag
        if tag in BLOCK_TAGS:
            self._flush()
        self._stack.append((tag, skip, excluded, caption, heading, body_marker))
        self._skip_depth += skip
        self._excluded_depth += excluded
        self._caption_depth += caption
        self._heading_depth += heading
        if tag == "article":
            self._article_depth += 1
        if (container_tag or tag == "article" and (CONTAINER_MARKER.search(marker) or body_itemprop)) and not self._container_stack:
            self._container_count += 1
            self._container_stack.append(self._container_count)
            self._container_tags.append(tag)
        elif self._container_stack:
            self._container_tags.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag == "script" and self._json_ld_active:
            self._json_ld_active = False
            raw = "".join(self._json_buffer).strip()
            try:
                self.json_ld.append(json.loads(raw))
            except (TypeError, ValueError):
                pass
        if tag in VOID_TAGS:
            return
        if not any(row[0] == tag for row in self._stack):
            return
        if tag in BLOCK_TAGS:
            self._flush(tag)
        while self._stack:
            open_tag, skip, excluded, caption, heading, _body_marker = self._stack.pop()
            self._skip_depth -= skip
            self._excluded_depth -= excluded
            self._caption_depth -= caption
            self._heading_depth -= heading
            if open_tag == "article":
                self._article_depth = max(0, self._article_depth - 1)
            if self._container_stack and self._container_tags:
                self._container_tags.pop()
                if not self._container_tags:
                    self._flush(open_tag)
                    self._container_stack.pop()
            if open_tag == tag:
                break

    def handle_data(self, data: str) -> None:
        if self._json_ld_active:
            self._json_buffer.append(data)
            return
        if self._in_title:
            self.title_tag_text += data
            return
        if self._skip_depth:
            return
        self._buffer.append(data)
        if data.strip() and not any(row[0] == "a" for row in self._stack):
            self._buffer_has_nonlink_text = True

    def close(self) -> None:
        super().close()
        self._flush()


def _json_ld_bodies(value: object) -> Iterable[tuple[str, dict]]:
    if isinstance(value, dict):
        body = value.get("articleBody")
        if isinstance(body, str) and body.strip():
            yield body, value
        for child in value.values():
            if isinstance(child, (dict, list)):
                yield from _json_ld_bodies(child)
    elif isinstance(value, list):
        for child in value:
            yield from _json_ld_bodies(child)


def _json_ld_meta(values: list[object]) -> dict[str, str]:
    meta: dict[str, str] = {}

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key in ("headline", "datePublished", "dateModified"):
                if isinstance(value.get(key), str) and key not in meta:
                    meta[key] = clean_text(value[key])
            publisher = value.get("publisher")
            if isinstance(publisher, dict) and isinstance(publisher.get("name"), str):
                meta.setdefault("publisher", clean_text(publisher["name"]))
            for child in value.values():
                if isinstance(child, (dict, list)):
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(values)
    return meta


@dataclass
class Extraction:
    paragraphs: list[str] = field(default_factory=list)
    path: str = "none"
    boundary_closed: bool = False
    meta: dict[str, str] = field(default_factory=dict)
    removed: dict[str, int] = field(default_factory=dict)
    removed_samples: dict[str, list[str]] = field(default_factory=dict)

    def note(self, reason: str, text: str) -> None:
        self.removed[reason] = self.removed.get(reason, 0) + 1
        samples = self.removed_samples.setdefault(reason, [])
        if len(samples) < 3:
            samples.append(clean_text(text)[:90])

    @property
    def sentences(self) -> list[str]:
        return [sentence for paragraph in self.paragraphs for sentence in paragraph_sentences(paragraph)]

    @property
    def paragraph_of_sentence(self) -> list[int]:
        return [index for index, paragraph in enumerate(self.paragraphs) for _sentence in paragraph_sentences(paragraph)]

    def diagnostics(self) -> dict[str, object]:
        sentences = self.sentences
        return {
            "extraction_version": EXTRACTION_VERSION,
            "path": self.path,
            "boundary_closed": self.boundary_closed,
            "paragraphs": len(self.paragraphs),
            "sentences": len(sentences),
            "characters": len(" ".join(sentences)),
            "removed": dict(sorted(self.removed.items())),
            "removed_samples": {key: value for key, value in sorted(self.removed_samples.items())},
            "meta_description_excluded": bool(self.meta.get("og:description") or self.meta.get("description")),
            "page_title": self.meta.get("og:title") or self.meta.get("headline") or self.meta.get("title", ""),
            "canonical_url": self.meta.get("canonical") or self.meta.get("og:url", ""),
            "page_published_time": self.meta.get("article:published_time") or self.meta.get("datePublished", ""),
        }


def paragraph_sentences(paragraph: str) -> list[str]:
    rows: list[str] = []
    for sentence in split_sentences(paragraph):
        if len(sentence) < 8:
            continue
        if len(sentence) < 25 and not is_sentence_like(sentence):
            continue
        rows.append(sentence)
    return rows


def _title_like(text: str, titles: list[str]) -> bool:
    value = normalized(re.sub(r"^\s*\[[^\]]{1,40}\]\s*", "", text))
    if not value:
        return False
    for title in titles:
        candidate = normalized(re.sub(r"^\s*\[[^\]]{1,40}\]\s*", "", title))
        if len(candidate) < 6:
            continue
        if value == candidate or (len(value) >= 10 and (value in candidate or candidate in value) and abs(len(value) - len(candidate)) <= 25):
            return True
    return False


def _arc_fusion_paragraphs(page: str) -> list[str]:
    """Text paragraphs of an Arc XP story embedded in the page (chosun.com).

    Only stories marked free (content_code empty/"0"/"free"/"open") are read;
    subscriber content is never extracted from page data.
    """
    start = (page or "").find("Fusion.globalContent")
    if start < 0:
        return []
    equals = page.find("=", start, start + 40)
    if equals < 0:
        return []
    try:
        content, _end = json.JSONDecoder().raw_decode(page[equals + 1:].lstrip())
    except ValueError:
        return []
    if not isinstance(content, dict) or content.get("type") != "story":
        return []
    restrictions = content.get("content_restrictions") if isinstance(content.get("content_restrictions"), dict) else {}
    if str(restrictions.get("content_code") or "").strip().lower() not in {"", "0", "free", "open"}:
        return []
    rows = []
    for element in content.get("content_elements") or []:
        if isinstance(element, dict) and element.get("type") == "text":
            text = clean_text(str(element.get("content") or ""))
            if text:
                rows.append(text)
    return rows


PAGE_DATA_PATHS = {"arc_fusion_content", "embedded_content_array", "next_flight_article_html"}


def unescape_fully(value: str, rounds: int = 8) -> str:
    """Undo repeated HTML escaping ("&amp;lt;p&amp;gt;" in NDTV's articleBody)."""
    for _ in range(rounds):
        decoded = html.unescape(value)
        if decoded == value:
            break
        value = decoded
    return value


def _next_flight_text(page: str) -> str:
    """Strings a Next.js page pushes into self.__next_f (its server payload)."""
    decoder = json.JSONDecoder()
    marker = "self.__next_f.push("
    parts: list[str] = []
    start = 0
    while True:
        index = page.find(marker, start)
        if index < 0:
            break
        try:
            value, end = decoder.raw_decode(page, index + len(marker))
        except ValueError:
            start = index + len(marker)
            continue
        if isinstance(value, list) and len(value) >= 2 and isinstance(value[1], str):
            parts.append(value[1])
        start = end
    return "".join(parts)


def _next_flight_article_paragraphs(page: str) -> list[str]:
    """Article HTML in a Next.js page's server payload (JTBC "articleContent").

    The browser renders the article from this payload; it is the same public
    page.  Paywall pages are refused by the caller (fetch_article).
    """
    if "self.__next_f" not in (page or ""):
        return []
    flight = _next_flight_text(page)
    for key in ('"articleContent":', '"articleInnerTextContent":'):
        start = flight.find(key)
        if start < 0:
            continue
        try:
            body, _end = json.JSONDecoder().raw_decode(flight[start + len(key):].lstrip())
        except ValueError:
            continue
        if isinstance(body, str) and re.fullmatch(r"\$[0-9a-f]+", body):
            body = _next_flight_row_text(flight, body[1:])  # "$82" → text row "82:T<hex length>,…"
        if not isinstance(body, str) or not clean_text(body):
            continue
        if "<" not in body:
            rows = [clean_text(line) for line in body.split("\n") if clean_text(line)]
        else:
            parser = ArticleBlockParser()
            try:
                parser.feed(body)
                parser.close()
            except Exception:
                pass
            rows = [block.text for block in parser.blocks if not block.excluded and not block.caption and clean_text(block.text)]
        if len(rows) >= 2:
            return rows
    return []


def _next_flight_row_text(flight: str, row_id: str) -> str:
    """Text row "<id>:T<hex byte length>," of a Next.js flight payload."""
    match = re.search(r"(?:^|\n)" + re.escape(row_id) + r":T([0-9a-f]+),", flight)
    if not match:
        return ""
    encoded = flight.encode("utf-8")
    start = len(flight[: match.end()].encode("utf-8"))
    return encoded[start: start + int(match.group(1), 16)].decode("utf-8", "ignore")


def _embedded_content_paragraphs(page: str) -> list[str]:
    """Text items of a page-data content array (news1.kr: "contentArrange").

    The article is rendered from this array in the browser; it is the same
    public page.  Paywall pages are refused by the caller (fetch_article).
    """
    key = '"contentArrange":'
    start = (page or "").find(key)
    if start < 0:
        return []
    try:
        rows, _end = json.JSONDecoder().raw_decode(page[start + len(key):].lstrip())
    except ValueError:
        return []
    if not isinstance(rows, list):
        return []
    texts = [clean_text(str(row.get("content") or "")) for row in rows if isinstance(row, dict) and row.get("type") == "text"]
    return [text for text in texts if text]


def extract_article(page: str, title: str = "", _dom_only: bool = False) -> Extraction:
    """Choose ONE body source, then clean it with explicit, auditable reasons."""
    result = _extract_article_once(page, title, _dom_only)
    # A JSON-LD/Arc teaser ("articleBody" of one sentence) or a structured body
    # that cleans down to nothing must not hide a complete DOM body.
    if not _dom_only and result.path in {"json_ld_article_body", *PAGE_DATA_PATHS} and len(result.sentences) < FULL_TEXT_MIN_SENTENCES:
        alternative = _extract_article_once(page, title, True)
        if len(alternative.sentences) > len(result.sentences):
            alternative.note("structured_body_too_short", f"{result.path} {len(result.sentences)}문장 → 페이지 본문 사용")
            result = alternative
    # A matched "container" can be a disclaimer box or a related-news teaser
    # ("view_article_disclaimer" on tokenpost AMP, "latest-news-text" on
    # fibre2fashion) while the real paragraphs sit outside any marked
    # container.  Only then are the <article> and plain-paragraph readings
    # tried; identity checks still decide whether the text is the article.
    # Headline teasers ("'상간 소송' 박지윤, 뜻밖의 고백 …") pass the length
    # filter, so the comparison counts only lines that end like sentences.
    def complete(row: Extraction) -> int:
        return sum(1 for sentence in row.sentences if is_sentence_like(sentence) and not TRUNCATED_END.search(sentence))

    if len(result.sentences) < FULL_TEXT_MIN_SENTENCES and result.path in {"container", "article_tag"}:
        candidates = [_extract_article_once(page, title, True, strategy)
                      for strategy in (("article", "paragraphs") if result.path == "container" else ("paragraphs",))]
        better = max(candidates, key=complete)
        if complete(better) >= FULL_TEXT_MIN_SENTENCES and complete(better) > complete(result):
            better.note("weak_container_fallback", f"{result.path} {len(result.sentences)}문장 → {better.path}")
            result = better
    # A broadcast replay page lists its segment titles ("코스피 하락세 원인은?")
    # where an article would have prose; such a page has no article body.
    sentences = result.sentences
    questions = sum(1 for sentence in sentences if re.search(r"\?[”\"’')\]]*\s*$", sentence))
    answers = sum(1 for sentence in sentences if is_sentence_like(sentence)
                  and not re.search(r"\?[”\"’')\]]*\s*$", sentence))
    if len(sentences) >= FULL_TEXT_MIN_SENTENCES and questions >= 0.6 * len(sentences) and not answers:
        result.note("question_list", f"{questions}/{len(sentences)}문장이 질문(방송 목차)")
        result.paragraphs = []
    return result


def _extract_article_once(page: str, title: str, dom_only: bool, strategy: str = "") -> Extraction:
    parser = ArticleBlockParser()
    try:
        parser.feed(page or "")
        parser.close()
    except Exception:  # malformed markup: keep what was parsed
        pass
    result = Extraction(meta=dict(parser.meta))
    result.meta.update({key: value for key, value in _json_ld_meta(parser.json_ld).items() if value})
    if parser.title_tag_text:
        result.meta.setdefault("title", clean_text(parser.title_tag_text))
    titles = [value for value in (title, result.meta.get("og:title", ""), result.meta.get("headline", ""), result.meta.get("twitter:title", "")) if value]

    json_bodies = [] if dom_only else sorted((body for value in parser.json_ld for body, _node in _json_ld_bodies(value)), key=len, reverse=True)
    arc_paragraphs = [] if dom_only or json_bodies else _arc_fusion_paragraphs(page)
    embedded_paragraphs = [] if dom_only or json_bodies or arc_paragraphs else _embedded_content_paragraphs(page)
    flight_paragraphs = [] if dom_only or json_bodies or arc_paragraphs or embedded_paragraphs else _next_flight_article_paragraphs(page)
    blocks: list[Block] = []
    if json_bodies and len(clean_text(json_bodies[0])) >= 150:
        raw_lines = [clean_text(line) for line in re.split(r"\n+|<br\s*/?>|</p>|<p(?:\s[^>]*)?>", unescape_fully(json_bodies[0]), flags=re.I) if clean_text(line)]
        blocks = [Block(line, "p", 0, True, False, False, False) for line in raw_lines]
        result.path = "json_ld_article_body"
        result.boundary_closed = True
        if any(block.container for block in parser.blocks):
            result.note("other_paths_ignored", "DOM 본문 컨테이너(JSON-LD articleBody 우선)")
    elif len(arc_paragraphs) >= 2 and len(" ".join(arc_paragraphs)) >= 150:
        blocks = [Block(line, "p", 0, True, False, False, False) for line in arc_paragraphs]
        result.path = "arc_fusion_content"
        result.boundary_closed = True
    elif len(embedded_paragraphs) >= 2 and len(" ".join(embedded_paragraphs)) >= 150:
        blocks = [Block(line, "p", 0, True, False, False, False) for line in embedded_paragraphs]
        result.path = "embedded_content_array"
        result.boundary_closed = True
    elif len(flight_paragraphs) >= 2 and len(" ".join(flight_paragraphs)) >= 150:
        blocks = [Block(line, "p", 0, True, False, False, False) for line in flight_paragraphs]
        result.path = "next_flight_article_html"
        result.boundary_closed = True
    else:
        by_container: dict[int, list[Block]] = {}
        for block in parser.blocks:
            if block.container:
                by_container.setdefault(block.container, []).append(block)
        best = max(by_container.values(), key=lambda rows: sum(len(row.text) for row in rows if not row.excluded and not row.caption), default=[])
        # A recognised body container is a structural signal; its length is
        # judged later by body_status(), not here.
        article_blocks = [block for block in parser.blocks if block.in_article]
        article_chars = sum(len(row.text) for row in article_blocks if not row.excluded)
        # A body container nested in a layout column whose class looks like a
        # side zone ("section.aside_left" on edaily, "print_wrap" on
        # economist.co.kr): ignore only those ancestor marks, and only when no
        # unexcluded container exists.
        rescued = max(by_container.values(), key=lambda rows: sum(len(row.text) for row in rows if row.layout_only and not row.caption), default=[])
        rescued_chars = sum(len(row.text) for row in rescued if row.layout_only and not row.caption)
        if strategy == "paragraphs":
            blocks = [block for block in parser.blocks if block.tag in {"p", "blockquote"}]
            result.path = "paragraph_fallback" if blocks else "none"
        elif strategy == "article" and article_chars >= 40:
            blocks = article_blocks
            result.path = "article_tag"
            result.boundary_closed = True
        elif sum(len(row.text) for row in best if not row.excluded) >= 40:
            blocks = best
            result.path = "container"
            result.boundary_closed = True
        elif rescued_chars >= 200 and rescued_chars > article_chars:
            blocks = [replace(row, excluded=False) if row.layout_only else row for row in rescued]
            result.path = "container"
            result.boundary_closed = True
            result.note("layout_zone_ignored", "본문 컨테이너를 감싼 레이아웃 영역 표식(aside/print 등) 무시")
        else:
            article_rescued = sum(len(row.text) for row in article_blocks if row.layout_only and not row.caption)
            if article_chars >= 40:
                blocks = article_blocks
                result.path = "article_tag"
                result.boundary_closed = True
            elif article_rescued >= 200:
                blocks = [replace(row, excluded=False) if row.layout_only else row for row in article_blocks]
                result.path = "article_tag"
                result.boundary_closed = True
                result.note("layout_zone_ignored", "<article>를 감싼 레이아웃 영역 표식(menu/aside 등) 무시")
            else:
                blocks = [block for block in parser.blocks if block.tag in {"p", "blockquote"}]
                result.path = "paragraph_fallback" if blocks else "none"

    # Leading page chrome before a title line is only removed in the
    # fallback path, and only when that line is a standalone headline (not a
    # body sentence that happens to resemble the title).
    if result.path == "paragraph_fallback":
        for index, block in enumerate(blocks[:20]):
            if _title_like(block.text, titles) and not is_sentence_like(block.text):
                for dropped in blocks[:index]:
                    result.note("before_title", dropped.text)
                blocks = blocks[index:]
                break

    paragraphs: list[str] = []
    seen: set[str] = set()
    body_started = False
    body_sentences = 0
    for block in blocks:
        text = clean_text(block.text)
        if not text:
            continue
        if block.excluded and body_sentences >= 2 and HASHTAG_LINE.search(text) and not is_sentence_like(text):
            # A tag list (even in its own tag box) ends the article; teasers
            # for other stories follow it on donga.com.
            result.note("boundary", text)
            result.boundary_closed = True
            for dropped in blocks[blocks.index(block) + 1:]:
                if clean_text(dropped.text):
                    result.note("after_boundary", dropped.text)
            break
        if block.excluded:
            result.note("excluded_zone", text)
            continue
        if block.caption or CAPTION_LINE.search(text) and len(text) <= 160 and not is_sentence_like(text.split("(")[0]):
            result.note("caption", text)
            continue
        cleaned_text = clean_article_text(text)
        if cleaned_text != text:
            result.note("inline_debris", text[len(cleaned_text):])
            text = cleaned_text
        if not text:
            continue
        if CODE_LINE.search(text) and (len(re.findall(r"[가-힣]", text)) < len(text) * 0.3):
            result.note("code", text)
            continue
        if _title_like(text, titles):
            result.note("title", text)
            continue
        if block.heading and (not body_started or not is_sentence_like(text)):
            result.note("heading", text)
            continue
        if block.link_only and (not is_sentence_like(text) or TRUNCATED_END.search(text) or text.endswith("?")):
            result.note("navigation_link", text)
            continue
        if re.match(r"^(?:크롤링\s*데이터\s*기준\s*확인되는\s*사실만|절대\s*크롤링\s*데이터\s*라는걸)", text):
            result.note("editorial_instruction", text)
            continue
        if re.search(r"차트\s*보기\s*바로가기|해당\s*내용은\s*정보\s*제공의\s*목적으로만\s*해석되어야", text):
            result.note("ui", text)
            continue
        # "취재기자 연결해 … 알아보겠습니다. 김웅래 기자!" is an anchor's cue in a
        # broadcast transcript, not the closing byline.
        byline_end = BYLINE_LINE.search(text) and len(text) <= 80 and not BROADCAST_CUE.search(text)
        if body_sentences >= 2 and (COPYRIGHT_LINE.search(text) and len(text) <= 160 or byline_end
                                    or AI_SUMMARY_START.match(text) or RELATED_LABEL.fullmatch(text)
                                    or HASHTAG_LINE.search(text) and not is_sentence_like(text)):
            result.note("boundary", text)
            result.boundary_closed = True
            index = blocks.index(block)
            for dropped in blocks[index + 1:]:
                if clean_text(dropped.text):
                    result.note("after_boundary", dropped.text)
            break
        if COPYRIGHT_LINE.search(text) and len(text) <= 160 or BYLINE_LINE.search(text) and len(text) <= 80:
            result.note("byline_or_copyright", text)
            continue
        if STRONG_UI.search(text) and (len(text) <= 140 or not is_sentence_like(text)):
            result.note("ui", text)
            continue
        if len(text) <= 40 and SHORT_UI_WORDS.search(text) and not is_sentence_like(text):
            result.note("ui", text)
            continue
        if HASHTAG_LINE.search(text):
            result.note("hashtag", text)
            continue
        if ATTACHMENT_LINE.search(text) and (len(text) <= 120 or re.search(r"바로\s*보기|바로\s*듣기|다운로드|첨부", text)):
            result.note("attachment", text)  # "보도자료.hwpx 바로보기", "스티커 시안 132404.png"
            continue
        if len(re.findall(r"[가-힣A-Za-z]", text)) < 4:
            result.note("non_text", text)  # bare dates, page numbers, separators
            continue
        if not body_started and not is_sentence_like(text) and len(text) <= 120:
            # Standalone subtitle/kicker lines precede the first real sentence.
            result.note("subtitle", text)
            continue
        key = normalized(text)
        if key in seen:
            result.note("duplicate", text)
            continue
        seen.add(key)
        sentences = paragraph_sentences(text)
        dropped_fragments = len(split_sentences(text)) - len(sentences)
        if dropped_fragments > 0:
            result.removed["fragment"] = result.removed.get("fragment", 0) + dropped_fragments
        if not sentences:
            continue
        kept: list[str] = []
        for sentence in sentences:
            if STRONG_UI.search(sentence) and len(sentence) <= 140:
                result.note("ui", sentence)
                continue
            kept.append(sentence)
        if not kept:
            continue
        body_started = True
        body_sentences += len(kept)
        paragraphs.append(" ".join(kept))
    result.paragraphs = paragraphs
    if result.path == "paragraph_fallback" and result.removed.get("boundary"):
        result.boundary_closed = True
    return result


# ---------------------------------------------------------------------------
# Identity / body status
# ---------------------------------------------------------------------------
YEAR_ONLY = re.compile(r"^(?:19|20)\d{2}$")


def _number_keys(text: str) -> set[str]:
    keys = set()
    for match in re.finditer(r"\d[\d,]*(?:\.\d+)?", clean_text(text)):
        digits = match.group(0).replace(",", "")
        if YEAR_ONLY.match(digits) or len(digits) == 0:
            continue
        keys.add(digits.rstrip("0").rstrip(".") if "." in digits else digits)
    return keys


def token_overlap(title: str, text: str) -> tuple[int, int]:
    wanted = title_tokens(title)
    found = {token.lower() for token in TOKEN.findall(text) if len(token) >= 2}
    hits = {token for token in wanted if any(body == token or body.startswith(token) or (len(body) >= 3 and token.startswith(body)) for body in found)}
    return len(hits), len(wanted)


def lexical_similarity(left: str, right: str) -> float:
    a, b = title_tokens(left), title_tokens(right)
    if not a or not b:
        return 0.0
    hits = sum(1 for token in a if any(other == token or other.startswith(token) or token.startswith(other) for other in b))
    return hits / max(len(a), len(b))


def verify_identity(title: str, sentences: list[str], meta: dict[str, str] | None = None, *, expected_date: str = "", strict: bool = False) -> dict[str, object]:
    """Check that a body belongs to the headline (topic, key numbers, date)."""
    meta = meta or {}
    reasons: list[str] = []
    lead = " ".join(sentences[:15])
    hits, wanted = token_overlap(title, lead)
    required = 1 if wanted <= 2 else 2
    page_title = meta.get("og:title") or meta.get("headline") or ""
    if page_title and normalized(page_title) == normalized(meta.get("og:site_name", "")):
        page_title = ""  # a bare site name ("한민족센터") says nothing about the story
    page_title_similarity = lexical_similarity(title, page_title) if page_title else None
    topic_ok = hits >= required or (page_title_similarity is not None and page_title_similarity >= 0.6 and hits >= 1)
    if not topic_ok:
        reasons.append(f"제목 핵심어 일치 부족({hits}/{wanted})")
    title_numbers = _number_keys(title)
    body_numbers = _number_keys(" ".join(sentences) + " " + page_title)
    numbers_ok = not title_numbers or bool(title_numbers & body_numbers)
    if not numbers_ok:
        reasons.append("제목의 핵심 수치가 본문에 없음")
    date_ok = True
    published = meta.get("article:published_time") or meta.get("datePublished") or ""
    if expected_date and published[:10] and re.match(r"\d{4}-\d{2}-\d{2}", published[:10]):
        try:
            gap = abs((date.fromisoformat(published[:10]) - date.fromisoformat(expected_date[:10])).days)
            date_ok = gap <= 2
            if not date_ok:
                reasons.append(f"발행일 불일치({published[:10]} vs {expected_date[:10]})")
        except ValueError:
            pass
    page_title_ok = page_title_similarity is None or page_title_similarity >= (0.5 if strict else 0.2)
    if not page_title_ok:
        reasons.append("페이지 제목과 기사 제목 불일치")
    ok = topic_ok and numbers_ok and date_ok and page_title_ok
    return {
        "ok": ok,
        "title_token_hits": hits,
        "title_token_total": wanted,
        "page_title_similarity": None if page_title_similarity is None else round(page_title_similarity, 2),
        "title_numbers_found": numbers_ok,
        "date_consistent": date_ok,
        "reasons": reasons,
    }


def body_status(sentences: list[str], *, boundary_closed: bool, path: str, identity_ok: bool) -> tuple[str, str]:
    """Return (article_body_status, body_completeness) under BODY_CONTRACT."""
    chars = len(" ".join(sentences))
    if not identity_ok or not sentences:
        return "unavailable", "none"
    dedicated = path in {"json_ld_article_body", *PAGE_DATA_PATHS, "container", "article_tag"} or boundary_closed
    if len(sentences) >= FULL_TEXT_MIN_SENTENCES and chars >= FULL_TEXT_MIN_CHARS and dedicated:
        return "full_text", "complete" if boundary_closed else "complete_region"
    if len(sentences) >= EXCERPT_MIN_SENTENCES and chars >= EXCERPT_MIN_CHARS:
        if dedicated:
            return "verified_excerpt", "complete_short"
        return "verified_excerpt", "boundary_unconfirmed"
    return "unavailable", "too_short"


# ---------------------------------------------------------------------------
# Actors (who)
# ---------------------------------------------------------------------------
PARTICLES = (
    "에서는", "에서도", "으로부터", "에게서", "으로서", "으로써", "에서", "에게", "까지", "부터", "조차", "마저", "처럼", "보다",
    "으로", "이라는", "라는", "이며", "이고", "와의", "과의", "에는", "에도", "로는", "들은", "들이", "들의", "들도",
    "은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과", "도", "만", "들",
)
SUBJECT_PARTICLES = ("은", "는", "이", "가", "도", "에서는", "측은", "측이", "들은", "들이", "들도")
ORG_SUFFIXES = (
    "금융지주", "금융그룹", "지주", "은행", "증권", "자산운용", "운용", "리츠", "그룹", "전자", "공사", "공단", "협회", "위원회", "위원단",
    "거래소", "연구원", "연구소", "재단", "정부", "당국", "법원", "재판부", "검찰", "국회", "의회", "기업", "홀딩스", "캐피탈", "카드",
    "생명", "손해보험", "보험", "건설", "중공업", "제약", "바이오", "에너지", "화학", "통신", "텔레콤", "신협", "새마을금고", "조합",
    "연합회", "협의회", "청", "처", "통계국", "중앙은행", "준비제도", "연준", "시청", "도청", "구청", "군청",
    "대학교", "대학", "병원", "항공", "해운", "자동차", "모빌리티", "반도체", "디스플레이", "솔루션", "시스템", "테크", "랩스",
    "컴퍼니", "파트너스", "인베스트먼트", "벤처스", "캐피털", "증권사", "은행권", "카드사", "보험사", "운용사", "건설사", "제조사",
    "엔터테인먼트", "엔터", "물산", "상사", "로보틱스", "모터스", "첨단소재", "소재",
    "Inc", "Corp", "Group", "Bank", "Capital", "Partners", "Holdings", "Securities", "Ministry", "Committee", "Reserve",
)
MINISTRIES = (
    "기획재정부", "재정경제부", "국토교통부", "산업통상자원부", "산업통상부", "법무부", "행정안전부", "고용노동부", "보건복지부", "교육부",
    "국방부", "외교부", "통일부", "환경부", "기후에너지환경부", "여성가족부", "문화체육관광부", "농림축산식품부", "해양수산부",
    "중소벤처기업부", "과학기술정보통신부", "재무부", "상무부", "노동부", "국무부", "에너지부", "무역대표부", "금융위원회", "금융감독원",
)
KNOWN_ENTITIES = (
    "연준", "미 연준", "연방준비제도", "한은", "한국은행", "한국거래소", "금감원", "금융위", "기재부", "국토부", "공정위", "국세청",
    "백악관", "트럼프 대통령", "LH", "SH", "IMF", "OPEC", "OPEC+", "ECB", "BOJ", "Fed", "SEC", "NASA", "WTO", "OECD", "PBOC",
    "인민은행", "일본은행", "유럽중앙은행", "블랙록", "엔비디아", "애플", "테슬라", "마이크로소프트", "구글", "아마존", "메타",
)
PERSON_TITLES = (
    "대통령", "부총리", "장관", "차관", "총재", "부총재", "의장", "위원장", "위원", "대표이사", "대표", "회장", "부회장", "사장", "부사장",
    "본부장", "전무", "상무", "이사장", "이사", "교수", "연구원", "연구위원", "애널리스트", "이코노미스트", "센터장", "팀장", "국장", "청장",
    "원장", "행장", "부행장", "시장", "도지사", "지사", "구청장", "대변인", "최고경영자", "CEO", "CFO", "CIO", "전략가", "수석",
)
NON_ACTOR_WORDS = {
    "이날", "한편", "이번", "현재", "시장", "업계", "관계자", "기사", "보도", "경쟁", "가격", "금리", "물가", "환율", "주가", "지수", "전망",
    "가능성", "증가", "감소", "상승", "하락", "결과", "상황", "흐름", "추세", "경기", "수요", "공급", "매출", "이익", "실적", "규모", "비중",
    "투자", "지분", "지분증권", "자산", "부채", "부담", "사업", "계획", "정책", "제도", "규제", "한도", "출자", "매각", "배당", "특별배당",
    "고용", "실업률", "신규 고용", "거래", "거래량", "분양", "청약", "아파트", "주택", "전세", "월세", "올해", "내년", "지난해", "최근",
    "이후", "당시", "이어", "다만", "또한", "특히", "반면", "이에", "그러나", "하지만", "따라서", "결국", "이로써", "앞서", "또", "이와",
    "주유소", "컨소시엄", "발행법인", "정부안", "법안", "시행령", "방안", "대출", "담보대출", "차입금", "만기", "재원", "수익", "비용",
    "AI", "IT", "ETF", "GDP", "PCE", "CPI", "PPI", "EPS", "BTC", "ETH", "XRP", "WTI", "LTV", "DSR", "DTI", "PF", "IPO", "RSS", "KRW",
    "USD", "VIX", "MD", "IP", "SDV", "ADR", "PER", "PBR", "ROE", "M&A", "bp", "YoY", "QoQ", "TV", "PC", "OS", "API", "HBM", "D램",
    "은행", "증권", "정부", "당국", "기업", "회사", "업체", "투자자", "전문가", "전문가들", "애널리스트", "소비자", "주주", "국민", "시민",
}
LOCAL_GOVERNMENT = re.compile(
    r"(?:서울|부산|대구|인천|광주|대전|울산|세종|제주)(?:특별시|광역시|특별자치시|특별자치도|시)?|"
    r"(?:경기|강원|충청북|충청남|충북|충남|전라북|전라남|전북|전남|경상북|경상남|경북|경남)(?:도|특별자치도)|"
    r"(?:수원|성남|고양|용인|화성|창원|청주|천안|전주|포항|김해|평택|안산|안양|남양주|파주|시흥|김포|하남|광명|의정부|구리|오산|군포|"
    r"이천|양주|여주|광주|원주|춘천|강릉|아산|세종|구미|경주|진주|양산|거제|목포|여수|순천|익산|군산|제주|서귀포|부천|안동|충주|제천)시|"
    r"(?:강남|서초|송파|강동|마포|용산|성동|광진|동대문|중랑|성북|강북|도봉|노원|은평|서대문|종로|중|영등포|동작|관악|금천|구로|양천|강서)구"
)
FINANCIAL_GROUP = re.compile(r"(?:KB|신한|하나|우리|NH농협|농협|BNK|DGB|iM|JB|메리츠|한국투자|미래에셋|삼성|한화|교보|DB|IBK|KDB)(?:금융|금융지주|금융그룹)")
ADMIN_FALSE_POSITIVE = re.compile(
    r"(?:연도|년도|정도|제도|한도|속도|용도|의도|주도|강도|빈도|각도|태도|온도|밀도|농도|시도|보도|인도|지도|가구|인구|요구|연구|"
    r"선거구|지역구|당시|동시|즉시|상시|수시|감시|무시|표시|제시|지시|개시|게시|다시|역시|혹시|우군|아군|적군)$"
)
WHO_QUOTE_VERBS = re.compile(r"(?:말했|밝혔|설명했|덧붙였|강조했|전했|언급했|지적했|주장했|평가했|분석했|내다봤|예상했|전망했|우려했|답했|발표했|공시했)")


def strip_particle(token: str) -> tuple[str, str]:
    for particle in PARTICLES:
        if token.endswith(particle) and len(token) > len(particle) + 1:
            return token[: -len(particle)], particle
    return token, ""


def _is_entity(stem: str, title: str = "") -> bool:
    value = re.sub(r"\([^)]{1,20}\)$", "", stem).strip(" ,.'\"‘’“”")
    if not value or value in NON_ACTOR_WORDS or len(value) < 2:
        return False
    if re.fullmatch(r"\d+(?:년|월|일)부", value) or re.fullmatch(r"(?:S&P\s*500|CAC\s*40|IBEX\s*35|NASDAQ\s*100)", value, re.I):
        return False  # dates and indices are not organisations; G7/MI5/GS25 may be
    if re.fullmatch(r"[\d,.%~\-]+(?:[가-힣]{0,3})", value):
        return False  # numbers, dates ("2023년", "9월", "26일"), counts
    if re.search(r"\d{1,4}(?:년|월|일|분기|개월|주)$", value):
        return False
    if re.match(r"\d[\d.,]*(?:[만억조%㎡…]|\s|$)", value):
        return False  # "84.93㎡", "1만1521가구", "3.85%…인터넷은행" are figures
    if value in KNOWN_ENTITIES or any(value.endswith(ministry) for ministry in MINISTRIES):
        return True
    if FINANCIAL_GROUP.fullmatch(value):
        return True
    if "·" in value:
        parts = [part for part in value.split("·") if part]
        # "KB·신한·하나금융" – a list of named groups sharing one suffix.
        if len(parts) >= 2 and (FINANCIAL_GROUP.fullmatch(parts[-1]) or _is_entity(parts[-1], title)):
            return True
    if re.fullmatch(r"[A-Z][A-Z0-9&+.]{1,7}", value):
        return value not in NON_ACTOR_WORDS
    if re.fullmatch(r"[A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,4}", value) and value.split()[-1].rstrip(".") in {"Inc", "Corp", "Group", "Bank", "Capital", "Partners", "Holdings", "Securities", "Reserve", "Ministry", "Committee", "Fund", "Management"}:
        return True
    for suffix in ORG_SUFFIXES:
        if value.endswith(suffix) and len(value) > len(suffix):
            head = value[: -len(suffix)].strip(" ·")
            # A one-syllable head is a common noun ("걸그룹", "적금리"), not a name.
            if len(head) >= 2 and not re.fullmatch(r"[\d\s]+(?:대|개)?", head) and head not in NON_ACTOR_WORDS:
                return True
    # Local governments only from a known place list ("용인시", "경기도");
    # a generic 시/도/군/구 suffix also matches 기여도·전도도·속도·당시.
    if LOCAL_GOVERNMENT.fullmatch(value):
        return True
    # Korean headlines put the actor first: "SK리츠, …", "한화갤러리아, …".
    if title and normalized(value) in headline_subjects(title):
        return True
    return False


def headline_subjects(title: str) -> set[str]:
    head = re.sub(r"^\s*\[[^\]]{1,40}\]\s*", "", clean_text(title))
    match = re.match(r"^([^,，…·\"“”']{2,30}?)\s*(?:[,，]|[\"“”'‘](?=\S))", head)
    if not match:
        return set()
    words = [strip_particle(word)[0] for word in match.group(1).split()]
    picks = {words[0], words[-1]} if words else set()
    return {normalized(word) for word in picks if len(normalized(word)) >= 2 and word not in NON_ACTOR_WORDS}


PERSON_PATTERN = re.compile(
    r"(?P<name>[가-힣]{2,4})\s+(?P<org>(?:[가-힣A-Za-z0-9·&]+\s+){0,2}?)(?P<title>[가-힣A-Za-z]{0,8}?(?:" + "|".join(sorted(PERSON_TITLES, key=len, reverse=True)) + r"))(?:은|는|이|가|도|측은)?(?=[\s,.]|$)"
)
OFFICIAL_PATTERN = re.compile(r"(?P<who>(?:[가-힣A-Za-z0-9·&]+\s+){0,2}[가-힣A-Za-z0-9·&]+)\s+(?:관계자|측|대변인)(?:는|은|도|가|이)\s")
NON_PERSON_WORDS = {
    "미국", "한국", "중국", "일본", "영국", "독일", "프랑스", "정부", "회사", "업계", "시장", "담당", "관련", "해당", "전체", "금융", "증권", "은행",
    "국내", "해외", "글로벌", "현지", "당시", "현재", "전직", "신임", "초대", "공동", "대표", "회장", "사장", "부사장", "본부장", "관계자",
    "이런", "그런", "저런", "이번", "이날", "이후", "이어", "이에", "이와", "이를", "이는", "가운데", "한편", "또한", "특히", "다만", "반면",
    "전문", "주요", "다른", "또다른", "여러", "각국", "각사", "일부", "모든", "많은", "최근", "당초", "향후", "앞서", "같은", "해당사",
}
NON_NAME_PREFIX = {"이날", "한편", "다만", "또한", "특히", "반면", "이어", "현재", "최근", "이후", "당시", "올해", "지난해", "내년", "이번", "지난"}


def extract_actors(sentences: list[str], title: str = "", limit: int = 6) -> list[dict[str, str]]:
    """Return actors with evidence.  Only subjects/speakers with an entity signal qualify."""
    actors: list[dict[str, str]] = []
    names: set[str] = set()

    def add(name: str, sentence: str, role: str) -> None:
        name = SPACE.sub(" ", name).strip(" ,.'\"‘’“”")
        key = normalized(name)
        if not name or key in names or len(actors) >= limit:
            return
        # Prefer the fuller phrase ("백민주 SK리츠운용 투자본부장" over "SK리츠운용").
        for row in actors:
            if key and key in normalized(row["name"]) and role != "speaker":
                return
            # Same person mentioned again with a shorter title ("이민혁 이코노미스트").
            if role == "speaker" and row["role"] == "speaker" and " " in name and name.split()[0] == row["name"].split()[0] and len(name.split()[0]) >= 2 and not name.endswith("관계자"):
                return
        names.add(key)
        actors.append({"name": name, "role": role, "evidence": sentence[:240]})

    for raw in sentences:
        sentence = strip_dateline(raw)
        for match in PERSON_PATTERN.finditer(sentence):
            name = match.group("name")
            if name in NON_NAME_PREFIX or name in NON_ACTOR_WORDS or name in NON_PERSON_WORDS:
                continue
            if name[-1] == "의" or (len(name) >= 3 and name[-1] in "이가은는을를에도로와과"):
                continue  # "7명의 위원", "관계인이 …" are phrases, not names
            if match.start() > 0 and re.match(r"[\d\w]", sentence[match.start() - 1]):
                continue  # the "name" is the tail of a longer word or number
            org_words = match.group("org").split()
            if any(re.match(r"\d", word) for word in org_words):
                continue  # "좁힌 5만 달러 시장", "힘입어 2026년 3분기 시장": a market, not a mayor
            if any(word in NON_PERSON_WORDS or re.search(r"(?:은|는|을|를|의|에|에서|에는|와|과|으로|하는|되는|된|한|할|던|면|며|고|데)$", word) for word in org_words):
                continue
            tail = sentence[match.end():match.end() + 220]
            if match.group(0).rstrip().endswith(("은", "는", "이", "가", "도")) or WHO_QUOTE_VERBS.search(tail[:200]):
                add(f"{name} {match.group('org')}{match.group('title')}", sentence, "speaker")
        for match in OFFICIAL_PATTERN.finditer(sentence):
            who = match.group("who").strip()
            first = who.split()[0]
            if first in NON_NAME_PREFIX:
                who = " ".join(who.split()[1:])
            if who and (_is_entity(who.split()[-1], title) or re.search(r"\d+대\s|[가-힣]+(?:은행|금융|증권|지주|운용|정부|당국|부)$", who)):
                add(f"{who} 관계자", sentence, "speaker")
        # Grammatical subject: skip adverbials ("업계에서는", "26일", "금융권에
        # 따르면") and take the first 은/는/이/가 phrase.  If that subject is not
        # an entity ("가격이 올랐다") stop instead of grabbing a later object.
        tokens = sentence.split()
        for position, token in enumerate(tokens[:14]):
            stem, particle = strip_particle(token.strip(",;:'\"‘’“”"))
            if particle not in {"은", "는", "이", "가", "도", "들은", "들이", "들도"}:
                continue
            candidate = re.sub(r"\(([A-Za-z]{2,10})\)$", "", stem)
            # "광진구(2.29%)는", "엔비디아(+2.78%)는", "메타플래닛(3350)은": the
            # parenthesis is a figure or ticker code, not part of the name.
            figure_paren = re.search(r"\([^()]*\d[^()]*\)$", candidate)
            if figure_paren:
                candidate = candidate[: figure_paren.start()]
                if LOCAL_GOVERNMENT.fullmatch(candidate):
                    break  # a district in a price table is a statistic row, not an actor
            if not candidate.split():
                break
            if position >= 1 and tokens[position - 1] in {"미", "美", "미국", "중국", "일본", "영국", "독일", "EU"} and _is_entity(candidate, title):
                candidate = f"{tokens[position - 1]} {candidate}"
            if _is_entity(candidate.split()[-1], title) or _is_entity(candidate, title):
                add(candidate, sentence, "subject")
            break
        if len(actors) >= limit:
            break
    return actors


# ---------------------------------------------------------------------------
# Time facts (when)
# ---------------------------------------------------------------------------
DATE_PATTERN = re.compile(
    r"(?P<prefix>지난|오는|올해|내년|지난해|작년|이달|다음 달|지난달)?\s*"
    r"(?:(?P<year>(?:19|20)\d{2})년\s*)?(?:(?P<month>1[0-2]|0?[1-9])월\s*)?(?:(?P<day>3[01]|[12]\d|0?[1-9])일)?"
    r"(?P<local>\s*\(현지시간\))?"
)
PERIOD_PATTERN = re.compile(r"(?:올해|내년|지난해|작년|올\s|올들어|상반기|하반기|[1-4]분기|연말|연초|이달|다음 달|지난달)")


def _shift_month(value: date, months: int) -> date:
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    day = min(value.day, [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def extract_date_facts(sentences: list[str], published_at: str) -> list[dict[str, object]]:
    """Resolve explicit dates against the publication date and keep the basis.

    Ambiguous expressions are kept with ``resolved`` empty instead of guessed.
    """
    try:
        base = date.fromisoformat(str(published_at)[:10])
    except ValueError:
        base = None
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for sentence in sentences:
        for match in DATE_PATTERN.finditer(sentence):
            text = match.group(0).strip()
            if not (match.group("day") or match.group("month") or match.group("year")):
                continue
            if not match.group("day") and not match.group("month"):
                continue  # a bare year is a period, handled below
            following = sentence[match.end():match.end() + 3]
            if re.match(r"\s*(?:간|째|동안|여간|만에|연속|이내)", following):
                continue  # durations such as "3일간"
            prefix = match.group("prefix") or ""
            year = int(match.group("year")) if match.group("year") else None
            month = int(match.group("month")) if match.group("month") else None
            day = int(match.group("day")) if match.group("day") else None
            resolved = ""
            basis = ""
            if base:
                try:
                    if year and month and day:
                        resolved, basis = date(year, month, day).isoformat(), "본문 절대 날짜"
                    elif month and day:
                        guess_year = base.year + (1 if prefix == "내년" else -1 if prefix in {"지난해", "작년"} else 0)
                        candidate = date(guess_year, month, day)
                        if not prefix and candidate > base + timedelta(days=45):
                            resolved, basis = "", "연도 불명확(발행일보다 먼 미래)"
                        else:
                            resolved, basis = candidate.isoformat(), f"발행일 {base.isoformat()} 기준 연도 보완"
                    elif day and not month:
                        if prefix == "오는":
                            candidate = date(base.year, base.month, day) if day >= base.day else _shift_month(date(base.year, base.month, 1), 1).replace(day=day)
                            resolved, basis = candidate.isoformat(), f"발행일 {base.isoformat()} 기준 다가오는 {day}일"
                        elif day <= base.day:
                            resolved, basis = date(base.year, base.month, day).isoformat(), f"발행일 {base.isoformat()} 기준 같은 달"
                        elif prefix == "지난":
                            candidate = _shift_month(date(base.year, base.month, 1), -1).replace(day=day)
                            resolved, basis = candidate.isoformat(), f"발행일 {base.isoformat()} 기준 전달"
                        else:
                            resolved, basis = "", "발행일보다 큰 일자(월 불명확)"
                    elif month and not day:
                        guess_year = base.year + (1 if prefix == "내년" else -1 if prefix in {"지난해", "작년"} else 0)
                        resolved, basis = f"{year or guess_year:04d}-{month:02d}", "월 단위(연도는 발행일 기준)" if not year else "본문 절대 연월"
                except ValueError:
                    resolved, basis = "", "날짜 계산 불가"
            key = f"{text}|{resolved}"
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "text": text,
                "resolved": resolved,
                "basis": basis or "발행일 정보 없음",
                "local_time": bool(match.group("local")),
                "evidence": sentence[:240],
            })
    for sentence in sentences:
        for match in PERIOD_PATTERN.finditer(sentence):
            text = match.group(0).strip()
            if text in seen:
                continue
            seen.add(text)
            resolved = ""
            if base:
                resolved = {"올해": str(base.year), "올": str(base.year), "올들어": str(base.year), "내년": str(base.year + 1), "지난해": str(base.year - 1), "작년": str(base.year - 1)}.get(text, "")
            rows.append({"text": text, "resolved": resolved, "basis": "기간 표현" + (f"(발행연도 {base.year} 기준)" if base and resolved else ""), "local_time": False, "evidence": sentence[:240]})
    return rows[:16]


# ---------------------------------------------------------------------------
# Statement status (fact / quote / plan / forecast)
# ---------------------------------------------------------------------------
STATUS_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"검토(?:하고 있|중|할 계획|할 방침|하기로|한다|해 나갈|에 들어갔)|검토할"), "검토"),
    (re.compile(r"(?:할|될|하는|되는)\s*(?:계획|예정|방침)|계획(?:이다|입니다|이라|이며|을 세웠)|예정(?:이다|입니다|이라|이며)|방침(?:이다|입니다)|추진(?:할|한다|키로)|하기로\s*했|겠다(?:[”\"’']|고|며|라|\s*(?:밝혔|말했|설명했))"), "계획·예정"),
    (re.compile(r"전망(?:이다|입니다|된다|됩니다|했|하며|이라)|예상(?:된다|됩니다|했|하며|이라)|예상\s*(?:배당금|배당|금액|액|규모|실적|매출|이익|수익|손실)|관측(?:이|된다|됩니다|했)|가능성|(?:할|될|있을)\s*것으로\s*(?:보인|보입|예상|전망|관측|분석)|수\s*있(?:다|습니다|다고)|내다봤|우려"), "전망·예상"),
    (re.compile(r"주장(?:했|하며|이다)|지적(?:했|하며)|비판(?:했|하며)|반박(?:했|하며)"), "주장"),
    (re.compile(r"시행(?:했|됐|되었|에 들어갔|하고 있)|시행됐|발효(?:됐|했)"), "시행"),
    (re.compile(r"(?:의결|결정|확정|승인|인가|타결)(?:했|됐|되었|하였)|하기로\s*결정"), "결정·확정"),
    (re.compile(r"체결(?:했|됐|하였)|계약(?:을)?\s*맺"), "체결"),
    (re.compile(r"공시(?:했|됐|하였)"), "공시"),
    (re.compile(r"발표(?:했|됐|하였)|공개(?:했|됐)|내놨"), "발표"),
)
QUOTE_SPEECH = re.compile(r"[“\"][^”\"]{4,}[”\"].{0,30}(?:말했|밝혔|설명했|덧붙였|강조했|전했|언급했|답했)|(?:말했|밝혔|설명했|덧붙였|강조했|전했)(?:다|습니다)")


def classify_statement(sentence: str) -> str:
    text = clean_text(sentence)
    # Modality wins over the reporting verb: "인하를 검토할 계획이라고 발표했다"
    # is a plan/review announcement, not an executed cut.
    for pattern, label in STATUS_RULES[:4]:
        if pattern.search(text):
            if label in {"검토", "계획·예정", "전망·예상"} and re.search(r"(?:발표|공시)(?:했|하였)", text):
                return f"{label}(발표)"
            if label in {"검토", "계획·예정", "전망·예상"} and QUOTE_SPEECH.search(text):
                return f"{label}(발언)"
            return label
    if QUOTE_SPEECH.search(text):
        return "당사자 발언"
    for pattern, label in STATUS_RULES[4:]:
        if pattern.search(text):
            return label
    return "보도된 사실"


UNCERTAINTY_PATTERN = re.compile(
    r"미정|미확정|확정되지(?:는)?\s*않|정해지지\s*않|불투명|불확실|미지수|가늠하기(?:는|가)?\s*어렵|알\s*수\s*없|검토|예정|계획|방침|전망|"
    r"가능성|추정|관측|변수|시행령에서\s*정할|논의\s*중|협의\s*중|아직|여부(?:가|에\s*따라)|달렸|조건|려면|장담할\s*수\s*없|보장(?:이|은)?\s*없"
)


def uncertainty_rows(sentences: list[str], limit: int = 6) -> list[str]:
    rows = [clean_text(row) for row in sentences if UNCERTAINTY_PATTERN.search(row)]
    if rows:
        return rows[:limit]
    return ["원문에서 불확실성·조건을 명시한 문장을 찾지 못함(불확실성이 없다는 뜻은 아님)"]


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
UNIT = (
    r"%p|%포인트|퍼센트포인트|%|퍼센트|bp|bps|베이시스포인트|basis\s+points?|"
    r"조\s*\d[\d,]*억\s*원|조\s*\d[\d,]*억|조원|억\s*원|억원|만\s*원|만원|천원|원|"
    r"억\s*달러|만\s*달러|달러|弗|엔|위안|유로|파운드|"
    r"trillion|billion|million|"
    r"조|억|만|가구|세대|곳|개사|개|명|건|척|호|대|주|배럴|톤|포인트|p|배|위|차|회|거래일|개월|분기|년|월|일"
)
FIGURE_PATTERN = re.compile(
    r"(?<![\w.])(?P<sign>[-+△▲▼]|마이너스\s*)?(?:[$€£¥]\s*)?"
    r"(?P<num>\d[\d,]*(?:\.\d+)?(?:\s*(?:조|억|만)\s*\d[\d,]*(?:\.\d+)?)*(?:(?:조|억|만)(?=\s*[~∼〜]\s*\d))?)"
    r"(?:\s*(?P<range>[~∼〜\-]|에서)\s*(?P<num2>[-+]?\d[\d,]*(?:\.\d+)?(?:\s*(?:조|억|만)\s*\d[\d,]*)*))?"
    r"\s*(?P<unit>" + UNIT + r")?",
    re.I,
)
DIRECTION = (
    (re.compile(r"^\s*(?:로|으로)?\s*(?:증가|늘|상승|올라|오른|올랐|인상|급등|뛰|확대|웃돌|높)"), "증가·상승"),
    (re.compile(r"^\s*(?:로|으로)?\s*(?:감소|줄|하락|내려|내린|내렸|인하|급락|빠지|빠졌|축소|밑돌|낮)"), "감소·하락"),
)
QUALIFIERS = (
    (re.compile(r"예상치|컨센서스|시장\s*예상|전망치"), "예상치"),
    (re.compile(r"전월|직전|이전치|전년\s*동기|전년\s*대비|전분기|전주"), "비교 기준 포함"),
    (re.compile(r"잠정"), "잠정치"),
    (re.compile(r"목표"), "목표치"),
    (re.compile(r"전망|예상(?!치)|추정|할 것으로"), "전망·추정"),
    (re.compile(r"한도|상한|제한|초과"), "한도·규제값"),
)


def _figure_kind(unit: str) -> str:
    unit = unit.lower().replace(" ", "")
    if unit in {"%p", "%포인트", "퍼센트포인트", "bp", "bps", "베이시스포인트"} or unit.startswith("basis"):
        return "변동폭(포인트)"
    if unit in {"%", "퍼센트"}:
        return "비율"
    if any(token in unit for token in ("원", "달러", "弗", "엔", "위안", "유로", "파운드", "trillion", "billion", "million")) or unit in {"조", "억", "만"}:
        return "금액·규모"
    if unit in {"년", "월", "일", "분기", "개월", "거래일"}:
        return "기간·시점"
    return "수량" if unit else "수치"


def extract_figures(sentences: list[str], actors: list[dict[str, str]] | None = None) -> list[dict[str, object]]:
    """Every number with unit, sign, range, label words, direction and source sentence."""
    actors = actors or []
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for index, sentence in enumerate(sentences):
        text = clean_text(sentence)
        for match in FIGURE_PATTERN.finditer(text):
            unit = SPACE.sub("", match.group("unit") or "")
            raw = SPACE.sub(" ", match.group(0)).strip()
            if not re.search(r"\d", raw):
                continue
            kind = _figure_kind(unit)
            following = text[match.end():match.end() + 12]
            # Pure calendar references belong to date facts, not key figures.
            if unit in {"년", "월", "일"} and not re.match(r"\s*(?:간|여간|동안|째|만에|연속|이내|여)", following):
                continue
            if unit == "" and re.fullmatch(r"\d{1,2}", match.group("num")) and not re.match(r"\s*(?:곳|개|명|건|가구|세대|척|호|대|위|번째|배)", following):
                continue  # article numbering / stray digits
            if re.fullmatch(r"(?:19|20)\d{2}\.\d{1,2}(?:\.\d{1,2})?\.?", match.group("num")):
                continue  # dotted calendar dates such as 2026.11.27
            sign = (match.group("sign") or "").strip()
            negative = sign in {"-", "△", "▼"} or sign.startswith("마이너스")
            label_window = text[max(0, match.start() - 30):match.start()]
            label_window = re.split(r"[,.“”\"」』)(]|며\s|고\s|지만\s|는데\s", label_window)[-1]
            label_words = [strip_particle(word)[0] for word in TOKEN.findall(label_window)][-3:]
            direction = next((name for pattern, name in DIRECTION if pattern.search(text[match.end():match.end() + 14])), "")
            qualifier = next((name for pattern, name in QUALIFIERS if pattern.search(text[max(0, match.start() - 30):match.end() + 18])), "")
            subject = next((actor["name"] for actor in actors if actor["name"].split()[-1] in text), "")
            key = (normalized(raw), normalized(text))
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "value": raw,
                "number": match.group("num").replace(" ", ""),
                "upper": (match.group("num2") or "").replace(" ", ""),
                "unit": unit,
                "kind": kind,
                "negative": negative,
                "label": " ".join(label_words),
                "direction": direction,
                "qualifier": qualifier,
                "subject": subject,
                "sentence_index": index,
                "context": text[:400],
            })
    return rows


def figure_key(value: str) -> str:
    return re.sub(r"[\s,]", "", str(value)).lower()


def figure_coverage(figures: list[dict[str, object]], summary_text: str) -> dict[str, object]:
    compact = figure_key(summary_text)
    important = [row for row in figures if row["kind"] in {"금액·규모", "비율", "변동폭(포인트)", "수량"}]
    missing = [row for row in important if figure_key(str(row["value"])) not in compact]
    return {
        "important_total": len(important),
        "important_in_summary": len(important) - len(missing),
        "missing": [{"value": row["value"], "context": str(row["context"])[:160]} for row in missing[:12]],
    }


def unsupported_numbers(summary_text: str, body_text: str) -> list[str]:
    """Numbers (with unit) in the summary that cannot be traced to the body."""
    body = figure_key(body_text)
    rows = []
    for match in FIGURE_PATTERN.finditer(clean_text(summary_text)):
        raw = SPACE.sub(" ", match.group(0)).strip()
        if re.search(r"\d", raw) and figure_key(raw) not in body:
            rows.append(raw)
    return rows


# ---------------------------------------------------------------------------
# Summary selection
# ---------------------------------------------------------------------------
INFO_PATTERN = re.compile(
    r"때문|따라|영향|여파|배경|이유|목적|위해|으로\s*인해|조건|다만|하지만|반면|그러나|예정|계획|방침|시행|만기|마감|기한|"
    r"발표|결정|의결|체결|공시|매각|인수|인상|인하|동결|검토|전망|예상|가능성|우려|리스크|위험"
)
BRIDGE_ONLY = re.compile(r"^(?:이는|이것은|그래서|이처럼|이에 따라|이 때문에)\s")


MAJOR_FIGURE_KINDS = {"금액·규모", "비율", "변동폭(포인트)"}


def select_summary_sentences(sentences: list[str], figures: list[dict[str, object]], actors: list[dict[str, str]], title: str = "") -> list[int]:
    """Pick sentences in article order by priority instead of a fixed head cut.

    Priority: lead → sentences adding a new amount/ratio → decisions, plans,
    conditions and uncertainty → first quote of each speaker → counts → an
    informative ending.  Sentences carrying a major figure may exceed the soft
    budget so that late conditions and numbers are not silently dropped.
    """
    total = len(sentences)
    if total <= 8:
        return list(range(total))
    budget = max(8, min(18, round(total * 0.5)))
    chosen: list[int] = [0]
    if total > 4:
        chosen.append(1)
    covered: set[str] = set()

    def add(index: int) -> None:
        if index not in chosen:
            chosen.append(index)
        covered.update(figure_key(str(row["value"])) for row in figures if int(row["sentence_index"]) == index)

    for index in list(chosen):
        add(index)
    major = [row for row in figures if row["kind"] in MAJOR_FIGURE_KINDS]
    for row in major:
        if len(chosen) >= budget:
            break
        if figure_key(str(row["value"])) not in covered:
            add(int(row["sentence_index"]))
    for index, sentence in enumerate(sentences):
        if len(chosen) >= budget:
            break
        if (INFO_PATTERN.search(sentence) or UNCERTAINTY_PATTERN.search(sentence)) and not BRIDGE_ONLY.match(sentence):
            add(index)
    speakers_seen: set[str] = set()
    for actor in actors:
        if actor.get("role") != "speaker" or len(chosen) >= budget:
            continue
        surname_key = actor["name"].split()[0][:1] + actor["name"].split()[-1]
        if surname_key in speakers_seen:
            continue
        speakers_seen.add(surname_key)
        for index, sentence in enumerate(sentences):
            if actor["evidence"][:60] and sentence.startswith(actor["evidence"][:60]):
                add(index)
                break
    for row in figures:
        if len(chosen) >= budget:
            break
        if row["kind"] == "수량" and figure_key(str(row["value"])) not in covered:
            add(int(row["sentence_index"]))
    # Late major figures that are still missing may exceed the soft budget.
    overflow = 0
    for row in major:
        if overflow >= 4:
            break
        if figure_key(str(row["value"])) not in covered:
            add(int(row["sentence_index"]))
            overflow += 1
    if INFO_PATTERN.search(sentences[-1]) or UNCERTAINTY_PATTERN.search(sentences[-1]) or any(int(row["sentence_index"]) == total - 1 for row in major):
        add(total - 1)
    return sorted(set(chosen))


def group_paragraphs(indices: list[int], sentences: list[str], paragraph_of: list[int] | None, max_paragraphs: int = 7) -> list[str]:
    groups: list[list[str]] = []
    last_paragraph = None
    for index in indices:
        paragraph = paragraph_of[index] if paragraph_of and index < len(paragraph_of) else index
        if groups and paragraph == last_paragraph and len(groups[-1]) < 3:
            groups[-1].append(sentences[index])
        else:
            groups.append([sentences[index]])
        last_paragraph = paragraph
    while len(groups) > max_paragraphs:
        # merge the two shortest neighbours
        position = min(range(len(groups) - 1), key=lambda i: len(" ".join(groups[i])) + len(" ".join(groups[i + 1])))
        groups[position:position + 2] = [groups[position] + groups[position + 1]]
    return [" ".join(group) for group in groups]


def core_summary(sentences: list[str], indices: list[int], figures: list[dict[str, object]], limit: int = 420) -> str:
    """Lead sentence + first major-figure sentence + first decision/plan/condition sentence."""
    if not indices:
        return ""
    picks = [indices[0]]
    major_rows = [int(row["sentence_index"]) for row in figures if row["kind"] in MAJOR_FIGURE_KINDS]
    lead_has_major = indices[0] in major_rows

    def fits(index: int) -> bool:
        return len(" ".join(sentences[i] for i in sorted(picks + [index]))) <= limit

    if not lead_has_major:
        figure_index = next((index for index in indices[1:] if index in major_rows and fits(index)), None)
        if figure_index is not None:
            picks.append(figure_index)
    action_index = next((index for index in indices[1:] if index not in picks and STATUS_ACTION.search(sentences[index]) and fits(index)), None)
    if action_index is not None:
        picks.append(action_index)
    if len(picks) == 1:
        filler = next((index for index in indices[1:] if fits(index)), None)
        if filler is not None:
            picks.append(filler)
    return " ".join(sentences[index] for index in sorted(picks))


STATUS_ACTION = re.compile(r"결정|의결|체결|발표|공시|매각|인수|인상|인하|동결|시행|계획|예정|방침|검토|추진|허용|승인|배당")


def language_of(text: str) -> str:
    sample = clean_text(text)
    korean = len(re.findall(r"[가-힣]", sample))
    latin = len(re.findall(r"[A-Za-z]", sample))
    if latin >= 24 and latin > max(12, korean * 1.25):
        return "en"
    return "ko" if korean else "unknown"


def translation_check(original: list[str], translated: list[str]) -> dict[str, object]:
    """Numbers must survive translation; output must actually be Korean."""
    problems: list[str] = []
    if len(original) != len(translated) or not all(translated):
        problems.append("번역 결과 누락")
    for source, target in zip(original, translated):
        missing = _number_keys(source) - _number_keys(target)
        if missing:
            problems.append(f"수치 불일치: {', '.join(sorted(missing))}")
        if language_of(target) != "ko":
            problems.append("번역문이 한국어가 아님")
    return {"ok": not problems, "problems": problems[:8]}
