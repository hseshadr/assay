import {
  type AdditiveRequest,
  type AdditiveTerm,
  type ExplainedComponent,
  type Interval,
  parseRequest,
  parseScoreResult,
  type ScoreResult,
} from "./contracts.js";
import { ContractCode, ContractValidationError } from "./errors.js";
import { inputsHash } from "./requestHash.js";

function finiteOutput(value: number): number {
  if (!Number.isFinite(value)) {
    throw new ContractValidationError(ContractCode.INVALID_NUMBER);
  }
  return value === 0 ? 0 : value;
}

function contribution(term: AdditiveTerm, value = term.value): number {
  return finiteOutput(value * term.coefficient);
}

function termBounds(term: AdditiveTerm): readonly [number, number] {
  if (term.interval === null) {
    const point = contribution(term);
    return [point, point];
  }
  return [
    contribution(term, term.interval.low),
    contribution(term, term.interval.high),
  ];
}

function contributionInterval(term: AdditiveTerm): Interval | null {
  const [low, high] = termBounds(term);
  return low === high ? null : { low, high };
}

function row(term: AdditiveTerm): ExplainedComponent {
  return {
    id: term.id,
    raw: term.value,
    normalized: null,
    declared_weight: null,
    operation: term.operation,
    coefficient: term.coefficient,
    contribution: contribution(term),
    contribution_interval: contributionInterval(term),
  };
}

function apply(
  total: number,
  amount: number,
  operation: "add" | "subtract",
): number {
  return finiteOutput(operation === "add" ? total + amount : total - amount);
}

function final(value: number, request: AdditiveRequest): number {
  const result = finiteOutput(value);
  if (request.clamp === null) return result;
  if (request.clamp === "clamp") return Math.min(1, Math.max(0, result)) || 0;
  if (result < 0 || result > 1) {
    throw new ContractValidationError(ContractCode.OUT_OF_RANGE);
  }
  return result;
}

function point(
  request: AdditiveRequest,
  rows: ReadonlyArray<ExplainedComponent>,
): number {
  let total = finiteOutput(request.intercept);
  for (const item of rows)
    total = apply(total, item.contribution, item.operation);
  return final(total, request);
}

function advanceBounds(
  low: number,
  high: number,
  term: AdditiveTerm,
): readonly [number, number] {
  const [termLow, termHigh] = termBounds(term);
  return term.operation === "add"
    ? [apply(low, termLow, "add"), apply(high, termHigh, "add")]
    : [apply(low, termHigh, "subtract"), apply(high, termLow, "subtract")];
}

function resultInterval(request: AdditiveRequest): Interval | null {
  if (!request.terms.some((term) => term.interval !== null)) return null;
  let low = finiteOutput(request.intercept);
  let high = low;
  for (const term of request.terms)
    [low, high] = advanceBounds(low, high, term);
  const result = { low: final(low, request), high: final(high, request) };
  return result.low === result.high ? null : result;
}

export function additive(input: AdditiveRequest): ScoreResult {
  const request = parseRequest(input);
  if (request.method !== "additive") {
    throw new ContractValidationError(ContractCode.INVALID_METHOD);
  }
  const rows = request.terms.map(row);
  return parseScoreResult({
    schema: "assay.result/v1",
    method: { id: request.method, version: request.method_version },
    score: point(request, rows),
    interval: resultInterval(request),
    clamp: request.clamp,
    intercept: request.intercept,
    weight_total: null,
    components: rows,
    inputs_hash: inputsHash(request),
    selected_component_id: null,
  });
}
