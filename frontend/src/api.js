// Browser requests stay same-origin; the server proxy adds the private API key.
function getErrorMessage(result) {
  for (const value of [result?.error, result?.detail]) {
    if (typeof value === "string" && value.trim()) {
      return value;
    }
    if (value && typeof value === "object") {
      for (const key of ["message", "detail", "msg"]) {
        if (typeof value[key] === "string" && value[key].trim()) {
          return value[key];
        }
      }
    }
  }
  return "The request could not be completed.";
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
  } catch (error) {
    throw new Error("Could not connect to the booking service.", { cause: error });
  }

  const result = await response.json();
  if (!response.ok) {
    throw new Error(getErrorMessage(result));
  }
  return result;
}

export async function getSlots() {
  const result = await request("/slots");
  if (Array.isArray(result)) return result;
  if (Array.isArray(result?.slots)) return result.slots;
  throw new Error("The booking service returned an unexpected slots response.");
}

export function createBooking(booking, idempotencyKey) {
  return request("/bookings", {
    method: "POST",
    body: JSON.stringify(booking),
    headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
  });
}

export function getBookingHistory(email, { cursor, limit } = {}) {
  const params = new URLSearchParams({ email });
  if (cursor) params.set("cursor", cursor);
  if (limit) params.set("limit", String(limit));
  return request(`/bookings?${params.toString()}`);
}

export function getBooking(bookingId) {
  return request(`/bookings/${encodeURIComponent(bookingId)}`);
}

export function cancelBooking(bookingId) {
  return request(`/bookings/${encodeURIComponent(bookingId)}`, {
    method: "DELETE",
  });
}