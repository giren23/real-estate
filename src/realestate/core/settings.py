from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    service_key: str
    apartment_list_key: str
    trade_endpoint: str
    trade_fallback_endpoint: str
    apartment_list_endpoint: str
    default_history_months: int
    max_months_per_run: int
    request_delay_seconds: float


def _key(name: str, fallback: str = "") -> str:
    value = os.getenv(name, "").strip() or fallback.strip()
    return unquote(value) if "%" in value else value


def load_settings() -> Settings:
    path = Path(os.getenv("REALESTATE_CONFIG", ROOT / "config/settings.json"))
    if not path.exists():
        path = ROOT / "config/settings.example.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    service_key = _key("MOLIT_SERVICE_KEY")
    return Settings(
        service_key=service_key,
        apartment_list_key=_key("APT_LIST_SERVICE_KEY", service_key),
        trade_endpoint=data["trade_endpoint"],
        trade_fallback_endpoint=data.get(
            "trade_fallback_endpoint",
            "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/"
            "getRTMSDataSvcAptTradeDev",
        ),
        apartment_list_endpoint=data["apartment_list_endpoint"],
        default_history_months=int(data["default_history_months"]),
        max_months_per_run=int(data["max_months_per_run"]),
        request_delay_seconds=float(data["request_delay_seconds"]),
    )
