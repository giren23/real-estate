"""Re-process stored news articles with the current extractor — dry-run by default.

Examples (PowerShell, from D:\\AIServer):

  # 1) Dry-run: re-fetch the public pages of two days and write a comparison report only
  .venv\\Scripts\\python.exe scripts\\reprocess_news.py --dates 2026-11-27 2026-11-28 --limit 20

  # 2) Same, offline: re-structure stored summaries (who/when/figures/status) without network
  .venv\\Scripts\\python.exe scripts\\reprocess_news.py --dates 2026-11-27 --mode offline

  # 3) Apply only the verified improvements (day files are backed up first)
  .venv\\Scripts\\python.exe scripts\\reprocess_news.py --dates 2026-11-28 --apply

  # 4) Undo an applied run
  .venv\\Scripts\\python.exe scripts\\reprocess_news.py --restore backups\\news-reprocess-YYYYMMDD-HHMMSS

Rules: an item is replaced only when the new result passes the body contract,
identity check and quality gate.  A stored publishable summary is never
replaced by a failed attempt.  Paywalls/logins/CAPTCHA/403/429 are recorded
and skipped, never bypassed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_economic_news as U  # noqa: E402

NQ = U.NQ
CHANGED_KEYS = (
    "article_body_status", "publication_status", "body_completeness", "summary_basis", "article_summary", "narrative_paragraphs",
    "core_summary", "summary", "easy_explanation", "six_w_one_h", "six_w_one_h_evidence", "six_w_one_h_meta", "date_facts",
    "key_figures", "figure_coverage", "fact_status", "uncertainties", "summary_quality", "quality_gate", "identity_check",
    "extraction_diagnostics", "extraction_version", "article_source_url", "fetched_url", "canonical_source_url",
    "primary_source_role", "translation_status", "translation_check", "original_summary", "summary_language", "highlight_keywords",
    "summary_method", "summary_sentence_indices", "article_body_sentence_count", "skipped_leading_lines", "news_charts",
    "article_body_checked_at", "next_body_retry_at", "recovery_status", "recovery_search_links",
    "body_source_publisher", "body_published_at",
    "date", "published_time", "feed_date", "date_correction", "source_corrections", "sources", "discovery_method",
    "manual_verified", "editorial_verification",
)


def snapshot(item: dict[str, object]) -> dict[str, object]:
    six_w = item.get("six_w_one_h") if isinstance(item.get("six_w_one_h"), dict) else {}
    summary = item.get("article_summary") or []
    quality = item.get("summary_quality") if isinstance(item.get("summary_quality"), dict) else {}
    return {
        "status": item.get("article_body_status"),
        "publication": item.get("publication_status"),
        "visible": U.is_publishable_detail(item),
        "who": six_w.get("who", []),
        "when": (six_w.get("when") or [])[:4],
        "core_summary": str(item.get("core_summary") or "")[:300],
        "summary_first": str(summary[0] if summary else "")[:200],
        "summary_chars": sum(len(str(row)) for row in summary),
        "figures": len(item.get("key_figures") or []),
        "quality_score": quality.get("score"),
        "deductions": quality.get("deductions", []),
        "summary_text": " ".join([*(str(row) for row in summary), str(item.get("core_summary") or "")]),
    }


def article_url(item: dict[str, object]) -> str:
    for value in (item.get("fetched_url"), item.get("article_source_url")):
        if str(value or "").startswith(("http://", "https://")) and "news.google.com" not in str(value):
            return str(value)
    for source in item.get("sources") or []:
        for key in ("resolved_url", "canonical_url", "url"):
            value = str(source.get(key) or "")
            if value.startswith(("http://", "https://")) and "news.google.com" not in value:
                return value
    return ""


def relay_url(item: dict[str, object]) -> str:
    for source in item.get("sources") or []:
        value = str(source.get("url") or "")
        if "news.google.com" in value:
            return value
    return ""


def refetch_fields(item: dict[str, object]) -> tuple[dict[str, object] | None, str]:
    url = article_url(item)
    if not url and relay_url(item):
        # Same resolver the collector uses (rate-limited); old relays may no
        # longer resolve, which is then reported as before.
        try:
            resolved = U.resolve_article_url(relay_url(item))
        except Exception:
            resolved = ""
        if resolved and "news.google.com" not in resolved:
            url = resolved
    if not url:
        return None, "확보된 원문 주소 없음(구글 뉴스 중계 주소만 있음)"
    title = str(item.get("title") or "")
    try:
        extraction, final_url = U.fetch_article(url, title)
    except U.AccessRestricted as error:
        return None, f"접근 제한: {error}"
    except U.NotAnArticlePage as error:
        return None, f"기사 아님: {error}"
    except U.ArticleGone as error:
        return None, f"원문 삭제: {error}"
    except Exception as error:  # network/HTTP errors are reported, not retried here
        return None, f"원문 요청 실패: {str(error)[:160]}"
    identity = NQ.verify_identity(title, extraction.sentences, extraction.meta, expected_date=str(item.get("date") or ""))
    status, _ = NQ.body_status(extraction.sentences, boundary_closed=extraction.boundary_closed, path=extraction.path, identity_ok=bool(identity["ok"]))
    if not identity["ok"]:
        reasons = [str(reason) for reason in identity["reasons"]]
        page_differs = any(reason.startswith(("페이지 제목과 기사 제목 불일치", "발행일 불일치")) for reason in reasons)
        if len(extraction.sentences) < NQ.FULL_TEXT_MIN_SENTENCES and not page_differs:
            # The page title still matches; the extractor simply found no body
            # (unknown layout).  That says nothing against the stored summary.
            return None, f"본문 추출 실패(경로 {extraction.path}, {len(extraction.sentences)}문장, 페이지 제목 일치): " + ", ".join(reasons)
        date_differs = any(reason.startswith("발행일 불일치") for reason in reasons)
        words_differ = any(reason.startswith("제목 핵심어 일치 부족") for reason in reasons)
        page_title_differs = any(reason.startswith("페이지 제목과 기사 제목 불일치") for reason in reasons)
        if not (date_differs or (words_differ and page_title_differs)):
            # An updated wire headline, one number written differently, or a
            # body that merely avoids the headline's words (short premium/blog
            # titles) is not enough to call the page another article.
            return None, "제목·본문 일부 불일치(판정 보류): " + ", ".join(reasons)
        return None, "제목·본문 불일치: " + ", ".join(reasons)
    if status == "unavailable":
        return None, f"본문 계약 미충족({len(extraction.sentences)}문장·{len(' '.join(extraction.sentences))}자, 경로 {extraction.path})"
    fields = U._build_verified_fields(title, str(item.get("publisher") or "원문"), str(item.get("date") or ""), extraction, final_url, identity)
    fields["_body_sentences"] = extraction.sentences  # report-only; never stored in the archive
    return fields, ""


def offline_fields(item: dict[str, object]) -> tuple[dict[str, object] | None, str]:
    """Re-structure the stored summary text only (no network, summary text not extended)."""
    paragraphs = [str(row) for row in item.get("article_summary") or [] if str(row).strip()]
    if not paragraphs or item.get("article_body_status") not in U.PUBLISHABLE_BODY_STATUSES:
        return None, "저장된 상세 요약 없음"
    title = str(item.get("title") or "")
    sentences = [row for paragraph in paragraphs for row in NQ.split_sentences(paragraph)]
    cleaned = [NQ.clean_article_text(row) for row in sentences]
    cleaned = [row for row in cleaned if row and not (NQ.CODE_LINE.search(row) or NQ.STRONG_UI.search(row))]
    # Old summaries glued "title subtitle first-sentence" into one string.
    title_key = NQ.normalized(title)
    if cleaned and title_key and NQ.normalized(cleaned[0]).startswith(title_key[:16]):
        # Only the exact headline prefix can be removed offline; a glued
        # subtitle has no reliable boundary, so refetch mode is needed for it.
        first = cleaned[0]
        cleaned[0] = first[len(title):].strip() if first.startswith(title) else first
        cleaned = [row for row in cleaned if row]
    status, completeness = NQ.body_status(cleaned, boundary_closed=True, path="stored_summary", identity_ok=True)
    if status == "unavailable":
        return None, "정제 후 남은 문장 부족"
    identity = NQ.verify_identity(title, cleaned)
    if not identity["ok"] and not (item.get("identity_check") or {}).get("ok"):
        return None, "정제 후 제목과 본문 일치 미확인: 원문 재검수 필요"
    # Offline cleanup is not another compression pass: preserve every surviving
    # factual sentence rather than reducing an already summarised article.
    preserved = NQ.group_paragraphs(list(range(len(cleaned))), cleaned, list(range(len(cleaned))))
    core = NQ.core_summary(cleaned, NQ.select_summary_sentences(cleaned, NQ.extract_figures(cleaned), NQ.extract_actors(cleaned, title), title), NQ.extract_figures(cleaned))
    fields = U.structured_summary_fields(title, str(item.get("publisher") or "원문"), str(item.get("date") or ""), preserved, core, body_sentences=cleaned)
    fields.update({"narrative_paragraphs": preserved, "core_summary": core})
    fields["article_body_status"] = status if item.get("article_body_status") != "verified_reconstruction" else "verified_reconstruction"
    fields["body_completeness"] = completeness
    fields["summary_basis"] = f"{item.get('summary_basis') or '저장 요약'} · 오프라인 재구조화(원문 재수집 아님)"
    fields["reprocessed_offline"] = True
    # These are stored summary sentences, not a fresh full article extraction.
    for key in ("article_body_sentence_count", "summary_sentence_indices"):
        fields.pop(key, None)
    fields["quality_gate"] = U.quality_gate(fields)
    if not fields["quality_gate"]["passed"]:
        fields["publication_status"] = "statistics_only"
    return fields, ""


def recovery_source_urls(item: dict[str, object]) -> list[str]:
    return U.recovery_source_urls(item)


def recover_original_fields(item: dict[str, object], *, allow_date_correction: bool = False) -> tuple[dict[str, object] | None, str]:
    """Retry a bounded list of original public addresses, preserving refusal reasons."""
    if U.NON_ARTICLE_TITLE_PATTERN.search(str(item.get("title") or "")):
        return None, "기사 아님: 종목 시세 페이지"
    errors = []
    for url in recovery_source_urls(item):
        try:
            extraction, final_url = U.fetch_article(url, str(item.get("title") or ""))
            fields, error = recovered_source_fields(item, extraction, final_url, allow_date_correction=allow_date_correction)
            if fields:
                return fields, ""
            errors.append(error)
        except Exception as error:
            errors.append(f"{type(error).__name__}: {error}")
        time.sleep(1.5)
    return None, "; ".join(errors) or "확인 가능한 원문 주소 없음"


def recovered_source_fields(item: dict[str, object], extraction: NQ.Extraction, final_url: str,
                            *, allow_date_correction: bool = False) -> tuple[dict[str, object] | None, str]:
    return U.recovered_source_fields(item, extraction, final_url, allow_date_correction=allow_date_correction)


# Only a page that carries a different story (substantial body or different
# page title/date) may hide a stored summary.  An empty extraction, a short
# teaser or a network/access failure never does.
UNVERIFIABLE_PREFIXES = ("제목·본문 불일치", "기사 아님")


STORED_CODE = re.compile(r"adsbygoogle|googletag|\bvar\s+\w+\s*=|function\s*\(|document\.\w|window\.\w|\{\s*[\w-]+\s*:\s*[\w#.%-]+\s*;|\b\d+px\s*;")
STORED_UI = re.compile(r"멤버는\s*매월\s*\d+\s*개|누구에게나\s*선물할\s*수|계정/결제\s*관리를\s*위해|작성\s*권한은\s*창작자\s*설정")
NUMBERED_HEADLINES = re.compile(r"(?:^|\s)0[1-9]\.?\s+\S")


def stored_summary_problem(item: dict[str, object]) -> str:
    """Why the summary already stored for this item cannot be shown, or "".

    Only unmistakable cases count: page script/CSS, paywall/UI notices, a
    numbered list of other headlines ("02. … 03 …"), or a Korean summary
    sharing no keyword at all with its Korean headline.
    """
    sentences = [sentence for paragraph in item.get("article_summary") or [] for sentence in NQ.split_sentences(str(paragraph))]
    text = " ".join(sentences)
    if not text:
        return ""
    if STORED_CODE.search(text):
        return "페이지 코드 혼입"
    if STORED_UI.search(text) or NQ.DEBRIS_TAIL.search(text) or NQ.BROADCAST_NOTICE.search(text):
        return "유료·안내 문구"
    if len(NUMBERED_HEADLINES.findall(text)) >= 2:
        return "다른 기사 제목 목록"
    title = str(item.get("title") or "")
    if re.search(r"[가-힣]", title) and re.search(r"[가-힣]", text):
        page_identity = item.get("identity_check") or {}
        confirmed_mismatch = page_identity.get("date_consistent") is False or (
            page_identity.get("page_title_similarity") is not None and page_identity["page_title_similarity"] < 0.2)
        if not confirmed_mismatch:
            return ""  # lexical disagreement alone cannot prove that a stored summary is another story
        identity = NQ.verify_identity(title, sentences, {}, expected_date="")
        for reason in identity.get("reasons") or []:
            match = re.match(r"제목 핵심어 일치 부족\(0/(\d+)\)", str(reason))
            if match and int(match.group(1)) >= 5:
                return "제목과 무관한 내용"
    return ""


def decide(item: dict[str, object], fields: dict[str, object] | None, error: str, demote: bool = False) -> str:
    if fields is not None:
        new_ok = fields.get("publication_status") != "statistics_only" and fields.get("article_body_status") in U.PUBLISHABLE_BODY_STATUSES
        if new_ok:
            return "replace"
        error = "새 결과가 발행 기준 미달 " + "; ".join((fields.get("quality_gate") or {}).get("failures") or [])
    if demote and U.is_publishable_detail(item):
        # The stored URL was reachable but carries another story or no article
        # at all (fund data page).  Network/access failures never demote ...
        if fields is None and error.startswith(UNVERIFIABLE_PREFIXES):
            return "demote:" + error
        # ... unless the summary already on screen is itself page debris.
        problem = stored_summary_problem(item)
        if problem:
            return f"demote:저장 요약 오염({problem}) · {error}"
    return "keep:" + (error or "새 결과 없음")


def merged_item(item: dict[str, object], fields: dict[str, object]) -> dict[str, object]:
    updated = dict(item)
    for key in CHANGED_KEYS:
        if key in fields:
            updated[key] = fields[key]
    updated["summary"] = str(fields.get("core_summary") or updated.get("summary") or "")[:900]
    paragraphs = fields.get("narrative_paragraphs") or fields.get("article_summary") or []
    if paragraphs:
        updated["easy_explanation"] = str(paragraphs[0])
    updated["summary_schema_version"] = U.SUMMARY_SCHEMA_VERSION
    updated["reprocessed_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    updated["detail_visible"] = U.is_publishable_detail(updated)
    if updated["detail_visible"]:
        updated.pop("article_body_error", None)
        updated.pop("article_body_failure_kind", None)
    updated.pop("last_refresh", None)
    U.strip_summary_provenance(updated)
    return updated


def select_items(args: argparse.Namespace) -> list[tuple[Path, int, dict[str, object]]]:
    files = sorted(U.NEWS_DIR.glob("20??-??-??.json"), reverse=True)
    if args.dates:
        wanted = set(args.dates)
        files = [path for path in files if path.stem in wanted]
    ids = set(args.ids or [])
    rows: list[tuple[Path, int, dict[str, object]]] = []
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for index, item in enumerate(payload.get("items", [])):
            if ids and str(item.get("id")) not in ids:
                continue
            if not ids and args.only_unextracted and int(item.get("extraction_version") or 0) >= NQ.EXTRACTION_VERSION:
                continue
            rows.append((path, index, item))
            if args.limit and len(rows) >= args.limit:
                return rows
    return rows


def write_report(out: Path, rows: list[dict[str, object]], args: argparse.Namespace) -> None:
    summary = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": args.mode,
        "applied": bool(args.apply),
        "selected": len(rows),
        "replace": sum(row["decision"] == "replace" for row in rows),
        "demote": sum(str(row["decision"]).startswith("demote:") for row in rows),
        "kept": sum(str(row["decision"]).startswith("keep:") for row in rows),
    }
    (out / "report.json").write_text(json.dumps({"summary": summary, "items": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# 뉴스 재처리 보고서 ({summary['generated_at']})", "", f"- 방식: {args.mode} · 실제 반영: {'예' if args.apply else '아니오(dry-run)'}",
             f"- 대상 {summary['selected']}건 · 교체 {summary['replace']}건 · 노출 중단 {summary['demote']}건 · 유지 {summary['kept']}건", ""]
    for row in rows:
        before, after = row["before"], row.get("after") or {}
        lines += [f"## {row['date']} · {row['title']}", f"- id: `{row['id']}` · 결정: **{row['decision']}**",
                  f"- 상태: {before['status']}/{before['publication']} → {after.get('status', '-')}/{after.get('publication', '-')}",
                  f"- 누가: {before['who']} → {after.get('who', '-')}",
                  f"- 핵심요약 전: {before['core_summary'][:160]}", f"- 핵심요약 후: {str(after.get('core_summary', '-'))[:160]}",
                  f"- 수치 {before['figures']} → {after.get('figures', '-')} · 품질점수 {before['quality_score']} → {after.get('quality_score', '-')} {after.get('deductions', '')}", ""]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


# Fields a collector run rewrites when it re-enriches an article.  Importance
# flags are left out on purpose: rebuild_index() recomputes them every run.
FINGERPRINT_KEYS = tuple(dict.fromkeys((*CHANGED_KEYS, "title", "date", "publisher", "sources", "detail_visible",
                                      "article_body_error", "article_body_failure_kind", "reprocessed_at", "summary_schema_version")))


def _fingerprint(item: dict[str, object]) -> tuple[str, ...]:
    return tuple(json.dumps(item.get(key), ensure_ascii=False, sort_keys=True) for key in FINGERPRINT_KEYS)


def apply_changes(path: Path, changes: dict[int, tuple[dict[str, object], dict[str, object]]],
                  journal: Path | None = None) -> tuple[int, list[str]]:
    """Write reprocessed items back without clobbering a concurrent update.

    A long refetch can overlap the 4-hourly collector, which may move items or
    re-enrich archived ones.  Each change is applied only where the stored item
    is still exactly the one that was reprocessed; anything else is skipped.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items", [])
    applied, skipped, entries = 0, [], []
    for index, (original, candidate) in changes.items():
        item_id = original.get("id")
        if index < len(items) and items[index].get("id") == item_id:
            position = index
        else:
            matches = [number for number, row in enumerate(items) if row.get("id") == item_id]
            if len(matches) != 1:
                skipped.append(f"{path.stem} {item_id}: 날짜 파일에서 위치를 확정할 수 없음({len(matches)}곳)")
                continue
            position = matches[0]
        if _fingerprint(items[position]) != _fingerprint(original):
            skipped.append(f"{path.stem} {item_id}: 재처리 중 다른 실행이 이 기사를 갱신함")
            continue
        # Keep unrelated metadata refreshed while the original was being read.
        updated = dict(items[position])
        for key in original.keys() | candidate.keys():
            if key not in candidate:
                updated.pop(key, None)
            elif key not in original or candidate[key] != original[key]:
                updated[key] = candidate[key]
        entries.append({"file": path.name, "id": item_id, "before": items[position], "after": updated,
                        "changed_keys": [key for key in original.keys() | candidate.keys()
                                         if original.get(key) != candidate.get(key) or (key in original) != (key in candidate)],
                        "changed_at": datetime.now().astimezone().isoformat(timespec="seconds")})
        items[position] = updated
        applied += 1
    if applied:
        if journal is not None:
            # Durable undo evidence first; a failed write is skipped by restore's
            # post-change fingerprint, never mistaken for a completed change.
            with journal.open("a", encoding="utf-8") as output:
                for entry in entries:
                    output.write(json.dumps(entry, ensure_ascii=False) + "\n")
                output.flush()
                os.fsync(output.fileno())
        U.atomic_write_json(path, payload)
    return applied, skipped


