import {
  type Component,
  type ExplainedComponent,
  type Interval,
  parseRequest,
  parseScoreResult,
  type ScoreResult,
  type WeightedMeanRequest,
} from "./contracts.js";
import { ContractCode, ContractValidationError } from "./errors.js";
import { normalize } from "./normalize.js";
import { inputsHash } from "./requestHash.js";

function finiteOutput(value: number): number {
  if (!Number.isFinite(value)) {
    throw new ContractValidationError(ContractCode.INVALID_NUMBER);
  }
  return value === 0 ? 0 : value;
}

function leftAdd(values: ReadonlyArray<number>): number {
  let total = 0;
  for (const value of values) total = finiteOutput(total + value);
  return total;
}

function bounds(
  component: Component,
  request: WeightedMeanRequest,
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

function contributionInterval(
  component: Component,
  request: WeightedMeanRequest,
  coefficient: number,
): Interval | null {
  if (component.interval === null) return null;
  const [low, high] = bounds(component, request);
  const result = {
    low: finiteOutput(low * coefficient),
    high: finiteOutput(high * coefficient),
  };
  return result.low === result.high ? null : result;
}

function row(
  component: Component,
  request: WeightedMeanRequest,
  coefficient: number,
): ExplainedComponent {
  const normalized = normalize(component.value, component.scale, request.clamp);
  const weight = component.weight;
  if (weight === null)
    throw new ContractValidationError(ContractCode.MISSING_WEIGHT);
  return {
    id: component.id,
    raw: component.value,
    normalized,
    declared_weight: weight,
    operation: "add",
    coefficient,
    contribution: finiteOutput(normalized * coefficient),
    contribution_interval: contributionInterval(
      component,
      request,
      coefficient,
    ),
  };
}

function resultInterval(
  rows: ReadonlyArray<ExplainedComponent>,
): Interval | null {
  if (!rows.some((item) => item.contribution_interval !== null)) return null;
  const lows = rows.map(
    (item) => item.contribution_interval?.low ?? item.contribution,
  );
  const highs = rows.map(
    (item) => item.contribution_interval?.high ?? item.contribution,
  );
  const interval = { low: leftAdd(lows), high: leftAdd(highs) };
  return interval.low === interval.high ? null : interval;
}

export function weightedMean(input: WeightedMeanRequest): ScoreResult {
  const request = parseRequest(input);
  if (request.method !== "weighted_mean") {
    throw new ContractValidationError(ContractCode.INVALID_METHOD);
  }
  const weights = request.components.map((component) => component.weight ?? 0);
  const total = leftAdd(weights);
  const coefficients = weights.map((weight) => finiteOutput(weight / total));
  const rows = request.components.map((component, index) =>
    row(component, request, coefficients[index] ?? Number.NaN),
  );
  return parseScoreResult({
    schema: "assay.result/v1",
    method: { id: request.method, version: request.method_version },
    score: leftAdd(rows.map((item) => item.contribution)),
    interval: resultInterval(rows),
    clamp: request.clamp,
    intercept: null,
    weight_total: total,
    components: rows,
    inputs_hash: inputsHash(request),
    selected_component_id: null,
  });
}
