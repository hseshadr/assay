import type {
  AdditiveRequest,
  AdditiveTerm,
  Component,
  Interval,
  ScoreRequest,
} from "./contracts.js";

type Token = string | null | ReadonlyArray<Token>;

const PREIMAGE_VERSION = "assay.request/v1";
const INITIAL_STATE = [
  0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c,
  0x1f83d9ab, 0x5be0cd19,
] as const;
const ROUND_CONSTANTS = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
  0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
  0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
  0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
  0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
  0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
] as const;

function rotateRight(value: number, amount: number): number {
  return (value >>> amount) | (value << (32 - amount));
}

function word(values: ArrayLike<number>, index: number): number {
  return values[index] ?? 0;
}

function padded(input: Uint8Array): Uint8Array {
  const total = Math.ceil((input.length + 9) / 64) * 64;
  const output = new Uint8Array(total);
  output.set(input);
  output[input.length] = 0x80;
  new DataView(output.buffer).setBigUint64(
    total - 8,
    BigInt(input.length) * 8n,
    false,
  );
  return output;
}

function schedule(view: DataView, offset: number): Uint32Array {
  const words = new Uint32Array(64);
  for (let index = 0; index < 16; index += 1) {
    words[index] = view.getUint32(offset + index * 4, false);
  }
  for (let index = 16; index < 64; index += 1) {
    const previous = word(words, index - 15);
    const earlier = word(words, index - 2);
    const low =
      rotateRight(previous, 7) ^ rotateRight(previous, 18) ^ (previous >>> 3);
    const high =
      rotateRight(earlier, 17) ^ rotateRight(earlier, 19) ^ (earlier >>> 10);
    words[index] =
      (word(words, index - 16) + low + word(words, index - 7) + high) >>> 0;
  }
  return words;
}

function round(state: Uint32Array, words: Uint32Array): Uint32Array {
  const working = Uint32Array.from(state);
  for (let index = 0; index < 64; index += 1) {
    const a = word(working, 0);
    const e = word(working, 4);
    const choose = (e & word(working, 5)) ^ (~e & word(working, 6));
    const majority =
      (a & word(working, 1)) ^
      (a & word(working, 2)) ^
      (word(working, 1) & word(working, 2));
    const high = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
    const low = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22);
    const first =
      (word(working, 7) +
        high +
        choose +
        word(ROUND_CONSTANTS, index) +
        word(words, index)) >>>
      0;
    const second = (low + majority) >>> 0;
    working.set(
      [
        (first + second) >>> 0,
        a,
        word(working, 1),
        word(working, 2),
        (word(working, 3) + first) >>> 0,
        e,
        word(working, 5),
        word(working, 6),
      ],
      0,
    );
  }
  return working;
}

function compress(state: Uint32Array, view: DataView, offset: number): void {
  const working = round(state, schedule(view, offset));
  for (let index = 0; index < state.length; index += 1) {
    state[index] = (word(state, index) + word(working, index)) >>> 0;
  }
}

function sha256(input: string): string {
  const message = padded(new TextEncoder().encode(input));
  const view = new DataView(
    message.buffer,
    message.byteOffset,
    message.byteLength,
  );
  const state = Uint32Array.from(INITIAL_STATE);
  for (let offset = 0; offset < message.length; offset += 64) {
    compress(state, view, offset);
  }
  return Array.from(state, (value) => value.toString(16).padStart(8, "0")).join(
    "",
  );
}

function floatToken(value: number): string {
  const buffer = new ArrayBuffer(8);
  new DataView(buffer).setFloat64(0, value === 0 ? 0 : value, false);
  const bytes = new Uint8Array(buffer);
  return `f64:${Array.from(bytes, (item) => item.toString(16).padStart(2, "0")).join("")}`;
}

function intervalToken(interval: Interval | null): Token {
  return interval === null
    ? null
    : [floatToken(interval.low), floatToken(interval.high)];
}

function componentToken(component: Component): Token {
  return [
    component.id,
    component.label,
    floatToken(component.value),
    [
      floatToken(component.scale.minimum),
      floatToken(component.scale.maximum),
      component.scale.direction,
    ],
    intervalToken(component.interval),
    component.weight === null ? null : floatToken(component.weight),
  ];
}

function termToken(term: AdditiveTerm): Token {
  return [
    term.id,
    term.label,
    floatToken(term.value),
    floatToken(term.coefficient),
    term.operation,
    intervalToken(term.interval),
  ];
}

function additiveToken(request: AdditiveRequest): Token {
  return [
    PREIMAGE_VERSION,
    request.method,
    request.method_version,
    request.clamp,
    floatToken(request.intercept),
    request.terms.map(termToken),
  ];
}

function componentRequestToken(
  request: Exclude<ScoreRequest, AdditiveRequest>,
): Token {
  return [
    PREIMAGE_VERSION,
    request.method,
    request.method_version,
    request.clamp,
    request.components.map(componentToken),
  ];
}

export function inputsPreimage(request: ScoreRequest): string {
  const token =
    request.method === "additive"
      ? additiveToken(request)
      : componentRequestToken(request);
  return JSON.stringify(token);
}

export function inputsHash(request: ScoreRequest): string {
  return `sha256:${sha256(inputsPreimage(request))}`;
}
