const PUBLIC_SITE = "https://giren23.github.io/real-estate/";
const PUBLIC_REAL_ESTATE_APIS = new Set([
  "/api/catalog",
  "/api/meta",
  "/api/history",
  "/api/trades",
  "/api/map-complexes",
  "/api/geocode",
  "/api/reverse-geocode",
  "/api/official-price",
]);

function publicTarget(requestUrl) {
  const incoming = new URL(requestUrl);
  const base = new URL(PUBLIC_SITE);
  const relativePath = incoming.pathname.replace(/^\/+/, "");
  const target = new URL(relativePath || "index.html", base);
  target.search = incoming.search;
  return target;
}

function unavailableApi(message = "현재 PC의 부동산 데이터 서버에 연결할 수 없습니다. 저장된 공개 데이터로 전환합니다.") {
  return new Response(JSON.stringify({
    detail: message,
  }), {
    status: 503,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
    },
  });
}

async function localRealEstateApi(request, env, incoming) {
  if (!PUBLIC_REAL_ESTATE_APIS.has(incoming.pathname)) {
    return unavailableApi("이 API는 보안을 위해 로컬 PC에서만 사용할 수 있습니다.");
  }
  if (!env.UPSTREAM_ORIGIN) return unavailableApi();
  const target = new URL(incoming.pathname + incoming.search, env.UPSTREAM_ORIGIN);
  try {
    const upstream = await fetch(target, {
      method: request.method === "HEAD" ? "HEAD" : "GET",
      headers: { "user-agent": "korean-real-estate-readonly-gateway/1.0" },
      redirect: "follow",
      signal: AbortSignal.timeout(4500),
    });
    const headers = new Headers(upstream.headers);
    headers.delete("set-cookie");
    headers.set("cache-control", "no-store");
    headers.set("x-content-type-options", "nosniff");
    headers.set("x-real-estate-source", "local-pc");
    return new Response(upstream.body, {status: upstream.status, statusText: upstream.statusText, headers});
  } catch (_error) {
    return unavailableApi();
  }
}

export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);
    if (incoming.pathname.startsWith("/api/")) return localRealEstateApi(request, env, incoming);

    const target = publicTarget(request.url);
    const upstream = await fetch(target, {
      method: request.method === "HEAD" ? "HEAD" : "GET",
      headers: { "user-agent": "korean-real-estate-public-gateway/1.0" },
      redirect: "follow",
    });
    const responseHeaders = new Headers(upstream.headers);
    responseHeaders.delete("set-cookie");
    responseHeaders.set("x-content-type-options", "nosniff");
    responseHeaders.set("referrer-policy", "strict-origin-when-cross-origin");
    responseHeaders.set("x-real-estate-version", "2026-09-05-hybrid-real-estate");
    responseHeaders.set("cache-control", /\.(?:js|css|png|jpg|jpeg|svg|webp|woff2?)$/i.test(incoming.pathname)
      ? "public, max-age=300"
      : "public, max-age=60, must-revalidate");
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  },
};
