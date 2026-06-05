# AI Model Quality Gate — Capstone Project

[![CI](https://github.com/YOUR_USERNAME/ai-model-quality-gate/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/ai-model-quality-gate/actions/workflows/ci.yml)

An end-to-end ML testing pipeline that mirrors a real MLOps production workflow.
A text classifier is trained, exposed as a REST API, stress-tested with K6, and
wrapped with self-healing test automation that survives API changes without manual
intervention.

---

## Table of Contents

- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Setup](#setup)
- [Phase 1 — Model & API](#phase-1--model--api)
- [Phase 2 — K6 Performance Tests](#phase-2--k6-performance-tests)
- [Phase 3 — Self-Healing Tests](#phase-3--self-healing-tests)
- [Results Summary](#results-summary)

---

## Overview

```
Phase 1 — Train & validate the AI model
       ↓  API ready
Phase 2 — Performance test with K6
       ↓  Bottlenecks found
Phase 3 — Self-healing test scripts
       ↓  Deploy gate active
```

The model predicts task priority (**High / Medium / Low**) from a plain-text
task description. Everything is wired into a single pipeline: bad model → CI
blocks. Schema change → tests heal. Flaky server → retries kick in.

---

## Tech Stack

| Layer | Tools |
|---|---|
| Model | scikit-learn · TF-IDF · LogisticRegression |
| API | FastAPI · uvicorn · Pydantic |
| Contract tests | pytest · Pydantic v2 |
| Performance tests | K6 v2 |
| Self-healing | Python · pytest · unittest.mock |
| CI/CD | GitHub Actions |

---

## Project Structure

```
capstone project/
├── data/
│   └── dataset.csv              # 202 labelled task descriptions
├── src/
│   ├── train.py                 # Train + evaluate the model
│   ├── app.py                   # FastAPI application
│   └── model/
│       ├── pipeline.joblib      # Serialised TF-IDF + LR pipeline
│       ├── classes.json         # Label order used by the API
│       ├── metrics.json         # F1, accuracy, precision, recall
│       └── confusion_matrix.png # Confusion matrix
├── tests/
│   ├── conftest.py              # Shared TestClient fixture
│   ├── test_contract.py         # 27 Pydantic contract tests
│   ├── test_self_healing.py     # 4 Phase 3 self-healing scenarios
│   └── self_healing/
│       ├── schema_healer.py     # Schema drift detection & healing
│       ├── retry_client.py      # Exponential backoff retry client
│       └── fixtures/
│           └── predict_schema.json  # Stored API response shape
├── k6/
│   ├── ramp_up.js               # 1 → 50 VUs over 5 min
│   ├── spike.js                 # 5 → 100 VUs instant burst
│   ├── generate_report.py       # HTML report generator
│   └── results/
│       ├── ramp_up_summary.json
│       ├── spike_summary.json
│       └── report.html          # Performance report
└── requirements.txt
```

---

## Setup

**Prerequisites:** Python 3.10+, pip, K6

```bash
# Clone and enter the project
cd "AI testing course/Capstone project"

# Install Python dependencies
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org \
    -r requirements.txt

# Install K6 (macOS)
brew install k6
```

> **Note:** All Python commands below use the pyenv interpreter.
> Replace `python3` with the full path if needed:
> `~/.pyenv/versions/3.10.0/bin/python3.10`

---

## Phase 1 — Model & API

### 1. Train the model

```bash
python3 src/train.py
```

Expected output:
```
Accuracy   : 0.8780
F1 (macro) : 0.8787   ← must be ≥ 0.82
✓ PASSED
Pipeline  → src/model/pipeline.joblib
Metrics   → src/model/metrics.json
```

### 2. Start the API

```bash
python3 -m uvicorn src.app:app --host 0.0.0.0 --port 8000
```

### 3. Try the endpoints

```bash
# Health check
curl http://localhost:8000/health

# Predict priority
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"Task": "Fix production database crash affecting all users"}'
# → {"label":"High","confidence":0.6564}

# Model metrics
curl http://localhost:8000/metrics
```

### 4. Run contract tests

```bash
python3 -m pytest tests/test_contract.py -v
# → 27 passed in 0.08s
```

---

## Phase 2 — K6 Performance Tests

> Requires the API to be running on `http://localhost:8000`.

### Ramp-up test (1 → 50 VUs over 5 min)

```bash
k6 run --out json=k6/results/ramp_up.json k6/ramp_up.js
```

### Spike test (5 → 100 VUs instant)

```bash
k6 run --out json=k6/results/spike.json k6/spike.js
```

### Generate HTML report

```bash
python3 k6/generate_report.py
open k6/results/report.html
```

#### Thresholds (defined in both scripts)

| Metric | Threshold |
|---|---|
| p95 response time | < 500 ms |
| TTFB p95 | < 400 ms |
| Error rate | < 1% |
| Throughput | ≥ 50 RPS |

---

## Phase 3 — Self-Healing Tests

### What it covers

| Mechanism | File | Behaviour |
|---|---|---|
| Schema healing | `self_healing/schema_healer.py` | Detects field renames → logs `SCHEMA_DRIFT` → updates fixture → continues |
| Smart retry | `self_healing/retry_client.py` | Exponential backoff on 5xx: 1 s → 2 s → 4 s, max 3 retries |

### Run all four scenarios

```bash
python3 -m pytest tests/test_self_healing.py -v
```

### Scenarios at a glance

**Scenario 1 — Field rename**
```
API returns: {"priority": "High", "confidence": 0.87}   ← was "label"
Healer:      WARNING  SCHEMA_DRIFT — added={'priority'} removed={'label'}
             Fixture updated → continuing tests
```

**Scenario 2 — Missing required field**
```
API returns: {"status": "ok"}   ← no label or confidence
Healer:      ERROR  SCHEMA_BREAK — required fields missing: ['confidence', 'label']
             SchemaBrokenError raised immediately
```

**Scenario 3 — Transient 503 (flaky)**
```
Attempt 1/4:  HTTP 503 — retrying in 1s ...
Attempt 2/4:  HTTP 503 — retrying in 2s ...
Attempt 3/4:  200 OK — classified as FLAKY (transient server error)
```

**Scenario 4 — Genuine failure**
```
Attempt 1/4:  HTTP 503 — retrying in 1s ...
Attempt 2/4:  HTTP 503 — retrying in 2s ...
Attempt 3/4:  HTTP 503 — retrying in 4s ...
Attempt 4/4:  HTTP 503
GenuineFailureError: all 4 attempts failed — server is consistently failing
```

---

## Docker

### Run the full stack (API + Prometheus + Grafana)

```bash
docker-compose up --build
```

| Service | URL |
|---|---|
| API | http://localhost:8000 |
| Prometheus | http://localhost:9090 |
| Grafana dashboard | http://localhost:3000 |

### Run K6 with Prometheus remote write

```bash
# Stream K6 metrics live into Prometheus → visible in Grafana
k6 run --out experimental-prometheus-rw \
       -e K6_PROMETHEUS_RW_SERVER_URL=http://localhost:9090/api/v1/write \
       k6/spike.js
```

The Grafana dashboard is pre-provisioned — open http://localhost:3000 and the
**K6 + API** dashboard appears automatically, showing live VU count, RPS,
p95 latency, and error rate.

---

## Performance Optimisation

### ≥ 20% p95 improvement — proven

Switching from `--workers 1` to `--workers 4` (removing the Python GIL bottleneck
under concurrent load) produces a **46.7% p95 reduction** on the spike test:

| Configuration | p95 Latency | vs Baseline |
|---|---|---|
| 1 worker (baseline) | 48.2 ms | — |
| 4 workers (optimised) | **25.7 ms** | **↓ 46.7%** |

The production `Dockerfile` and `docker-compose.yml` already use `--workers 4`.

### Threshold history log

Every calibration run is appended to `k6/threshold_history.json`:

```
Run 1  51.3 ms  →  59.0 ms calibrated  (pre-optimisation)
Run 2  25.7 ms  →  29.5 ms calibrated  (post-optimisation)
                ↓ 49.9% improvement
```

---

## Confidence Band Tests

Tests that each known input's confidence score stays within ±0.10 of its
baseline. Every check — pass or fail — is appended to `tests/confidence_audit.json`
for cross-run regression tracking.

```bash
python3 -m pytest tests/test_confidence_band.py -v
# → 10 passed
```

---

## Results Summary

| Phase | Metric | Result | Target | Status |
|---|---|---|---|---|
| 1 | F1 score (macro) | 0.879 | ≥ 0.82 | ✅ |
| 1 | API response time | ~2.5 ms | < 200 ms | ✅ |
| 1 | Contract tests | 27 / 27 | all green | ✅ |
| 2 | p95 latency (ramp-up) | 18.5 ms | < 500 ms | ✅ |
| 2 | p95 latency (spike) | 51.3 ms | < 500 ms | ✅ |
| 2 | Error rate | 0.00% | < 1% | ✅ |
| 2 | Throughput (spike) | 55.3 RPS | ≥ 50 RPS | ✅ |
| 3 | Self-healing tests | 22 / 22 | all green | ✅ |
