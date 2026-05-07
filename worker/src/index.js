import { handleGameRequest, handleGameCron } from "./game.js";

// k-ant-daily quote proxy — Cloudflare Worker
//
// Proxies Naver Finance's realtime polling + news endpoints and adds CORS
// so the static GitHub Pages site can hit them from the browser.
//
// GET /quote?codes=005930,000660,...
//   → { "005930": {price, change, change_pct, direction, name, ts}, ... }
// GET /stock-news?codes=005930,000660,...
//   → { "005930": {news: [{title, url, source, published_at}], latest_at}, ... }
//
// Edge-cached per unique code-set — one upstream call serves all concurrent
// visitors until the cache expires. Quote: 30s, news: 5 min.

const NAVER_POLL = "https://polling.finance.naver.com/api/realtime";
const NAVER_ITEM = "https://finance.naver.com/item";
const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36";
const CACHE_TTL = 30;       // seconds — quote / ticker
const NEWS_CACHE_TTL = 300; // seconds — stock-news (5 min)
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
  // Allow whitespace inside the change span — Naver intermittently pads small
  // numbers ("<span class=\"change\"> 0.80</span>") and a strict [\d,.]+ would
  // backtrack and grab the next currency's section (JPY) instead.
  const m = html.match(/미국 USD[\s\S]{0,2000}?<span class="value">\s*([\d,.]+)\s*<\/span>[\s\S]{0,500}?<span class="change">\s*([\d,.]+)\s*<\/span>[\s\S]{0,500}?<span class="blind">(상승|하락|보합)<\/span>/);
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

// ─────────────────────────────────────────────────────────────────────
// Stock news — HTML scrape of the per-item news tab on Naver Finance.
// Used by the browser's intraday news-refresh polling; replaces the old
// launchd-based "crawl + commit every 10 min" workflow.
// ─────────────────────────────────────────────────────────────────────

// "2026.04.22 10:15" or "2026.04.22 10:15:30" → ISO-8601 + KST.
function parseNaverDate(s) {
  const m = String(s || "").match(/(\d{4})\.(\d{2})\.(\d{2})\s+(\d{2}):(\d{2})(?::(\d{2}))?/);
  if (!m) return null;
  return `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6] || "00"}+09:00`;
}

function stripTags(s) {
  return String(s || "").replace(/<[^>]*>/g, "").replace(/&nbsp;/g, " ").trim();
}

// HTML entity decoder for Naver headlines — named entities we see commonly
// plus numeric references. We keep this small because Korean headlines almost
// never use the full HTML5 named-entity set; anything exotic falls through
// untouched, which is better than URL-corrupting it.
const NAMED_ENTITIES = {
  amp: "&", lt: "<", gt: ">", quot: '"', apos: "'",
  nbsp: " ",
  hellip: "…", middot: "·", bull: "•",
  ldquo: "“", rdquo: "”", lsquo: "‘", rsquo: "’",
  uarr: "↑", darr: "↓", larr: "←", rarr: "→",
  times: "×", divide: "÷",
};
function unescHtml(s) {
  return String(s || "").replace(/&(#x?[0-9a-f]+|[a-z]+);/gi, (m, name) => {
    if (name.startsWith("#x") || name.startsWith("#X")) {
      const code = parseInt(name.slice(2), 16);
      return isNaN(code) ? m : String.fromCodePoint(code);
    }
    if (name.startsWith("#")) {
      const code = parseInt(name.slice(1), 10);
      return isNaN(code) ? m : String.fromCodePoint(code);
    }
    return NAMED_ENTITIES[name.toLowerCase()] || m;
  });
}

