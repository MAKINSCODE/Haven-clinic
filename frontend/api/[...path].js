function jsonError(response, status, message) {
  response.status(status).json({ error: message });
}

function resolveBackendPath(pathname, method) {
  if (pathname === "/api/slots" && method === "GET") {
    return "/slots";
  }
  if (pathname === "/api/bookings" && ["GET", "POST"].includes(method)) {
    return "/bookings";
  }

  const bookingMatch = pathname.match(/^\/api\/bookings\/([^/]+)$/);
  if (bookingMatch && ["GET", "DELETE"].includes(method)) {
    let bookingId;
    try {
      bookingId = decodeURIComponent(bookingMatch[1]);
    } catch {
      return null;
    }
    if (!bookingId || bookingId.includes("/")) {
      return null;
    }
    return `/bookings/${encodeURIComponent(bookingId)}`;
  }

  return null;
}

export default async function handler(request, response) {
  const backendUrl = process.env.BACKEND_API_URL;
  const apiKey = process.env.API_KEY;
  if (!backendUrl || !apiKey) {
    return jsonError(response, 500, "booking service is not configured");
  }

  let incomingUrl;
  let upstreamPath;
  try {
    incomingUrl = new URL(request.url, "http://localhost");
    upstreamPath = resolveBackendPath(incomingUrl.pathname, request.method);
  } catch {
    return jsonError(response, 400, "invalid API request");
  }
  if (!upstreamPath) {
    return jsonError(response, 404, "API route not found");
  }

  const headers = {
    "X-API-Key": apiKey,
    Accept: "application/json",
  };
  if (request.headers["content-type"]) {
    headers["Content-Type"] = request.headers["content-type"];
  }
  if (request.headers["idempotency-key"]) {
    headers["Idempotency-Key"] = request.headers["idempotency-key"];
  }

  let body;
  if (request.method === "POST" && request.body !== undefined) {
    body =
      typeof request.body === "string"
        ? request.body
        : JSON.stringify(request.body);
  }

  try {
    const backendBase = backendUrl.replace(/\/+$/, "");
    const upstream = await fetch(
      `${backendBase}${upstreamPath}${incomingUrl.search}`,
      { method: request.method, headers, body },
    );
    const responseBody = await upstream.text();
    response.status(upstream.status);
    response.setHeader(
      "Content-Type",
      upstream.headers.get("content-type") || "application/json",
    );
    const retryAfter = upstream.headers.get("retry-after");
    if (retryAfter) {
      response.setHeader("Retry-After", retryAfter);
    }
    return response.send(responseBody);
  } catch (error) {
    console.error("Haven Clinic backend proxy request failed", error);
    return jsonError(response, 502, "booking service is unavailable");
  }
}
