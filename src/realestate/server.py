from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from datetime import date, datetime
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from realestate.local_store import LocalStore


ROOT = Path(os.environ.get("AISERVER_ROOT", Path(__file__).resolve().parents[2]))
STORE = LocalStore(ROOT)
STORE.initialize()
if not STORE.catalog_path.exists():
    STORE.import_complexes(ROOT / "data" / "raw" / "complexes.csv")
    STORE.import_seed_public_data(ROOT / "data" / "public")
    STORE.build_catalog()

app = FastAPI(title="Korean real estate prices local server", docs_url="/api/docs")
UPDATE_POLL_SECONDS = 60
TRANSIENT_RETRY_SECONDS = 600
MAP_CACHE_SECONDS = 60 * 60
MAP_QUERY_PADDING = 0.008
OVERPASS_URLS = (
    "https://lz4.overpass-api.de/api/interpreter",
)
_map_cache: list[dict] = []
_geocode_cache: dict[str, object] = {}
_nominatim_lock = threading.Lock()
_last_nominatim_request = 0.0


def _read_collection_state() -> dict:
    path = STORE.local_dir / "collection_state.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _finished_for_today(state: dict) -> bool:
    """Only stop retrying when work succeeded or the day's usable quota was consumed."""
    status = state.get("state")
    if status == "completed":
        return True
    if status == "quota":
        latest = state.get("latest") or {}
        # An immediate quota response just after midnight can be a delayed reset.
        # Retry it; if any latest work succeeded, the available quota was genuinely used.
        return state.get("phase") == "history" or int(latest.get("completed_jobs") or 0) > 0
    return False


def _daily_update_loop() -> None:
    marker = STORE.local_dir / "last_daily_update.txt"
    logs = STORE.local_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    retry_after = 0.0
    while True:
        already = marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
        # Start the day's collection as soon as the PC/server becomes available.
        # The marker still ensures that it runs at most once per calendar day.
        if already != date.today().isoformat() and time.monotonic() >= retry_after:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            with (logs / f"daily-{stamp}.log").open("a", encoding="utf-8") as output:
                process = subprocess.run(
                    [sys.executable, str(ROOT / "scripts" / "daily_local_update.py")],
                    cwd=ROOT,
                    env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    check=False,
                )
                # Market indicators and news use independent public sources, so a
                # housing-data quota response must not prevent their daily refresh.
                for script, arguments in (
                    ("update_economic_context.py", []),
                    ("update_market_snapshot.py", []),
                    ("update_economic_news.py", ["--backfill-days", "2", "--limit-per-day", "60"]),
                    ("update_editorial_analysis.py", ["--lookback-days", "45", "--company-limit", "20", "--analysis-limit", "20"]),
                ):
                    subprocess.run(
                        [sys.executable, str(ROOT / "scripts" / script), *arguments],
                        cwd=ROOT,
                        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        check=False,
                    )
            state = _read_collection_state()
            if process.returncode == 0 and _finished_for_today(state):
                marker.write_text(date.today().isoformat(), encoding="utf-8")
            else:
                retry_after = time.monotonic() + TRANSIENT_RETRY_SECONDS
        time.sleep(UPDATE_POLL_SECONDS)


@app.on_event("startup")
def start_daily_updater() -> None:
    threading.Thread(target=_daily_update_loop, name="daily-real-estate-update", daemon=True).start()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "database": str(STORE.db_path), "catalog": STORE.catalog_path.exists()}


@app.get("/api/catalog")
def catalog() -> FileResponse:
    if not STORE.catalog_path.exists():
        STORE.build_catalog()
    return FileResponse(STORE.catalog_path, media_type="application/json", headers={"Cache-Control": "no-cache"})


@app.get("/api/meta")
def meta() -> dict:
    if not STORE.catalog_path.exists():
        return STORE.build_catalog()["meta"]
    return json.loads(STORE.catalog_path.read_text(encoding="utf-8")).get("meta", {})


@app.get("/api/status")
def status() -> dict:
    if STORE.status_path.exists():
        return json.loads(STORE.status_path.read_text(encoding="utf-8"))
    return {"finished_at": None, "completed_jobs": 0, "failures": []}


@app.get("/api/history")
def history(lawd_cd: str, dong: str, apt_name: str) -> list[dict]:
    rows = STORE.history(lawd_cd.zfill(5)[:5], dong, apt_name)
    if not rows:
        raise HTTPException(status_code=404, detail="이 단지의 공식 실거래 이력이 아직 없습니다.")
    return rows


