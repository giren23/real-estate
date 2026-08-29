from __future__ import annotations

from pathlib import Path

import pandas as pd


PRIORITY_REGION_PREFIXES = (
    "서울특별시",
    "경기도",
    "부산광역시",
    "충청북도 청주",
    "경상남도 창원",
)


def _read_regions(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"lawd_cd": str})
    frame["lawd_cd"] = frame["lawd_cd"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)
    return frame[["lawd_cd", "region_name"]].drop_duplicates("lawd_cd").reset_index(drop=True)


def priority_regions_from_complexes(
    complexes_path: Path,
    fallback_path: Path,
) -> pd.DataFrame:
    """Build district API targets for the five requested areas from the apartment directory."""
    if not complexes_path.exists():
        print(
            f"[WARN] 공동주택 단지 목록이 없어 기본 지역 목록을 사용합니다: {complexes_path}",
            flush=True,
        )
        return _read_regions(fallback_path)

    complexes = pd.read_csv(
        complexes_path,
        dtype={"bjd_code": str, "region_name": str},
    ).fillna("")
    required = {"bjd_code", "region_name"}
    if not required.issubset(complexes.columns):
        print(
            "[WARN] 공동주택 단지 목록에 bjd_code/region_name 열이 없어 기본 지역 목록을 사용합니다.",
            flush=True,
        )
        return _read_regions(fallback_path)

    names = complexes["region_name"].astype(str).str.strip()
    mask = names.map(
        lambda value: any(
            value.startswith(prefix)
            for prefix in PRIORITY_REGION_PREFIXES
        )
    )
    selected = complexes.loc[mask, ["bjd_code", "region_name"]].copy()
    selected["lawd_cd"] = (
        selected["bjd_code"]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(10)
        .str[:5]
    )
    selected = selected[selected["lawd_cd"].str.fullmatch(r"\d{5}", na=False)]
    regions = (
        selected[["lawd_cd", "region_name"]]
        .drop_duplicates("lawd_cd")
        .sort_values(["region_name", "lawd_cd"])
        .reset_index(drop=True)
    )
    if regions.empty:
        print(
            "[WARN] 우선 갱신 지역을 만들지 못해 기본 지역 목록을 사용합니다.",
            flush=True,
        )
        return _read_regions(fallback_path)

    counts = []
    for prefix in PRIORITY_REGION_PREFIXES:
        count = int(
            regions["region_name"].map(
                lambda value: value.startswith(prefix)
            ).sum()
        )
        counts.append(f"{prefix} {count}개")
    print(
        f"[REGIONS] 우선 갱신 지역 {len(regions)}개 법정동 코드: " + ", ".join(counts),
        flush=True,
    )
    return regions
