from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "web" / "content" / "editorial.json"
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_PATTERN = re.compile(r"^[a-z0-9-]+$")
REQUIRED_FIELDS = {
    "id",
    "date",
    "eyebrow",
    "read_minutes",
    "title",
    "summary",
    "easy_explanation",
    "market_comment",
    "sections",
    "sources",
    "disclaimer",
}


def validate(path: Path = DEFAULT_PATH) -> list[str]:
    errors: list[str] = []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not DATE_PATTERN.match(str(payload.get("as_of", ""))):
        errors.append("as_of must use YYYY-MM-DD")

    sections = payload.get("sections")
    if not isinstance(sections, list) or {section.get("id") for section in sections} != {"news", "company", "analysis"}:
        errors.append("sections must contain news, company, and analysis exactly once")
        return errors

    seen_ids: set[str] = set()
    for section in sections:
        items = section.get("items")
        if not isinstance(items, list) or not items:
            errors.append(f"{section.get('id')}: items must not be empty")
            continue
        for item in items:
            item_id = str(item.get("id", ""))
            missing = REQUIRED_FIELDS - item.keys()
            if missing:
                errors.append(f"{item_id or '<missing id>'}: missing {sorted(missing)}")
            if not ID_PATTERN.match(item_id):
                errors.append(f"{item_id}: invalid id")
            if item_id in seen_ids:
                errors.append(f"{item_id}: duplicate id")
            seen_ids.add(item_id)
            if not DATE_PATTERN.match(str(item.get("date", ""))):
                errors.append(f"{item_id}: invalid date")
            if len(str(item.get("title", ""))) > 38:
                errors.append(f"{item_id}: title is longer than 38 characters")
            if len(str(item.get("summary", ""))) > 90:
                errors.append(f"{item_id}: summary is longer than 90 characters")
            if len(item.get("tags", [])) > 3:
                errors.append(f"{item_id}: at most 3 tags are allowed")
            sources = item.get("sources", [])
            minimum_sources = 2 if section.get("id") == "company" else 1
            if len(sources) < minimum_sources:
                errors.append(f"{item_id}: requires at least {minimum_sources} sources")
            for source in sources:
                if not str(source.get("url", "")).startswith("https://"):
                    errors.append(f"{item_id}: source URL must use HTTPS")
                if not DATE_PATTERN.match(str(source.get("published_at", ""))):
                    errors.append(f"{item_id}: source published_at is invalid")
    return errors


def main() -> int:
    path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_PATH
    errors = validate(path)
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors))
        return 1
    print(f"OK: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
