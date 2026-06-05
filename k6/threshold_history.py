"""
Threshold History Log
======================
Appends each calibration run's p95 readings to a running history file,
so you can track latency improvement across pipeline runs over time.

Run automatically after calibrate_thresholds.py, or standalone:
    python3 k6/threshold_history.py
"""

import json
from datetime import datetime
from pathlib import Path

ROOT         = Path(__file__).resolve().parent.parent
RESULTS_DIR  = ROOT / "k6" / "results"
CONFIG_PATH  = ROOT / "k6" / "config.json"
HISTORY_PATH = ROOT / "k6" / "threshold_history.json"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def main():
    config = load_json(CONFIG_PATH)
    if not config:
        print("No config.json found — run calibrate_thresholds.py first.")
        return

    history = load_json(HISTORY_PATH)
    runs    = history.get("runs", [])

    new_entry = {
        "run":           len(runs) + 1,
        "timestamp":     datetime.now().isoformat(timespec="seconds"),
        "worst_p95_ms":  config.get("worst_observed_p95_ms"),
        "calibrated_p95_ms": config.get("thresholds", {}).get("http_req_duration_p95_ms"),
        "per_scenario":  config.get("per_scenario", {}),
    }
    runs.append(new_entry)

    # ── Print history table ────────────────────────────────────────
    print("\n┌─────────────────────────────────────────────────────────┐")
    print("│          Threshold History — p95 Latency (ms)           │")
    print("├──────┬──────────────────────┬───────────┬───────────────┤")
    print("│  Run │      Timestamp       │ Worst p95 │ Calibrated p95│")
    print("├──────┼──────────────────────┼───────────┼───────────────┤")
    for r in runs:
        wp  = f"{r['worst_p95_ms']:.1f}" if r["worst_p95_ms"] else "—"
        cp  = f"{r['calibrated_p95_ms']:.1f}" if r["calibrated_p95_ms"] else "—"
        print(f"│ {r['run']:4} │ {r['timestamp']:20} │ {wp:>9} │ {cp:>13} │")
    print("└──────┴──────────────────────┴───────────┴───────────────┘")

    # ── Show improvement trend ────────────────────────────────────
    if len(runs) >= 2:
        first = runs[0]["worst_p95_ms"]
        last  = runs[-1]["worst_p95_ms"]
        if first and last and first != last:
            change  = last - first
            pct     = (change / first) * 100
            arrow   = "↓" if change < 0 else "↑"
            label   = "improvement" if change < 0 else "regression"
            print(f"\n  {arrow} {abs(pct):.1f}% {label} from run 1 → run {len(runs)}"
                  f"  ({first:.1f} ms → {last:.1f} ms)")

    # ── Save ──────────────────────────────────────────────────────
    HISTORY_PATH.write_text(json.dumps({"runs": runs}, indent=2))
    print(f"\n  History saved → {HISTORY_PATH}  ({len(runs)} run(s))\n")


if __name__ == "__main__":
    main()
