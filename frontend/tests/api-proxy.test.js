import assert from "node:assert/strict";
import test from "node:test";

import handler from "../api/[...path].js";

function createResponse() {
  return {
    statusCode: 0,
    headers: new Map(),
    body: "",
    status(code) {
      this.statusCode = code;
      return this;
    },
    setHeader(name, value) {
      this.headers.set(name.toLowerCase(), value);
    },
    send(body) {
      this.body = body;
      return body;
    },
  };
}

test("booking proxy preserves the Retry-After header", async (context) => {
  const originalFetch = globalThis.fetch;
  const originalBackendUrl = process.env.BACKEND_API_URL;
  const originalApiKey = process.env.API_KEY;

  context.after(() => {
    globalThis.fetch = originalFetch;
    if (originalBackendUrl === undefined) {
      delete process.env.BACKEND_API_URL;
    } else {
      process.env.BACKEND_API_URL = originalBackendUrl;
    }
    if (originalApiKey === undefined) {
      delete process.env.API_KEY;
    } else {
      process.env.API_KEY = originalApiKey;
    }
  });

  process.env.BACKEND_API_URL = "https://clinic-api.example";
  process.env.API_KEY = "server-only-test-key";
  globalThis.fetch = async (url, options) => {
    assert.equal(url, "https://clinic-api.example/bookings");
    assert.equal(options.headers["X-API-Key"], "server-only-test-key");
    return new Response('{"error":"too many booking attempts"}', {
      status: 429,
      headers: {
        "Content-Type": "application/json",
        "Retry-After": "42",
      },
    });
  };

  const response = createResponse();
  await handler(
    {
      url: "/api/bookings",
      method: "POST",
      headers: { "content-type": "application/json" },
      body: { email: "patient@example.com" },
    },
    response,
  );

  assert.equal(response.statusCode, 429);
  assert.equal(response.headers.get("retry-after"), "42");
  assert.equal(response.body, '{"error":"too many booking attempts"}');
});
