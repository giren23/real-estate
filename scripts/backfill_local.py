from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from realestate.local_collect import collect
from realestate.local_store import LocalStore


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="공식 실거래 CSV를 로컬 SQLite에 수집합니다.")
    parser.add_argument("--codes", default="", help="쉼표로 구분한 5자리 법정동 시군구 코드")
    parser.add_argument("--years", default="", help="쉼표/범위 예: 2006-2026 또는 2025,2026")
    parser.add_argument("--current-year", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--initialize-only", action="store_true")
    parser.add_argument("--max-jobs", type=int, default=0, help="이번 실행에서 새로 처리할 지역·연도 수")
    args = parser.parse_args()

    store = LocalStore(ROOT)
    store.initialize()
    complex_count = store.import_complexes(ROOT / "data" / "raw" / "complexes.csv")
    seeded = store.import_seed_public_data(ROOT / "data" / "public")
    catalog = store.build_catalog()
    print(
        f"[초기화] 대상 단지 {complex_count:,}개, 기존 월별이력 {seeded['history']:,}행, "
        f"최근 상세거래 {seeded['trades']:,}건",
        flush=True,
    )
    if args.initialize_only:
        print(f"[준비 완료] 검색 가능 {catalog['meta']['complex_count']:,}개", flush=True)
        return

    codes = {item.strip().zfill(5) for item in args.codes.split(",") if item.strip()} or None
    if args.current_year:
        years = [date.today().year]
    elif args.years:
        years = []
        for part in args.years.split(","):
            if "-" in part:
                first, last = map(int, part.split("-", 1))
                years.extend(range(first, last + 1))
            else:
                years.append(int(part))
        years = sorted(set(years))
    else:
        years = None

    report = collect(ROOT, codes=codes, years=years, force=args.force, max_jobs=args.max_jobs or None)
    if report["failures"]:
        print("\n[최종 실패 목록]", flush=True)
        for item in report["failures"]:
            print(f"- {item['region']} ({item['lawd_cd']}) {item['year']}: {item['error']}", flush=True)
        raise SystemExit(1)
    if report.get("paused"):
        print(f"[안전 중지] {report['paused']}", flush=True)
    print(f"[전체 완료] 작업 {report['completed_jobs']:,}개, 신규/교체 {report['new_rows']:,}건", flush=True)


if __name__ == "__main__":
    main()
