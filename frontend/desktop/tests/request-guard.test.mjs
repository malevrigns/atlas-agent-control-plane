import assert from "node:assert/strict";
import test from "node:test";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { normalizeApiRequest } = require("../electron/request-guard.cjs");

test("accepts the API paths the desktop client actually calls", () => {
  const paths = [
    "/api/control-plane/tasks?project_id=default&limit=1",
    "/api/skills",
    "/api/skills/context?query=%E9%83%A8%E7%BD%B2",
    "/api/rag/knowledge-bases",
    "/api/rag/knowledge-bases/2f4a/query",
  ];
  for (const path of paths) {
    assert.equal(normalizeApiRequest({ path }).path, path);
  }
});

test("normalizes the method and defaults to GET", () => {
  assert.equal(normalizeApiRequest({ path: "/api/skills" }).method, "GET");
  assert.equal(
    normalizeApiRequest({ path: "/api/skills", method: "post" }).method,
    "POST",
  );
});

test("rejects paths that escape the API prefix", () => {
  const hostile = [
    "/etc/passwd",
    "api/skills",
    "//evil.test/api/steal",
    "/api/../../secret",
    "/api/skills\\..\\..",
    "/api/skills\nX-Injected: 1",
    "https://evil.test/api/skills",
  ];
  for (const path of hostile) {
    assert.throws(() => normalizeApiRequest({ path }), /invalid Atlas API path/, path);
  }
});

test("rejects methods outside the allowlist", () => {
  for (const method of ["PUT", "OPTIONS", "TRACE", "CONNECT"]) {
    assert.throws(
      () => normalizeApiRequest({ path: "/api/skills", method }),
      /unsupported Atlas API method/,
    );
  }
});

test("passes the body through untouched", () => {
  const body = { enabled: true, tags: ["部署"] };
  assert.deepEqual(
    normalizeApiRequest({ path: "/api/skills/x/enabled", method: "POST", body }).body,
    body,
  );
  assert.equal(normalizeApiRequest({ path: "/api/skills" }).body, undefined);
});

test("survives a malformed request object", () => {
  assert.throws(() => normalizeApiRequest(undefined), /invalid Atlas API path/);
  assert.throws(() => normalizeApiRequest({}), /invalid Atlas API path/);
});
