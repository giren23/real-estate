from __future__ import annotations

import csv
import gzip
import io
import json
import random
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from realestate.local_store import LocalStore, is_target_lawd


RTMS_PAGE = "https://rt.molit.go.kr/pt/xls/xls.do"
RTMS_CSV = "https://rt.molit.go.kr/pt/xls/ptXlsCSVDown.do"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Safari/537.36"
)
PRIORITY_REGION_CODES = ("11200",)
PRIORITY_CODE_PREFIXES = ("11", "41", "4311", "4812")
# The official history currently starts in 2006. Keep this wider than the full
# history so one district can normally be filled with a single download.
MAX_BULK_YEARS = 30


class DailyQuotaError(RuntimeError):
    pass


@dataclass(frozen=True)
class Region:
    lawd_cd: str
    region_name: str
    sido: str
    sigungu: str


def target_regions(complex_csv: Path) -> list[Region]:
    found: dict[str, Region] = {}
    with Path(complex_csv).open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            code = str(row.get("bjd_code", "")).replace(".0", "").zfill(10)[:5]
            if not is_target_lawd(code):
                continue
            found.setdefault(
                code,
                Region(
                    lawd_cd=code,
                    region_name=(row.get("region_name") or "").strip(),
                    sido=(row.get("sido") or "").strip(),
                    sigungu=(row.get("sigungu") or "").strip(),
                ),
            )
    return sorted(found.values(), key=region_priority)


def region_priority(region: Region) -> tuple[int, str]:
    """Keep collection focused on Oksu-dong's district, then requested areas."""
    code = region.lawd_cd
    if code in PRIORITY_REGION_CODES:
        return (0, code)
    for order, prefix in enumerate(PRIORITY_CODE_PREFIXES, start=1):
        if code.startswith(prefix):
            return (order, code)
    return (len(PRIORITY_CODE_PREFIXES) + 1, code)


