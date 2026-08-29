from __future__ import annotations
from datetime import date
from dateutil.relativedelta import relativedelta

def month_range(start_ym: str, end_ym: str) -> list[str]:
    start = date(int(start_ym[:4]), int(start_ym[4:6]), 1)
    end = date(int(end_ym[:4]), int(end_ym[4:6]), 1)
    if start > end:
        raise ValueError("시작월이 종료월보다 늦습니다.")
    result = []
    cur = start
    while cur <= end:
        result.append(cur.strftime("%Y%m"))
        cur += relativedelta(months=1)
    return result

def recent_month_range(months: int) -> tuple[str, str]:
    end = date.today().replace(day=1)
    start = end - relativedelta(months=months - 1)
    return start.strftime("%Y%m"), end.strftime("%Y%m")
