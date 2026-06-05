"""
Smart Retry Client — wraps /predict calls with exponential backoff on 5xx.

Distinguishes between:
  Flaky failure   : request eventually succeeds within the retry budget.
  Genuine failure : all retries exhausted — server is consistently broken.

Backoff schedule (default): 1 s → 2 s → 4 s  (max 3 retries = 4 total attempts)
"""

import logging
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger("retry_client")

DEFAULT_DELAYS: list[int] = [1, 2, 4]   # seconds before each retry


# ── Exceptions ─────────────────────────────────────────────────────────────────

class GenuineFailureError(Exception):
    """All retry attempts exhausted — server is consistently failing."""


# ── Result object ───────────────────────────────────────────────────────────────

@dataclass
class RetryResult:
    data: dict
    attempts: int
    flaky: bool        # True  → succeeded after at least one retry
    status_history: list[int]   # HTTP status code per attempt


# ── Client ──────────────────────────────────────────────────────────────────────

class SmartClient:
    """
    Parameters
    ----------
    base_url : API root, e.g. "http://localhost:8000"
    delays   : seconds to sleep before each successive retry
    """

    def __init__(self, base_url: str, delays: list[int] = None):
        self.base_url = base_url.rstrip("/")
        self.delays   = delays if delays is not None else DEFAULT_DELAYS

    @property
    def max_retries(self) -> int:
        return len(self.delays)

    # ── Public API ──────────────────────────────────────────────────────────────

    def predict(self, task: str) -> RetryResult:
        """
        POST /predict with smart retry on 5xx.

        Raises
        ------
        GenuineFailureError  if every attempt returns 5xx.
        httpx.HTTPStatusError for non-retryable 4xx responses.
        """
        status_history: list[int] = []
        last_status: int | None = None

        for attempt in range(self.max_retries + 1):
            try:
                resp = httpx.post(
                    f"{self.base_url}/predict",
                    json={"Task": task},
                    timeout=10.0,
                )
                status_history.append(resp.status_code)

                if resp.status_code == 200:
                    flaky = attempt > 0
                    if flaky:
                        logger.warning(
                            "Succeeded on attempt %d/%d after %d retries — "
                            "classified as FLAKY (transient server error)",
                            attempt + 1, self.max_retries + 1, attempt,
                        )
                    else:
                        logger.debug("Succeeded on first attempt.")
                    return RetryResult(
                        data=resp.json(),
                        attempts=attempt + 1,
                        flaky=flaky,
                        status_history=status_history,
                    )

                if resp.status_code >= 500:
                    last_status = resp.status_code
                    if attempt < self.max_retries:
                        delay = self.delays[attempt]
                        logger.warning(
                            "HTTP %d on attempt %d/%d — retrying in %ds ...",
                            resp.status_code, attempt + 1,
                            self.max_retries + 1, delay,
                        )
                        time.sleep(delay)
                        continue
                    # Final attempt also failed
                    break

                # 4xx — not retryable
                resp.raise_for_status()

            except httpx.ConnectError as exc:
                last_status = 0
                status_history.append(0)
                if attempt < self.max_retries:
                    delay = self.delays[attempt]
                    logger.warning(
                        "Connection error on attempt %d/%d — retrying in %ds ...",
                        attempt + 1, self.max_retries + 1, delay,
                    )
                    time.sleep(delay)
                    continue
                raise GenuineFailureError(
                    f"Could not connect after {self.max_retries + 1} attempts."
                ) from exc

        raise GenuineFailureError(
            f"GENUINE FAILURE — all {self.max_retries + 1} attempts returned "
            f"HTTP {last_status}. Status history: {status_history}. "
            f"Server is consistently failing, not just flaky."
        )
