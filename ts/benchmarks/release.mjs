import { execFileSync, spawnSync } from "node:child_process";
import { performance } from "node:perf_hooks";

import { compose, parseRequest, parseScoreResult } from "../dist/index.js";
import { peakRssMib } from "./resourceUsage.mjs";

const COMPOSITION_BATCH_COUNT = 2000;
const HEAVY_SAMPLES = 5;
const MINIMUM_COMPONENT_COUNT = 150000;
const TIMEOUT_MARGIN_MS = 15000;
const BUDGETS_MS = new Map([
  ["typescript-composition-batch", 8000],
  ["typescript-minimum-compose-replay", 60000],
]);
const RSS_BUDGET_MIB = new Map([
  ["typescript-composition-batch", 512],
  ["typescript-minimum-compose-replay", 1536],
]);
const WORKLOADS = new Map([
  ["composition", "typescript-composition-batch"],
  ["minimum", "typescript-minimum-compose-replay"],
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

function percentile(values, fraction) {
  const ordered = [...values].sort((first, second) => first - second);
  const index = Math.max(0, Math.ceil(fraction * ordered.length) - 1);
  return ordered[index];
}

function identity() {
  return {
    node: process.versions.node,
    pnpm: execFileSync("pnpm", ["--version"], { encoding: "utf8" }).trim(),
    platform: `${process.platform}-${process.arch}`,
    sha: execFileSync("git", ["rev-parse", "HEAD"], {
      encoding: "utf8",
    }).trim(),
  };
}

function sample(workload, count, operation) {
  const started = performance.now();
  operation();
  return {
    workload,
    count,
    elapsed_ms: performance.now() - started,
    peak_rss_mib: peakRssMib(process.resourceUsage()),
    ...identity(),
  };
}

function compositionSample() {
  const request = smallRequest();
  const run = () => {
    for (let index = 0; index < COMPOSITION_BATCH_COUNT; index += 1)
      compose(request);
  };
  return sample("typescript-composition-batch", COMPOSITION_BATCH_COUNT, run);
}

function minimumSample() {
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
  return sample(
    "typescript-minimum-compose-replay",
    MINIMUM_COMPONENT_COUNT,
    run,
  );
}

const RUNNERS = new Map([
  ["composition", compositionSample],
  ["minimum", minimumSample],
]);

function report(samples) {
  const values = samples.map((item) => item.elapsed_ms);
  const first = samples[0];
  return {
    workload: first.workload,
    count: first.count,
    samples: samples.length,
    p50_ms: percentile(values, 0.5),
    p95_ms: percentile(values, 0.95),
    p99_ms: percentile(values, 0.99),
    peak_rss_mib: Math.max(...samples.map((item) => item.peak_rss_mib)),
    node: first.node,
    pnpm: first.pnpm,
    platform: first.platform,
    sha: first.sha,
  };
}

function requireBudget(result) {
  if (result.p99_ms > BUDGETS_MS.get(result.workload))
    throw new Error("benchmark latency budget exceeded");
  if (result.peak_rss_mib > RSS_BUDGET_MIB.get(result.workload))
    throw new Error("benchmark memory budget exceeded");
}

function childSample(name) {
  const workload = WORKLOADS.get(name);
  const result = spawnSync(
    process.execPath,
    [import.meta.filename, "--sample", name],
    {
      encoding: "utf8",
      timeout: BUDGETS_MS.get(workload) + TIMEOUT_MARGIN_MS,
    },
  );
  if (result.error?.code === "ETIMEDOUT")
    throw new Error("benchmark child timed out");
  if (result.status !== 0)
    throw new Error(result.stderr || "benchmark child failed");
  return JSON.parse(result.stdout);
}

function isolatedReport(name) {
  const samples = Array.from({ length: HEAVY_SAMPLES }, () =>
    childSample(name),
  );
  return report(samples);
}

if (process.argv.length === 4 && process.argv[2] === "--sample") {
  console.log(JSON.stringify(RUNNERS.get(process.argv[3])()));
} else if (process.argv.length === 4 && process.argv[2] === "--workload") {
  const result = isolatedReport(process.argv[3]);
  requireBudget(result);
  console.log(JSON.stringify(result));
} else {
  for (const name of RUNNERS.keys()) {
    const result = isolatedReport(name);
    requireBudget(result);
    console.log(JSON.stringify(result));
  }
}
