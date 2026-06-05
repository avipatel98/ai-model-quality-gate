/**
 * K6 Soak Test — Task Priority Classifier API
 *
 * Goal: hold 50 VUs for 30 minutes and surface memory leaks,
 * connection-pool exhaustion, or latency creep in the model server.
 *
 * The SOAK_DURATION env var lets CI override the duration without
 * editing this file (e.g. K6_ENV=SOAK_DURATION=2m for a smoke run).
 *
 * Run (full):
 *   k6 run --out json=k6/results/soak.json k6/soak.js
 *
 * Run (CI smoke — 2 min):
 *   k6 run -e SOAK_DURATION=2m --out json=k6/results/soak.json k6/soak.js
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Rate, Counter } from "k6/metrics";

// ── Custom metrics ─────────────────────────────────────────────────────────────
const predictionLatency = new Trend("prediction_latency", true);
const errorRate         = new Rate("error_rate");
const successCount      = new Counter("success_count");

// ── Config ─────────────────────────────────────────────────────────────────────
const BASE_URL      = __ENV.BASE_URL      || "http://localhost:8000";
const SOAK_DURATION = __ENV.SOAK_DURATION || "30m";

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
  "Investigate and fix data corruption in user records",
  "Set up automated database backups on a daily schedule",
  "Update personal bio on the company internal wiki",
];

// ── Test options ───────────────────────────────────────────────────────────────
export const options = {
  stages: [
    { duration: "2m",          target: 50 },   // ramp up
    { duration: SOAK_DURATION, target: 50 },   // hold — watch for drift
    { duration: "1m",          target: 0  },   // cool-down
  ],
  thresholds: {
    http_req_duration:  ["p(95)<500"],
    error_rate:         ["rate<0.01"],
    prediction_latency: ["p(95)<500"],
    http_req_waiting:   ["p(95)<400"],
    http_reqs:          ["rate>=50"],           // throughput ≥ 50 RPS
  },
};

// ── Main VU loop ───────────────────────────────────────────────────────────────
export default function () {
  const task    = TASKS[Math.floor(Math.random() * TASKS.length)];
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
  const dur   = data.metrics.http_req_duration || {};
  const fails = data.metrics.http_req_failed   || {};
  const reqs  = data.metrics.http_reqs         || {};
  const v     = dur.values || {};

  const fmt = (n) => (n != null ? Number(n).toFixed(2) : "n/a");
  const p95 = v["p(95)"] ?? v["p95"];

  console.log("\n========== SOAK TEST SUMMARY ==========");
  console.log(`Duration        : ${SOAK_DURATION} hold @ 50 VUs`);
  console.log(`Total requests  : ${reqs.values?.count ?? "n/a"}`);
  console.log(`RPS (avg)       : ${fmt(reqs.values?.rate)}`);
  console.log(`p95 latency     : ${fmt(p95)} ms`);
  console.log(`Max latency     : ${fmt(v.max)} ms`);
  console.log(`Error rate      : ${fmt((fails.values?.rate ?? 0) * 100)}%`);
  console.log("========================================\n");

  return {
    "k6/results/soak_summary.json": JSON.stringify(data, null, 2),
  };
}
