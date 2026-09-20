import os
import time
from collections import defaultdict
from typing import Optional, Dict, List
from fastapi import Request, HTTPException, Header, status

def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization")
) -> bool:
    """
    Validates API key for mutating endpoints when STORY_FORECASTER_API_KEY is configured.
    Supports both 'X-API-Key: <key>' and 'Authorization: Bearer <key>' headers.
    If no STORY_FORECASTER_API_KEY environment variable is set, defaults to permissive dev mode.
    """
    expected_key = os.getenv("STORY_FORECASTER_API_KEY")
    if not expected_key:
        return True

    token = x_api_key
    if not token and authorization:
        if authorization.startswith("Bearer "):
            token = authorization[7:].strip()
        else:
            token = authorization.strip()

    if not token or token != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Please provide valid X-API-Key or Authorization header."
        )
    return True


class SlidingWindowRateLimiter:
    """
    Sliding window in-memory rate limiter per client IP.
    Protects compute-heavy and mutating endpoints from denial of service.
    """
    def __init__(self, requests_per_window: int = 60, window_seconds: int = 60):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self._history: Dict[str, List[float]] = defaultdict(list)

    def check(self, request: Request, max_requests: Optional[int] = None, window_seconds: Optional[int] = None):
        # Allow bypass for automated test suites
        if os.getenv("TESTING") == "true" or request.headers.get("X-Test-Bypass") == "1":
            return True

        limit = max_requests or self.requests_per_window
        window = window_seconds or self.window_seconds

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - window

        # Filter out expired timestamps
        timestamps = [t for t in self._history[client_ip] if t > window_start]
        if len(timestamps) >= limit:
            oldest = timestamps[0]
            retry_after = int(window - (now - oldest)) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: max {limit} requests per {window}s.",
                headers={"Retry-After": str(max(1, retry_after))}
            )

        timestamps.append(now)
        self._history[client_ip] = timestamps
        return True


default_rate_limiter = SlidingWindowRateLimiter(requests_per_window=120, window_seconds=60)
heavy_rate_limiter = SlidingWindowRateLimiter(requests_per_window=30, window_seconds=60)

def rate_limit_default(request: Request):
    return default_rate_limiter.check(request)

def rate_limit_heavy(request: Request):
    return heavy_rate_limiter.check(request)
