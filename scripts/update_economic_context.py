from __future__ import annotations

import csv
import io
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "public" / "economic_context.json"
FRED_SERIES = {
    "exchange_rates": ("EXKOUS", "krw_per_usd"),
    "us_policy_rates": ("FEDFUNDS", "rate"),
    "japan_policy_rates": ("IRSTCI01JPM156N", "rate"),
}
GROUPED_FRED_SERIES = {
    "metal_prices": {
        "copper_usd_ton": "PCOPPUSDM",
    },
    "oil_prices": {
        "brent_usd_barrel": "POILBREUSDM",
        "wti_usd_barrel": "POILWTIUSDM",
        "dubai_usd_barrel": "POILDUBUSDM",
    },
    "bond_yields": {
        "kr_short_proxy": "IRSTCI01KRM156N",
        "kr_10y": "IRLTLT01KRM156N",
        "us_1y": "GS1",
        "us_10y": "GS10",
        "us_30y": "GS30",
        "jp_short_proxy": "IRSTCI01JPM156N",
        "jp_10y": "IRLTLT01JPM156N",
    },
}
YAHOO_SERIES = {
    "kospi": "^KS11",
    "kosdaq": "^KQ11",
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "dow": "^DJI",
    "bitcoin": "BTC-USD",
    "sox": "^SOX",
    "vix": "^VIX",
}
YAHOO_METAL_SERIES = {"gold_usd_oz": "GC=F", "silver_usd_oz": "SI=F"}
YAHOO_CURRENT_MONTH_GROUPS = {
    "exchange_rates": {"krw_per_usd": "KRW=X"},
    "oil_prices": {"brent_usd_barrel": "BZ=F", "wti_usd_barrel": "CL=F"},
    "bond_yields": {"us_10y": "^TNX", "us_30y": "^TYX"},
}
BOK_BOND_ITEMS = {"kr_1y": "010190000", "kr_10y": "010210000", "kr_30y": "010230000"}
BOK_BOND_TABLE = "817Y002"
CNN_FEAR_GREED_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata/2021-02-01"
JAPAN_MOF_BOND_URL = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KoreanRealEstateDashboard/1.0"
MONEY_SUPPLY_URL = (
    "https://snapshot.bok.or.kr/api/chart/getChartData?"
    "series=USER-M-00402,USER-M-00403"
)
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
    {
        "date": "2026-01-23",
        "title": "2026년 부동산 세제·금융 제도 변경",
        "summary": "월세 세액공제 대상을 무주택 세대주의 배우자까지 넓히고, 주택청약종합저축 세제혜택을 2028년까지 연장했으며 지방 준공 후 미분양 주택의 취득·보유·양도 단계 세 부담 완화를 2026년 말까지 적용합니다.",
        "url": "https://www.korea.kr/multi/visualNewsView.do?newsId=148958477",
    },
    {
        "date": "2026-08-11",
        "title": "2026 세제개편안: 주택 보유·거주 과세 개편",
        "summary": "정부 개편안은 양도세 장기보유특별공제를 거주 중심으로 단계 전환하고 종부세 기본공제를 거주용 1주택 14억원, 비거주 1주택 9억원 등으로 조정하며 다주택자 양도세 중과를 2027~2028년 한시 완화하는 내용을 담았습니다. 국회 입법 전 개편안입니다.",
        "url": "https://www.korea.kr/multi/visualNewsView.do?newsId=148969827",
    },
    {
        "date": "2026-08-26",
        "title": "2026 지방세제 개편안: 취득세·재산세 지원",
        "summary": "생애최초 취득세 감면을 일정 요건의 주거용 오피스텔까지 확대하고 40세 미만 청년 감면 한도를 300만원으로 높이며, 공시가격 9억원 이하 1주택 재산세 특례를 2029년까지 연장하는 내용입니다. 국회 입법 전 개편안입니다.",
        "url": "https://www.korea.kr/news/policyNewsView.do?newsId=148970644",
    },
]


