import pandas as pd
from realestate.analysis.metrics import apartment_metrics

def test_apartment_metrics():
    df = pd.DataFrame([
        {"lawd_cd":"41135","region_name":"분당구","dong":"정자동","apt_name":"A","area_m2":84.9,
         "trade_date":"2026-01-01","price_eok":15.0,"price_per_pyeong_manwon":5800},
        {"lawd_cd":"41135","region_name":"분당구","dong":"정자동","apt_name":"A","area_m2":84.9,
         "trade_date":"2026-06-01","price_eok":17.0,"price_per_pyeong_manwon":6600},
    ])
    row = apartment_metrics(df).iloc[0]
    assert row["range_eok"] == 2.0
    assert round(row["change_pct"], 2) == 13.33
