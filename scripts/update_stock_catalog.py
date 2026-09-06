from __future__ import annotations

import io
import json
import os
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "web" / "data" / "stock_catalog.json"


def main() -> int:
    api_key = os.environ.get("DART_API_KEY", "").strip()
    if not api_key:
        print("DART_API_KEY가 없어 기존 종목 카탈로그를 유지합니다.")
        return 0
    request = urllib.request.Request(
        f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={api_key}",
        headers={"User-Agent": "KoreanRealEstateStockCatalog/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
    root = ElementTree.fromstring(archive.read("CORPCODE.xml"))
    items = []
    for row in root.findall("list"):
        symbol = (row.findtext("stock_code") or "").strip()
        name = (row.findtext("corp_name") or "").strip()
        if len(symbol) == 6 and symbol.isdigit() and name:
            items.append({"symbol": symbol, "name": name, "exchange": "KRX"})
    items.sort(key=lambda row: (row["name"], row["symbol"]))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({"updated_at": datetime.now().astimezone().isoformat(timespec="seconds"), "items": items}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"상장사 종목 카탈로그 {len(items):,}개 저장")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
