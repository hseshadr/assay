import {
  type Component,
  type ExplainedComponent,
  type Interval,
  type MinimumRequest,
  parseRequest,
  parseScoreResult,
  type ScoreResult,
} from "./contracts.js";
import { ContractCode, ContractValidationError } from "./errors.js";
import { normalize } from "./normalize.js";
import { inputsHash } from "./requestHash.js";

function bounds(
  component: Component,
  request: MinimumRequest,
): readonly [number, number] {
  if (component.interval === null) {
    const point = normalize(component.value, component.scale, request.clamp);
    return [point, point];
  }
  const first = normalize(
    component.interval.low,
    component.scale,
    request.clamp,
  );
  const second = normalize(
    component.interval.high,
    component.scale,
    request.clamp,
  );
  return [Math.min(first, second), Math.max(first, second)];
}

function candidateInterval(
  component: Component,
  request: MinimumRequest,
): Interval | null {
  if (component.interval === null) return null;
  const [low, high] = bounds(component, request);
  return low === high ? null : { low, high };
}

function row(
  component: Component,
  request: MinimumRequest,
): ExplainedComponent {
  const normalized = normalize(component.value, component.scale, request.clamp);
  return {
    id: component.id,
    raw: component.value,
    normalized,
    declared_weight: null,
    operation: "add",
    coefficient: 1,
    contribution: normalized,
    contribution_interval: candidateInterval(component, request),
  };
}

function resultInterval(request: MinimumRequest): Interval | null {
  if (!request.components.some((component) => component.interval !== null))
    return null;
  let low = Number.POSITIVE_INFINITY;
  let high = Number.POSITIVE_INFINITY;
  for (const component of request.components) {
    const [candidateLow, candidateHigh] = bounds(component, request);
    low = Math.min(low, candidateLow);
    high = Math.min(high, candidateHigh);
  }
  return low === high ? null : { low, high };
}

function firstMinimum(
  rows: ReadonlyArray<ExplainedComponent>,
): ExplainedComponent {
  const first = rows[0] as ExplainedComponent;
  let selected = first;
  for (const candidate of rows.slice(1)) {
    if (candidate.contribution < selected.contribution) selected = candidate;
  }
  return selected;
}

export function minimum(input: MinimumRequest): ScoreResult {
  const request = parseRequest(input);
  if (request.method !== "minimum") {
    throw new ContractValidationError(ContractCode.INVALID_METHOD);
  }
  const rows = request.components.map((component) => row(component, request));
  const selected = firstMinimum(rows);
  return parseScoreResult({
    schema: "assay.result/v1",
    method: { id: request.method, version: request.method_version },
    score: selected.contribution,
    interval: resultInterval(request),
    clamp: request.clamp,
    intercept: null,
    weight_total: null,
    components: rows,
    inputs_hash: inputsHash(request),
    selected_component_id: selected.id,
  });
}
