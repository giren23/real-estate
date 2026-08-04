from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote
import json
import os

ROOT = Path(__file__).resolve().parents[3]

@dataclass(frozen=True)
class Settings:
    service_key: str
    trade_endpoint: str
    default_history_months: int
    max_months_per_run: int
    request_delay_seconds: float

def load_settings() -> Settings:
    path = Path(os.getenv("REALESTATE_CONFIG", ROOT / "config/settings.json"))
    if not path.exists():
        path = ROOT / "config/settings.example.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    key = os.getenv("MOLIT_SERVICE_KEY", "").strip()
    if "%" in key:
        key = unquote(key)
    return Settings(
        service_key=key,
        trade_endpoint=data["trade_endpoint"],
        default_history_months=int(data["default_history_months"]),
        max_months_per_run=int(data["max_months_per_run"]),
        request_delay_seconds=float(data["request_delay_seconds"]),
    )
