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

async function readSmallJson(bucket, key, maxBytes = 1024 * 1024) {
  const object = await bucket.get(key);
  if (!object || object.size > maxBytes) return null;
  try {
    return await object.json();
  } catch (_error) {
    return null;
  }
}

async function archivedRealEstateApi(request, env, incoming) {
  const bucket = env.REAL_ESTATE_ARCHIVE;
  if (!bucket || !["/api/catalog", "/api/meta", "/api/history", "/api/trades"].includes(incoming.pathname)) {
    return unavailableApi();
  }
  const current = await readSmallJson(bucket, "current.json", 16 * 1024);
  if (!current?.manifest_key) return unavailableApi("검증된 공개 실거래 스냅샷이 아직 없습니다.");
  const manifest = await readSmallJson(bucket, current.manifest_key);
  if (!manifest || manifest.snapshot_id !== current.snapshot_id) {
    return unavailableApi("공개 실거래 스냅샷 검증 정보가 일치하지 않습니다.");
  }
  if (incoming.pathname === "/api/meta") {
    return Response.json(manifest.meta || {}, {
      headers: {"cache-control": "public, max-age=60", "x-real-estate-source": "cloud-archive"},
    });
  }
  let descriptor = manifest.catalog;
  if (incoming.pathname === "/api/history" || incoming.pathname === "/api/trades") {
    const lawd = incoming.searchParams.get("lawd_cd") || "";
    if (!/^\d{5}$/.test(lawd)) return new Response(JSON.stringify({detail: "법정동 지역코드가 올바르지 않습니다."}), {status: 400, headers: {"content-type": "application/json"}});
    descriptor = manifest[incoming.pathname === "/api/history" ? "history" : "trades"]?.[lawd];
  }
  if (!descriptor?.key) return unavailableApi("선택한 지역의 검증된 공개 자료가 아직 없습니다.");
  const object = await bucket.get(descriptor.key);
  if (!object || object.size !== descriptor.bytes || object.key.split("/").pop()?.split(".")[0] !== descriptor.sha256) {
    return unavailableApi("공개 자료의 크기 또는 해시 식별자가 검증 정보와 일치하지 않습니다.");
  }
  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("content-type", "application/json; charset=utf-8");
  headers.set("content-encoding", "gzip");
  headers.set("cache-control", "public, max-age=31536000, immutable");
  headers.set("etag", object.httpEtag);
  headers.set("x-real-estate-source", "cloud-archive");
  headers.set("x-real-estate-snapshot", manifest.snapshot_id);
  return new Response(request.method === "HEAD" ? null : object.body, {headers});
}

async function localRealEstateApi(request, env, incoming) {
  if (!PUBLIC_REAL_ESTATE_APIS.has(incoming.pathname)) {
    return unavailableApi("이 API는 보안을 위해 로컬 PC에서만 사용할 수 있습니다.");
  }
  if (env.UPSTREAM_ORIGIN) {
    const target = new URL(incoming.pathname + incoming.search, env.UPSTREAM_ORIGIN);
    try {
      const upstream = await fetch(target, {
        method: request.method === "HEAD" ? "HEAD" : "GET",
        headers: { "user-agent": "korean-real-estate-readonly-gateway/1.0" },
        redirect: "follow",
        signal: AbortSignal.timeout(4500),
      });
      if (upstream.ok || upstream.status < 500) {
        const headers = new Headers(upstream.headers);
        headers.delete("set-cookie");
        headers.set("cache-control", "no-store");
        headers.set("x-content-type-options", "nosniff");
        headers.set("x-real-estate-source", "local-pc");
        return new Response(upstream.body, {status: upstream.status, statusText: upstream.statusText, headers});
      }
    } catch (_error) {
      // Fall through to the last fully verified immutable cloud snapshot.
    }
  }
  return archivedRealEstateApi(request, env, incoming);
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
