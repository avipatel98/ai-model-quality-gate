"""
Task Priority Classifier — FastAPI application.

Endpoints
---------
GET  /health       Liveness check
POST /predict      Returns label + confidence for a given task text
GET  /metrics      Model performance metrics
GET  /prometheus   Prometheus-format metrics
"""

import json
import time
from pathlib import Path

import joblib
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, field_validator

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "model" / "pipeline.joblib"
CLASSES_PATH = ROOT / "model" / "classes.json"
METRICS_PATH = ROOT / "model" / "metrics.json"

# ── Load model once at startup ─────────────────────────────────────────────────
if not MODEL_PATH.exists():
    raise RuntimeError(f"Model not found at {MODEL_PATH}. Run src/train.py first.")

pipeline = joblib.load(MODEL_PATH)
classes: list[str] = json.loads(CLASSES_PATH.read_text())

# ── In-process counters for Prometheus metrics ────────────────────────────────
_predict_count:   int   = 0
_predict_errors:  int   = 0
_predict_latency: float = 0.0   # cumulative ms

# ── Pydantic schemas ───────────────────────────────────────────────────────────
class PredictRequest(BaseModel):
    Task: str

    @field_validator("Task")
    @classmethod
    def task_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Task must not be empty")
        return v.strip()


class PredictResponse(BaseModel):
    label: str
    confidence: float


class HealthResponse(BaseModel):
    status: str


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Task Priority Classifier",
    description="Predicts task priority (High / Medium / Low) from a text description.",
    version="1.0.0",
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest) -> PredictResponse:
    global _predict_count, _predict_latency
    t0 = time.perf_counter()
    proba = pipeline.predict_proba([request.Task])[0]
    label = pipeline.classes_[int(np.argmax(proba))]
    confidence = round(float(np.max(proba)), 4)
    _predict_count  += 1
    _predict_latency += (time.perf_counter() - t0) * 1000
    return PredictResponse(label=label, confidence=confidence)


@app.get("/metrics")
def metrics() -> dict:
    """Return cached model evaluation metrics."""
    if not METRICS_PATH.exists():
        raise HTTPException(status_code=503, detail="Metrics not yet computed. Run src/train.py.")
    return json.loads(METRICS_PATH.read_text())


@app.get("/prometheus", response_class=PlainTextResponse)
def prometheus_metrics() -> str:
    """Prometheus text-format metrics — scraped by Prometheus every 5 s."""
    avg_ms = (_predict_latency / _predict_count) if _predict_count else 0.0
    lines = [
        "# HELP predict_requests_total Total number of /predict calls",
        "# TYPE predict_requests_total counter",
        f"predict_requests_total {_predict_count}",
        "",
        "# HELP predict_avg_latency_ms Rolling average prediction latency in ms",
        "# TYPE predict_avg_latency_ms gauge",
        f"predict_avg_latency_ms {avg_ms:.3f}",
        "",
        "# HELP predict_errors_total Total failed predictions",
        "# TYPE predict_errors_total counter",
        f"predict_errors_total {_predict_errors}",
    ]
    return "\n".join(lines) + "\n"
