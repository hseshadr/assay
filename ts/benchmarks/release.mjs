import { execFileSync, spawnSync } from "node:child_process";
import { performance } from "node:perf_hooks";

import { compose, parseRequest, parseScoreResult } from "../dist/index.js";

const COMPOSITION_BATCH_COUNT = 2000;
const COMPOSITION_SAMPLES = 5;
const MINIMUM_COMPONENT_COUNT = 150000;
const BUDGETS_MS = new Map([
  ["typescript-composition-batch", 8000],
  ["typescript-minimum-compose-replay", 60000],
]);
const RSS_BUDGET_MIB = new Map([
  ["typescript-composition-batch", 512],
  ["typescript-minimum-compose-replay", 1536],
]);

function component(index, value) {
  return {
    id: `component-${index}`,
    label: `Component ${index}`,
    value,
    scale: { minimum: 0, maximum: 100, direction: "higher_is_better" },
    interval: null,
    weight: null,
  };
}

function smallRequest() {
  return parseRequest({
    method: "minimum",
    method_version: "benchmark-v1",
    components: [component(0, 60), component(1, 80)],
    clamp: "reject",
  });
}

function timings(operation, samples) {
  const values = [];
  for (let index = 0; index < samples; index += 1) {
    const started = performance.now();
    operation();
    values.push(performance.now() - started);
  }
  return values;
}

function percentile(values, fraction) {
  const ordered = [...values].sort((first, second) => first - second);
  const index = Math.max(0, Math.ceil(fraction * ordered.length) - 1);
  return ordered[index];
}

function evidence(workload, count, values) {
  return {
    workload,
    count,
    p50_ms: percentile(values, 0.5),
    p95_ms: percentile(values, 0.95),
    p99_ms: percentile(values, 0.99),
    peak_rss_mib: process.memoryUsage().rss / 1024 / 1024,
    node: process.versions.node,
    pnpm: execFileSync("pnpm", ["--version"], { encoding: "utf8" }).trim(),
    platform: `${process.platform}-${process.arch}`,
    sha: execFileSync("git", ["rev-parse", "HEAD"], {
      encoding: "utf8",
    }).trim(),
  };
}

function compositionBatch() {
  const request = smallRequest();
  const run = () => {
    for (let index = 0; index < COMPOSITION_BATCH_COUNT; index += 1)
      compose(request);
  };
  return evidence(
    "typescript-composition-batch",
    COMPOSITION_BATCH_COUNT,
    timings(run, COMPOSITION_SAMPLES),
  );
}

function minimumComposeReplay() {
  const components = Array.from(
    { length: MINIMUM_COMPONENT_COUNT },
    (_, index) => component(index, index % 101),
  );
  const request = parseRequest({
    method: "minimum",
    method_version: "benchmark-v1",
    components,
    clamp: "reject",
  });
  const run = () =>
    parseScoreResult(JSON.parse(JSON.stringify(compose(request))));
  return evidence(
    "typescript-minimum-compose-replay",
    MINIMUM_COMPONENT_COUNT,
    timings(run, 1),
  );
}

const RUNNERS = new Map([
  ["composition", compositionBatch],
  ["minimum", minimumComposeReplay],
]);

function requireBudget(report) {
  if (report.p99_ms > BUDGETS_MS.get(report.workload)) {
    throw new Error("benchmark latency budget exceeded");
  }
  if (report.peak_rss_mib > RSS_BUDGET_MIB.get(report.workload)) {
    throw new Error("benchmark memory budget exceeded");
  }
}

function child(name) {
  const result = spawnSync(
    process.execPath,
    [import.meta.filename, "--workload", name],
    {
      encoding: "utf8",
    },
  );
  if (result.status !== 0)
    throw new Error(result.stderr || "benchmark child failed");
  return JSON.parse(result.stdout);
}

if (process.argv.length === 4 && process.argv[2] === "--workload") {
  const report = RUNNERS.get(process.argv[3])();
  requireBudget(report);
  console.log(JSON.stringify(report));
} else {
  for (const name of RUNNERS.keys()) {
    const report = child(name);
    requireBudget(report);
    console.log(JSON.stringify(report));
  }
}
