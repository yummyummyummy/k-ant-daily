// k-ant-daily quote proxy — Cloudflare Worker
//
// Proxies Naver Finance's realtime polling endpoint and adds CORS so the
// static GitHub Pages site can hit it from the browser.
//
// GET /quote?codes=005930,000660,...
//   → { "005930": {price, change, change_pct, direction, name, ts}, ... }
//
// Edge-cached for 30s per unique code-set — one upstream call serves all
// concurrent visitors until the cache expires.

const NAVER_POLL = "https://polling.finance.naver.com/api/realtime";
const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36";
const CACHE_TTL = 30; // seconds
const MAX_CODES = 32;

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Max-Age": "86400",
};

function json(obj, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...CORS_HEADERS,
      ...extraHeaders,
    },
  });
}

// Map Naver's `rf` (risefall) code → direction.
// 1=상한, 2=상승, 3=보합, 4=하한, 5=하락
function rfToDirection(rf) {
  const s = String(rf ?? "");
  if (s === "1" || s === "2") return "up";
  if (s === "4" || s === "5") return "down";
  if (s === "3") return "flat";
  return "";
}

// Naver's polling API only returns one item per query, so fan out.
// Response body is EUC-KR encoded; we decode manually since TextDecoder
// supports legacy Korean encodings in Workers.
async function fetchOne(code) {
  const url = `${NAVER_POLL}?query=${encodeURIComponent(`SERVICE_ITEM:${code}`)}`;
  const res = await fetch(url, {
    headers: {
      "User-Agent": UA,
      "Referer": "https://finance.naver.com/",
      "Accept": "application/json, text/plain, */*",
      "Accept-Language": "ko-KR,ko;q=0.9",
    },
    cf: { cacheTtl: CACHE_TTL, cacheEverything: true },
  });
  if (!res.ok) return null;
  const buf = await res.arrayBuffer();
  const text = new TextDecoder("euc-kr").decode(buf);
  let data;
  try { data = JSON.parse(text); } catch { return null; }
  const d = data?.result?.areas?.[0]?.datas?.[0];
  if (!d?.cd) return null;
  const direction = rfToDirection(d.rf);
  // Naver returns `cv` (absolute change) and `cr` (change ratio) both
  // unsigned. Sign them here so downstream consumers don't need the rf code.
  const mag = direction === "down" ? -1 : 1;
  return {
    price: d.nv,
    change: Math.abs(Number(d.cv)) * mag,
    change_pct: Math.abs(Number(d.cr)) * mag,
    direction,
    name: d.nm,
    ts: Date.now(),
  };
}

async function fetchQuotes(codes) {
  const results = await Promise.all(codes.map((c) => fetchOne(c).catch(() => null)));
  const out = {};
  codes.forEach((code, i) => {
    const q = results[i];
    if (q) out[code] = q;
  });
  return out;
}

export default {
  async fetch(request, env, ctx) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    const url = new URL(request.url);
    if (url.pathname === "/" || url.pathname === "/health") {
      return json({ ok: true, service: "k-ant-daily-quotes" });
    }
    if (url.pathname !== "/quote") {
      return json({ error: "not found" }, 404);
    }

    const raw = url.searchParams.get("codes") || "";
    const codes = raw
      .split(",")
      .map((c) => c.trim())
      .filter((c) => /^\d{6}$/.test(c))
      .slice(0, MAX_CODES);

    if (!codes.length) {
      return json({ error: "missing or invalid ?codes=005930,000660" }, 400);
    }

    // Cache key: stable sort so re-ordering doesn't bust cache.
    const sorted = [...codes].sort().join(",");
    const cacheKey = new Request(`https://cache.k-ant-daily/quote?codes=${sorted}`, {
      method: "GET",
    });
    const cache = caches.default;

    const cached = await cache.match(cacheKey);
    if (cached) {
      // Ensure CORS headers on cached response.
      const body = await cached.text();
      return new Response(body, {
        status: 200,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": `public, max-age=${CACHE_TTL}`,
          "X-Cache": "HIT",
          ...CORS_HEADERS,
        },
      });
    }

    let quotes;
    try {
      quotes = await fetchQuotes(codes);
    } catch (e) {
      return json({ error: "upstream failed", detail: e.message }, 502);
    }

    const body = JSON.stringify(quotes);
    const response = new Response(body, {
      status: 200,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": `public, max-age=${CACHE_TTL}`,
        "X-Cache": "MISS",
        ...CORS_HEADERS,
      },
    });
    ctx.waitUntil(cache.put(cacheKey, response.clone()));
    return response;
  },
};
