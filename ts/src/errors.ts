export const ContractCode = {
  DUPLICATE_IDENTIFIER: "assay.duplicate_identifier",
  EMPTY_COMPONENTS: "assay.empty_components",
  EMPTY_TERMS: "assay.empty_terms",
  INVALID_CLAMP_POLICY: "assay.invalid_clamp_policy",
  INVALID_COEFFICIENT: "assay.invalid_coefficient",
  INVALID_CONTRACT: "assay.invalid_contract",
  INVALID_DIRECTION: "assay.invalid_direction",
  INVALID_IDENTIFIER: "assay.invalid_identifier",
  INVALID_INPUTS_HASH: "assay.invalid_inputs_hash",
  INVALID_INTERVAL: "assay.invalid_interval",
  INVALID_LABEL: "assay.invalid_label",
  INVALID_METHOD: "assay.invalid_method",
  INVALID_NUMBER: "assay.invalid_number",
  INVALID_OBJECT: "assay.invalid_object",
  INVALID_OPERATION: "assay.invalid_operation",
  INVALID_RESULT: "assay.invalid_result",
  INVALID_SCALE: "assay.invalid_scale",
  INVALID_TEXT: "assay.invalid_text",
  INVALID_WEIGHT: "assay.invalid_weight",
  MISSING_FIELD: "assay.missing_field",
  MISSING_WEIGHT: "assay.missing_weight",
  OUT_OF_RANGE: "assay.out_of_range",
  UNKNOWN_FIELD: "assay.unknown_field",
} as const;

export type ContractCode = (typeof ContractCode)[keyof typeof ContractCode];

export class AssayError extends Error {
  public readonly code: string = "assay.error";

  public constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = new.target.name;
  }
}

export class ContractValidationError extends AssayError {
  public override readonly code: ContractCode;

  public constructor(code: ContractCode = ContractCode.INVALID_CONTRACT) {
    super(code);
    this.code = code;
  }
}

export class InvalidScoreRequest extends AssayError {
  public override readonly code = "assay.invalid_request";
}

export class InvalidRankingRequest extends AssayError {
  public override readonly code = "assay.invalid_ranking_request";
}

export class EmptyRelevantSet extends AssayError {
  public override readonly code = "assay.empty_relevant_set";
}
