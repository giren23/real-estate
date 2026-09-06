const PUBLIC_SITE = "https://giren23.github.io/real-estate/";
const PRIVATE_ACCESS_COOKIE = "kre_private_access";
const PRIVATE_ACCESS_MAX_AGE = 60 * 60 * 24 * 180;
const PAPER_MAX_BYTES = 200000;
const PAPER_MAX_SYMBOLS = 20;
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

function json(data, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {"content-type":"application/json; charset=utf-8","cache-control":"no-store","x-content-type-options":"nosniff",...extraHeaders},
  });
}

function base64url(bytes) {
  let binary = "";
  for (const value of bytes) binary += String.fromCharCode(value);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

async function sha256(value) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, "0")).join("");
}

function constantTimeEqual(left, right) {
  const leftBytes = new TextEncoder().encode(left);
  const rightBytes = new TextEncoder().encode(right);
  if (leftBytes.length !== rightBytes.length) return false;
  let difference = 0;
  for (let index = 0; index < leftBytes.length; index += 1) {
    difference |= leftBytes[index] ^ rightBytes[index];
  }
  return difference === 0;
}

function cookieValue(request, name) {
  const cookie = request.headers.get("cookie") || "";
  for (const part of cookie.split(";")) {
    const separator = part.indexOf("=");
    if (separator < 0) continue;
    if (part.slice(0, separator).trim() === name) return part.slice(separator + 1).trim();
  }
  return "";
}

function privateHeaders(contentType = "text/html; charset=utf-8") {
  return {
    "content-type": contentType,
    "cache-control": "private, no-store",
    "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    "referrer-policy": "no-referrer",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
  };
}

