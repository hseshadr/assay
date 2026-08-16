import {
  type ClampPolicy,
  finiteNumber,
  type NativeScale,
  parseClampPolicy,
  parseNativeScale,
} from "./contracts.js";
import { ContractCode, ContractValidationError } from "./errors.js";

function fail(): never {
  throw new ContractValidationError(ContractCode.INVALID_NUMBER);
}

function formula(value: number, scale: NativeScale): number {
  const width = scale.maximum - scale.minimum;
  const offset =
    scale.direction === "lower_is_better"
      ? scale.maximum - value
      : value - scale.minimum;
  if (!Number.isFinite(width) || !Number.isFinite(offset)) fail();
  const result = offset / width;
  return Number.isFinite(result) ? result : fail();
}

function applyPolicy(value: number, policy: ClampPolicy): number {
  if (policy === "clamp") return Math.min(1, Math.max(0, value)) || 0;
  if (value < 0 || value > 1) {
    throw new ContractValidationError(ContractCode.OUT_OF_RANGE);
  }
  return value === 0 ? 0 : value;
}

export function normalize(
  value: unknown,
  scale: unknown,
  policy: unknown,
): number {
  const number = finiteNumber(value);
  const parsedScale = parseNativeScale(scale);
  return applyPolicy(formula(number, parsedScale), parseClampPolicy(policy));
}