def wait_for_run_lock(minutes: float) -> bool:
    deadline = time.monotonic() + max(0.0, minutes) * 60
    while not U.acquire_run_lock():
        if time.monotonic() >= deadline:
            return False
        print("정기 뉴스 갱신이 실행 중이라 끝날 때까지 기다립니다…", flush=True)
        time.sleep(30)
    return True


def restore(backup: Path) -> None:
    journal = backup / "change-journal.jsonl"
    if not journal.is_file():
        raise SystemExit("기사별 변경 저널이 없어 자동 복원을 중단함. 오래된 날짜 파일 전체 복사는 이후 수집분을 잃을 수 있음.")
    entries = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines() if line.strip()]
    result = []
    for entry in reversed(entries):
        name = str(entry["file"])
        if Path(name).name != name:
            raise ValueError("복구 저널의 파일 경로가 잘못됨")
        path = U.NEWS_DIR / name
        payload = json.loads(path.read_text(encoding="utf-8"))
        matches = [row for row in payload.get("items", []) if row.get("id") == entry["id"]]
        if len(matches) != 1 or _fingerprint(matches[0]) != _fingerprint(entry["after"]):
            result.append({"id": entry["id"], "result": "skipped_concurrent_change"})
            continue
        row = matches[0]
        for key in entry["changed_keys"]:
            if key in entry["before"]:
                row[key] = entry["before"][key]
            else:
                row.pop(key, None)
        U.atomic_write_json(path, payload)
        result.append({"id": entry["id"], "result": "restored"})
    U.atomic_write_json(backup / "restore-result.json", result)
    U.rebuild_index()
    print(f"기사별 복구 {sum(row['result'] == 'restored' for row in result)}건 · 이후 수정된 기사는 건너뜀")


