"""
Threshold Self-Calibration
===========================
Parses K6 JSON summary output, computes p95 × 1.15 headroom for each
scenario, and writes the calibrated values to k6/config.json.

The K6 scripts read this file on the next run so thresholds stay
anchored to observed reality rather than hand-coded guesses.

Run:
    python3 k6/calibrate_thresholds.py
"""

import json
from pathlib import Path
from datetime import datetime

ROOT        = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "k6" / "results"
CONFIG_PATH = ROOT / "k6" / "config.json"
HEADROOM    = 1.15   # 15% headroom above observed p95


def extract_p95(summary: dict, metric: str = "http_req_duration") -> float | None:
    try:
        values = summary["metrics"][metric]["values"]
        return values.get("p(95)") or values.get("p95")
    except (KeyError, TypeError):
        return None


def load_summary(name: str) -> dict:
    path = RESULTS_DIR / name
    if not path.exists():
        print(f"  ⚠  {name} not found — skipping")
        return {}
    return json.loads(path.read_text())


def main():
    print("=" * 55)
    print("Threshold Self-Calibration")
    print("=" * 55)

    scenarios = {
        "ramp_up": load_summary("ramp_up_summary.json"),
        "spike":   load_summary("spike_summary.json"),
        "soak":    load_summary("soak_summary.json"),
    }

    # ── Collect p95s ───────────────────────────────────────────────
    p95_values = {}
    for name, data in scenarios.items():
        if not data:
            continue
        p95 = extract_p95(data)
        rps = None
        try:
            rps = data["metrics"]["http_reqs"]["values"]["rate"]
        except (KeyError, TypeError):
            pass

        if p95 is not None:
            p95_values[name] = {"p95_ms": round(p95, 2), "rps": round(rps, 2) if rps else None}
            rps_str = f"{rps:.1f}" if rps else "—"
            print(f"  {name:10}  p95={p95:.2f} ms   rps={rps_str}")

    if not p95_values:
        print("  No summary files found. Run k6 tests first.")
        return

    # ── Calibrate ──────────────────────────────────────────────────
    worst_p95  = max(v["p95_ms"] for v in p95_values.values())
    calibrated = round(worst_p95 * HEADROOM, 1)

    # TTFB is typically ~98% of p95 (minimal queueing on local server)
    ttfb_calibrated = round(worst_p95 * HEADROOM * 0.95, 1)

    print(f"\n  Worst observed p95 : {worst_p95:.2f} ms")
    print(f"  Headroom factor    : ×{HEADROOM}  (+15%)")
    print(f"  Calibrated p95     : {calibrated} ms")
    print(f"  Calibrated TTFB    : {ttfb_calibrated} ms")

    # ── Write config ───────────────────────────────────────────────
    existing = {}
    if CONFIG_PATH.exists():
        existing = json.loads(CONFIG_PATH.read_text())

    config = {
        **existing,
        "calibrated_at":     datetime.now().isoformat(timespec="seconds"),
        "headroom_factor":   HEADROOM,
        "worst_observed_p95_ms": worst_p95,
        "thresholds": {
            "http_req_duration_p95_ms": calibrated,
            "http_req_waiting_p95_ms":  ttfb_calibrated,
            "error_rate_pct":           1.0,
            "min_rps":                  50,
        },
        "per_scenario": p95_values,
    }

    CONFIG_PATH.write_text(json.dumps(config, indent=2))
    print(f"\n  Config written → {CONFIG_PATH}")
    print("=" * 55)


if __name__ == "__main__":
    main()