function developmentPage(status = 200) {
  const body = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>개발 중</title><style>html{color-scheme:dark}body{min-height:100vh;margin:0;display:grid;place-items:center;background:#07111f;color:#e8eef8;font-family:system-ui,-apple-system,sans-serif}.card{width:min(84vw,420px);padding:38px 28px;border:1px solid #263750;border-radius:18px;background:#0d1a2b;text-align:center;box-shadow:0 18px 60px #0006}h1{margin:0 0 12px;font-size:1.55rem}p{margin:0;color:#aebed3;line-height:1.7}</style></head><body><main class="card"><h1>아직 개발 중입니다.</h1><p>서비스 준비가 완료되면 공개하겠습니다.</p></main></body></html>`;
  return new Response(body, {status, headers: privateHeaders()});
}

async function hasPrivateAccess(request, env) {
  const expected = String(env.PRIVATE_ACCESS_HASH || "");
  const supplied = cookieValue(request, PRIVATE_ACCESS_COOKIE);
  return /^[a-f0-9]{64}$/.test(expected) && constantTimeEqual(supplied, expected);
}

async function unlockPrivateAccess(request, env, incoming) {
  if (request.method !== "GET") return developmentPage(404);
  const key = incoming.searchParams.get("key") || "";
  if (key.length < 32 || key.length > 128) return developmentPage(404);
  const candidate = await sha256(key);
  const expected = String(env.PRIVATE_ACCESS_HASH || "");
  if (!/^[a-f0-9]{64}$/.test(expected) || !constantTimeEqual(candidate, expected)) return developmentPage(404);
  return new Response(null, {
    status: 303,
    headers: {
      location: "/index.html",
      "set-cookie": `${PRIVATE_ACCESS_COOKIE}=${candidate}; Path=/; Max-Age=${PRIVATE_ACCESS_MAX_AGE}; HttpOnly; Secure; SameSite=Strict`,
      ...privateHeaders(),
    },
  });
}

function logoutPrivateAccess() {
  return new Response(null, {
    status: 303,
    headers: {
      location: "/index.html",
      "set-cookie": `${PRIVATE_ACCESS_COOKIE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict`,
      ...privateHeaders(),
    },
  });
}

function paperCredentials(request) {
  const accountId = request.headers.get("x-paper-account") || "";
  const authorization = request.headers.get("authorization") || "";
  const token = authorization.startsWith("Bearer ") ? authorization.slice(7) : "";
  if (!/^[a-f0-9]{24}$/.test(accountId) || !/^[A-Za-z0-9_-]{40,64}$/.test(token)) return null;
  return {accountId, token};
}

function validPaperPayload(value) {
  if (!value || value.version !== 1 || !Number.isFinite(value.initialCash) || !Number.isFinite(value.cash)) return false;
  if (!value.positions || typeof value.positions !== "object" || Array.isArray(value.positions) || !Array.isArray(value.orders)) return false;
  if (Object.keys(value.positions).length > 100 || value.orders.length > 5000) return false;
  return Object.keys(value.positions).every(symbol => /^\d{6}$/.test(symbol));
}

async function createPaperAccount(env) {
  if (!env.PAPER_DB) return json({detail:"모의투자 저장소가 연결되지 않았습니다."}, 503);
  const token = base64url(crypto.getRandomValues(new Uint8Array(32)));
  const tokenHash = await sha256(token);
  const accountId = tokenHash.slice(0, 24);
  const now = new Date().toISOString();
  const payload = {version:1,initialCash:100000000,cash:100000000,realized:0,positions:{},orders:[],watchlist:[]};
  await env.PAPER_DB.prepare("INSERT INTO paper_portfolios(account_id,token_hash,payload,created_at,updated_at) VALUES(?,?,?,?,?)")
    .bind(accountId, tokenHash, JSON.stringify(payload), now, now).run();
  return json({account_id:accountId, token, payload, warning:"복구키를 잃으면 모의계좌를 복구할 수 없습니다."}, 201);
}

async function paperAccount(request, env) {
  if (!env.PAPER_DB) return json({detail:"모의투자 저장소가 연결되지 않았습니다."}, 503);
  const credentials = paperCredentials(request);
  if (!credentials) return json({detail:"유효한 모의계좌 복구키가 필요합니다."}, 401);
  const tokenHash = await sha256(credentials.token);
  const row = await env.PAPER_DB.prepare("SELECT payload,updated_at FROM paper_portfolios WHERE account_id=? AND token_hash=?")
    .bind(credentials.accountId, tokenHash).first();
  if (!row) return json({detail:"모의계좌를 찾을 수 없습니다."}, 401);
  if (request.method === "GET") return json({payload:JSON.parse(row.payload),updated_at:row.updated_at});
  if (request.method === "DELETE") {
    await env.PAPER_DB.prepare("DELETE FROM paper_portfolios WHERE account_id=? AND token_hash=?").bind(credentials.accountId, tokenHash).run();
    return json({deleted:true});
  }
  if (request.method !== "PUT") return json({detail:"지원하지 않는 요청입니다."}, 405, {allow:"GET, PUT, DELETE"});
  const length = Number(request.headers.get("content-length") || 0);
  if (length > PAPER_MAX_BYTES) return json({detail:"저장 데이터가 너무 큽니다."}, 413);
  let body;
  try { body = await request.json(); } catch (_error) { return json({detail:"JSON 형식이 아닙니다."}, 400); }
  const encoded = JSON.stringify(body?.payload);
  if (encoded.length > PAPER_MAX_BYTES || !validPaperPayload(body?.payload)) return json({detail:"유효하지 않은 모의투자 데이터입니다."}, 400);
  const now = new Date().toISOString();
  await env.PAPER_DB.prepare("UPDATE paper_portfolios SET payload=?,updated_at=? WHERE account_id=? AND token_hash=?")
    .bind(encoded, now, credentials.accountId, tokenHash).run();
  return json({saved:true,updated_at:now});
}

function yahooSymbol(symbol) { return `${symbol}.KS`; }

async function fetchYahooQuote(symbol) {
  const load = async suffix => {
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol + suffix)}?interval=1m&range=1d`;
    const response = await fetch(url, {headers:{"user-agent":"Mozilla/5.0 KoreanRealEstatePaper/1.0"}});
    if (!response.ok) return null;
    const payload = await response.json();
    return payload?.chart?.result?.[0] || null;
  };
  const result = await load(".KS") || await load(".KQ");
  if (!result) return {symbol,error:"시세 없음"};
  const meta = result.meta || {};
  const price = Number(meta.regularMarketPrice || meta.previousClose || 0);
  const previous = Number(meta.chartPreviousClose || meta.previousClose || 0);
  return {symbol,name:meta.shortName || meta.longName || symbol,price,change:price-previous,change_pct:previous ? (price/previous-1)*100 : 0,currency:meta.currency || "KRW",exchange:meta.exchangeName || "",observed_at:new Date((meta.regularMarketTime || Date.now()/1000)*1000).toISOString(),delayed:true};
}

async function paperQuotes(incoming) {
  const symbols = [...new Set((incoming.searchParams.get("symbols") || "").split(",").map(value => value.trim()).filter(Boolean))];
  if (!symbols.length || symbols.length > PAPER_MAX_SYMBOLS || symbols.some(value => !/^\d{6}$/.test(value))) return json({detail:`종목코드는 숫자 6자리, 최대 ${PAPER_MAX_SYMBOLS}개입니다.`}, 400);
  return json({available:true,items:await Promise.all(symbols.map(fetchYahooQuote)),limit:PAPER_MAX_SYMBOLS,refresh_seconds:15,read_only:true,source:"Yahoo Finance 공개 지연시세"});
}

async function paperSearch(incoming) {
  const query = (incoming.searchParams.get("q") || "").trim().slice(0, 40);
  if (query.length < 1) return json({items:[]});
  const response = await fetch(new URL("data/stock_catalog.json", PUBLIC_SITE), {headers:{"user-agent":"korean-real-estate-paper-search/1.0"}});
  if (!response.ok) return json({detail:"종목 카탈로그를 불러올 수 없습니다."}, 502);
  const payload = await response.json();
  const needle = query.replace(/\s+/g, "").toLowerCase();
  const items = (payload.items || []).filter(row => String(row.symbol || "").includes(needle) || String(row.name || "").replace(/\s+/g, "").toLowerCase().includes(needle)).slice(0, 10);
  return json({items});
}

async function paperApi(request, env, incoming) {
  if (incoming.pathname === "/api/paper/account" && request.method === "POST") return createPaperAccount(env);
  if (incoming.pathname === "/api/paper/account") return paperAccount(request, env);
  if (incoming.pathname === "/api/paper/quotes" && request.method === "GET") return paperQuotes(incoming);
  if (incoming.pathname === "/api/paper/search" && request.method === "GET") return paperSearch(incoming);
  return json({detail:"모의투자 API를 찾을 수 없습니다."}, 404);
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
    if (incoming.pathname === "/private-access") return unlockPrivateAccess(request, env, incoming);
    if (incoming.pathname === "/private-logout") return logoutPrivateAccess();
    if (!(await hasPrivateAccess(request, env))) {
      if (incoming.pathname.startsWith("/api/")) return json({detail:"찾을 수 없습니다."}, 404, privateHeaders("application/json; charset=utf-8"));
      return developmentPage();
    }
    if (incoming.pathname.startsWith("/api/paper/")) return paperApi(request, env, incoming);
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
    responseHeaders.set("referrer-policy", "no-referrer");
    responseHeaders.set("x-real-estate-version", "2026-09-05-hybrid-real-estate");
    responseHeaders.set("cache-control", "private, no-store");
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  },
};
