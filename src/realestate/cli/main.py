from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

from realestate.analysis.publish import build_public_data
from realestate.collectors.complexes import collect_complexes
from realestate.collectors.trades import collect_trades
from realestate.core.dates import month_range, recent_month_range
from realestate.core.regions import priority_regions_from_complexes
from realestate.core.settings import ROOT, load_settings


EARLIEST_TRADE_MONTH = "200601"


def main() -> None:
    parser = argparse.ArgumentParser(description="전국 부동산 데이터 플랫폼")
    sub = parser.add_subparsers(dest="command", required=True)

    collect = sub.add_parser("collect")
    collect.add_argument("--regions", default=str(ROOT / "config/regions.csv"))
    collect.add_argument(
        "--priority-coverage",
        action="store_true",
        help="서울·경기·부산 전역과 청주·창원 전역의 법정동 코드를 단지 목록에서 생성",
    )
    collect.add_argument(
        "--complexes",
        default=str(ROOT / "data/raw/complexes.csv"),
        help="우선 갱신 지역을 만들 공동주택 단지 목록 CSV",
    )
    collect.add_argument("--start")
    collect.add_argument("--end")
    collect.add_argument("--months", type=int, default=2)
    collect.add_argument("--all-history", action="store_true")
    collect.add_argument("--codes")
    collect.add_argument("--output", default=str(ROOT / "data/raw/trades"))
    collect.add_argument(
        "--failure-report",
        default=str(ROOT / "data/reports/trade_collection_failures.json"),
    )

    complexes = sub.add_parser("collect-complexes")
    complexes.add_argument("--output", default=str(ROOT / "data/raw/complexes.csv"))

    sub.add_parser("publish")

    args = parser.parse_args()
    settings = load_settings()

    if args.command == "collect":
        regions_path = Path(args.regions)
        if args.priority_coverage:
            regions = priority_regions_from_complexes(
                Path(args.complexes),
                regions_path,
            )
        else:
            regions = pd.read_csv(regions_path, dtype={"lawd_cd": str})
            regions["lawd_cd"] = regions["lawd_cd"].astype(str).str.zfill(5)

        if args.codes:
            wanted = {item.strip().zfill(5) for item in args.codes.split(",")}
            regions = regions[regions["lawd_cd"].isin(wanted)]

        if args.all_history:
            months = month_range(
                EARLIEST_TRADE_MONTH,
                date.today().strftime("%Y%m"),
            )
        elif args.start and args.end:
            months = month_range(args.start, args.end)
        else:
            start, end = recent_month_range(args.months)
            months = month_range(start, end)

        if len(months) > settings.max_months_per_run:
            raise SystemExit(
                f"한 번에 최대 {settings.max_months_per_run}개월입니다."
            )
        if regions.empty:
            raise SystemExit("수집할 지역이 없습니다.")

        print(
            f"[PLAN] {len(regions):,}개 지역 × {len(months):,}개월을 수집합니다.",
            flush=True,
        )
        collect_trades(
            settings,
            regions,
            months,
            Path(args.output),
            Path(args.failure_report) if args.failure_report else None,
        )
        return

    if args.command == "collect-complexes":
        collect_complexes(settings, Path(args.output))
        return

    build_public_data(ROOT)
    print("공개 JSON 생성 완료")


if __name__ == "__main__":
    main()