async function fetchStockNews(code, limit = 10) {
  const pageUrl = `${NAVER_ITEM}/news_news.naver?code=${code}&page=1&sm=title_entity_id.basic&clusterId=`;
  const referer = `${NAVER_ITEM}/main.naver?code=${code}`;
  const res = await fetch(pageUrl, {
    headers: {
      "User-Agent": UA,
      "Referer": referer,
      "Accept": "text/html,application/xhtml+xml",
      "Accept-Language": "ko-KR,ko;q=0.9",
    },
    cf: { cacheTtl: NEWS_CACHE_TTL, cacheEverything: true },
  });
  if (!res.ok) return [];
  const buf = await res.arrayBuffer();
  const html = new TextDecoder("euc-kr").decode(buf);

  // Don't try to bound the extraction by the outer <table class="type5">.
  // Naver nests its own cluster <table class="type5"> inside `relation_lst`
  // rows, which breaks any non-greedy `</table>` match. Iterate every <tr>
  // in the document and filter by attributes + presence of the title anchor.
  const items = [];
  const trRegex = /<tr([^>]*)>([\s\S]*?)<\/tr>/g;
  let m;
  while ((m = trRegex.exec(html)) !== null) {
    const attrs = m[1];
    // Skip cluster-related rows and hidden news rows Naver interleaves.
    if (/class\s*=\s*"[^"]*relation_lst/i.test(attrs)) continue;
    if (/class\s*=\s*"[^"]*hide_news/i.test(attrs)) continue;
    const row = m[2];

    // <td class="title"> <a class="tit" href="…">title</a></td>
    const titleMatch = row.match(
      /<td[^>]*class="[^"]*title[^"]*"[^>]*>[\s\S]*?<a[^>]*href="([^"]*)"[^>]*class="[^"]*tit[^"]*"[^>]*>([\s\S]*?)<\/a>/i,
    );
    if (!titleMatch) continue;
    let href = unescHtml(titleMatch[1]);
    if (href.startsWith("/")) href = "https://finance.naver.com" + href;
    const title = unescHtml(stripTags(titleMatch[2]));
    if (!title) continue;

    const infoMatch = row.match(/<td[^>]*class="[^"]*info[^"]*"[^>]*>([\s\S]*?)<\/td>/i);
    const source = infoMatch ? unescHtml(stripTags(infoMatch[1])) : "";

    const dateMatch = row.match(/<td[^>]*class="[^"]*date[^"]*"[^>]*>([\s\S]*?)<\/td>/i);
    const rawDate = dateMatch ? stripTags(dateMatch[1]) : "";
    const published_at = parseNaverDate(rawDate);

    items.push({ title, url: href, source, published_at });
    if (items.length >= limit) break;
  }
  // Newest first — the Naver table is already ordered that way, but enforce
  // in case the markup shifts.
  items.sort((a, b) => (b.published_at || "").localeCompare(a.published_at || ""));
  return items;
}

async function fetchAllStockNews(codes) {
  const results = await Promise.all(codes.map((c) => fetchStockNews(c).catch(() => [])));
  const out = {};
  codes.forEach((code, i) => {
    const news = results[i] || [];
    out[code] = {
      news,
      latest_at: news.length > 0 ? news[0].published_at : null,
    };
  });
  return out;
}

// ─────────────────────────────────────────────────────────────────────
// NXT (대체거래소) quotes — surfaces the pre-open (08:00-09:00) gap so the
// browser can adjust the 07:30 briefing's recommendation when NXT shows a
// meaningfully different direction. Data source: Naver 's three NXT sise
// list pages (상승·하락·시총). Scrape all three, merge by stock code.
// ─────────────────────────────────────────────────────────────────────

// Paginated NXT market-cap listings cover all ~644 NXT-listed stocks
// (KOSPI ~359 / KOSDAQ ~285 as of 2026-04). The rise/fall pages are subsets
// of the same rows and redundant now that we paginate market_sum.
const NXT_PAGES = (() => {
  const urls = [];
  for (let p = 1; p <= 8; p++) urls.push(`https://finance.naver.com/sise/nxt_sise_market_sum.naver?sosok=0&page=${p}`);
  for (let p = 1; p <= 6; p++) urls.push(`https://finance.naver.com/sise/nxt_sise_market_sum.naver?sosok=1&page=${p}`);
  return urls;
})();

async function fetchNxtPage(url) {
  const res = await fetch(url, {
    headers: {
      "User-Agent": UA,
      "Referer": "https://finance.naver.com/",
      "Accept": "text/html,application/xhtml+xml",
      "Accept-Language": "ko-KR,ko;q=0.9",
    },
    cf: { cacheTtl: 120, cacheEverything: true },  // 2-min edge cache
  });
  if (!res.ok) return {};
  const buf = await res.arrayBuffer();
  const html = new TextDecoder("euc-kr").decode(buf);

  // Each row carries (rank, name, currentPrice, 상승/하락, absChange, pct%, ...).
  // We pull code from the `code=XXXXXX` href and read the current price +
  // pct directly from positional text cells after stripping tags.
  const out = {};
  const rowRegex = /<tr[^>]*>([\s\S]*?)<\/tr>/g;
  let m;
  while ((m = rowRegex.exec(html)) !== null) {
    const body = m[1];
    const codeMatch = body.match(/code=(\d{6})/);
    if (!codeMatch) continue;
    const code = codeMatch[1];
    // Strip tags, split into non-empty cells.
    const text = body.replace(/<[^>]+>/g, "|");
    const cells = text.split("|").map((s) => s.trim()).filter(Boolean);
    if (cells.length < 6) continue;
    // Layout: [rank, name, price, direction(상승/하락/보합), absChange, "+X.XX%", ...]
    // Find first %-cell (등락률) and the price is 3 positions before it.
    let pctIdx = -1;
    for (let i = 0; i < cells.length; i++) {
      if (/^[+-]?\d+\.\d+%$/.test(cells[i])) { pctIdx = i; break; }
    }
    if (pctIdx < 3) continue;
    const pctStr   = cells[pctIdx];
    const price    = cells[pctIdx - 3];
    const absStr   = cells[pctIdx - 1];
    if (!/^[\d,]+$/.test(price)) continue;
    const direction = cells[pctIdx - 2];  // 상승/하락/보합
    const pctNum = parseFloat(pctStr.replace("%", ""));
    if (isNaN(pctNum)) continue;
    const absNum = parseFloat(absStr.replace(/,/g, ""));
    const priceNum = parseFloat(price.replace(/,/g, ""));
    // Naver's fall page renders pct/abs without explicit "-" prefix but marks
    // direction as "하락"; normalize the sign.
    const sign = direction === "하락" ? -1 : 1;
    const signedPct    = sign * Math.abs(pctNum);
    const signedChange = sign * Math.abs(isNaN(absNum) ? 0 : absNum);
    const dirCode = direction === "상승" ? "up"
                  : direction === "하락" ? "down"
                  : "flat";
    if (!out[code]) {
      // `price` is numeric so the client's fmtPrice (Number.toLocaleString)
      // works on it the same way it does for /quote responses — NXT becomes
      // a drop-in source for coffee-section updates during its session hours.
      out[code] = {
        price: isNaN(priceNum) ? null : priceNum,
        change: signedChange,
        change_pct: signedPct,
        direction: dirCode,
      };
    }
  }
  return out;
}