@app.get("/api/trades")
def trades(
    lawd_cd: str,
    dong: str,
    apt_name: str,
    area_m2: float | None = None,
    limit: int = Query(default=1000, ge=1, le=5000),
) -> list[dict]:
    return STORE.trades(lawd_cd.zfill(5)[:5], dong, apt_name, area_m2=area_m2, limit=limit)


def _contains_bounds(outer: tuple[float, float, float, float], inner: tuple[float, float, float, float]) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


@app.get("/api/map-complexes")
def map_complexes(
    south: float = Query(ge=-90, le=90),
    west: float = Query(ge=-180, le=180),
    north: float = Query(ge=-90, le=90),
    east: float = Query(ge=-180, le=180),
) -> dict:
    """Return named apartment/building features for the viewport with a pan-friendly cache."""
    if south >= north or west >= east or north - south > 0.2 or east - west > 0.2:
        raise HTTPException(status_code=400, detail="지도 범위가 너무 크거나 올바르지 않습니다.")

    requested = (south, west, north, east)
    now = time.monotonic()
    _map_cache[:] = [entry for entry in _map_cache if now - entry["created_at"] < MAP_CACHE_SECONDS]
    for entry in reversed(_map_cache):
        if _contains_bounds(entry["bounds"], requested):
            return {"elements": entry["elements"], "cached": True}

    query_bounds = (
        max(-90.0, south - MAP_QUERY_PADDING),
        max(-180.0, west - MAP_QUERY_PADDING),
        min(90.0, north + MAP_QUERY_PADDING),
        min(180.0, east + MAP_QUERY_PADDING),
    )
    bbox = ",".join(str(value) for value in query_bounds)
    query = (
        '[out:json][timeout:7];('
        f'way["building"="apartments"]["name"]({bbox});'
        f'relation["building"="apartments"]["name"]({bbox});'
        ');out center 700;'
    )
    last_error: Exception | None = None
    for endpoint in OVERPASS_URLS:
        try:
            response = requests.post(
                endpoint,
                data={"data": query},
                headers={"User-Agent": "KoreanRealEstateMap/1.0"},
                timeout=(3, 8),
            )
            response.raise_for_status()
            elements = response.json().get("elements", [])
            _map_cache.append({"bounds": query_bounds, "elements": elements, "created_at": now})
            if len(_map_cache) > 24:
                del _map_cache[:-24]
            return {"elements": elements, "cached": False}
        except (requests.RequestException, ValueError, AttributeError) as error:
            last_error = error
    raise HTTPException(status_code=502, detail=f"주변 단지 지도 조회에 실패했습니다: {last_error}")


def _nominatim(path: str, params: dict[str, object]) -> object:
    global _last_nominatim_request
    cache_key = path + "?" + "&".join(f"{key}={params[key]}" for key in sorted(params))
    if cache_key in _geocode_cache:
        return _geocode_cache[cache_key]
    with _nominatim_lock:
        if cache_key in _geocode_cache:
            return _geocode_cache[cache_key]
        remaining = 1.05 - (time.monotonic() - _last_nominatim_request)
        if remaining > 0:
            time.sleep(remaining)
        try:
            response = requests.get(
                f"https://nominatim.openstreetmap.org/{path}",
                params=params,
                headers={"User-Agent": "KoreanRealEstateMap/1.0"},
                timeout=(3, 8),
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as error:
            raise HTTPException(status_code=502, detail=f"주소 좌표 조회에 실패했습니다: {error}") from error
        finally:
            _last_nominatim_request = time.monotonic()
        _geocode_cache[cache_key] = payload
        if len(_geocode_cache) > 5000:
            _geocode_cache.pop(next(iter(_geocode_cache)))
        return payload


@app.get("/api/geocode")
def geocode(q: str = Query(min_length=2, max_length=180), limit: int = Query(default=1, ge=1, le=5)) -> object:
    return _nominatim(
        "search",
        {"format": "jsonv2", "limit": limit, "countrycodes": "kr", "accept-language": "ko", "q": q},
    )


@app.get("/api/reverse-geocode")
def reverse_geocode(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    zoom: int = Query(default=16, ge=3, le=18),
) -> object:
    return _nominatim(
        "reverse",
        {"format": "jsonv2", "zoom": zoom, "addressdetails": 1, "accept-language": "ko", "lat": lat, "lon": lon},
    )


public_dir = ROOT / "data" / "public"
web_dir = ROOT / "web"
app.mount("/data", StaticFiles(directory=public_dir), name="data")
app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
