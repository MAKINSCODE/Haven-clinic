import assert from "node:assert/strict";
import test from "node:test";

import { getBooking } from "../src/api.js";

test("booking lookup extracts a readable message from structured errors", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });

  globalThis.fetch = async (url) => {
    assert.equal(url, "/api/bookings/booking-id");
    return new Response(
      JSON.stringify({
        error: {
          code: "NOT_FOUND",
          message: "booking not found",
        },
      }),
      {
        status: 404,
        headers: { "Content-Type": "application/json" },
      },
    );
  };

  await assert.rejects(getBooking("booking-id"), {
    message: "booking not found",
  });
});
