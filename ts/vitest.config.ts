import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.ts"],
      exclude: ["src/**/*.test.ts", "src/index.ts"],
      // Portable scoring logic must keep its input, method, and replay branches covered.
      thresholds: {
        lines: 90,
        functions: 90,
        branches: 90,
      },
    },
  },
});
