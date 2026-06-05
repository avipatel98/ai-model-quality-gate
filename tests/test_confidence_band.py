"""
Confidence Score Tolerance Band Tests
=======================================
Asserts that the model's confidence for known inputs stays within an
expected range (e.g. 0.66 ± 0.10) and writes every check to an audit
trail so regressions across model versions are traceable.

Audit trail: tests/confidence_audit.json
"""

import json
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# ── Audit trail path ───────────────────────────────────────────────────────────
AUDIT_PATH = Path(__file__).resolve().parent / "confidence_audit.json"


def _load_audit() -> list:
    if not AUDIT_PATH.exists():
        return []
    return json.loads(AUDIT_PATH.read_text())


def _append_audit(record: dict) -> None:
    log = _load_audit()
    log.append(record)
    AUDIT_PATH.write_text(json.dumps(log, indent=2))


# ── Tolerance band fixture ─────────────────────────────────────────────────────
#
# Format: (task_text, expected_label, centre, tolerance)
# The model's confidence must land in [centre - tolerance, centre + tolerance].
# Centres are taken from actual model output; tolerance is ±0.10 (10 pp).
#
TOLERANCE_CASES = [
    (
        "Fix production database crash affecting all users",
        "High", 0.656, 0.10,
    ),
    (
        "Write unit tests for the payment service layer",
        "Medium", 0.585, 0.10,
    ),
    (
        "Read the latest JavaScript weekly newsletter",
        "Low", 0.592, 0.10,
    ),
    (
        # Lower confidence because "emergency" + "security" are somewhat
        # ambiguous between High and Medium in the training vocabulary.
        "Deploy emergency security patch to authentication service",
        "High", 0.395, 0.10,
    ),
    (
        "Refactor authentication module to reduce code duplication",
        "Medium", 0.559, 0.10,
    ),
    (
        "Watch conference talk on Rust memory safety",
        "Low", 0.565, 0.10,
    ),
    (
        "Resolve payment gateway timeout causing failed transactions",
        "High", 0.612, 0.10,
    ),
    (
        "Add input validation to the user registration form",
        "Medium", 0.615, 0.10,
    ),
]


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from src.app import app
    with TestClient(app) as c:
        yield c


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestConfidenceBand:

    @pytest.mark.parametrize("task,expected_label,centre,tolerance", TOLERANCE_CASES)
    def test_confidence_within_tolerance_band(
        self, client, task, expected_label, centre, tolerance
    ):
        resp = client.post("/predict", json={"Task": task})
        assert resp.status_code == 200
        data = resp.json()

        label      = data["label"]
        confidence = data["confidence"]
        lo         = round(centre - tolerance, 4)
        hi         = round(centre + tolerance, 4)
        in_band    = lo <= confidence <= hi
        correct    = label == expected_label

        # ── Write to audit trail regardless of pass/fail ─────────────
        _append_audit({
            "timestamp":      datetime.now().isoformat(timespec="seconds"),
            "task":           task[:60],
            "expected_label": expected_label,
            "predicted_label": label,
            "label_correct":  correct,
            "confidence":     confidence,
            "band_centre":    centre,
            "tolerance":      tolerance,
            "band_lo":        lo,
            "band_hi":        hi,
            "in_band":        in_band,
        })

        assert correct, (
            f"Wrong label: expected '{expected_label}', got '{label}'"
        )
        assert in_band, (
            f"Confidence {confidence:.4f} outside band "
            f"[{lo:.4f}, {hi:.4f}] for task: '{task[:50]}'"
        )

    def test_audit_trail_is_written(self, client):
        """Verify the audit file exists and has entries after the tests run."""
        # Trigger at least one check to ensure the file was created
        client.post("/predict", json={"Task": "Fix production crash"})
        assert AUDIT_PATH.exists(), "Audit trail file was not created"
        log = _load_audit()
        assert len(log) > 0, "Audit trail is empty"

    def test_audit_entries_have_required_fields(self, client):
        log = _load_audit()
        required = {
            "timestamp", "task", "expected_label", "predicted_label",
            "confidence", "band_lo", "band_hi", "in_band",
        }
        for entry in log[-3:]:   # check last 3 entries
            missing = required - set(entry.keys())
            assert not missing, f"Audit entry missing fields: {missing}"
