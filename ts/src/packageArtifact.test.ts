import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const PACKAGE_ROOT = new URL("..", import.meta.url);
const ARCHIVE_NAME = "edgeproc-assay-0.5.0-dev.0.tgz";

function runAt(
  cwd: string | URL,
  command: string,
  args: ReadonlyArray<string>,
): string {
  return execFileSync(command, args, {
    cwd,
    encoding: "utf8",
    env: process.env,
    stdio: ["ignore", "pipe", "pipe"],
  });
}

function run(command: string, args: ReadonlyArray<string>): string {
  return runAt(PACKAGE_ROOT, command, args);
}

function pack(destination: string): string {
  run("pnpm", ["build"]);
  run("pnpm", ["pack", "--pack-destination", destination]);
  return join(destination, ARCHIVE_NAME);
}

describe("the real npm artifact", () => {
  it("contains only the Assay runtime, types, metadata, license, and README", () => {
    const destination = mkdtempSync(join(tmpdir(), "assay-pack-"));
    try {
      const archive = pack(destination);
      const names = run("tar", ["-tzf", archive]).trim().split("\n").sort();

      expect(names).toContain("package/LICENSE");
      expect(names).toContain("package/README.md");
      expect(names).toContain("package/dist/index.js");
      expect(names).toContain("package/dist/index.d.ts");
      expect(names).toContain("package/package.json");
      expect(
        names.every(
          (name) =>
            [
              "package/LICENSE",
              "package/README.md",
              "package/package.json",
            ].includes(name) || /^package\/dist\/.+\.(?:js|d\.ts)$/u.test(name),
        ),
      ).toBe(true);

      const text = run("tar", ["-xOzf", archive]);
      expect(text).not.toMatch(
        /canonicalBytes|generateSeedHex|signPayload|SignedReceipt|verifySignature|receipt-ui|@noble\/ed25519|canonicalize|Writ/u,
      );
    } finally {
      rmSync(destination, { recursive: true, force: true });
    }
  }, 30_000);

  it("installs cleanly and runs every method while legacy subpaths stay closed", () => {
    const destination = mkdtempSync(join(tmpdir(), "assay-install-"));
    try {
      const archive = pack(destination);
      writeFileSync(
        join(destination, "package.json"),
        JSON.stringify({ private: true, type: "module" }),
      );
      runAt(destination, "pnpm", ["add", "--ignore-scripts", archive]);
      writeFileSync(
        join(destination, "verify.mjs"),
        `import { readFileSync } from "node:fs";
import { compose, parseRequest, parseScoreResult } from "@edgeproc/assay";

const vectors = JSON.parse(readFileSync(process.argv[2], "utf8"));
const ids = [];
for (const vector of vectors) {
  const result = compose(parseRequest(vector.request));
  if (JSON.stringify(result) !== JSON.stringify(vector.expected)) throw new Error(vector.id);
  parseScoreResult(JSON.parse(JSON.stringify(result)));
  ids.push(vector.id);
}
for (const path of ["receipt", "keys", "canonical", "ledger", "writ"]) {
  try {
    await import(\`@edgeproc/assay/\${path}\`);
    throw new Error(\`legacy subpath resolved: \${path}\`);
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("legacy subpath")) throw error;
  }
}
console.log(JSON.stringify(ids));
`,
      );
      const vectorPath = new URL(
        "../../testdata/vectors/composition.json",
        import.meta.url,
      );
      const output = runAt(destination, "node", [
        "verify.mjs",
        vectorPath.pathname,
      ]);

      expect(JSON.parse(output) as ReadonlyArray<string>).toEqual([
        "northstar_uncapped_weighted",
        "edgereco_recommendation",
        "amlfilter_match_confidence",
        "almamesh_domain_strength_forward_tie",
        "almamesh_domain_strength_reverse_tie",
      ]);
    } finally {
      rmSync(destination, { recursive: true, force: true });
    }
  }, 30_000);
});
