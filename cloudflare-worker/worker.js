function configuredOrigin(env) {
  const value = String(env?.UPSTREAM_ORIGIN || "").trim();
  if (!value) throw new Error("PC tunnel is not configured.");
  const parsed = new URL(value);
  if (parsed.protocol !== "https:" || !parsed.hostname.endsWith(".trycloudflare.com")) {
    throw new Error("PC tunnel address is invalid.");
  }
  return parsed.origin;
}

async function fetchUpstream(target, request) {
  const retryable = request.method === "GET" || request.method === "HEAD";
  let lastError;
  for (let attempt = 0; attempt < (retryable ? 3 : 1); attempt += 1) {
    try {
      const response = await globalThis.fetch(target, {
        method: request.method,
        headers: request.headers,
        body: retryable ? undefined : request.body,
        redirect: "manual",
      });
      if (response.status !== 530) return response;
      lastError = new Error("PC server is offline.");
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error("PC server is offline.");
}

function offlineResponse() {
  return new Response("이 사이트는 지정된 PC와 터널이 실행 중일 때만 접속할 수 있습니다.", {
    status: 503,
    headers: {
      "content-type": "text/plain; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
    },
  });
}

export default {
  async fetch(request, env) {
    try {
      const origin = configuredOrigin(env);
      const incoming = new URL(request.url);
      const target = new URL(incoming.pathname + incoming.search, origin);
      const headers = new Headers(request.headers);
      headers.delete("host");
      headers.delete("authorization");
      headers.delete("cookie");
      const upstream = await fetchUpstream(target, new Request(request, { headers }));

      const responseHeaders = new Headers(upstream.headers);
      const location = responseHeaders.get("location");
      if (location && location.startsWith(origin)) {
        responseHeaders.set("location", location.replace(origin, incoming.origin));
      }
      responseHeaders.set("cache-control", "no-store");
      responseHeaders.set("x-content-type-options", "nosniff");
      responseHeaders.set("referrer-policy", "no-referrer");
      responseHeaders.set("x-real-estate-version", "2026-08-29-pc-only");

      return new Response(upstream.body, {
        status: upstream.status,
        statusText: upstream.statusText,
        headers: responseHeaders,
      });
    } catch (_error) {
      return offlineResponse();
    }
  },
};
