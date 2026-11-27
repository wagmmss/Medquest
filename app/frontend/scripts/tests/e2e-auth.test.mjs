import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

import { isE2EAuthBypassEnabled } from "../../src/lib/e2e-auth.ts";

test("isE2EAuthBypassEnabled stays closed when MEDQUEST_E2E_BUILD is missing", () => {
  assert.equal(
    isE2EAuthBypassEnabled({ PLAYWRIGHT_TEST: "true", CLERK_SECRET_KEY: "sk_test_mock" }, ""),
    false
  );
  assert.equal(
    isE2EAuthBypassEnabled({ PLAYWRIGHT_TEST: "true", CLERK_SECRET_KEY: "sk_test_mock" }, undefined),
    false
  );
});

test("isE2EAuthBypassEnabled stays closed without PLAYWRIGHT_TEST=true", () => {
  assert.equal(
    isE2EAuthBypassEnabled({ PLAYWRIGHT_TEST: "false", CLERK_SECRET_KEY: "sk_test_mock" }, "1"),
    false
  );
  assert.equal(
    isE2EAuthBypassEnabled({ CLERK_SECRET_KEY: "sk_test_mock" }, "1"),
    false
  );
});

test("isE2EAuthBypassEnabled refuses live Clerk secret keys even with build flag", () => {
  assert.equal(
    isE2EAuthBypassEnabled({ PLAYWRIGHT_TEST: "true", CLERK_SECRET_KEY: "sk_live_prod_secret" }, "1"),
    false
  );
});

test("isE2EAuthBypassEnabled activates only when all three guards match", () => {
  assert.equal(
    isE2EAuthBypassEnabled({ PLAYWRIGHT_TEST: "true", CLERK_SECRET_KEY: "sk_test_mock" }, "1"),
    true
  );
});

test("production Dockerfile never sets MEDQUEST_E2E_BUILD", () => {
  const dockerfilePath = path.resolve(import.meta.dirname, "../../Dockerfile");
  const content = fs.readFileSync(dockerfilePath, "utf8");
  assert.equal(content.includes("MEDQUEST_E2E_BUILD"), false);
});
