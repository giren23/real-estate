from __future__ import annotations
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

class ApiError(RuntimeError):
    pass

@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
def get_text(url: str, params: dict, timeout: int = 45) -> str:
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    text = response.text
    if "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in text or "SERVICE_ACCESS_DENIED_ERROR" in text:
        raise ApiError("서비스키 또는 활용신청 상태를 확인하세요.")
    return text
