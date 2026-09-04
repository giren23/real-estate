const PUBLIC_SITE = "https://giren23.github.io/real-estate/";

function publicTarget(requestUrl) {
  const incoming = new URL(requestUrl);
  const base = new URL(PUBLIC_SITE);
  const relativePath = incoming.pathname.replace(/^\/+/, "");
  const target = new URL(relativePath || "index.html", base);
  target.search = incoming.search;
  return target;
}

function unavailableApi() {
  return new Response(JSON.stringify({
    detail: "이 기능은 로컬 PC 전용입니다. 공개 사이트에서는 저장된 최신 데이터로 동작합니다.",
  }), {
    status: 503,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
    },
  });
}

export default {
  async fetch(request) {
    const incoming = new URL(request.url);
    if (incoming.pathname.startsWith("/api/")) return unavailableApi();

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
    responseHeaders.set("x-real-estate-version", "2026-09-05-github-always-on");
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
