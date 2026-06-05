"""
Phase 3 — Self-Healing Test Scenarios
======================================

Four scenarios are demonstrated here:

  Scenario 1 — Field rename
      API renames 'label' → 'priority'.
      Expected: SCHEMA_DRIFT logged, fixture auto-updated, test continues.

  Scenario 2 — Missing required field
      API response omits both 'label' and 'confidence'.
      Expected: SchemaBrokenError raised immediately — hard stop.

  Scenario 3 — Transient 5xx (flaky server)
      Server returns 503 on the first two attempts, then 200.
      Expected: two retries logged with backoff, result returned, marked flaky.

  Scenario 4 — Genuine server failure
      Server returns 503 on every attempt.
      Expected: GenuineFailureError raised after all retries are exhausted.
"""

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import httpx
import pytest

from tests.self_healing.retry_client import GenuineFailureError, RetryResult, SmartClient
from tests.self_healing.schema_healer import HealResult, SchemaBrokenError, SchemaHealer


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def healer(tmp_path: Path) -> SchemaHealer:
    """Fresh SchemaHealer backed by a temp fixture file — isolated per test."""
    return SchemaHealer(fixture_path=tmp_path / "predict_schema.json")


@pytest.fixture()
def fast_client() -> SmartClient:
    """SmartClient with zero sleep delays so tests run instantly."""
    return SmartClient(base_url="http://localhost:8000", delays=[0, 0, 0])