def fred_url(series_id: str) -> str:
    return f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"


def download(url: str, *, headers: dict[str, str] | None = None) -> bytes:
    request_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    request_headers.update(headers or {})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request = Request(url, headers=request_headers)
            with urlopen(request, timeout=45) as response:
                return response.read()
        except Exception as error:
            last_error = error
            if attempt < 2:
                time.sleep(2**attempt)
    assert last_error is not None
    raise last_error


def fetch_fred_series(series_id: str, value_key: str) -> list[dict[str, object]]:
    text = download(fred_url(series_id)).decode("utf-8-sig")
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        value = row.get(series_id)
        date = row.get("DATE") or row.get("observation_date")
        if not date or not value or value == ".":
            continue
        rows.append({"month": date[:7], value_key: round(float(value), 3)})
    return rows


def merge_monthly_series(series: dict[str, tuple[str, list[dict[str, object]]]]) -> list[dict[str, object]]:
    by_month: dict[str, dict[str, object]] = {}
    for value_key, (_, rows) in series.items():
        for row in rows:
            month = str(row["month"])
            by_month.setdefault(month, {"month": month})[value_key] = row[value_key]
    return [by_month[month] for month in sorted(by_month)]


def fetch_fred_group(mapping: dict[str, str]) -> list[dict[str, object]]:
    fetched: dict[str, tuple[str, list[dict[str, object]]]] = {}
    for value_key, series_id in mapping.items():
        try:
            fetched[value_key] = (series_id, fetch_fred_series(series_id, value_key))
        except Exception as error:
            print(f"{series_id} 개별 갱신 실패, 나머지 FRED 지표 계속: {error}")
    if not fetched:
        raise RuntimeError("FRED 묶음 지표를 하나도 갱신하지 못했습니다.")
    return merge_monthly_series(fetched)


def fetch_yahoo_monthly(mapping: dict[str, str] = YAHOO_SERIES) -> list[dict[str, object]]:
    now = int(time.time())
    series: dict[str, tuple[str, list[dict[str, object]]]] = {}
    for value_key, symbol in mapping.items():
        try:
            url = (
                "https://query1.finance.yahoo.com/v8/finance/chart/"
                f"{quote(symbol, safe='')}?period1=946684800&period2={now}&interval=1mo&events=history"
            )
            payload = json.loads(download(url, headers={"Accept": "application/json"}).decode("utf-8"))
            result = payload["chart"]["result"][0]
            timestamps = result.get("timestamp") or []
            quote_rows = result.get("indicators", {}).get("quote", [{}])[0]
            closes = quote_rows.get("close") or []
            rows: list[dict[str, object]] = []
            for timestamp, value in zip(timestamps, closes):
                if value is None:
                    continue
                month = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m")
                rows.append({"month": month, value_key: round(float(value), 4)})
            if rows:
                series[value_key] = (symbol, rows)
        except Exception as error:
            print(f"{symbol} 개별 갱신 실패, 나머지 Yahoo 지표 계속: {error}")
    if not series:
        raise RuntimeError("Yahoo 지표를 하나도 갱신하지 못했습니다.")
    return merge_monthly_series(series)


