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

async function sha1Hex(text) {
  const buf = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
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

// ─────────────────────────────────────────────────────────────────────
// Ticker sources — market indices, FX, crypto. Each returns:
//   { value, change_abs, change_pct, direction }
// value/change_abs/change_pct are pre-formatted strings so the client can
// drop them into spans without doing locale-specific rounding.
// ─────────────────────────────────────────────────────────────────────

function fmt(n, decimals) {
  return Number(n).toLocaleString("ko-KR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function signedAbs(n, decimals) {
  const sign = n > 0 ? "+" : n < 0 ? "-" : "";
  return sign + fmt(Math.abs(n), decimals);
}

function signedPct(n) {
  const sign = n > 0 ? "+" : "";
  return `${sign}${Number(n).toFixed(2)}%`;
}

// Naver SERVICE_INDEX. `nv` / `cv` are scaled by ×100 for index precision.
async function fetchIndex(code) {
  const url = `${NAVER_POLL}?query=${encodeURIComponent(`SERVICE_INDEX:${code}`)}`;
  const res = await fetch(url, {
    headers: { "User-Agent": UA, "Referer": "https://finance.naver.com/", "Accept": "application/json, text/plain, */*" },
    cf: { cacheTtl: CACHE_TTL, cacheEverything: true },
  });
  if (!res.ok) return null;
  const buf = await res.arrayBuffer();
  const text = new TextDecoder("euc-kr").decode(buf);
  let data;
  try { data = JSON.parse(text); } catch { return null; }
  const d = data?.result?.areas?.[0]?.datas?.[0];
  if (!d) return null;
  const value = d.nv / 100;
  const abs   = d.cv / 100;
  const pct   = d.cr;
  const direction = rfToDirection(d.rf);
  return {
    value: fmt(value, 2),
    change_abs: signedAbs(direction === "down" ? -Math.abs(abs) : Math.abs(abs), 2),
    change_pct: signedPct(direction === "down" ? -Math.abs(pct) : Math.abs(pct)),
    direction,
  };
}

// Naver marketindex HTML scrape — no JSON endpoint for FX.
async function fetchFxUsd() {
  const res = await fetch("https://finance.naver.com/marketindex/", {
    headers: { "User-Agent": UA, "Referer": "https://finance.naver.com/" },
    cf: { cacheTtl: CACHE_TTL, cacheEverything: true },
  });
  if (!res.ok) return null;
  const buf = await res.arrayBuffer();
  const html = new TextDecoder("euc-kr").decode(buf);
  // USD is the first li in ul#exchangeList. Capture value + change + rise/fall label.
  const m = html.match(/미국 USD[\s\S]{0,2000}?<span class="value">([\d,.]+)<\/span>[\s\S]{0,500}?<span class="change">([\d,.]+)<\/span>[\s\S]{0,500}?<span class="blind">(상승|하락|보합)<\/span>/);
  if (!m) return null;
  const [, value, change, rise] = m;
  const direction = rise === "상승" ? "up" : rise === "하락" ? "down" : "flat";
  const sign = direction === "up" ? "+" : direction === "down" ? "-" : "";
  return {
    value,
    change_abs: `${sign}${change}`,
    change_pct: null,  // Korean FX convention: no percentage
    direction,
  };
}

// Upbit public ticker — KRW-denominated crypto.
async function fetchUpbit(market) {
  const res = await fetch(`https://api.upbit.com/v1/ticker?markets=${market}`, {
    cf: { cacheTtl: CACHE_TTL, cacheEverything: true },
  });
  if (!res.ok) return null;
  const arr = await res.json().catch(() => null);
  const d = arr?.[0];
  if (!d) return null;
  const direction = d.change === "RISE" ? "up" : d.change === "FALL" ? "down" : "flat";
  const absRaw = Number(d.signed_change_price || 0);
  const pctRaw = Number(d.signed_change_rate || 0) * 100;
  return {
    value: fmt(Math.round(d.trade_price), 0),
    change_abs: signedAbs(absRaw, 0),
    change_pct: signedPct(pctRaw),
    direction,
  };
}

const TICKER_ITEMS = {
  KOSPI:  () => fetchIndex("KOSPI"),
  KOSDAQ: () => fetchIndex("KOSDAQ"),
  USDKRW: () => fetchFxUsd(),
  BTC:    () => fetchUpbit("KRW-BTC"),
  ETH:    () => fetchUpbit("KRW-ETH"),
};

async function fetchTicker(items) {
  const keys = items.filter((k) => k in TICKER_ITEMS);
  const results = await Promise.all(keys.map((k) => TICKER_ITEMS[k]().catch(() => null)));
  const out = {};
  keys.forEach((k, i) => { if (results[i]) out[k] = results[i]; });
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
    // Ticker strip — indices, FX, crypto.
    if (url.pathname === "/ticker") {
      const raw = url.searchParams.get("items") || "";
      const items = raw.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean).slice(0, 16);
      if (!items.length) {
        return json({ error: "missing ?items=KOSPI,KOSDAQ,USDKRW,BTC,ETH" }, 400);
      }
      const sortedItems = [...items].sort().join(",");
      const cacheKey = new Request(`https://cache.k-ant-daily/ticker?items=${sortedItems}`);
      const cache = caches.default;
      const cached = await cache.match(cacheKey);
      if (cached) {
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
      let data;
      try { data = await fetchTicker(items); }
      catch (e) { return json({ error: "upstream failed", detail: e.message }, 502); }
      const body = JSON.stringify(data);
      const resp = new Response(body, {
        status: 200,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": `public, max-age=${CACHE_TTL}`,
          "X-Cache": "MISS",
          ...CORS_HEADERS,
        },
      });
      ctx.waitUntil(cache.put(cacheKey, resp.clone()));
      return resp;
    }

    // ─── Feedback sync (news 👍/👎) ───
    // POST body: { url, rating ("up"|"down"|"clear"), ts, stock?, session_date }
    // KV key:    fb:<session_date>:<url_hash>
    // Value:     { url, rating, ts, stock }
    if (url.pathname === "/feedback") {
      if (!env.FEEDBACK) {
        return json({ error: "feedback store not configured" }, 503);
      }
      if (request.method === "POST") {
        let body;
        try { body = await request.json(); }
        catch { return json({ error: "invalid json" }, 400); }
        const u = String(body.url || "").slice(0, 500);
        const rating = String(body.rating || "");
        if (!u || !["up", "down", "clear"].includes(rating)) {
          return json({ error: "url + rating (up|down|clear) required" }, 400);
        }
        const sessionDate = /^\d{4}-\d{2}-\d{2}$/.test(body.session_date || "")
          ? body.session_date
          : new Date().toISOString().slice(0, 10);
        // Stable-ish hash of URL for readable keys.
        const urlHash = await sha1Hex(u);
        const key = `fb:${sessionDate}:${urlHash.slice(0, 12)}`;
        if (rating === "clear") {
          await env.FEEDBACK.delete(key);
        } else {
          const payload = JSON.stringify({
            url: u, rating, ts: Number(body.ts) || Date.now(),
            stock: body.stock || null,
          });
          await env.FEEDBACK.put(key, payload, {
            // 60-day retention — plenty for tuning cycles
            expirationTtl: 60 * 24 * 3600,
          });
        }
        return json({ ok: true }, 200);
      }
      if (request.method === "GET") {
        const date = url.searchParams.get("date");
        if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
          return json({ error: "missing ?date=YYYY-MM-DD" }, 400);
        }
        const list = await env.FEEDBACK.list({ prefix: `fb:${date}:`, limit: 1000 });
        const entries = [];
        for (const k of list.keys) {
          const v = await env.FEEDBACK.get(k.name);
          if (v) {
            try { entries.push(JSON.parse(v)); } catch {}
          }
        }
        return json({ date, count: entries.length, entries }, 200);
      }
      return json({ error: "method not allowed" }, 405);
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
