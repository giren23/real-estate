from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "public" / "economic_context.json"
FRED_SERIES = {
    "exchange_rates": ("EXKOUS", "krw_per_usd"),
    "bond_yields": ("IRLTLT01KRM156N", "rate"),
    "oil_prices": ("MCOILBRENTEU", "usd_per_barrel"),
}
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
    {
        "date": "2017-08-02",
        "title": "8·2 주택시장 안정화 방안",
        "summary": "투기과열지구·투기지역을 확대하고 다주택자 양도소득세, 재건축, 청약 및 주택담보대출 규제를 강화했습니다.",
        "url": "https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp",
    },
    {
        "date": "2018-09-13",
        "title": "9·13 주택시장 안정대책",
        "summary": "종합부동산세를 강화하고 규제지역 다주택자의 주택담보대출을 제한하는 한편 수도권 주택공급 확대 방침을 함께 제시했습니다.",
        "url": "https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp",
    },
    {
        "date": "2019-12-16",
        "title": "주택시장 안정화 방안",
        "summary": "15억원 초과 아파트 주택담보대출을 제한하고 9억원 초과분 LTV를 강화했으며 보유세·양도세와 청약 규제를 조정했습니다.",
        "url": "https://www.molit.go.kr/USR/NEWS/m_71/dtl.jsp?id=95083268",
    },
    {
        "date": "2020-06-17",
        "title": "주택시장 안정을 위한 관리방안",
        "summary": "규제지역을 확대하고 법인·갭투자 관련 대출과 세제를 강화했으며 정비사업 안전진단과 조합원 요건을 보완했습니다.",
        "url": "https://www.molit.go.kr/USR/NEWS/m_71/dtl.jsp?id=95084016",
    },
    {
        "date": "2020-07-10",
        "title": "주택시장 안정 보완대책",
        "summary": "다주택자의 취득·보유·양도 단계 세 부담을 높이고 등록임대 제도를 개편하면서 생애최초·서민 실수요 지원을 확대했습니다.",
        "url": "https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp",
    },
    {
        "date": "2021-02-04",
        "title": "공공주도 3080+ 주택공급 확대방안",
        "summary": "공공 직접시행 정비와 도심 공공주택 복합사업을 도입해 2025년까지 전국 83.6만호 공급 기반을 마련하는 방안입니다.",
        "url": "https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp",
    },
    {
        "date": "2022-08-16",
        "title": "국민 주거안정 실현방안",
        "summary": "향후 5년간 270만호 공급을 목표로 규제 정상화, 민간 정비사업 촉진, 청년·서민 주거복지 강화를 제시했습니다.",
        "url": "https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp",
    },
    {
        "date": "2023-01-03",
        "title": "규제지역·민간택지 분양가상한제 개편",
        "summary": "강남3구와 용산구를 제외한 규제지역을 해제하고 분양가상한제 적용지역, 전매제한과 실거주 의무를 완화했습니다.",
        "url": "https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp",
    },
    {
        "date": "2023-09-26",
        "title": "주택공급 활성화 방안",
        "summary": "프로젝트파이낸싱 지원과 인허가·착공 촉진, 공공주택 물량 확대를 통해 주택공급 지연을 완화하는 데 초점을 맞췄습니다.",
        "url": "https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp",
    },
    {
        "date": "2024-01-10",
        "title": "주택공급 확대 및 건설경기 보완방안",
        "summary": "재건축 안전진단 절차를 개선하고 소형주택·오피스텔 규제를 완화했으며 지방 미분양 주택에 대한 세제 지원을 포함했습니다.",
        "url": "https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp",
    },
    {
        "date": "2024-08-08",
        "title": "국민 주거안정을 위한 주택공급 확대방안",
        "summary": "수도권 42.7만호 공급 기반을 마련하고 그린벨트 해제, 공공택지 조기 공급, 재건축·재개발 촉진 방안을 제시했습니다.",
        "url": "https://www.molit.go.kr/2024_house_plan/news/bodo_1.pdf",
    },
    {
        "date": "2025-09-07",
        "title": "주택공급 확대방안",
        "summary": "수도권 공공택지와 도심 공급을 확대하고 인허가·착공 시기를 앞당겨 실제 입주 가능한 물량을 조기에 확보하는 방안입니다.",
        "url": "https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp",
    },
    {
        "date": "2025-10-15",
        "title": "주택시장 안정화 대책",
        "summary": "수도권·규제지역 고가주택의 주택담보대출 한도를 강화하고 투기수요 억제, 시장질서 확립과 공급 확대를 병행했습니다.",
        "url": "https://www.molit.go.kr/USR/NEWS/dtl.jsp?id=95091308",
    },
]


def fred_url(series_id: str) -> str:
    return f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"


def fetch_fred_series(series_id: str, value_key: str) -> list[dict[str, object]]:
    with urlopen(fred_url(series_id), timeout=30) as response:
        text = response.read().decode("utf-8-sig")
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        value = row.get(series_id)
        date = row.get("DATE") or row.get("observation_date")
        if not date or not value or value == ".":
            continue
        rows.append({"month": date[:7], value_key: round(float(value), 3)})
    return rows


def main() -> None:
    existing = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
    payload: dict[str, object] = {}
    for output_key, (series_id, value_key) in FRED_SERIES.items():
        try:
            payload[output_key] = fetch_fred_series(series_id, value_key)
        except Exception as error:
            if output_key not in existing:
                raise
            payload[output_key] = existing[output_key]
            print(f"{series_id} 갱신 실패, 기존 자료 유지: {error}")
    payload.update(
        {
            "base_rates": [{"date": date, "rate": rate} for date, rate in BASE_RATES],
            "policies": POLICIES,
            "sources": {
                "exchange_rate": "https://fred.stlouisfed.org/series/EXKOUS/",
                "base_rate": "https://www.bok.or.kr/portal/singl/baseRate/list.do?menuNo=200656",
                "bond_yield": "https://fred.stlouisfed.org/series/IRLTLT01KRM156N",
                "oil_price": "https://fred.stlouisfed.org/series/MCOILBRENTEU",
                "policies": "https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp",
            },
        }
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(
        "경제지표 JSON 생성 완료: "
        + ", ".join(f"{key} {len(payload[key])}개월" for key in FRED_SERIES)
    )


if __name__ == "__main__":
    main()