def archive_audit(out: Path) -> dict[str, object]:
    """Offline, reproducible plan. No network and no writes to the archive."""
    rows, changes, url_rows = [], [], {}
    for path in sorted(U.NEWS_DIR.glob("20??-??-??.json")):
        for index, item in enumerate(json.loads(path.read_text(encoding="utf-8")).get("items", [])):
            rows.append(item)
            for url in U._source_urls(item):
                url_rows.setdefault(url, []).append({"file": path.name, "id": item.get("id"), "title": item.get("title")})
            if not U.is_publishable_detail(item):
                continue
            reasons, updated = [], dict(item)
            text = " ".join([str(item.get("core_summary") or ""), *(str(row) for row in item.get("article_summary") or [])])
            if NQ.clean_article_text(text) != NQ.clean_text(text) or STORED_CODE.search(text):
                fields, error = offline_fields(item)
                if fields:
                    updated = merged_item(item, fields)
                    reasons.append("저장 요약의 광고·푸터·안내문 제거")
                else:
                    updated.update({"publication_status": "statistics_only", "detail_visible": False,
                                    "quality_gate": {"passed": False, "failures": [error]},
                                    "recovery_status": "retry_scheduled", "next_body_retry_at": U.next_body_retry_at(item)})
                    reasons.append("정제 후 본문 계약 미달: 원문 내용은 보존하고 상세만 보류")
            core = str(updated.get("core_summary") or "")
            if item.get("editorial_verification") and re.search(r"정정함|구분해\s*요약함|다룬\s*기사임|다룬\s*기사로", core):
                paragraphs = [NQ.clean_article_text(str(row)) for row in updated.get("article_summary") or []]
                sentences = [sentence for paragraph in paragraphs for sentence in NQ.split_sentences(paragraph)]
                removed_notes = [sentence for sentence in sentences if re.match(r"원문\s*발행일은.+아닌.+임", sentence)]
                sentences = [sentence for sentence in sentences if sentence not in removed_notes]
                if sentences:
                    facts = NQ.extract_figures(sentences)
                    new_core = NQ.core_summary(sentences, list(range(min(3, len(sentences)))), facts)
                    verification = dict(item["editorial_verification"])
                    verification["display_cleanup"] = {"previous_core_summary": core, "reason": "검수 메모는 본문 핵심 요약과 분리함"}
                    if removed_notes:
                        verification["display_cleanup"]["removed_notes"] = removed_notes
                        preserved = NQ.group_paragraphs(list(range(len(sentences))), sentences, list(range(len(sentences))))
                        updated.update({"article_summary": preserved, "narrative_paragraphs": preserved, "easy_explanation": preserved[0]})
                    updated.update({"core_summary": new_core, "summary": new_core, "editorial_verification": verification})
                    reasons.append("편집 작업 메모를 검수 기록으로 이동")
            who = (updated.get("six_w_one_h") or {}).get("who") or []
            filtered = [row for row in who if not re.fullmatch(r"\d+(?:년|월|일)부|S&P\s*500|CAC\s*40|IBEX\s*35|NASDAQ\s*100",
                        str(row.get("name") if isinstance(row, dict) else row), re.I)]
            if filtered != who:
                updated["six_w_one_h"] = {**updated["six_w_one_h"], "who": filtered}
                evidence = dict(updated.get("six_w_one_h_evidence") or {})
                evidence["who"] = [row for row in evidence.get("who") or [] if row.get("value") in filtered]
                updated["six_w_one_h_evidence"] = evidence
                if not filtered and updated.get("six_w_one_h_meta"):
                    meta = dict(updated["six_w_one_h_meta"])
                    missing = list(dict.fromkeys([*(meta.get("missing") or []), "who"]))
                    total = int(meta.get("total") or 7)
                    meta.update({"missing": missing, "covered": total-len(missing),
                                 "coverage_percent": round((total-len(missing))/total*100)})
                    updated["six_w_one_h_meta"] = meta
                reasons.append("지수·날짜 조각을 주체에서 제외(실제 기관명은 유지)")
            if reasons:
                changes.append({"file": path.name, "position": index, "id": item.get("id"),
                                "title": item.get("title"), "reasons": reasons, "before": item, "after": updated})
    duplicate_candidates = {url: group for url, group in url_rows.items() if len(group) > 1}
    plan = {"generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "total": len(rows), "visible": sum(U.is_publishable_detail(row) for row in rows),
            "changes": changes, "duplicate_candidates": duplicate_candidates,
            "duplicate_action": "report_only: 같은 URL도 잘못 연결된 다른 기사일 수 있으므로 자동 삭제·병합하지 않음"}
    out.mkdir(parents=True, exist_ok=True)
    (out / "audit-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["# 뉴스 오프라인 정리안 — 실제 반영 전", "", f"전체 {len(rows)}건 · 수정 후보 {len(changes)}건 · 중복 URL 후보 {len(duplicate_candidates)}개", "",
             "기사 내용을 새로 추정하지 않음. 원래 기사 ID·내용·보관 파일을 삭제하지 않음. 중복 후보는 보고만 함.", "",
             "| 보관 파일 | 기사 ID | 제목 | 조치 |", "|---|---|---|---|"]
    lines += [f"| {row['file']} | {row['id']} | {str(row['title']).replace('|', '/')} | {' · '.join(row['reasons'])} |" for row in changes]
    lines += ["", "## 중복 URL 후보 — 병합하지 않음", ""]
    for url, group in duplicate_candidates.items():
        lines += [f"- {url}", *[f"  - {row['file']} · {row['id']} · {row['title']}" for row in group]]
    (out / "audit-plan.md").write_text("\n".join(lines), encoding="utf-8")
    return plan


