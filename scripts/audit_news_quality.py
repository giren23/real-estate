from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
NEWS_DIR = ROOT / "web" / "content" / "news"
REPORT_DIR = ROOT / "docs" / "reports"
GOOD_BODY = {"full_text", "verified_reconstruction", "fetched"}
AGGREGATORS = {"news.google.com", "google.com", "www.google.com", "bing.com", "www.bing.com"}
SIX_W_KEYS = ("who", "when", "what", "why", "how")


def is_direct(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and parsed.hostname.lower() not in AGGREGATORS
    except ValueError:
        return False


def reasons(item: dict[str, object]) -> list[str]:
    found: list[str] = []
    if item.get("article_body_status") not in GOOD_BODY:
        found.append("원문 본문 미확보")
    sources = item.get("sources") or []
    direct = str(item.get("article_source_url") or "")
    if not is_direct(direct) and not any(is_direct(str(source.get("url") or "")) for source in sources):
        found.append("검증된 직접 링크 없음")
    paragraphs = [str(row).strip() for row in (item.get("article_summary") or item.get("narrative_paragraphs") or []) if str(row).strip()]
    if len(paragraphs) < 3 or sum(map(len, paragraphs)) < 250:
        found.append("상세 요약 부족")
    six_w = item.get("six_w_one_h") or {}
    if not all(isinstance(six_w.get(key), list) and six_w.get(key) for key in SIX_W_KEYS):
        found.append("필수 6하원칙 누락")
    if "�" in json.dumps(item, ensure_ascii=False):
        found.append("문자 인코딩 손상")
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description="저장된 모든 뉴스의 원문 링크와 요약 품질을 감사합니다.")
    parser.add_argument("--date", default=date.today().isoformat(), help="보고서 기준일")
    args = parser.parse_args()
    failures: list[dict[str, object]] = []
    total = 0
    for path in sorted(NEWS_DIR.glob("20??-??-??.json"), reverse=True):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload.get("items", []):
            total += 1
            failed = reasons(item)
            if failed:
                failures.append({
                    "archive_date": payload.get("date"), "article_date": item.get("date"),
                    "title": item.get("title"), "publisher": item.get("publisher"),
                    "reasons": failed, "body_status": item.get("article_body_status"),
                    "direct_url": item.get("article_source_url") or "",
                })
    counts = Counter(reason for item in failures for reason in item["reasons"])
    result = {"audited_at": args.date, "total_articles": total, "failed_articles": len(failures), "passed_articles": total - len(failures), "reason_counts": dict(counts), "items": failures}
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    base = REPORT_DIR / f"news_summary_audit_{args.date}"
    base.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"# 뉴스 원문·요약 품질 감사 — {args.date}", "", f"- 전체: {total:,}건", f"- 통과: {total - len(failures):,}건", f"- 재검토 필요: {len(failures):,}건", "", "## 사유별 건수", ""]
    lines.extend(f"- {key}: {value:,}건" for key, value in counts.most_common())
    lines.extend(["", "## 재검토 기사 전체 목록", "", "| 보관일 | 기사일 | 발행사 | 제목 | 사유 |", "|---|---|---|---|---|"])
    for item in failures:
        title = str(item["title"] or "").replace("|", "\\|")
        lines.append(f"| {item['archive_date'] or '-'} | {item['article_date'] or '-'} | {item['publisher'] or '-'} | {title} | {', '.join(item['reasons'])} |")
    base.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "items"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