def fetch_bok_base_rates() -> list[dict[str, object]]:
    """Fetch official daily BOK base rates and keep only actual change dates."""
    api_key = os.environ.get("BOK_ECOS_API_KEY", "").strip()
    if not api_key:
        return []
    end = datetime.now().strftime("%Y%m%d")
    url = (
        f"https://ecos.bok.or.kr/api/StatisticSearch/{api_key}/json/kr/1/10000/"
        f"722Y001/D/20060101/{end}/0101000"
    )
    payload = json.loads(download(url, headers={"Accept": "application/json"}).decode("utf-8"))
    source_rows = payload.get("StatisticSearch", {}).get("row", [])
    changes: list[dict[str, object]] = []
    previous: float | None = None
    for row in source_rows:
        stamp = str(row.get("TIME") or "")
        value_text = row.get("DATA_VALUE")
        if len(stamp) != 8 or value_text in (None, ""):
            continue
        value = float(value_text)
        if previous is None or value != previous:
            changes.append({"date": f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}", "rate": value})
            previous = value
    return changes


def convert_field(rows: list[dict[str, object]], key: str, factor: float) -> list[dict[str, object]]:
    converted: list[dict[str, object]] = []
    for row in rows:
        output = dict(row)
        if key in output:
            output[key] = round(float(output[key]) * factor, 4)
        converted.append(output)
    return converted


def filter_numeric_range(
    rows: list[dict[str, object]], key: str, minimum: float, maximum: float
) -> list[dict[str, object]]:
    """Drop impossible observations so a stale/corrupt fallback cannot distort charts."""
    filtered: list[dict[str, object]] = []
    for row in rows:
        if key not in row:
            continue
        try:
            value = float(row[key])
        except (TypeError, ValueError):
            continue
        if minimum <= value <= maximum:
            filtered.append(row)
        else:
            print(f"비정상 {key} 값 제외: {row.get('month')}={value}")
    return filtered


def latest_month_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Keep only the newest month from a feed used as a current-month overlay."""
    months = [str(row.get("month", "")) for row in rows if row.get("month")]
    if not months:
        return []
    latest_month = max(months)
    return [row for row in rows if str(row.get("month")) == latest_month]


def fetch_bok_bond_yields() -> list[dict[str, object]]:
    api_key = os.environ.get("BOK_ECOS_API_KEY", "").strip()
    if not api_key:
        return []
    end = datetime.now().strftime("%Y%m%d")
    series: dict[str, tuple[str, list[dict[str, object]]]] = {}
    for value_key, item_code in BOK_BOND_ITEMS.items():
        url = (
            f"https://ecos.bok.or.kr/api/StatisticSearch/{api_key}/json/kr/1/10000/"
            f"{BOK_BOND_TABLE}/D/20000101/{end}/{item_code}"
        )
        payload = json.loads(download(url, headers={"Accept": "application/json"}).decode("utf-8"))
        source_rows = payload.get("StatisticSearch", {}).get("row", [])
        monthly: dict[str, list[float]] = defaultdict(list)
        for row in source_rows:
            value = row.get("DATA_VALUE")
            stamp = str(row.get("TIME") or "")
            if value in (None, "") or len(stamp) < 6:
                continue
            monthly[f"{stamp[:4]}-{stamp[4:6]}"].append(float(value))
        rows = [
            {"month": month, value_key: round(sum(values) / len(values), 4)}
            for month, values in sorted(monthly.items())
            if values
        ]
        series[value_key] = (item_code, rows)
    return merge_monthly_series(series)


def fetch_japan_bond_yields() -> list[dict[str, object]]:
    """Fetch official constant-maturity JGB yields and average them by month."""
    text = download(JAPAN_MOF_BOND_URL, headers={"Accept": "text/csv"}).decode("utf-8-sig")
    lines = text.splitlines()
    reader = csv.DictReader(lines[1:])
    monthly: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    columns = {"jp_1y": "1Y", "jp_10y": "10Y", "jp_30y": "30Y"}
    for row in reader:
        stamp = str(row.get("Date") or "")
        if len(stamp) < 7:
            continue
        parts = stamp.split("/")
        if len(parts) < 2:
            continue
        month = f"{int(parts[0]):04d}-{int(parts[1]):02d}"
        for value_key, column in columns.items():
            value = str(row.get(column) or "").strip()
            if value and value != "-":
                monthly[month][value_key].append(float(value))
    return [
        {"month": month, **{key: round(sum(values) / len(values), 4) for key, values in fields.items() if values}}
        for month, fields in sorted(monthly.items())
    ]


def merge_rows(base: list[dict[str, object]], overlay: list[dict[str, object]]) -> list[dict[str, object]]:
    merged = {str(row["month"]): dict(row) for row in base}
    for row in overlay:
        merged.setdefault(str(row["month"]), {"month": row["month"]}).update(row)
    return [merged[month] for month in sorted(merged)]


def fetch_fear_greed() -> list[dict[str, object]]:
    payload = json.loads(
        download(
            CNN_FEAR_GREED_URL,
            headers={"Accept": "application/json, text/plain, */*", "Referer": "https://www.cnn.com/"},
        ).decode("utf-8")
    )
    historical = payload.get("fear_and_greed_historical", {}).get("data", [])
    by_month: dict[str, dict[str, object]] = {}
    for point in historical:
        timestamp = point.get("x")
        score = point.get("y")
        if timestamp is None or score is None:
            continue
        month = datetime.fromtimestamp(float(timestamp) / 1000, tz=timezone.utc).strftime("%Y-%m")
        by_month[month] = {"month": month, "score": round(float(score), 2)}
    return [by_month[month] for month in sorted(by_month)]


def fetch_money_supply() -> list[dict[str, object]]:
    """Fetch Bank of Korea M1/M2 monthly averages, in trillion won."""
    series = json.loads(download(MONEY_SUPPLY_URL, headers={"Accept": "application/json"}).decode("utf-8"))
    if not isinstance(series, list) or len(series) < 2:
        raise ValueError("한국은행 M1·M2 응답 형식이 올바르지 않습니다.")
    by_month: dict[str, dict[str, object]] = {}
    for value_key, points in zip(("m1_trillion_krw", "m2_trillion_krw"), series[:2]):
        for timestamp, value in points:
            month = datetime.fromtimestamp(float(timestamp) / 1000, tz=timezone.utc).strftime("%Y-%m")
            by_month.setdefault(month, {"month": month})[value_key] = round(float(value), 4)
    return [by_month[month] for month in sorted(by_month)]


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
    for output_key, mapping in GROUPED_FRED_SERIES.items():
        try:
            payload[output_key] = merge_rows(existing.get(output_key, []), fetch_fred_group(mapping))
        except Exception as error:
            if output_key not in existing:
                raise
            payload[output_key] = existing[output_key]
            print(f"{output_key} 갱신 실패, 기존 자료 유지: {error}")
    try:
        payload["metal_prices"] = merge_rows(payload["metal_prices"], fetch_yahoo_monthly(YAHOO_METAL_SERIES))
    except Exception as error:
        print(f"금·은 선물 월말가격 갱신 실패, 구리 자료만 유지: {error}")
    try:
        copper = fetch_yahoo_monthly({"copper_usd_ton": "HG=F"})
        payload["metal_prices"] = merge_rows(
            payload["metal_prices"],
            convert_field(copper, "copper_usd_ton", 2204.62262185),
        )
    except Exception as error:
        print(f"구리 당월 선물가격 갱신 실패, 공식 월간자료 유지: {error}")
    for output_key, mapping in YAHOO_CURRENT_MONTH_GROUPS.items():
        try:
            current_rows = latest_month_rows(fetch_yahoo_monthly(mapping))
            payload[output_key] = merge_rows(payload[output_key], current_rows)
        except Exception as error:
            print(f"{output_key} 당월 공개시세 갱신 실패, 공식 월간자료 유지: {error}")
    try:
        exact_korean_bonds = fetch_bok_bond_yields()
        if exact_korean_bonds:
            payload["bond_yields"] = merge_rows(payload["bond_yields"], exact_korean_bonds)
    except Exception as error:
        print(f"한국은행 만기별 국고채 갱신 실패, FRED 대용지표 유지: {error}")
    try:
        payload["bond_yields"] = merge_rows(payload["bond_yields"], fetch_japan_bond_yields())
    except Exception as error:
        print(f"일본 재무성 만기별 국채 갱신 실패, FRED 대용지표 유지: {error}")
    try:
        payload["market_indices"] = merge_rows(existing.get("market_indices", []), fetch_yahoo_monthly())
    except Exception as error:
        if "market_indices" not in existing:
            raise
        payload["market_indices"] = existing["market_indices"]
        print(f"시장지수 갱신 실패, 기존 자료 유지: {error}")
    try:
        payload["fear_greed"] = fetch_fear_greed()
    except Exception as error:
        if "fear_greed" not in existing:
            payload["fear_greed"] = []
        else:
            payload["fear_greed"] = existing["fear_greed"]
        print(f"CNN 공포·탐욕지수 갱신 실패, 기존 자료 유지: {error}")
    try:
        payload["money_supply"] = fetch_money_supply()
    except Exception as error:
        if "money_supply" not in existing:
            raise
        payload["money_supply"] = existing["money_supply"]
        print(f"한국은행 M1·M2 갱신 실패, 기존 자료 유지: {error}")
    payload["exchange_rates"] = filter_numeric_range(
        payload.get("exchange_rates", []), "krw_per_usd", 500.0, 3000.0
    )
    base_rates = [{"date": date, "rate": rate} for date, rate in BASE_RATES]
    try:
        official_base_rates = fetch_bok_base_rates()
        if official_base_rates:
            base_rates = official_base_rates
    except Exception as error:
        print(f"한국은행 기준금리 갱신 실패, 내장 이력 유지: {error}")
    payload.update(
        {
            "base_rates": base_rates,
            "policies": POLICIES,
            "sources": {
                "exchange_rate": "https://fred.stlouisfed.org/series/EXKOUS/",
                "base_rate": "https://www.bok.or.kr/portal/singl/baseRate/list.do?menuNo=200656",
                "us_policy_rate": "https://fred.stlouisfed.org/series/FEDFUNDS",
                "japan_policy_rate": "https://fred.stlouisfed.org/series/IRSTCI01JPM156N",
                "money_supply": "https://snapshot.bok.or.kr/chart.html?id=527",
                "metals": "https://fred.stlouisfed.org/categories/32217",
                "bond_yields": "https://fred.stlouisfed.org/tags/series?t=bonds%3Bgovernment%3Byield",
                "korean_bond_yields": "https://ecos.bok.or.kr/",
                "japanese_bond_yields": JAPAN_MOF_BOND_URL,
                "oil_prices": "https://fred.stlouisfed.org/tags/series?t=crude%3Bmonthly",
                "market_indices": "https://finance.yahoo.com/markets/",
                "fear_greed": "https://www.cnn.com/markets/fear-and-greed",
                "policies": "https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp",
            },
            "metadata": {
                "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "refresh_frequency": "multiple-times-daily",
                "observation_frequency": "지표별 일·월·정책변경 시점",
                "current_month_overlay": "환율·금속·원유·미국채·시장지수는 일일 공개시세의 당월 최신값을 포함하며 월이 끝나기 전에는 잠정치입니다.",
                "bond_notes": {
                    "kr_short_proxy": "한국 1년 국채 자료가 없을 때 OECD 단기금리를 대용지표로 사용합니다.",
                    "jp_1y": "일본 재무성 1년 만기 국채 수익률의 월평균입니다.",
                    "kr_30y": "BOK_ECOS_API_KEY가 설정된 실행에서 한국은행 국고채 30년 월평균을 추가합니다.",
                    "jp_30y": "일본 재무성 30년 만기 국채 수익률의 월평균입니다.",
                },
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
        + ", ".join(
            f"{key} {len(payload.get(key, []))}개월"
            for key in (*FRED_SERIES, *GROUPED_FRED_SERIES, "market_indices", "fear_greed", "money_supply")
        )
    )


if __name__ == "__main__":
    main()