def apply_audit(plan_path: Path) -> dict[str, object]:
    """Apply only reviewed per-article deltas; never re-run or broaden a plan."""
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    out = plan_path.parent
    if (out / "change-journal.jsonl").exists():
        raise ValueError("이미 반영 이력이 있는 정리안임. 새 dry-run으로 현재 상태를 확인해야 함")
    grouped = {}
    for row in plan["changes"]:
        if row.get("id") != row["before"].get("id") or row["after"].get("id") != row.get("id"):
            raise ValueError("정리안은 기사 ID를 바꿀 수 없음")
        name = str(row["file"])
        if Path(name).name != name or not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", name):
            raise ValueError("정리안 날짜 파일 경로가 잘못됨")
        grouped.setdefault(U.NEWS_DIR / name, {})[row["position"]] = (row["before"], row["after"])
    if not U.acquire_run_lock():
        raise RuntimeError("다른 수집이 실행 중임. 정리안은 반영하지 않음")
    try:
        backup = out / "day-files"
        backup.mkdir(exist_ok=True)
        total, skipped = 0, []
        for path, changes in grouped.items():
            shutil.copy2(path, backup / path.name)
            count, ignored = apply_changes(path, changes, journal=out / "change-journal.jsonl")
            total += count
            skipped.extend(ignored)
        U.rebuild_index()
        result = {"applied": total, "skipped": skipped, "rollback": str(out)}
        U.atomic_write_json(out / "apply-result.json", result)
        return result
    finally:
        U.release_run_lock()


