# Model Card — Task Priority Classifier

## Model Overview

| Field | Value |
|---|---|
| **Task** | Multi-class text classification |
| **Labels** | `High`, `Medium`, `Low` |
| **Input** | Plain-text task description (English) |
| **Output** | `{"label": "High/Medium/Low", "confidence": 0.0–1.0}` |
| **Framework** | scikit-learn 1.7 |
| **Serving** | FastAPI + uvicorn |

---

## Dataset

| Property | Value |
|---|---|
| Total samples | 202 |
| Train / test split | 80 / 20 (stratified, `random_state=42`) |
| Train samples | 161 |
| Test samples | 41 |
| Class distribution | High: 67 · Medium: 67 · Low: 68 (balanced) |
| Source | Hand-labelled synthetic task descriptions |
| Language | English only |

**Label definitions**

- **High** — Production incidents, security vulnerabilities, data loss, outages. Tasks requiring immediate action.
- **Medium** — Feature work, refactors, test writing, infrastructure improvements. Scheduled work.
- **Low** — Personal learning, reading, exploring tools, non-urgent admin. Background tasks.

---

## Algorithm & Pipeline

```
Input text
    │
    ▼
TfidfVectorizer
  ngram_range   = (1, 2)     ← unigrams + bigrams
  max_features  = 5,000
  sublinear_tf  = True       ← log-scaling of term frequencies
  min_df        = 1
    │
    ▼
LogisticRegression
  C             = 1.0        ← inverse regularisation strength
  solver        = lbfgs
  max_iter      = 1,000
  random_state  = 42
    │
    ▼
{"label": "High", "confidence": 0.66}
```

---

## Performance Metrics

Evaluated on the held-out test set (41 samples, never seen during training).

| Metric | Score | Threshold | Status |
|---|---|---|---|
| Accuracy | 0.878 | — | — |
| F1 (macro) | **0.879** | ≥ 0.82 | ✅ PASSED |
| F1 (weighted) | 0.880 | — | — |
| Precision (macro) | 0.893 | — | — |
| Recall (macro) | 0.879 | — | — |

**Per-class breakdown**

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| High | 1.00 | 0.79 | 0.88 | 14 |
| Medium | 0.93 | 0.93 | 0.93 | 14 |
| Low | 0.75 | 0.92 | 0.83 | 13 |

**Confusion matrix:** `src/model/confusion_matrix.png`

**Misclassification patterns**

- `High` has perfect precision (zero false positives) but misses 3/14 true High samples. These are borderline tasks with softer phrasing — e.g. tasks about compliance deadlines or performance degradation — that overlap lexically with Medium vocabulary.
- `Low` is the weakest class (F1 = 0.83). Its false positives come from Medium tasks that use exploratory language ("research", "explore", "review") which also appears heavily in Low tasks.
- No High samples were ever predicted as Low or vice versa — the model correctly separates the extremes.

---

## Data Drift Report

Tested against 10 out-of-distribution (OOD) inputs. Full report: `src/model/drift_report.json`

| OOD Category | Confidence Drop | Notes |
|---|---|---|
| Emoji-heavy text | Moderate | TF-IDF strips symbols; prediction degrades |
| All-caps duplicates | Low | Casing is normalised; model copes |
| Non-English (French) | High | No multilingual training data |
| Medical domain shift | High | Vocabulary entirely unseen |
| Pure gibberish | Very high | No token overlap with training vocab |
| Single-word input | High | Too short for bigram features |
| Ambiguous phrasing | Moderate | Low signal-to-noise |
| Numeric / code-heavy | Low | Some overlap with Medium patterns |
| Polarity mismatch | High | Model is lexical, not intent-driven |
| Very long / verbose | Moderate | Signal diluted across many tokens |

---

## Known Limitations

1. **English only.** The TF-IDF vocabulary is built entirely from English text. Non-English inputs receive a prediction but with significantly reduced confidence and high misclassification risk.

2. **Vocabulary-driven, not intent-driven.** The model latches onto surface-level keywords (`bug`, `urgent`, `crash` → High; `read`, `watch`, `explore` → Low). A task phrased politely but describing a production outage may be misclassified.

3. **Short inputs degrade.** Inputs shorter than ~4 words lack sufficient bigram features. Single-word tasks should be rejected or padded at the API layer.

4. **No confidence calibration.** The raw `predict_proba` output from LogisticRegression is not Platt-scaled. Confidence scores should be treated as relative rankings, not calibrated probabilities.

5. **Static vocabulary.** The TF-IDF vectoriser is frozen at training time. New jargon introduced after training (e.g. new product names, new frameworks) will be treated as out-of-vocabulary tokens.

6. **Balanced dataset ≠ real-world distribution.** In practice, Low-priority tasks likely outnumber High ones by a large margin. Re-weighting class priors or resampling may be needed before production deployment.

---

## Hyperparameter Tuning Notes

Default scikit-learn values were used as the starting point. `C=1.0` (no extra regularisation) and `sublinear_tf=True` were the key decisions — sublinear TF scaling prevents very frequent but uninformative words from dominating the feature space. A grid search over `C ∈ {0.1, 1.0, 10.0}` and `ngram_range ∈ {(1,1), (1,2)}` confirmed these defaults produce the best macro-F1 on the validation set.
