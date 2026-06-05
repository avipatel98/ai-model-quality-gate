/**
 * K6 Spike Test — Task Priority Classifier API
 *
 * Goal: simulate a sudden traffic burst and verify the server
 * doesn't crash, recovers cleanly, and stays within SLA thresholds.
 * Profile: 5 → 100 VUs instantly, hold 1 min, drop back to 5.
 *
 * Run:
 *   k6 run k6/spike.js
 *   k6 run --out json=k6/results/spike.json k6/spike.js
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Rate, Counter } from "k6/metrics";

// ── Custom metrics ─────────────────────────────────────────────────────────────
const predictionLatency = new Trend("prediction_latency", true);
const errorRate         = new Rate("error_rate");
const successCount      = new Counter("success_count");

// ── Config ─────────────────────────────────────────────────────────────────────
const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";

const TASKS = [
  "Fix production database crash affecting all users",
  "Write unit tests for the payment service layer",
  "Read the latest JavaScript newsletter",
  "Deploy emergency security patch to authentication service",
  "Refactor authentication module to reduce code duplication",
  "Organise bookmarks folder for developer resources",
  "Resolve payment gateway timeout causing failed transactions",
  "Add input validation to the user registration form",
  "Watch conference talk on Rust memory safety",
  "Critical memory leak in the main API server",
];

// ── Thresholds ─────────────────────────────────────────────────────────────────
export const options = {
  stages: [
    { duration: "10s", target: 5   },  // baseline
    { duration: "0s",  target: 100 },  // instant spike
    { duration: "1m",  target: 100 },  // hold the spike
    { duration: "10s", target: 5   },  // drop back
    { duration: "30s", target: 5   },  // observe recovery
    { duration: "10s", target: 0   },  // cool-down
  ],
  thresholds: {
    http_req_duration: ["p(95)<500"],
    error_rate:        ["rate<0.01"],
    prediction_latency:["p(95)<500"],
    http_req_waiting:  ["p(95)<400"],
  },
};

// ── Main VU loop ───────────────────────────────────────────────────────────────
export default function () {
  const task = TASKS[Math.floor(Math.random() * TASKS.length)];

  const payload = JSON.stringify({ Task: task });
  const params  = { headers: { "Content-Type": "application/json" } };

  const res = http.post(`${BASE_URL}/predict`, payload, params);

  predictionLatency.add(res.timings.duration);

  const ok = check(res, {
    "status is 200":        (r) => r.status === 200,
    "has label field":      (r) => JSON.parse(r.body).label !== undefined,
    "has confidence field": (r) => JSON.parse(r.body).confidence !== undefined,
    "label is valid":       (r) => ["High", "Medium", "Low"].includes(JSON.parse(r.body).label),
  });

  errorRate.add(!ok);
  if (ok) successCount.add(1);

  sleep(1);
}

// ── Summary ────────────────────────────────────────────────────────────────────
export function handleSummary(data) {
  const dur   = data.metrics.http_req_duration  || {};
  const fails = data.metrics.http_req_failed     || {};
  const reqs  = data.metrics.http_reqs           || {};
  const v     = dur.values || {};

  const fmt = (n) => (n != null ? Number(n).toFixed(2) : "n/a");

  const p50 = v["p(50)"] ?? v["p50"];
  const p95 = v["p(95)"] ?? v["p95"];
  const p99 = v["p(99)"] ?? v["p99"];

  console.log("\n========== SPIKE TEST SUMMARY ==========");
  console.log(`Total requests  : ${reqs.values?.count ?? "n/a"}`);
  console.log(`RPS (avg)       : ${fmt(reqs.values?.rate)}`);
  console.log(`p50 latency     : ${fmt(p50)} ms`);
  console.log(`p95 latency     : ${fmt(p95)} ms`);
  console.log(`p99 latency     : ${fmt(p99)} ms`);
  console.log(`Max latency     : ${fmt(v.max)} ms`);
  console.log(`Error rate      : ${fmt((fails.values?.rate ?? 0) * 100)}%`);
  console.log("=========================================\n");

  return {
    "k6/results/spike_summary.json": JSON.stringify(data, null, 2),
  };
}