async function fetchAllNxtQuotes(codes) {
  const pages = await Promise.all(NXT_PAGES.map((u) => fetchNxtPage(u).catch(() => ({}))));
  const merged = {};
  for (const page of pages) Object.assign(merged, page);
  const out = {};
  for (const code of codes) out[code] = merged[code] || null;
  return out;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    // Game routes need their own CORS (POST + Content-Type), so handle them
    // *before* the global OPTIONS short-circuit.
    if (url.pathname.startsWith("/game/")) {
      return handleGameRequest(request, env, ctx);
    }
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }
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

    // NXT (대체거래소) pre-open / session quotes — serves the browser's
    // 08:00-15:30 NXT polling to adjust the 07:30 briefing's recommendations.
    if (url.pathname === "/nxt-quotes") {
      const raw = url.searchParams.get("codes") || "";
      const codes = raw
        .split(",")
        .map((c) => c.trim())
        .filter((c) => /^\d{6}$/.test(c))
        .slice(0, MAX_CODES);
      if (!codes.length) {
        return json({ error: "missing or invalid ?codes=005930,000660" }, 400);
      }
      const sorted = [...codes].sort().join(",");
      const cacheKey = new Request(`https://cache.k-ant-daily/nxt-quotes?codes=${sorted}`, { method: "GET" });
      const cache = caches.default;
      const cached = await cache.match(cacheKey);
      if (cached) {
        const body = await cached.text();
        return new Response(body, {
          status: 200,
          headers: {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "public, max-age=120",
            "X-Cache": "HIT",
            ...CORS_HEADERS,
          },
        });
      }
      let data;
      try { data = await fetchAllNxtQuotes(codes); }
      catch (e) { return json({ error: "upstream failed", detail: e.message }, 502); }
      const body = JSON.stringify(data);
      const resp = new Response(body, {
        status: 200,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": "public, max-age=120",
          "X-Cache": "MISS",
          ...CORS_HEADERS,
        },
      });
      ctx.waitUntil(cache.put(cacheKey, resp.clone()));
      return resp;
    }

    // Per-stock news tab scrape — serves the browser's intraday news polling.
    if (url.pathname === "/stock-news") {
      const raw = url.searchParams.get("codes") || "";
      const codes = raw
        .split(",")
        .map((c) => c.trim())
        .filter((c) => /^\d{6}$/.test(c))
        .slice(0, MAX_CODES);
      if (!codes.length) {
        return json({ error: "missing or invalid ?codes=005930,000660" }, 400);
      }

      const sorted = [...codes].sort().join(",");
      const cacheKey = new Request(`https://cache.k-ant-daily/stock-news?codes=${sorted}`, { method: "GET" });
      const cache = caches.default;
      const cached = await cache.match(cacheKey);
      if (cached) {
        const body = await cached.text();
        return new Response(body, {
          status: 200,
          headers: {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": `public, max-age=${NEWS_CACHE_TTL}`,
            "X-Cache": "HIT",
            ...CORS_HEADERS,
          },
        });
      }

      let data;
      try { data = await fetchAllStockNews(codes); }
      catch (e) { return json({ error: "upstream failed", detail: e.message }, 502); }

      const body = JSON.stringify(data);
      const resp = new Response(body, {
        status: 200,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": `public, max-age=${NEWS_CACHE_TTL}`,
          "X-Cache": "MISS",
          ...CORS_HEADERS,
        },
      });
      ctx.waitUntil(cache.put(cacheKey, resp.clone()));
      return resp;
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

  // Cron triggers — game lifecycle (open / lock / resolve).
  async scheduled(event, env, ctx) {
    ctx.waitUntil(handleGameCron(event, env, ctx));
  },
};
