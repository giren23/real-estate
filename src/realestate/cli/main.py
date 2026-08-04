from __future__ import annotations
from pathlib import Path
import argparse
from datetime import date
import pandas as pd

from realestate.core.settings import ROOT, load_settings
from realestate.core.dates import month_range, recent_month_range
from realestate.collectors.trades import collect_trades
from realestate.collectors.complexes import collect_complexes
from realestate.analysis.publish import build_public_data

EARLIEST_TRADE_MONTH = "200601"

def main() -> None:
    parser = argparse.ArgumentParser(description="전국 부동산 데이터 플랫폼")
    sub = parser.add_subparsers(dest="command", required=True)

    collect = sub.add_parser("collect")
    collect.add_argument("--regions", default=str(ROOT / "config/regions.csv"))
    collect.add_argument("--start")
    collect.add_argument("--end")
    collect.add_argument("--months", type=int, default=2)
    collect.add_argument("--all-history", action="store_true")
    collect.add_argument("--codes")
    collect.add_argument("--output", default=str(ROOT / "data/raw/trades"))

    complexes = sub.add_parser("collect-complexes")
    complexes.add_argument("--output", default=str(ROOT / "data/raw/complexes.csv"))

    sub.add_parser("publish")

    args = parser.parse_args()
    settings = load_settings()

    if args.command == "collect":
        regions = pd.read_csv(args.regions, dtype={"lawd_cd": str})
        if args.codes:
            wanted = {x.strip() for x in args.codes.split(",")}
            regions = regions[regions["lawd_cd"].isin(wanted)]
        if args.all_history:
            months = month_range(EARLIEST_TRADE_MONTH, date.today().strftime("%Y%m"))
        elif args.start and args.end:
            months = month_range(args.start, args.end)
        else:
            start, end = recent_month_range(args.months)
            months = month_range(start, end)
        if len(months) > settings.max_months_per_run:
            raise SystemExit(f"한 번에 최대 {settings.max_months_per_run}개월입니다.")
        collect_trades(settings, regions, months, Path(args.output))
        return

    if args.command == "collect-complexes":
        collect_complexes(settings, Path(args.output))
        return

    build_public_data(ROOT)
    print("공개 JSON 생성 완료")

if __name__ == "__main__":
    main()
