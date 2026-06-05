/**
 * K6 Ramp-Up Test — Task Priority Classifier API
 *
 * Goal: identify the VU count at which latency begins to degrade.
 * Profile: 1 → 50 VUs over 5 minutes, then hold for 1 minute.
 *
 * Run:
 *   k6 run k6/ramp_up.js
 *   k6 run --out json=k6/results/ramp_up.json k6/ramp_up.js
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
  "Migrate legacy REST endpoints to the new GraphQL schema",
  "Browse new UI component libraries for future consideration",
];

// ── Thresholds (tasks 7 & 8) ──────────────────────────────────────────────────
export const options = {
  stages: [
    { duration: "30s",  target: 1  },  // warm-up
    { duration: "1m",   target: 10 },  // low load
    { duration: "1m",   target: 25 },  // moderate load
    { duration: "1m",   target: 50 },  // target peak
    { duration: "1m",   target: 50 },  // hold at peak
    { duration: "30s",  target: 0  },  // cool-down
  ],
  thresholds: {
    // p95 response time under 500ms
    http_req_duration: ["p(95)<500"],
    // fewer than 1% of requests fail
    error_rate: ["rate<0.01"],
    // custom latency trend mirrors http_req_duration for reporting
    prediction_latency: ["p(95)<500"],
    // TTFB under 400ms
    http_req_waiting: ["p(95)<400"],
  },
};

// ── Main VU loop ───────────────────────────────────────────────────────────────
export default function () {
  const task = TASKS[Math.floor(Math.random() * TASKS.length)];

  const payload = JSON.stringify({ Task: task });
  const params  = { headers: { "Content-Type": "application/json" } };

  const res = http.post(`${BASE_URL}/predict`, payload, params);

  // Track custom latency metric
  predictionLatency.add(res.timings.duration);

  const ok = check(res, {
    "status is 200":          (r) => r.status === 200,
    "has label field":        (r) => JSON.parse(r.body).label !== undefined,
    "has confidence field":   (r) => JSON.parse(r.body).confidence !== undefined,
    "label is valid":         (r) => ["High", "Medium", "Low"].includes(JSON.parse(r.body).label),
    "confidence between 0-1": (r) => {
      const c = JSON.parse(r.body).confidence;
      return c >= 0.0 && c <= 1.0;
    },
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

  // k6 v2 uses "p(95)" keys; fall back to p95 for older builds
  const p50 = v["p(50)"] ?? v["p50"];
  const p95 = v["p(95)"] ?? v["p95"];
  const p99 = v["p(99)"] ?? v["p99"];

  console.log("\n========== RAMP-UP TEST SUMMARY ==========");
  console.log(`Total requests  : ${reqs.values?.count ?? "n/a"}`);
  console.log(`RPS (avg)       : ${fmt(reqs.values?.rate)}`);
  console.log(`p50 latency     : ${fmt(p50)} ms`);
  console.log(`p95 latency     : ${fmt(p95)} ms`);
  console.log(`p99 latency     : ${fmt(p99)} ms`);
  console.log(`Max latency     : ${fmt(v.max)} ms`);
  console.log(`Error rate      : ${fmt((fails.values?.rate ?? 0) * 100)}%`);
  console.log("==========================================\n");

  return {
    "k6/results/ramp_up_summary.json": JSON.stringify(data, null, 2),
  };
}
