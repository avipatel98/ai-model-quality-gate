"""
Contract tests for the Task Priority Classifier API.

Each test uses a Pydantic model to validate the exact response shape.
If the API renames, removes, or changes the type of any field these
tests will catch it before the change reaches production.
"""

from typing import Literal

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError


# ── Contract schemas (source of truth) ────────────────────────────────────────

class HealthContract(BaseModel):
    status: Literal["ok"]


class PredictContract(BaseModel):
    label: Literal["High", "Medium", "Low"]
    confidence: float

    model_config = {"extra": "forbid"}  # fail if API adds undocumented fields


class MetricsContract(BaseModel):
    accuracy: float
    f1_macro: float
    f1_weighted: float
    precision_macro: float
    recall_macro: float
    threshold: float
    passed: bool
    train_samples: int
    test_samples: int

    model_config = {"extra": "forbid"}


# ── /health ───────────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_returns_200(self, client: TestClient):
        response = client.get("/health")
        assert response.status_code == 200

    def test_response_matches_contract(self, client: TestClient):
        data = client.get("/health").json()
        # Raises ValidationError if shape or types don't match
        HealthContract.model_validate(data)

    def test_status_is_ok(self, client: TestClient):
        data = client.get("/health").json()
        assert data["status"] == "ok"

    def test_no_extra_fields(self, client: TestClient):
        data = client.get("/health").json()
        assert set(data.keys()) == {"status"}, (
            f"Unexpected fields in /health response: {set(data.keys()) - {'status'}}"
        )


# ── /predict ──────────────────────────────────────────────────────────────────

class TestPredictEndpoint:
    def test_returns_200_for_valid_input(self, client: TestClient):
        response = client.post("/predict", json={"Task": "Fix production crash"})
        assert response.status_code == 200

    def test_response_matches_contract(self, client: TestClient):
        data = client.post("/predict", json={"Task": "Fix production crash"}).json()
        PredictContract.model_validate(data)

    def test_label_field_present(self, client: TestClient):
        data = client.post("/predict", json={"Task": "Fix production crash"}).json()
        assert "label" in data, "Response is missing required field 'label'"

    def test_confidence_field_present(self, client: TestClient):
        data = client.post("/predict", json={"Task": "Fix production crash"}).json()
        assert "confidence" in data, "Response is missing required field 'confidence'"

    def test_label_is_valid_class(self, client: TestClient):
        data = client.post("/predict", json={"Task": "Fix production crash"}).json()
        assert data["label"] in {"High", "Medium", "Low"}, (
            f"Unexpected label value: {data['label']}"
        )

    def test_confidence_is_float_between_0_and_1(self, client: TestClient):
        data = client.post("/predict", json={"Task": "Fix production crash"}).json()
        conf = data["confidence"]
        assert isinstance(conf, float), f"confidence should be float, got {type(conf)}"
        assert 0.0 <= conf <= 1.0, f"confidence out of range: {conf}"

    def test_no_extra_fields(self, client: TestClient):
        data = client.post("/predict", json={"Task": "Fix production crash"}).json()
        assert set(data.keys()) == {"label", "confidence"}, (
            f"Unexpected fields in /predict response: {set(data.keys()) - {'label', 'confidence'}}"
        )

    # ── Label accuracy spot-checks ─────────────────────────────────────────────

    def test_high_priority_task(self, client: TestClient):
        data = client.post(
            "/predict", json={"Task": "Fix production database crash affecting all users"}
        ).json()
        assert data["label"] == "High"

    def test_medium_priority_task(self, client: TestClient):
        data = client.post(
            "/predict", json={"Task": "Write unit tests for the payment service"}
        ).json()
        assert data["label"] == "Medium"

    def test_low_priority_task(self, client: TestClient):
        data = client.post(
            "/predict", json={"Task": "Read the latest JavaScript newsletter"}
        ).json()
        assert data["label"] == "Low"

    # ── Input validation ───────────────────────────────────────────────────────

    def test_empty_task_returns_422(self, client: TestClient):
        response = client.post("/predict", json={"Task": ""})
        assert response.status_code == 422, (
            "Empty Task should be rejected with 422 Unprocessable Entity"
        )

    def test_whitespace_only_task_returns_422(self, client: TestClient):
        response = client.post("/predict", json={"Task": "   "})
        assert response.status_code == 422

    def test_missing_task_field_returns_422(self, client: TestClient):
        response = client.post("/predict", json={})
        assert response.status_code == 422

    def test_wrong_field_name_returns_422(self, client: TestClient):
        # Detects schema drift: if API silently accepts renamed input field,
        # the contract is broken — it should reject unknown fields.
        response = client.post("/predict", json={"text": "Fix production crash"})
        assert response.status_code == 422, (
            "SCHEMA_DRIFT: API accepted 'text' instead of required 'Task'"
        )

    # ── Schema drift detection ─────────────────────────────────────────────────

    def test_contract_rejects_renamed_label_field(self):
        """
        Simulates what happens if the API renames 'label' to 'priority'.
        The Pydantic contract model must raise ValidationError.
        """
        fake_response = {"priority": "High", "confidence": 0.91}
        with pytest.raises(ValidationError):
            PredictContract.model_validate(fake_response)

    def test_contract_rejects_renamed_confidence_field(self):
        """Simulates API renaming 'confidence' to 'score'."""
        fake_response = {"label": "High", "score": 0.91}
        with pytest.raises(ValidationError):
            PredictContract.model_validate(fake_response)

    def test_contract_rejects_invalid_label_value(self):
        """Simulates API returning an undocumented label like 'URGENT'."""
        fake_response = {"label": "URGENT", "confidence": 0.91}
        with pytest.raises(ValidationError):
            PredictContract.model_validate(fake_response)

    def test_contract_rejects_extra_fields(self):
        """Simulates API silently adding an undocumented field."""
        fake_response = {"label": "High", "confidence": 0.91, "model_version": "v2"}
        with pytest.raises(ValidationError):
            PredictContract.model_validate(fake_response)


# ── /metrics ──────────────────────────────────────────────────────────────────

class TestMetricsEndpoint:
    def test_returns_200(self, client: TestClient):
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_response_matches_contract(self, client: TestClient):
        data = client.get("/metrics").json()
        MetricsContract.model_validate(data)

    def test_f1_meets_threshold(self, client: TestClient):
        data = client.get("/metrics").json()
        assert data["f1_macro"] >= data["threshold"], (
            f"Model F1 {data['f1_macro']} is below threshold {data['threshold']}"
        )

    def test_passed_flag_is_true(self, client: TestClient):
        data = client.get("/metrics").json()
        assert data["passed"] is True, "Model did not meet the F1 quality gate"

    def test_all_metrics_are_valid_proportions(self, client: TestClient):
        data = client.get("/metrics").json()
        for field in ("accuracy", "f1_macro", "f1_weighted", "precision_macro", "recall_macro"):
            assert 0.0 <= data[field] <= 1.0, f"{field} out of range: {data[field]}"
