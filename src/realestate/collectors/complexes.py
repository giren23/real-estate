from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from realestate.core.http import get_text
from realestate.core.settings import Settings


def _items(payload: dict) -> tuple[list[dict], int]:
    response = payload.get("response", payload)
    header = response.get("header", {})
    code = str(header.get("resultCode", "00"))
    if code not in {"00", "000", "0"}:
        raise RuntimeError(f"공동주택 목록 API 오류 {code}: {header.get('resultMsg', '')}")
    body = response.get("body", {})
    items = body.get("items", [])
    if isinstance(items, dict):
        items = items.get("item", items)
    if isinstance(items, dict):
        items = [items]
    return list(items or []), int(body.get("totalCount", 0) or 0)


def collect_complexes(settings: Settings, output: Path) -> pd.DataFrame:
    if not settings.apartment_list_key:
        raise RuntimeError(
            "APT_LIST_SERVICE_KEY가 필요합니다. 공공데이터포털의 "
            "'국토교통부_공동주택 단지 목록제공 서비스' 활용신청 후 등록하세요."
        )

    rows: list[dict] = []
    page = 1
    page_size = 1000
    while True:
        print(f"[START] 공동주택 전국 단지 목록 {page}페이지", flush=True)
        text = get_text(settings.apartment_list_endpoint, {
            "serviceKey": settings.apartment_list_key,
            "pageNo": page,
            "numOfRows": page_size,
            "_type": "json",
        })
        page_rows, total = _items(json.loads(text))
        rows.extend(page_rows)
        print(f"[OK] 공동주택 전국 단지 목록: {len(rows):,}/{total:,}개", flush=True)
        if not page_rows or len(rows) >= total:
            break
        page += 1

    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError("공동주택 전국 단지 목록이 비어 있습니다.")

    def column(*names: str) -> pd.Series:
        for name in names:
            if name in frame.columns:
                return frame[name].fillna("").astype(str).str.strip()
        return pd.Series([""] * len(frame), index=frame.index)

    result = pd.DataFrame({
        "complex_code": column("kaptCode", "kapt_code"),
        "apt_name": column("kaptName", "kapt_name"),
        "sido": column("as1"),
        "sigungu": column("as2"),
        "dong": column("as3", "as4"),
        "bjd_code": column("bjdCode", "bjd_code"),
    })
    result["region_name"] = (result["sido"] + " " + result["sigungu"]).str.strip()
    result["address"] = (result["region_name"] + " " + result["dong"]).str.strip()
    result = result[result["apt_name"] != ""].drop_duplicates("complex_code")
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)
    print(f"전국 공동주택 단지 {len(result):,}개 저장 완료: {output}", flush=True)
    return result
