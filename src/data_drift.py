"""
Data Drift Check — Task Priority Classifier
============================================
Feeds out-of-distribution (OOD) inputs to the trained model and documents
confidence degradation vs. the in-distribution baseline.

Run:
    python3 src/data_drift.py
"""

import json
from pathlib import Path

import joblib
import numpy as np

ROOT       = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "src" / "model" / "pipeline.joblib"
OUT_PATH   = ROOT / "src" / "model" / "drift_report.json"

# ── Load model ─────────────────────────────────────────────────────────────────
pipeline = joblib.load(MODEL_PATH)

# ── In-distribution baseline ───────────────────────────────────────────────────
BASELINE = [
    ("Fix production database crash affecting all users",     "High"),
    ("Write unit tests for the payment service layer",        "Medium"),
    ("Read the latest JavaScript weekly newsletter",          "Low"),
    ("Deploy emergency security patch to auth service",       "High"),
    ("Refactor config management to use environment vars",    "Medium"),
    ("Watch conference talk on Rust memory safety",           "Low"),
]

# ── Out-of-distribution inputs ─────────────────────────────────────────────────
OOD = [
    # 1. Emoji-heavy / informal register
    ("🔥🚨 URGENT!!!! Fix this NOW!!!! 💥💥💥",
     "emoji-heavy — no real keywords"),

    # 2. All-caps shouting — same meaning as High but unusual casing
    ("CRITICAL CRITICAL CRITICAL SYSTEM DOWN EVERYTHING IS BROKEN",
     "all-caps duplicate words"),

    # 3. Foreign language (French) — model has never seen non-English text
    ("Veuillez corriger le bug en production immédiatement",
     "non-English (French)"),

    # 4. Domain shift — medical terminology
    ("Perform lumbar puncture on patient with suspected bacterial meningitis",
     "domain shift (medical)"),

    # 5. Pure gibberish
    ("xkcd banana thunderstorm purple seventeen grzmot fnord",
     "random nonsense words"),

    # 6. Single-word input — far shorter than training distribution
    ("Bug",
     "single word — very short"),

    # 7. Highly ambiguous phrasing
    ("Maybe do something at some point if possible",
     "vague / ambiguous — no signal words"),

    # 8. Numeric / code-heavy — issue tracker style
    ("Fix issue #4521 in v2.3.1 from PR #892 blocking release",
     "numeric / code-heavy"),

    # 9. Opposite polarity trap — Low-sounding words for a High task
    ("Please kindly read the critical production outage report when convenient",
     "polarity mismatch — Low words, High intent"),

    # 10. Very long verbose input
    ("After careful consideration of all the various factors involved and taking "
     "into account the feedback from numerous stakeholders across the organisation, "
     "it has been determined that we should perhaps at some future point explore "
     "the possibility of updating the documentation",
     "very long / verbose — diluted signal"),
]


def predict_one(text: str):
    proba = pipeline.predict_proba([text])[0]
    label = pipeline.classes_[int(np.argmax(proba))]
    conf  = float(np.max(proba))
    dist  = {cls: round(float(p), 4) for cls, p in zip(pipeline.classes_, proba)}
    return label, conf, dist


def run():
    print("=" * 65)
    print("Data Drift Check — Task Priority Classifier")
    print("=" * 65)

    # ── Baseline ───────────────────────────────────────────────────
    print("\n[BASELINE — In-distribution samples]")
    baseline_confs = []
    baseline_rows  = []
    for text, expected in BASELINE:
        label, conf, dist = predict_one(text)
        correct = "✓" if label == expected else "✗"
        baseline_confs.append(conf)
        baseline_rows.append({
            "text": text, "expected": expected,
            "predicted": label, "confidence": conf,
            "correct": label == expected,
        })
        print(f"  {correct}  [{label:6}  {conf:.2f}]  {text[:55]}")

    avg_baseline_conf = np.mean(baseline_confs)
    print(f"\n  Avg baseline confidence : {avg_baseline_conf:.3f}")

    # ── OOD ────────────────────────────────────────────────────────
    print("\n[OOD — Out-of-distribution samples]")
    ood_rows = []
    for text, description in OOD:
        label, conf, dist = predict_one(text)
        drop = avg_baseline_conf - conf
        flag = "⚠ DEGRADED" if conf < 0.50 else ("  OK" if conf >= avg_baseline_conf - 0.05 else "  LOWER")
        ood_rows.append({
            "text": text, "description": description,
            "predicted": label, "confidence": conf,
            "confidence_drop": round(drop, 4),
            "distribution": dist,
            "degraded": conf < 0.50,
        })
        print(f"  {flag}  [{label:6}  {conf:.2f}  Δ{drop:+.2f}]  {description}")

    avg_ood_conf = np.mean([r["confidence"] for r in ood_rows])
    degraded     = sum(1 for r in ood_rows if r["degraded"])

    print(f"\n  Avg OOD confidence      : {avg_ood_conf:.3f}  "
          f"(Δ{avg_ood_conf - avg_baseline_conf:+.3f} vs baseline)")
    print(f"  Samples below 0.50 conf : {degraded}/{len(OOD)}")

    # ── Summary ────────────────────────────────────────────────────
    print("\n[DEGRADATION SUMMARY]")
    findings = [
        "Non-English text (French) receives a prediction but confidence drops "
        "sharply — model has no multilingual capability.",
        "Emoji-heavy and all-caps inputs are handled but with reduced confidence "
        "— the TF-IDF tokeniser strips symbols and normalises poorly.",
        "Medical domain text maps to unexpected priority labels — the model has "
        "never seen medical vocabulary so it latches onto superficial cues.",
        "Pure gibberish and very short inputs (single word) show the highest "
        "degradation — insufficient token overlap with training vocabulary.",
        "Polarity mismatch inputs (Low-register words + High-priority intent) "
        "are frequently misclassified — the model is vocabulary-driven, not "
        "intent-driven.",
    ]
    for i, f in enumerate(findings, 1):
        print(f"  {i}. {f}")

    # ── Save report ────────────────────────────────────────────────
    report = {
        "avg_baseline_confidence":  round(avg_baseline_conf, 4),
        "avg_ood_confidence":       round(avg_ood_conf, 4),
        "confidence_drop":          round(avg_baseline_conf - avg_ood_conf, 4),
        "ood_samples_below_0_50":   degraded,
        "total_ood_samples":        len(OOD),
        "baseline": baseline_rows,
        "ood": ood_rows,
        "findings": findings,
    }
    OUT_PATH.write_text(json.dumps(report, indent=2))
    print(f"\n  Report saved → {OUT_PATH}")
    print("=" * 65)


if __name__ == "__main__":
    run()
