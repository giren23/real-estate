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
        regions = target_regions(ROOT / "data" / "raw" / "complexes.csv")
        if not regions:
            raise RuntimeError("수집할 지역이 없습니다. 단지 원본 데이터를 확인하세요.")

        write_run_state(
            "running",
            "history",
            f"미수집 과거 이력 최대 {HISTORY_JOB_COUNT}개 연도를 최우선 묶음 수집 중입니다.",
            started_at=started_at,
            planned_history_jobs=HISTORY_JOB_COUNT,
        )
        print(
            f"[미수집 이력 최우선] 최대 {HISTORY_JOB_COUNT}개 연도를 전체 범위부터 시작해 실패 시 자동 분할",
            flush=True,
        )
        history = collect(ROOT, max_jobs=HISTORY_JOB_COUNT)
        failures = list(history.get("failures", []))
        if history.get("paused") and "일일 다운로드" in history["paused"]:
            write_run_state(
                "quota",
                "history",
                "오늘 사용 가능한 공식 다운로드를 미수집 이력에 모두 사용했습니다. 다음 날짜에 자동 재개합니다.",
                started_at=started_at,
                finished_at=datetime.now().isoformat(timespec="seconds"),
                history=history,
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
                failures=failures,
            )
            return

        selection_count = min(LATEST_REGION_COUNT, len(regions))
        selected = select_stalest_regions(regions, selection_count, date.today().year)
        codes = {region.lawd_cd for region in selected}
        write_run_state(
            "running",
            "latest",
            f"미수집 이력을 모두 채워 가장 오래된 최신 자료 {selection_count}개 지역을 갱신 중입니다.",
            started_at=started_at,
            history=history,
            planned_latest_jobs=selection_count,
        )
        print("[오래된 최신 자료 갱신] " + ", ".join(region.region_name for region in selected), flush=True)
        latest = collect(ROOT, codes=codes, years=[date.today().year], force=True, max_jobs=selection_count)
        failures = list(latest.get("failures", []))
        if latest.get("paused") and "일일 다운로드" in latest["paused"]:
            write_run_state(
                "quota",
                "latest",
                "미수집 이력 완료 후 최신 자료 갱신 중 오늘 한도에 도달했습니다.",
                started_at=started_at,
                finished_at=datetime.now().isoformat(timespec="seconds"),
                history=history,
                latest=latest,
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
