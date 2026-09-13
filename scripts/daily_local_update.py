from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from realestate.local_collect import Region, collect, target_regions
from realestate.local_store import LocalStore


ROOT = Path(__file__).resolve().parents[1]
ROTATION_PATH = ROOT / "data" / "local" / "latest_rotation.json"
RUN_STATE_PATH = ROOT / "data" / "local" / "collection_state.json"
LATEST_REGION_COUNT = 15
HISTORY_JOB_COUNT = 2_500
ONE_DAY_PRIORITY_DATE = date(2026, 9, 15)
ONE_DAY_PRIORITY_CODES = (
    "41135",  # 경기 성남시 분당구
    "48121",  # 경남 창원시 의창구
    "48123",  # 경남 창원시 성산구
    "48125",  # 경남 창원시 마산합포구
    "48127",  # 경남 창원시 마산회원구
    "48129",  # 경남 창원시 진해구
)


def one_day_priority_regions(regions: list[Region], run_date: date) -> list[Region]:
    """Return the requested districts only for the explicitly scheduled day."""
    if run_date != ONE_DAY_PRIORITY_DATE:
        return []
    by_code = {region.lawd_cd: region for region in regions}
    return [by_code[code] for code in ONE_DAY_PRIORITY_CODES if code in by_code]


def select_stalest_regions(
    regions: list[Region], count: int, year: int, *, root: Path = ROOT
) -> list[Region]:
    """Refresh the oldest current-year regions first, never yesterday's while older data exists."""
    store = LocalStore(root)
    with store.connect() as db:
        updated = {
            row["lawd_cd"]: row["updated_at"]
            for row in db.execute(
                "SELECT lawd_cd, updated_at FROM collection_status WHERE year=? AND status='ok'",
                (year,),
            )
        }
    return sorted(regions, key=lambda region: (updated.get(region.lawd_cd, ""), region.lawd_cd))[:count]


