from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "public" / "economic_context.json"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=EXKOUS"

BASE_RATES = [
    ("2006-02-09", 4.00), ("2006-06-08", 4.25), ("2006-08-10", 4.50),
    ("2007-07-12", 4.75), ("2007-08-09", 5.00), ("2008-08-07", 5.25),
    ("2008-10-09", 5.00), ("2008-10-27", 4.25), ("2008-11-07", 4.00),
    ("2008-12-11", 3.00), ("2009-01-09", 2.50), ("2009-02-12", 2.00),
    ("2010-07-09", 2.25), ("2010-11-16", 2.50), ("2011-01-13", 2.75),
    ("2011-03-10", 3.00), ("2011-06-10", 3.25), ("2012-07-12", 3.00),
    ("2012-10-11", 2.75), ("2013-05-09", 2.50), ("2014-08-14", 2.25),
    ("2014-10-15", 2.00), ("2015-03-12", 1.75), ("2015-06-11", 1.50),
    ("2016-06-09", 1.25), ("2017-11-30", 1.50), ("2018-11-30", 1.75),
    ("2019-07-18", 1.50), ("2019-10-16", 1.25), ("2020-03-17", 0.75),
    ("2020-05-28", 0.50), ("2021-08-26", 0.75), ("2021-11-25", 1.00),
    ("2022-01-14", 1.25), ("2022-04-14", 1.50), ("2022-05-26", 1.75),
    ("2022-07-13", 2.25), ("2022-08-25", 2.50), ("2022-10-12", 3.00),
    ("2022-11-24", 3.25), ("2023-01-13", 3.50), ("2024-10-11", 3.25),
    ("2024-11-28", 3.00), ("2025-02-25", 2.75), ("2025-05-29", 2.50),
    ("2026-07-16", 2.75),
]

POLICIES = [
    ("2017-08-02", "8·2 주택시장 안정화 방안"),
    ("2018-09-13", "9·13 주택시장 안정대책"),
    ("2019-12-16", "주택시장 안정화 방안"),
    ("2020-06-17", "주택시장 안정을 위한 관리방안"),
    ("2020-07-10", "주택시장 안정 보완대책"),
    ("2021-02-04", "공공주도 3080+ 주택공급 확대방안"),
    ("2022-08-16", "국민 주거안정 실현방안"),
    ("2023-01-03", "규제지역·민간택지 분양가상한제 개편"),
    ("2023-09-26", "주택공급 활성화 방안"),
    ("2024-01-10", "주택공급 확대 및 건설경기 보완방안"),
    ("2024-08-08", "국민 주거안정을 위한 주택공급 확대방안"),
    ("2025-09-07", "주택공급 확대방안"),
    ("2025-10-15", "주택시장 안정화 대책"),
]


def fetch_exchange_rates() -> list[dict[str, object]]:
    with urlopen(FRED_URL, timeout=30) as response:
        text = response.read().decode("utf-8-sig")
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        value = row.get("EXKOUS")
        if not value or value == ".":
            continue
        date = row.get("DATE") or row.get("observation_date")
        if not date:
            continue
        rows.append({"month": date[:7], "krw_per_usd": round(float(value), 2)})
    return rows


def main() -> None:
    exchange_rates = []
    try:
        exchange_rates = fetch_exchange_rates()
    except Exception as error:
        if OUTPUT.exists():
            exchange_rates = json.loads(OUTPUT.read_text(encoding="utf-8")).get("exchange_rates", [])
            print(f"FRED 갱신 실패, 기존 환율 자료 유지: {error}")
        else:
            raise
    payload = {
        "exchange_rates": exchange_rates,
        "base_rates": [{"date": date, "rate": rate} for date, rate in BASE_RATES],
        "policies": [{"date": date, "title": title} for date, title in POLICIES],
        "sources": {
            "exchange_rate": FRED_URL,
            "base_rate": "https://www.bok.or.kr/portal/singl/baseRate/list.do?dataSeCd=01&menuNo=200643",
            "policies": "https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp",
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"경제지표 JSON 생성 완료: 환율 {len(exchange_rates)}개월")


if __name__ == "__main__":
    main()