def _mock_response(status: int, body: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    if body:
        resp.json.return_value = body
    return resp


# ── Scenario 1 — Field rename ──────────────────────────────────────────────────

class TestScenario1FieldRename:
    """API renames 'label' → 'priority'. Healer detects drift and carries on."""

    def test_baseline_fixture_is_created_on_first_check(self, healer, caplog):
        with caplog.at_level(logging.INFO, logger="schema_healer"):
            result = healer.check({"label": "High", "confidence": 0.87})
        assert result.ok
        assert not result.healed
        assert "Fixture initialised" in caplog.text

    def test_schema_drift_is_detected_after_field_rename(self, healer, caplog):
        # Establish fixture with the original shape
        healer.check({"label": "High", "confidence": 0.87})

        # API now returns 'priority' instead of 'label'
        with caplog.at_level(logging.WARNING, logger="schema_healer"):
            result = healer.check({"priority": "High", "confidence": 0.87})

        assert "SCHEMA_DRIFT" in caplog.text

    def test_healer_continues_after_drift(self, healer):
        healer.check({"label": "High", "confidence": 0.87})
        result = healer.check({"priority": "High", "confidence": 0.87})

        assert result.ok, "Test should continue after healing"
        assert result.healed, "Result should be marked as healed"
        assert "label" in result.removed_fields
        assert "priority" in result.added_fields

    def test_fixture_is_updated_with_new_shape(self, healer):
        healer.check({"label": "High", "confidence": 0.87})
        healer.check({"priority": "High", "confidence": 0.87})

        # Fixture on disk now reflects the new schema
        fixture_data = json.loads(healer.fixture_path.read_text())
        assert "priority" in fixture_data["fields"]
        assert "label" not in fixture_data["fields"]

    def test_subsequent_check_with_healed_schema_passes_cleanly(self, healer):
        healer.check({"label": "High", "confidence": 0.87})
        healer.check({"priority": "High", "confidence": 0.87})   # drift + heal

        result = healer.check({"priority": "Medium", "confidence": 0.72})  # clean
        assert result.ok
        assert not result.healed


# ── Scenario 2 — Missing required field ───────────────────────────────────────

class TestScenario2MissingField:
    """API returns a response with no recognisable fields — hard stop."""

    def test_missing_both_required_fields_raises_immediately(self, healer):
        with pytest.raises(SchemaBrokenError) as exc_info:
            healer.check({"status": "ok"})   # no label, no confidence
        assert "SCHEMA_BREAK" in str(exc_info.value)
        assert "label" in str(exc_info.value) or "confidence" in str(exc_info.value)

    def test_missing_label_raises_schema_broken_error(self, healer):
        with pytest.raises(SchemaBrokenError):
            healer.check({"confidence": 0.87})   # label absent

    def test_missing_confidence_raises_schema_broken_error(self, healer):
        with pytest.raises(SchemaBrokenError):
            healer.check({"label": "High"})   # confidence absent

    def test_empty_response_raises_schema_broken_error(self, healer):
        with pytest.raises(SchemaBrokenError):
            healer.check({})

    def test_schema_break_is_logged_as_error(self, healer, caplog):
        with caplog.at_level(logging.ERROR, logger="schema_healer"):
            with pytest.raises(SchemaBrokenError):
                healer.check({"score": 0.91})
        assert "SCHEMA_BREAK" in caplog.text


# ── Scenario 3 — Transient 503 (flaky) ────────────────────────────────────────

class TestScenario3TransientRetry:
    """Server returns 503 twice then recovers — request marked flaky."""

    def test_succeeds_after_two_503s(self, fast_client):
        good_body = {"label": "High", "confidence": 0.88}
        responses = [
            _mock_response(503),
            _mock_response(503),
            _mock_response(200, good_body),
        ]
        with patch("httpx.post", side_effect=responses):
            result = fast_client.predict("Fix production crash")

        assert result.data == good_body
        assert result.attempts == 3
        assert result.flaky is True

    def test_retry_sleeps_are_called_with_backoff_delays(self, fast_client):
        # Override with real delays to verify sleep calls
        client = SmartClient("http://localhost:8000", delays=[1, 2, 4])
        good_body = {"label": "High", "confidence": 0.88}
        responses = [
            _mock_response(503),
            _mock_response(503),
            _mock_response(200, good_body),
        ]
        with patch("httpx.post", side_effect=responses), \
             patch("time.sleep") as mock_sleep:
            client.predict("Fix production crash")

        assert mock_sleep.call_count == 2
        mock_sleep.assert_has_calls([call(1), call(2)])

    def test_status_history_records_all_attempts(self, fast_client):
        responses = [
            _mock_response(503),
            _mock_response(200, {"label": "Low", "confidence": 0.61}),
        ]
        with patch("httpx.post", side_effect=responses):
            result = fast_client.predict("Read newsletter")

        assert result.status_history == [503, 200]

    def test_single_503_then_success_is_flagged_flaky(self, fast_client):
        responses = [
            _mock_response(503),
            _mock_response(200, {"label": "Medium", "confidence": 0.73}),
        ]
        with patch("httpx.post", side_effect=responses):
            result = fast_client.predict("Write unit tests")

        assert result.flaky is True
        assert result.attempts == 2

    def test_first_attempt_success_is_not_flagged_flaky(self, fast_client):
        with patch("httpx.post", return_value=_mock_response(200, {"label": "Low", "confidence": 0.6})):
            result = fast_client.predict("Read newsletter")

        assert result.flaky is False
        assert result.attempts == 1

    def test_flaky_result_is_logged_as_warning(self, fast_client, caplog):
        responses = [_mock_response(503), _mock_response(200, {"label": "High", "confidence": 0.9})]
        with patch("httpx.post", side_effect=responses), \
             caplog.at_level(logging.WARNING, logger="retry_client"):
            fast_client.predict("Fix crash")

        assert "FLAKY" in caplog.text


# ── Scenario 4 — Genuine failure ──────────────────────────────────────────────

class TestScenario4GenuineFailure:
    """Server returns 503 on every attempt — GenuineFailureError is raised."""

    def test_raises_genuine_failure_after_all_retries_exhausted(self, fast_client):
        with patch("httpx.post", return_value=_mock_response(503)):
            with pytest.raises(GenuineFailureError) as exc_info:
                fast_client.predict("Fix production crash")

        assert "GENUINE FAILURE" in str(exc_info.value)

    def test_all_four_attempts_are_made(self, fast_client):
        with patch("httpx.post", return_value=_mock_response(503)) as mock_post:
            with pytest.raises(GenuineFailureError):
                fast_client.predict("Fix production crash")

        # default delays has 3 retries → 4 total attempts
        assert mock_post.call_count == 4

    def test_status_history_shows_all_503s(self, fast_client):
        with patch("httpx.post", return_value=_mock_response(503)):
            with pytest.raises(GenuineFailureError) as exc_info:
                fast_client.predict("Fix crash")

        assert "503" in str(exc_info.value)

    def test_genuine_failure_message_distinguishes_from_flakiness(self, fast_client):
        with patch("httpx.post", return_value=_mock_response(503)):
            with pytest.raises(GenuineFailureError) as exc_info:
                fast_client.predict("Fix crash")

        err = str(exc_info.value)
        assert "consistently" in err or "GENUINE" in err

    def test_all_retries_sleep_before_each_retry(self):
        client = SmartClient("http://localhost:8000", delays=[1, 2, 4])
        with patch("httpx.post", return_value=_mock_response(503)), \
             patch("time.sleep") as mock_sleep:
            with pytest.raises(GenuineFailureError):
                client.predict("Fix crash")

        # 3 retries → 3 sleep calls with the full backoff schedule
        assert mock_sleep.call_count == 3
        mock_sleep.assert_has_calls([call(1), call(2), call(4)])
