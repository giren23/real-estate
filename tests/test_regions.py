from __future__ import annotations

import pandas as pd

from realestate.core.regions import priority_regions_from_complexes


def test_priority_regions_cover_requested_areas_and_deduplicate(tmp_path):
    complexes_path = tmp_path / "complexes.csv"
    fallback_path = tmp_path / "regions.csv"
    pd.DataFrame(
        [
            {
                "bjd_code": "1111010100",
                "region_name": "서울특별시 종로구",
            },
            {
                "bjd_code": "1111010200",
                "region_name": "서울특별시 종로구",
            },
            {
                "bjd_code": "4113510100",
                "region_name": "경기도 성남시 분당구",
            },
            {
                "bjd_code": "2611010100",
                "region_name": "부산광역시 중구",
            },
            {
                "bjd_code": "4311110100",
                "region_name": "충청북도 청주시 상당구",
            },
            {
                "bjd_code": "4812110100",
                "region_name": "경상남도 창원시 의창구",
            },
            {
                "bjd_code": "3011010100",
                "region_name": "대전광역시 동구",
            },
        ]
    ).to_csv(complexes_path, index=False)
    pd.DataFrame(
        [{"lawd_cd": "11110", "region_name": "서울특별시 종로구"}]
    ).to_csv(fallback_path, index=False)

    result = priority_regions_from_complexes(
        complexes_path,
        fallback_path,
    )

    assert set(result["lawd_cd"]) == {
        "11110",
        "41135",
        "26110",
        "43111",
        "48121",
    }
    assert len(result) == 5
    assert "30110" not in set(result["lawd_cd"])


def test_priority_regions_use_fallback_when_directory_is_missing(tmp_path):
    fallback_path = tmp_path / "regions.csv"
    pd.DataFrame(
        [{"lawd_cd": "11110", "region_name": "서울특별시 종로구"}]
    ).to_csv(fallback_path, index=False)

    result = priority_regions_from_complexes(
        tmp_path / "missing.csv",
        fallback_path,
    )

    assert result.to_dict(orient="records") == [
        {"lawd_cd": "11110", "region_name": "서울특별시 종로구"}
    ]
