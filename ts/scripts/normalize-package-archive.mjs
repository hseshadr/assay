#!/usr/bin/env node

import {
  readFileSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";

const FIXED_HEADER = Buffer.from([
  0x1f, 0x8b, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
]);
const MINIMUM_GZIP_SIZE = 18;
const GZIP_OS_OFFSET = 9;
const UNIX_OS = 0x03;

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
}

function validHeader(bytes) {
  return (
    bytes.length >= MINIMUM_GZIP_SIZE &&
    bytes.subarray(0, 9).equals(FIXED_HEADER)
  );
}

function normalize(path) {
  const bytes = readFileSync(path);
  if (!validHeader(bytes)) {
    fail("expected canonical gzip header");
    return;
  }
  if (bytes[GZIP_OS_OFFSET] === UNIX_OS) return;
  const normalized = Buffer.from(bytes);
  normalized[GZIP_OS_OFFSET] = UNIX_OS;
  const temporary = `${path}.normalize-${process.pid}`;
  try {
    writeFileSync(temporary, normalized, { mode: statSync(path).mode });
    renameSync(temporary, path);
  } finally {
    rmSync(temporary, { force: true });
  }
}

const paths = process.argv.slice(2);
if (paths.length !== 1)
  fail("usage: normalize-package-archive.mjs ARCHIVE.tgz");
else normalize(paths[0]);
