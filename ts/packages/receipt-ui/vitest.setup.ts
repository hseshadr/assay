import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Unmount every rendered tree between tests so a leaked `role="status"` from one
// test can never satisfy a `getByRole` in the next.
afterEach(() => {
  cleanup();
});
