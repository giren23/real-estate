from __future__ import annotations

import time

import requests


DEFAULT_TIMEOUT = (8, 25)
HTTP_ATTEMPTS = 2


class ApiError(RuntimeError):
    pass


def _request_once(
    url: str,
    params: dict,
    timeout: tuple[float, float],
) -> str:
    try:
        response = requests.get(url, params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise ApiError(f"HTTP 요청 실패: {type(exc).__name__}") from exc

    if response.status_code >= 400:
        raise ApiError(f"HTTP 응답 오류: {response.status_code}")

    text = response.text
    if (
        "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in text
        or "SERVICE_ACCESS_DENIED_ERROR" in text
    ):
        raise ApiError("서비스키 또는 활용신청 상태를 확인하세요.")
    return text


def get_text(
    url: str,
    params: dict,
    timeout: tuple[float, float] = DEFAULT_TIMEOUT,
) -> str:
    last_error: Exception | None = None
    for attempt in range(1, HTTP_ATTEMPTS + 1):
        try:
            return _request_once(url, params, timeout)
        except Exception as exc:
            last_error = exc
            if attempt >= HTTP_ATTEMPTS:
                break
            wait_seconds = min(2**attempt, 4)
            print(
                f"[HTTP RETRY] {attempt}/{HTTP_ATTEMPTS} 실패, "
                f"{wait_seconds}초 후 재시도: {type(exc).__name__}: {exc}",
                flush=True,
            )
            time.sleep(wait_seconds)

    assert last_error is not None
    raise last_error