def _decode(content: bytes) -> str:
    for encoding in ("cp949", "utf-8-sig", "utf-8"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise RuntimeError("공식 CSV의 문자 인코딩을 해석하지 못했습니다.")


def parse_rtms_csv(content: bytes | str, region: Region) -> list[dict]:
    text = _decode(content) if isinstance(content, bytes) else content
    lines = text.splitlines()
    try:
        header_index = next(i for i, line in enumerate(lines) if "거래금액(만원)" in line and "단지명" in line)
    except StopIteration as exc:
        preview = " ".join(lines[:3])[:240]
        raise RuntimeError(f"공식 CSV 헤더가 없습니다: {preview}") from exc

    trades: list[dict] = []
    for item in csv.DictReader(io.StringIO("\n".join(lines[header_index:]))):
        if (item.get("해제사유발생일") or "").strip() not in {"", "-"}:
            continue
        deal_ym = (item.get("계약년월") or "").strip()
        apt_name = (item.get("단지명") or "").strip()
        place = (item.get("시군구") or "").strip()
        if not (len(deal_ym) == 6 and deal_ym.isdigit() and apt_name and place):
            continue
        try:
            day = int((item.get("계약일") or "0").strip())
            price = int((item.get("거래금액(만원)") or "0").replace(",", "").strip())
            area = float((item.get("전용면적(㎡)") or "0").strip())
        except ValueError:
            continue
        if day <= 0 or price <= 0 or area <= 0:
            continue
        dong = place.split()[-1]
        floor_text = (item.get("층") or "").strip()
        build_year_text = (item.get("건축년도") or "").strip()
        pyeong = area / 3.3058
        trades.append(
            {
                "lawd_cd": region.lawd_cd,
                "region_name": region.region_name,
                "dong": dong,
                "jibun": (item.get("번지") or "").strip(),
                "apt_name": apt_name,
                "area_m2": area,
                "deal_ym": deal_ym,
                "trade_date": f"{deal_ym[:4]}-{deal_ym[4:]}-{day:02d}",
                "apt_dong": (item.get("동") or "").strip(),
                "floor": int(floor_text) if floor_text.lstrip("-").isdigit() else None,
                "build_year": int(build_year_text) if build_year_text.isdigit() else None,
                "price_manwon": price,
                "price_eok": price / 10000,
                "price_per_m2_manwon": round(price / area, 2),
                "price_per_pyeong_manwon": round(price / pyeong, 2),
                "deal_type": (item.get("거래유형") or "").strip(),
                "registration_date": (item.get("등기일자") or "").strip(),
                "source_no": (item.get("NO") or "").strip(),
            }
        )
    return trades


class OfficialCsvCollector:
    def __init__(self, store: LocalStore, *, timeout: int = 90, delay: float = 1.5):
        self.store = store
        self.timeout = timeout
        self.delay = delay
        self.cache_dir = store.local_dir / "raw"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Referer": RTMS_PAGE})
        self._initialized = False

    def close(self) -> None:
        self.session.close()

    def _ensure_session(self) -> None:
        if self._initialized:
            return
        response = self.session.get(RTMS_PAGE, timeout=30)
        response.raise_for_status()
        self._initialized = True

    def _payload(self, region: Region, start: date, end: date) -> dict[str, str]:
        return {
            "srhThingNo": "A",
            "srhDelngSecd": "1",
            "srhAddrGbn": "1",
            "srhLfstsSecd": "1",
            "srhFromDt": start.isoformat(),
            "srhToDt": end.isoformat(),
            "srhNewRonSecd": "",
            "srhSidoCd": region.lawd_cd[:2] + "000",
            "srhSggCd": region.lawd_cd,
            "srhEmdCd": "",
            "srhLoadCd": "",
            "srhHsmpCd": "",
            "srhArea": "",
            "srhLrArea": "",
            "srhFromAmount": "",
            "srhToAmount": "",
            "sidoNm": region.sido,
            "sggNm": region.sigungu,
            "emdNm": "전체",
            "loadNm": "전체",
            "areaNm": "전체",
            "hsmpNm": "전체",
        }

    def _download(self, region: Region, start: date, end: date) -> bytes:
        self._ensure_session()
        started = time.monotonic()
        response = self.session.post(
            RTMS_CSV,
            data=self._payload(region, start, end),
            timeout=(15, min(self.timeout, 30)),
            stream=True,
        )
        response.raise_for_status()
        chunks: list[bytes] = []
        for chunk in response.iter_content(chunk_size=256 * 1024):
            if chunk:
                chunks.append(chunk)
            if time.monotonic() - started > self.timeout:
                response.close()
                raise TimeoutError(f"공식 CSV 다운로드가 {self.timeout}초를 초과했습니다")
        content = b"".join(chunks)
        if len(content) < 500:
            try:
                message = json.loads(content.decode("utf-8")).get("error", "")
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                message = ""
            if "일일 다운로드 횟수" in message:
                raise DailyQuotaError(message)
        if len(content) < 200 or content.lstrip().startswith(b"<"):
            raise RuntimeError(f"공식 CSV 응답이 올바르지 않습니다({len(content)} bytes)")
        parse_rtms_csv(content, region)
        time.sleep(self.delay + random.uniform(0, 0.2))
        return content

    def _download_twice(self, region: Region, start: date, end: date) -> tuple[bytes, int]:
        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
                return self._download(region, start, end), attempt
            except DailyQuotaError:
                raise
            except Exception as exc:  # continue by design and report at the end
                last_error = exc
                print(f"[재시도 {attempt}/2] {region.region_name} {start}~{end}: {exc}", flush=True)
                self._initialized = False
                if attempt == 1:
                    time.sleep(15)
        raise RuntimeError(str(last_error))

    def _year_cache(self, region: Region, year: int) -> Path:
        return self.cache_dir / region.lawd_cd / f"{year}.csv.gz"

    def recommended_year_span(self, region: Region) -> int:
        """Start with the widest range; failed downloads are split automatically."""
        return MAX_BULK_YEARS

    def collect_year_span(self, region: Region, years: list[int]) -> dict[int, int]:
        """Download several contiguous years once, then validate and store each year separately."""
        years = sorted(set(years))
        if len(years) < 2 or years != list(range(years[0], years[-1] + 1)):
            raise ValueError("묶음 다운로드 연도는 2개 이상의 연속된 범위여야 합니다.")
        start = date(years[0], 1, 1)
        end = min(date(years[-1], 12, 31), date.today())
        content = self._download(region, start, end)
        trades = parse_rtms_csv(content, region)
        requested = set(years)
        unexpected = sorted({int(row["deal_ym"][:4]) for row in trades if int(row["deal_ym"][:4]) not in requested})
        if unexpected:
            raise RuntimeError(f"요청 범위 밖 연도가 포함됐습니다: {unexpected}")

        audit_path = self.cache_dir / "bulk" / region.lawd_cd / f"{years[0]}-{years[-1]}.csv.gz"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_tmp = audit_path.with_suffix(audit_path.suffix + ".tmp")
        audit_tmp.write_bytes(gzip.compress(content, compresslevel=6))
        audit_tmp.replace(audit_path)

        by_year: dict[int, list[dict]] = {year: [] for year in years}
        for row in trades:
            by_year[int(row["deal_ym"][:4])].append(row)

        counts: dict[int, int] = {}
        updated_at = datetime.now().isoformat(timespec="seconds")
        for year in years:
            rows = by_year[year]
            cache_path = self._year_cache(region, year).with_suffix(".json.gz")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
            temporary.write_bytes(gzip.compress(json.dumps(rows, ensure_ascii=False).encode("utf-8"), compresslevel=6))
            temporary.replace(cache_path)
            count = self.store.replace_region_year(region.lawd_cd, year, rows)
            self.store.status(region.lawd_cd, year, "ok", 1, count, updated_at, f"{years[0]}-{years[-1]} 묶음 다운로드")
            counts[year] = count
            print(f"[완료] {region.region_name} {year}: {count:,}건 (묶음)", flush=True)
        return counts

    def collect_year(self, region: Region, year: int, *, force: bool = False) -> int:
        previously_completed = self.store.completed(region.lawd_cd, year)
        if not force and previously_completed:
            print(f"[건너뜀] {region.region_name} {year}: 이미 완료", flush=True)
            return -1
        cache_path = self._year_cache(region, year)
        json_cache_path = cache_path.with_suffix(".json.gz")
        start = date(year, 1, 1)
        end = min(date(year, 12, 31), date.today())
        attempts = 0
        try:
            if (cache_path.exists() or json_cache_path.exists()) and not force:
                selected_cache = cache_path if cache_path.exists() else json_cache_path
                content = gzip.decompress(selected_cache.read_bytes())
                trades = json.loads(content.decode("utf-8")) if selected_cache.name.endswith(".json.gz") else parse_rtms_csv(content, region)
                print(f"[캐시] {region.region_name} {year}: {len(trades):,}건", flush=True)
            else:
                try:
                    content, attempts = self._download_twice(region, start, end)
                    trades = parse_rtms_csv(content, region)
                except DailyQuotaError:
                    raise
                except Exception as yearly_error:
                    print(f"[우회] {region.region_name} {year}: 연간 다운로드 실패, 분기별로 전환 ({yearly_error})", flush=True)
                    chunks: list[bytes] = []
                    trades = []
                    for month_start, month_end in ((1, 3), (4, 6), (7, 9), (10, 12)):
                        quarter_start = date(year, month_start, 1)
                        quarter_end = min(date(year, month_end + 1, 1), date.today()) if month_end < 12 else min(date(year, 12, 31), date.today())
                        if month_end < 12:
                            quarter_end -= timedelta(days=1)
                        if quarter_start > end:
                            continue
                        chunk, used = self._download_twice(region, quarter_start, quarter_end)
                        attempts += used
                        chunks.append(chunk)
                        trades.extend(parse_rtms_csv(chunk, region))
                    content = json.dumps(trades, ensure_ascii=False).encode("utf-8")
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                if content.startswith(b"["):
                    cache_path = json_cache_path
                cache_path.write_bytes(gzip.compress(content, compresslevel=6))

            count = self.store.replace_region_year(region.lawd_cd, year, trades)
            self.store.status(region.lawd_cd, year, "ok", max(attempts, 1), count, datetime.now().isoformat(timespec="seconds"))
            print(f"[완료] {region.region_name} {year}: {count:,}건", flush=True)
            return count
        except DailyQuotaError as exc:
            if not previously_completed:
                self.store.status(region.lawd_cd, year, "quota", max(attempts, 1), 0, datetime.now().isoformat(timespec="seconds"), str(exc))
            print(f"[오늘 한도 도달] {region.region_name} {year}: "+("기존 완료 자료 유지" if previously_completed else "내일 자동 재개"), flush=True)
            raise
        except Exception as exc:
            if not previously_completed:
                self.store.status(region.lawd_cd, year, "failed", max(attempts, 2), 0, datetime.now().isoformat(timespec="seconds"), str(exc))
            print(f"[실패] {region.region_name} {year}: {exc}"+(" (기존 완료 자료 유지)" if previously_completed else ""), flush=True)
            raise


def _year_batches(years: list[int], max_span: int) -> list[list[int]]:
    """Split sorted years into contiguous batches without bridging completed gaps."""
    batches: list[list[int]] = []
    contiguous: list[int] = []
    for year in sorted(set(years)):
        if contiguous and year != contiguous[-1] + 1:
            batches.extend(contiguous[index:index + max_span] for index in range(0, len(contiguous), max_span))
            contiguous = []
        contiguous.append(year)
    if contiguous:
        batches.extend(contiguous[index:index + max_span] for index in range(0, len(contiguous), max_span))
    return batches


def collect(
    root: Path,
    *,
    codes: set[str] | None = None,
    years: list[int] | None = None,
    force: bool = False,
    continue_on_error: bool = True,
    max_jobs: int | None = None,
) -> dict:
    store = LocalStore(root)
    store.initialize()
    regions = target_regions(root / "data" / "raw" / "complexes.csv")
    if codes:
        regions = [region for region in regions if region.lawd_cd in codes]
    requested_years = years or list(range(2006, date.today().year + 1))
    collector = OfficialCsvCollector(store)
    failures: list[dict] = []
    completed = rows = attempted = 0
    last_catalog_completed = 0
    paused = ""
    total = len(regions) * len(requested_years)
    try:
        for region in regions:
            pending = [year for year in requested_years if force or not store.completed(region.lawd_cd, year)]
            if max_jobs:
                pending = pending[:max(0, max_jobs - attempted)]
            if not pending:
                if max_jobs and attempted >= max_jobs:
                    paused = f"오늘 계획한 {max_jobs}개 지역·연도 작업 완료"
                    break
                continue

            span = 1 if len(requested_years) == 1 else collector.recommended_year_span(region)
            queue = _year_batches(pending, span)
            print(f"[묶음 계획] {region.region_name}: 최대 {span}년씩, 미완료 {len(pending)}개 연도", flush=True)
            while queue:
                batch = queue.pop(0)
                label = str(batch[0]) if len(batch) == 1 else f"{batch[0]}-{batch[-1]}"
                print(f"[진행 {attempted + 1}/{max_jobs or total}] {region.region_name} {label}", flush=True)
                try:
                    if len(batch) == 1:
                        count = collector.collect_year(region, batch[0], force=force)
                        counts = {batch[0]: count}
                    else:
                        counts = collector.collect_year_span(region, batch)
                    completed += len(batch)
                    attempted += len(batch)
                    rows += sum(max(0, count) for count in counts.values())
                except DailyQuotaError as exc:
                    paused = str(exc)
                    break
                except Exception as exc:
                    if len(batch) > 1:
                        midpoint = len(batch) // 2
                        left, right = batch[:midpoint], batch[midpoint:]
                        print(f"[자동 분할] {region.region_name} {label}: {exc}", flush=True)
                        queue[0:0] = [left, right]
                        continue
                    attempted += 1
                    failures.append({"lawd_cd": region.lawd_cd, "region": region.region_name, "year": batch[0], "error": str(exc)})
                    if not continue_on_error:
                        raise

                if completed - last_catalog_completed >= 10:
                    store.build_catalog()
                    last_catalog_completed = completed
            if paused:
                break
            if max_jobs and attempted >= max_jobs:
                paused = f"오늘 계획한 {max_jobs}개 지역·연도 작업 완료"
                break
    finally:
        collector.close()
        catalog = store.build_catalog()
        report = {
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "completed_jobs": completed,
            "new_rows": rows,
            "failures": failures,
            "paused": paused,
            "meta": catalog["meta"],
        }
        store.status_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
