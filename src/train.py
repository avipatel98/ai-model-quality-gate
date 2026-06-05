"""
Train a TF-IDF + LogisticRegression text classifier for task priority prediction.

Outputs
-------
src/model/pipeline.joblib   Trained sklearn Pipeline (vectoriser + classifier)
src/model/classes.json      Ordered label list used by the API
"""

import json
import os
import sys
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "dataset.csv"
MODEL_DIR = ROOT / "src" / "model"
MODEL_PATH = MODEL_DIR / "pipeline.joblib"
CLASSES_PATH = MODEL_DIR / "classes.json"
CONFUSION_MATRIX_PATH = MODEL_DIR / "confusion_matrix.png"
METRICS_PATH = MODEL_DIR / "metrics.json"

F1_THRESHOLD = 0.82
RANDOM_STATE = 42
TEST_SIZE = 0.20
LABEL_ORDER = ["High", "Medium", "Low"]


def load_data(path: Path) -> tuple[list[str], list[str]]:
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    if "Task" not in df.columns or "Priority" not in df.columns:
        sys.exit(f"Expected columns 'Task' and 'Priority', found: {list(df.columns)}")
    df = df.dropna(subset=["Task", "Priority"])
    df = df[df["Priority"].isin(LABEL_ORDER)]
    return df["Task"].tolist(), df["Priority"].tolist()


def build_pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(
            ngram_range=(1, 2),
            max_features=5000,
            sublinear_tf=True,
            min_df=1,
        )),
        ("clf", LogisticRegression(
            C=1.0,
            max_iter=1000,
            random_state=RANDOM_STATE,
            solver="lbfgs",
        )),
    ])


def save_confusion_matrix(y_true, y_pred, labels, path: Path) -> None:
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    fig, ax = plt.subplots(figsize=(6, 5))
    sns.heatmap(
        cm,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=labels,
        yticklabels=labels,
        ax=ax,
    )
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title("Confusion Matrix — Task Priority Classifier")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Confusion matrix saved → {path}")


def main() -> None:
    print("=" * 60)
    print("Task Priority Classifier — Training")
    print("=" * 60)

    # ── Load ──────────────────────────────────────────────────────
    print(f"\n[1/5] Loading data from {DATA_PATH} ...")
    X, y = load_data(DATA_PATH)
    print(f"  Loaded {len(X)} samples")
    from collections import Counter
    print(f"  Class distribution: {dict(Counter(y))}")

    # ── Split ─────────────────────────────────────────────────────
    print(f"\n[2/5] Splitting data (test_size={TEST_SIZE}, seed={RANDOM_STATE}) ...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=y,
    )
    print(f"  Train: {len(X_train)}  Test: {len(X_test)}")

    # ── Train ─────────────────────────────────────────────────────
    print("\n[3/5] Training TF-IDF + LogisticRegression pipeline ...")
    pipeline = build_pipeline()
    pipeline.fit(X_train, y_train)
    print("  Training complete.")

    # ── Evaluate ──────────────────────────────────────────────────
    print("\n[4/5] Evaluating on held-out test set ...")
    y_pred = pipeline.predict(X_test)

    accuracy = accuracy_score(y_test, y_pred)
    f1_macro = f1_score(y_test, y_pred, average="macro")
    f1_weighted = f1_score(y_test, y_pred, average="weighted")

    print(f"\n  Accuracy          : {accuracy:.4f}")
    print(f"  F1 (macro)        : {f1_macro:.4f}")
    print(f"  F1 (weighted)     : {f1_weighted:.4f}")
    print(f"\n  Classification Report:\n")
    print(classification_report(y_test, y_pred, target_names=LABEL_ORDER))

    save_confusion_matrix(y_test, y_pred, LABEL_ORDER, CONFUSION_MATRIX_PATH)

    # ── Threshold check ───────────────────────────────────────────
    print(f"\n  Threshold check: F1 (macro) {f1_macro:.4f} >= {F1_THRESHOLD} ?")
    if f1_macro < F1_THRESHOLD:
        print(f"  ✗ FAILED — F1 {f1_macro:.4f} is below required {F1_THRESHOLD}")
        sys.exit(1)
    print(f"  ✓ PASSED")

    # ── Save ──────────────────────────────────────────────────────
    print(f"\n[5/5] Saving model artifacts ...")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, MODEL_PATH)
    CLASSES_PATH.write_text(json.dumps(LABEL_ORDER))

    from sklearn.metrics import precision_score, recall_score
    metrics_data = {
        "accuracy": round(accuracy, 4),
        "f1_macro": round(f1_macro, 4),
        "f1_weighted": round(f1_weighted, 4),
        "precision_macro": round(precision_score(y_test, y_pred, average="macro"), 4),
        "recall_macro": round(recall_score(y_test, y_pred, average="macro"), 4),
        "threshold": F1_THRESHOLD,
        "passed": f1_macro >= F1_THRESHOLD,
        "train_samples": len(X_train),
        "test_samples": len(X_test),
    }
    METRICS_PATH.write_text(json.dumps(metrics_data, indent=2))

    print(f"  Pipeline  → {MODEL_PATH}")
    print(f"  Classes   → {CLASSES_PATH}")
    print(f"  Metrics   → {METRICS_PATH}")

    # ── Quick sanity check ────────────────────────────────────────
    print("\n  Sanity check (3 examples):")
    examples = [
        "Fix production database crash affecting all users",
        "Write unit tests for the payment service",
        "Read the latest JavaScript newsletter",
    ]
    for text in examples:
        proba = pipeline.predict_proba([text])[0]
        pred = pipeline.classes_[np.argmax(proba)]
        conf = np.max(proba)
        print(f"    '{text[:45]}...' → {pred} ({conf:.2f})")

    print("\n" + "=" * 60)
    print("Training complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
