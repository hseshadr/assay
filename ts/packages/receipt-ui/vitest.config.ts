import { defineConfig } from "vitest/config";

export default defineConfig({
  // JSX compiles via oxc using tsconfig `jsx: "react-jsx"` — no extra config.
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["./vitest.setup.ts"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/index.ts"],
      // Component logic floor — the verify state machine, pin gate, tamper and
      // untrusted-signer paths, and the hex/status formatting.
      thresholds: {
        lines: 90,
        functions: 90,
        branches: 90,
      },
    },
  },
});
