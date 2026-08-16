import { additive } from "./additive.js";
import {
  type AdditiveRequest,
  type MinimumRequest,
  parseRequest,
  type ScoreRequest,
  type ScoreResult,
  type WeightedMeanRequest,
} from "./contracts.js";
import { minimum } from "./minimum.js";
import { weightedMean } from "./weightedMean.js";

export function compose(input: WeightedMeanRequest): ScoreResult;
export function compose(input: AdditiveRequest): ScoreResult;
export function compose(input: MinimumRequest): ScoreResult;
export function compose(input: ScoreRequest): ScoreResult;
export function compose(input: ScoreRequest): ScoreResult {
  const request = parseRequest(input);
  if (request.method === "weighted_mean") return weightedMean(request);
  if (request.method === "additive") return additive(request);
  return minimum(request);
}