def load_rotation(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        return max(0, int(state.get("next", 0)))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        print("[회전 상태 복구] 상태 파일을 읽지 못해 첫 지역부터 다시 시작합니다.", flush=True)
        return 0


def save_rotation(path: Path, next_index: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            {"next": next_index, "updated_at": datetime.now().isoformat(timespec="seconds")},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def write_run_state(state: str, phase: str, message: str, **details: object) -> None:
    RUN_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "state": state,
        "phase": phase,
        "message": message,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        **details,
    }
    temporary = RUN_STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(RUN_STATE_PATH)


def main() -> None:
    started_at = datetime.now().isoformat(timespec="seconds")
    try:
        run_date = date.today()
        regions = target_regions(ROOT / "data" / "raw" / "complexes.csv")
        if not regions:
            raise RuntimeError("수집할 지역이 없습니다. 단지 원본 데이터를 확인하세요.")

        priority_regions = one_day_priority_regions(regions, run_date)
        priority = None
        priority_failures: list[dict] = []
        if priority_regions:
            priority_codes = {region.lawd_cd for region in priority_regions}
            priority_names = ", ".join(region.region_name for region in priority_regions)
            write_run_state(
                "running",
                "latest",
                "2026년 9월 15일 한정으로 분당구 전체와 창원시 전체의 최신 신고분을 먼저 갱신 중입니다.",
                started_at=started_at,
                planned_latest_jobs=len(priority_regions),
                one_day_priority={"date": run_date.isoformat(), "regions": priority_names},
            )
            print(f"[9월 15일 한정 최우선 최신 갱신] {priority_names}", flush=True)
            priority = collect(
                ROOT,
                codes=priority_codes,
                years=[run_date.year],
                force=True,
                max_jobs=len(priority_regions),
            )
            priority_failures = list(priority.get("failures", []))
            if priority.get("paused") and "일일 다운로드" in priority["paused"]:
                write_run_state(
                    "quota",
                    "latest",
                    "분당구·창원시 최신 신고분을 우선 갱신하던 중 오늘의 공식 다운로드 한도에 도달했습니다.",
                    started_at=started_at,
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                    latest=priority,
                    one_day_priority=priority,
                    failures=priority_failures,
                )
                return
            if priority_failures:
                write_run_state(
                    "completed_with_failures",
                    "latest",
                    f"분당구·창원시 우선 갱신 중 {len(priority_failures)}개 작업이 실패해 먼저 재시도합니다.",
                    started_at=started_at,
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                    latest=priority,
                    one_day_priority=priority,
                    failures=priority_failures,
                )
                return

        write_run_state(
            "running",
            "history",
            f"서울·경기·충북·경남·부산 완주 후 서울 인접 순으로 전국 미수집 이력 최대 {HISTORY_JOB_COUNT}개 연도를 묶음 수집 중입니다.",
            started_at=started_at,
            planned_history_jobs=HISTORY_JOB_COUNT,
            one_day_priority=priority,
        )
        print(
            f"[전국 미수집 이력 최우선] 서울·경기·충북·경남·부산 후 서울 인접 순, 최대 {HISTORY_JOB_COUNT}개 연도를 전체 범위부터 시작해 실패 시 자동 분할",
            flush=True,
        )
        history = collect(ROOT, max_jobs=HISTORY_JOB_COUNT)
        failures = priority_failures + list(history.get("failures", []))
        if history.get("paused") and "일일 다운로드" in history["paused"]:
            write_run_state(
                "quota",
                "history",
                "오늘 사용 가능한 공식 다운로드를 미수집 이력에 모두 사용했습니다. 다음 날짜에 자동 재개합니다.",
                started_at=started_at,
                finished_at=datetime.now().isoformat(timespec="seconds"),
                history=history,
                one_day_priority=priority,
                failures=failures,
            )
            print("[다음 날짜 재개] 오늘 한도를 미수집 이력에 모두 사용했습니다.", flush=True)
            return
        if failures:
            write_run_state(
                "completed_with_failures",
                "history",
                f"미수집 이력 {len(failures)}개 작업이 실패해 최신 자료 갱신보다 먼저 재시도합니다.",
                started_at=started_at,
                finished_at=datetime.now().isoformat(timespec="seconds"),
                history=history,
                one_day_priority=priority,
                failures=failures,
            )
            return

        priority_codes = {region.lawd_cd for region in priority_regions}
        latest_pool = [region for region in regions if region.lawd_cd not in priority_codes]
        selection_count = min(LATEST_REGION_COUNT, len(latest_pool))
        selected = select_stalest_regions(latest_pool, selection_count, run_date.year)
        codes = {region.lawd_cd for region in selected}
        write_run_state(
            "running",
            "latest",
            f"미수집 이력을 모두 채워 가장 오래된 최신 자료 {selection_count}개 지역을 갱신 중입니다.",
            started_at=started_at,
            history=history,
            one_day_priority=priority,
            planned_latest_jobs=selection_count,
        )
        print("[오래된 최신 자료 갱신] " + ", ".join(region.region_name for region in selected), flush=True)
        latest = collect(ROOT, codes=codes, years=[run_date.year], force=True, max_jobs=selection_count)
        failures = priority_failures + list(latest.get("failures", []))
        if latest.get("paused") and "일일 다운로드" in latest["paused"]:
            write_run_state(
                "quota",
                "latest",
                "미수집 이력 완료 후 최신 자료 갱신 중 오늘 한도에 도달했습니다.",
                started_at=started_at,
                finished_at=datetime.now().isoformat(timespec="seconds"),
                history=history,
                latest=latest,
                one_day_priority=priority,
                failures=failures,
            )
            return

        write_run_state(
            "completed_with_failures" if failures else "completed",
            "finished",
            "오늘의 수집을 마쳤습니다." if not failures else f"수집을 마쳤지만 {len(failures)}개 작업은 재시도 대상입니다.",
            started_at=started_at,
            finished_at=datetime.now().isoformat(timespec="seconds"),
            latest=latest,
            history=history,
            one_day_priority=priority,
            failures=failures,
        )
        print("[일일 작업 종료] 다음 실행에서 자동으로 이어집니다.", flush=True)
    except Exception as error:
        write_run_state(
            "failed",
            "failed",
            f"수집을 시작하거나 진행하는 중 오류가 발생했습니다: {error}",
            started_at=started_at,
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )
        raise


if __name__ == "__main__":
    main()