def main() -> None:
    parser = argparse.ArgumentParser(description="저장된 뉴스 기사를 새 추출·구조화 규칙으로 재처리합니다(기본 dry-run).")
    parser.add_argument("--dates", nargs="*", help="대상 날짜 YYYY-MM-DD (생략 시 전체)")
    parser.add_argument("--ids", nargs="*", help="대상 기사 id")
    parser.add_argument("--limit", type=int, default=0, help="최대 기사 수(0=제한 없음)")
    parser.add_argument("--mode", choices=("refetch", "offline"), default="refetch", help="refetch=공개 원문 재수집, offline=저장 요약 재구조화")
    parser.add_argument("--only-unextracted", action="store_true", help="새 추출기로 처리되지 않은 기사만")
    parser.add_argument("--recover-sources", action="store_true", help="잘못 연결된 수집본 대신 원래 피드·출판사 주소부터 재검증")
    parser.add_argument("--correct-published-date", action="store_true", help="--recover-sources와 함께 동일 제목 원문의 발행일만 정정(이전 날짜 보존)")
    parser.add_argument("--sleep", type=float, default=1.5, help="원문 요청 사이 대기(초)")
    parser.add_argument("--apply", action="store_true", help="검증 통과 결과를 실제 날짜 파일에 반영")
    parser.add_argument("--keep-body-in-report", action="store_true", help="검증용으로 본문 문장을 보고서 JSON에 남김(로컬 검수용)")
    parser.add_argument("--demote-unverifiable", action="store_true", help="저장 URL이 다른 기사(다른 본문·페이지 제목·발행일)로 확인된 경우 기존 상세 노출을 통계용으로 내림(내용은 보존, 본문 추출 실패·짧은 본문·접근 실패는 제외)")
    parser.add_argument("--lock-wait", type=float, default=40.0, help="반영 직전 정기 뉴스 갱신이 실행 중이면 기다릴 최대 분")
    parser.add_argument("--out", default="", help="보고서·백업 폴더")
    parser.add_argument("--restore", default="", help="--apply 때 만든 백업 폴더에서 날짜 파일 복구")
    parser.add_argument("--audit-archive", action="store_true", help="광고·푸터·작업 메모·중복 URL을 오프라인 점검(계획만 저장)")
    parser.add_argument("--apply-audit", default="", help="검토한 audit-plan.json의 기사별 변경만 잠금·지문 확인 후 반영")
    args = parser.parse_args()
    if args.audit_archive:
        out = Path(args.out) if args.out else U.ROOT / "backups" / f"news-audit-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        plan = archive_audit(out)
        print(f"수정 후보 {len(plan['changes'])}건, 중복 URL {len(plan['duplicate_candidates'])}개(병합 안 함): {out / 'audit-plan.md'}")
        return
    if args.apply_audit:
        print(apply_audit(Path(args.apply_audit)))
        return
    if args.correct_published_date and not args.recover_sources:
        parser.error("--correct-published-date는 --recover-sources와 함께 사용해야 합니다")
    if args.restore:
        if not U.acquire_run_lock():
            raise SystemExit("뉴스 갱신이 실행 중입니다. 끝난 뒤 다시 실행하세요.")
        try:
            restore(Path(args.restore))
        finally:
            U.release_run_lock()
        return
    out = Path(args.out) if args.out else U.ROOT / "backups" / f"news-reprocess-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    out.mkdir(parents=True, exist_ok=True)
    targets = select_items(args)
    rows: list[dict[str, object]] = []
    replacements: dict[Path, dict[int, tuple[dict[str, object], dict[str, object]]]] = {}
    for number, (path, index, item) in enumerate(targets, 1):
        try:
            if args.mode == "refetch":
                fields, error = (recover_original_fields(item, allow_date_correction=args.correct_published_date)
                                 if args.recover_sources else refetch_fields(item))
            else:
                fields, error = offline_fields(item)
        except Exception as exc:  # one bad article must not abort a long run
            fields, error = None, f"처리 오류: {type(exc).__name__}: {str(exc)[:160]}"
        if args.mode == "refetch":
            time.sleep(max(0.0, args.sleep))
        decision = decide(item, fields, error, args.demote_unverifiable)
        row = {"date": path.stem, "id": item.get("id"), "title": item.get("title"), "publisher": item.get("publisher"),
               "url": article_url(item), "decision": decision, "before": snapshot(item)}
        if decision.startswith("demote:"):
            demoted = dict(item)
            demoted["publication_status"] = "statistics_only"
            demoted["detail_visible"] = False
            demoted["quality_gate"] = {"passed": False, "failures": [f"재검증 실패: {decision.split(':', 1)[1]}"], "checked_at": datetime.now().astimezone().isoformat(timespec="seconds")}
            demoted["reprocessed_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
            row["after"] = snapshot(demoted)
            replacements.setdefault(path, {})[index] = (item, demoted)
        if fields is not None:
            body = fields.pop("_body_sentences", None)
            if body is not None and args.keep_body_in_report:
                row["body_sentences"] = body
            candidate = merged_item(item, fields)
            if not decision.startswith("demote:"):
                row["after"] = snapshot(candidate)
            row["identity"] = fields.get("identity_check")
            row["extraction"] = fields.get("extraction_diagnostics")
            row["figure_coverage"] = fields.get("figure_coverage")
            if decision == "replace":
                replacements.setdefault(path, {})[index] = (item, candidate)
        rows.append(row)
        print(f"[{number}/{len(targets)}] {decision[:60]} · {str(item.get('title'))[:50]}", flush=True)
        if number % 100 == 0:
            write_report(out, rows, args)  # interim report so a long run is never lost
    write_report(out, rows, args)
    print(f"보고서: {out / 'report.md'}")
    if not args.apply:
        print("dry-run: 날짜 파일은 바꾸지 않았습니다. 반영하려면 --apply를 붙이세요.")
        return
    if not replacements:
        print("반영할 교체 결과가 없습니다.")
        return
    if not wait_for_run_lock(args.lock_wait):
        raise SystemExit("뉴스 갱신이 계속 실행 중입니다. 끝난 뒤 다시 실행하세요(아무것도 바꾸지 않음, 보고서는 저장됨).")
    try:
        backup = out / "day-files"
        backup.mkdir(exist_ok=True)
        shutil.copy2(U.INDEX_PATH, out / "index.json.bak")
        total, skipped_all = 0, []
        for path, changes in replacements.items():
            shutil.copy2(path, backup / path.name)
            applied, skipped = apply_changes(path, changes, journal=out / "change-journal.jsonl")
            total += applied
            skipped_all += skipped
            print(f"반영: {path.name} {applied}/{len(changes)}건 (백업 {backup / path.name})", flush=True)
        (out / "apply-skipped.json").write_text(json.dumps(skipped_all, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"반영 {total}건 · 건너뜀 {len(skipped_all)}건(다른 실행이 먼저 갱신, {out / 'apply-skipped.json'})")
        U.rebuild_index()
        print(f"index.json 재생성 완료. 되돌리기: scripts\\reprocess_news.py --restore {out}")
    finally:
        U.release_run_lock()


if __name__ == "__main__":
    main()
