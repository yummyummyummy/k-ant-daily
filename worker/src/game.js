// Game routes — "국장 예측" friend betting game.
//
// 10 fixed stocks, daily ↑/↓ votes, parimutuel odds payout.
// State machine: open (07:30~09:00 KST) → closed (09:00~20:10) → resolved (20:10+)
// or `void` if no NXT closes available (휴장일).

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Access-Control-Max-Age": "86400",
};

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      ...CORS,
    },
  });
}

// 10 fixed stocks. To change, also bump GAME_STOCKS_VERSION so old rounds
// stay readable as snapshots.
export const GAME_STOCKS = [
  { code: "005930", name: "삼성전자" },
  { code: "000660", name: "SK하이닉스" },
  { code: "042700", name: "한미반도체" },
  { code: "005380", name: "현대차" },
  { code: "299660", name: "셀리드" },
  { code: "310210", name: "보로노이" },
  { code: "445680", name: "큐리옥스바이오시스템즈" },
  { code: "166480", name: "코아스템켐온" },
  { code: "174900", name: "앱클론" },
  { code: "298380", name: "에이비엘바이오" },
];

// ─── Date helpers (KST) ────────────────────────────────────────────────
//
// Cloudflare Workers run in UTC. Convert by adding 9h.

function nowKstDate() {
  const d = new Date(Date.now() + 9 * 3600 * 1000);
  return d.toISOString().slice(0, 10); // YYYY-MM-DD
}

function nowKstHour() {
  const d = new Date(Date.now() + 9 * 3600 * 1000);
  return d.getUTCHours();
}

function isWeekend(dateStr) {
  const d = new Date(dateStr + "T00:00:00Z");
  const dow = d.getUTCDay();
  return dow === 0 || dow === 6;
}

function nextTradingDay(dateStr) {
  let d = new Date(dateStr + "T00:00:00Z");
  for (let i = 0; i < 7; i++) {
    d = new Date(d.getTime() + 24 * 3600 * 1000);
    const dow = d.getUTCDay();
    if (dow !== 0 && dow !== 6) return d.toISOString().slice(0, 10);
  }
  return dateStr;
}

function previousTradingDay(dateStr) {
  let d = new Date(dateStr + "T00:00:00Z");
  for (let i = 0; i < 7; i++) {
    d = new Date(d.getTime() - 24 * 3600 * 1000);
    const dow = d.getUTCDay();
    if (dow !== 0 && dow !== 6) return d.toISOString().slice(0, 10);
  }
  return dateStr;
}

// The currently "focus" round date — what the UI shows as today's voting/result.
//   - Before 20:00 KST on a trading day  → today's round (votable until 09:00, then locked)
//   - After 20:00 KST on a trading day   → next trading day's round (voting just opened)
//   - On weekends                        → next trading day's round
function activeRoundDate() {
  const d = new Date(Date.now() + 9 * 3600 * 1000);
  const today = d.toISOString().slice(0, 10);
  const hour = d.getUTCHours();
  if (isWeekend(today)) return nextTradingDay(today);
  if (hour < 20) return today;
  return nextTradingDay(today);
}

// ISO 8601 week key — e.g. "2026-W20". Date string in "YYYY-MM-DD" (KST).
function weekKey(dateStr) {
  const d = new Date(dateStr + "T00:00:00Z");
  const day = d.getUTCDay() || 7;        // Sun=0 → 7
  d.setUTCDate(d.getUTCDate() + 4 - day);  // shift to Thursday of the same ISO week
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil(((d - yearStart) / 86400000 + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(weekNo).padStart(2, "0")}`;
}

// Returns { start, end } as YYYY-MM-DD for Monday and Friday of given week key.
function weekBounds(week) {
  const m = week.match(/^(\d{4})-W(\d{2})$/);
  if (!m) return null;
  const year = parseInt(m[1], 10);
  const w = parseInt(m[2], 10);
  // Jan 4 is always in ISO week 1. Compute Monday of W1, then offset.
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const dayOfJan4 = jan4.getUTCDay() || 7;
  const w1Mon = new Date(jan4.getTime() - (dayOfJan4 - 1) * 86400000);
  const monday = new Date(w1Mon.getTime() + (w - 1) * 7 * 86400000);
  const friday = new Date(monday.getTime() + 4 * 86400000);
  return {
    start: monday.toISOString().slice(0, 10),
    end: friday.toISOString().slice(0, 10),
  };
}

// Voting is open from (previousTradingDay(roundDate) 20:00 KST) → (roundDate 09:00 KST).
// Includes the entire weekend if previous trading day is Friday.
function isVotingOpenFor(roundDate) {
  const now = new Date(Date.now() + 9 * 3600 * 1000);
  const todayKst = now.toISOString().slice(0, 10);
  const hour = now.getUTCHours();
  const prevTrading = previousTradingDay(roundDate);

  if (todayKst === roundDate) return hour < 9;
  if (todayKst === prevTrading) return hour >= 20;
  // Strictly between previous trading day and round date → weekend window
  if (todayKst > prevTrading && todayKst < roundDate) return true;
  return false;
}

// ─── Token helpers ─────────────────────────────────────────────────────

function newId(prefix = "", len = 8) {
  // Crypto-safe alphanumeric. Workers globalThis.crypto is available.
  const bytes = new Uint8Array(len);
  crypto.getRandomValues(bytes);
  const alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"; // unambiguous
  let out = "";
  for (const b of bytes) out += alphabet[b % alphabet.length];
  return prefix + out;
}

function newToken() {
  // Long opaque token — used as auth credential.
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

// ─── Round lifecycle ───────────────────────────────────────────────────

async function ensureRoundExists(env, date) {
  // Idempotent: open the round for `date` if not already there. Skip weekends.
  // Captures prev_close at creation time (= the most recent available price,
  // typically the previous trading day's close since voting opens at 20:00
  // after market close).
  if (isWeekend(date)) return null;
  const existing = await env.DB.prepare("SELECT * FROM rounds WHERE date = ?")
    .bind(date)
    .first();
  if (existing) return existing;
  const stocksJson = JSON.stringify(GAME_STOCKS);
  const codes = GAME_STOCKS.map((s) => s.code);
  const prevCloses = await fetchNaverPrices(codes);
  await env.DB.prepare(
    `INSERT INTO rounds (date, stocks_json, status, prev_closes_json, locked_at)
     VALUES (?, ?, 'open', ?, ?)`
  )
    .bind(date, stocksJson, JSON.stringify(prevCloses), Date.now())
    .run();
  return { date, stocks_json: stocksJson, status: "open", prev_closes_json: JSON.stringify(prevCloses) };
}

async function resolveRound(env, date, fetchClosesFn, { force = false } = {}) {
  // Compute directions, write results, compute scores.
  // Accept 'open'/'closed'/'void' here. With the new time-based voting window
  // we no longer have a separate 'closed' lock cron, so a round goes
  // open → resolved directly. `force=true` also accepts 'resolved' for
  // re-resolution (e.g. fixing missing NXT data).
  const round = await env.DB.prepare("SELECT * FROM rounds WHERE date = ?")
    .bind(date)
    .first();
  if (!round) return;
  const allowed = force ? ["open", "closed", "resolved", "void"] : ["open", "closed"];
  if (!allowed.includes(round.status)) return;

  const stocks = JSON.parse(round.stocks_json);
  const codes = stocks.map((s) => s.code);
  const prevCloses = JSON.parse(round.prev_closes_json || "{}");
  const todayCloses = await fetchClosesFn(codes);

  // KRX fallback — NXT covers ~644 stocks but small-cap KOSDAQ (e.g. 셀리드,
  // 앱클론, 코아스템켐온) often miss. Re-fetch any nulls from Naver realtime
  // (= KRX 15:30 close once the market is closed). Friday-evening / weekend /
  // holiday queries also return the most recent KRX close.
  const missing = codes.filter((c) => todayCloses[c] == null);
  if (missing.length > 0) {
    const fallback = await fetchNaverPrices(missing);
    for (const c of missing) {
      if (fallback[c] != null) todayCloses[c] = fallback[c];
    }
  }

  // No closes = holiday. Mark void.
  const validCodes = codes.filter(
    (c) => todayCloses[c] != null && prevCloses[c] != null
  );
  if (validCodes.length === 0) {
    await env.DB.prepare(
      "UPDATE rounds SET status='void', resolved_at=? WHERE date=?"
    )
      .bind(Date.now(), date)
      .run();
    return;
  }

  const results = {};
  for (const code of codes) {
    const prev = prevCloses[code];
    const today = todayCloses[code];
    if (prev == null || today == null) {
      results[code] = { direction: "void", close: today, prev_close: prev };
      continue;
    }
    const changePct = ((today - prev) / prev) * 100;
    let direction;
    if (Math.abs(changePct) < 0.1) direction = "flat";
    else direction = today > prev ? "up" : "down";
    results[code] = { direction, close: today, prev_close: prev, change_pct: changePct };
  }

  // Score every (room, member) for this date.
  // Step 1: pull all votes for this date.
  const voteRows = await env.DB.prepare(
    "SELECT room_id, member_name, stock_code, pick FROM votes WHERE date = ?"
  )
    .bind(date)
    .all();

  // Step 2: compute per-(room, stock) vote counts.
  const counts = new Map(); // key = `${room}|${code}` → {up, down}
  for (const v of voteRows.results || []) {
    const key = `${v.room_id}|${v.stock_code}`;
    let c = counts.get(key);
    if (!c) {
      c = { up: 0, down: 0 };
      counts.set(key, c);
    }
    c[v.pick] += 1;
  }

  // Step 3: aggregate per-(room, member) → {hits, total, points}.
  const scoreMap = new Map(); // key = `${room}|${member}` → {hits, total, points}
  for (const v of voteRows.results || []) {
    const r = results[v.stock_code];
    if (!r) continue;
    const key = `${v.room_id}|${v.member_name}`;
    let s = scoreMap.get(key);
    if (!s) {
      s = { hits: 0, total: 0, points: 0 };
      scoreMap.set(key, s);
    }
    if (r.direction === "void" || r.direction === "flat") continue; // count nothing
    s.total += 1;
    if (v.pick === r.direction) {
      const c = counts.get(`${v.room_id}|${v.stock_code}`);
      const sameSide = c[v.pick];
      const totalVoters = c.up + c.down;
      const odds = sameSide > 0 ? totalVoters / sameSide : 0;
      s.hits += 1;
      s.points += Math.round(odds * 100) / 100;
    }
  }

  // Step 4: write scores + round results in a transaction-like batch.
  const stmts = [
    env.DB.prepare(
      "UPDATE rounds SET status='resolved', results_json=?, resolved_at=? WHERE date=?"
    ).bind(JSON.stringify(results), Date.now(), date),
  ];
  for (const [key, s] of scoreMap.entries()) {
    const [room, member] = key.split("|");
    stmts.push(
      env.DB.prepare(
        `INSERT INTO scores (room_id, member_name, date, hits, total, points)
         VALUES (?, ?, ?, ?, ?, ?)
         ON CONFLICT(room_id, member_name, date) DO UPDATE
           SET hits=excluded.hits, total=excluded.total, points=excluded.points`
      ).bind(room, member, date, s.hits, s.total, s.points)
    );
  }
  await env.DB.batch(stmts);
}

// ─── Naver price fetchers ─────────────────────────────────────────────

const NAVER_POLL = "https://polling.finance.naver.com/api/realtime";
const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36";

async function fetchNaverPrice(code) {
  const url = `${NAVER_POLL}?query=${encodeURIComponent(`SERVICE_ITEM:${code}`)}`;
  const res = await fetch(url, {
    headers: { "User-Agent": UA, "Referer": "https://finance.naver.com/" },
    cf: { cacheTtl: 60, cacheEverything: true },
  });
  if (!res.ok) return null;
  const buf = await res.arrayBuffer();
  const text = new TextDecoder("euc-kr").decode(buf);
  let data;
  try { data = JSON.parse(text); } catch { return null; }
  const d = data?.result?.areas?.[0]?.datas?.[0];
  return d?.nv ?? null;
}

async function fetchNaverPrices(codes) {
  const results = await Promise.all(codes.map((c) => fetchNaverPrice(c).catch(() => null)));
  const out = {};
  codes.forEach((c, i) => { if (results[i] != null) out[c] = results[i]; });
  return out;
}

// NXT 20:00 close — paginate the NXT 시총 listings, find each game stock.
const NXT_PAGES = (() => {
  const urls = [];
  for (let p = 1; p <= 8; p++) urls.push(`https://finance.naver.com/sise/nxt_sise_market_sum.naver?sosok=0&page=${p}`);
  for (let p = 1; p <= 6; p++) urls.push(`https://finance.naver.com/sise/nxt_sise_market_sum.naver?sosok=1&page=${p}`);
  return urls;
})();

async function fetchNxtPage(url) {
  const res = await fetch(url, {
    headers: { "User-Agent": UA, "Referer": "https://finance.naver.com/" },
    cf: { cacheTtl: 120, cacheEverything: true },
  });
  if (!res.ok) return {};
  const buf = await res.arrayBuffer();
  const html = new TextDecoder("euc-kr").decode(buf);
  const out = {};
  const rowRegex = /<tr[^>]*>([\s\S]*?)<\/tr>/g;
  let m;
  while ((m = rowRegex.exec(html)) !== null) {
    const body = m[1];
    const codeMatch = body.match(/code=(\d{6})/);
    if (!codeMatch) continue;
    const code = codeMatch[1];
    const text = body.replace(/<[^>]+>/g, "|");
    const cells = text.split("|").map((s) => s.trim()).filter(Boolean);
    if (cells.length < 6) continue;
    let pctIdx = -1;
    for (let i = 0; i < cells.length; i++) {
      if (/^[+-]?\d+\.\d+%$/.test(cells[i])) { pctIdx = i; break; }
    }
    if (pctIdx < 3) continue;
    const price = cells[pctIdx - 3];
    if (!/^[\d,]+$/.test(price)) continue;
    const priceNum = parseFloat(price.replace(/,/g, ""));
    if (!out[code] && !isNaN(priceNum)) out[code] = priceNum;
  }
  return out;
}

async function fetchNxtCloses(codes) {
  const pages = await Promise.all(NXT_PAGES.map((u) => fetchNxtPage(u).catch(() => ({}))));
  const merged = {};
  for (const page of pages) Object.assign(merged, page);
  const out = {};
  for (const code of codes) out[code] = merged[code] ?? null;
  return out;
}

// ─── Route handlers ────────────────────────────────────────────────────

async function createRoom(env, body) {
  const name = (body.name || "").trim();
  const members = Array.isArray(body.members) ? body.members.map((m) => String(m).trim()).filter(Boolean) : [];
  if (!name) return json({ error: "name required" }, 400);
  if (members.length === 0) return json({ error: "members required" }, 400);
  if (members.length > 20) return json({ error: "too many members (max 20)" }, 400);

  const roomId = newId("R", 8);
  await env.DB.prepare("INSERT INTO rooms (id, name, created_at) VALUES (?, ?, ?)")
    .bind(roomId, name, Date.now())
    .run();

  const stmts = members.map((m) =>
    env.DB.prepare("INSERT INTO members (room_id, name) VALUES (?, ?)").bind(roomId, m)
  );
  await env.DB.batch(stmts);

  return json({ room_id: roomId, name, members });
}

async function claimMember(env, roomId, body) {
  const name = (body.name || "").trim();
  if (!name) return json({ error: "name required" }, 400);
  const member = await env.DB.prepare(
    "SELECT name, token FROM members WHERE room_id = ? AND name = ?"
  )
    .bind(roomId, name)
    .first();
  if (!member) return json({ error: "name not in room roster" }, 404);
  if (member.token) return json({ error: "name already claimed" }, 409);

  const token = newToken();
  await env.DB.prepare(
    "UPDATE members SET token=?, joined_at=? WHERE room_id=? AND name=?"
  )
    .bind(token, Date.now(), roomId, name)
    .run();
  return json({ name, token });
}

async function addMember(env, roomId, body) {
  // Anyone can add a missing roster name (friend group, low trust ceremony).
  const name = (body.name || "").trim();
  if (!name) return json({ error: "name required" }, 400);
  const room = await env.DB.prepare("SELECT id FROM rooms WHERE id=?").bind(roomId).first();
  if (!room) return json({ error: "room not found" }, 404);
  try {
    await env.DB.prepare("INSERT INTO members (room_id, name) VALUES (?, ?)")
      .bind(roomId, name)
      .run();
  } catch (e) {
    return json({ error: "name already in roster" }, 409);
  }
  return json({ ok: true, name });
}

async function whoAmI(env, roomId, token) {
  if (!token) return null;
  const member = await env.DB.prepare(
    "SELECT name FROM members WHERE room_id=? AND token=?"
  )
    .bind(roomId, token)
    .first();
  return member ? member.name : null;
}

// Most recent resolved round before `excludeDate`, with per-stock results
// and reveal of every member's pick + each member's points for that day.
async function getRecentResolved(env, roomId, excludeDate) {
  const round = await env.DB.prepare(
    `SELECT date, stocks_json, results_json FROM rounds
     WHERE status='resolved' AND date < ?
     ORDER BY date DESC LIMIT 1`
  )
    .bind(excludeDate)
    .first();
  if (!round) return null;

  const stocks = JSON.parse(round.stocks_json);
  const results = JSON.parse(round.results_json || "{}");

  const voteRows = await env.DB.prepare(
    "SELECT member_name, stock_code, pick FROM votes WHERE room_id=? AND date=?"
  )
    .bind(roomId, round.date)
    .all();
  const votesByMember = {};
  const counts = {};
  for (const v of voteRows.results || []) {
    const m = votesByMember[v.member_name] || (votesByMember[v.member_name] = {});
    m[v.stock_code] = v.pick;
    const c = counts[v.stock_code] || (counts[v.stock_code] = { up: 0, down: 0 });
    c[v.pick] += 1;
  }

  const stockState = stocks.map((s) => {
    const c = counts[s.code] || { up: 0, down: 0 };
    const total = c.up + c.down;
    return {
      code: s.code,
      name: s.name,
      counts: c,
      odds: {
        up: c.up > 0 ? Math.round((total / c.up) * 100) / 100 : null,
        down: c.down > 0 ? Math.round((total / c.down) * 100) / 100 : null,
      },
      result: results[s.code] || null,
    };
  });

  // Per-member points for this round only.
  const scoreRows = await env.DB.prepare(
    "SELECT member_name, hits, total, points FROM scores WHERE room_id=? AND date=?"
  )
    .bind(roomId, round.date)
    .all();
  const scoresByMember = {};
  for (const r of scoreRows.results || []) {
    scoresByMember[r.member_name] = {
      hits: r.hits, total: r.total,
      points: Math.round((r.points || 0) * 100) / 100,
    };
  }

  return {
    date: round.date,
    stocks: stockState,
    votes_by_member: votesByMember,
    scores_by_member: scoresByMember,
  };
}

async function getRoomState(env, roomId, token) {
  const room = await env.DB.prepare("SELECT id, name, created_at FROM rooms WHERE id=?")
    .bind(roomId)
    .first();
  if (!room) return json({ error: "room not found" }, 404);

  const memberRows = await env.DB.prepare(
    "SELECT name, token IS NOT NULL AS claimed FROM members WHERE room_id=? ORDER BY name"
  )
    .bind(roomId)
    .all();
  const members = (memberRows.results || []).map((r) => ({
    name: r.name,
    claimed: !!r.claimed,
  }));

  const me = await whoAmI(env, roomId, token);

  // Active round = focus of UI (votable today, or next trading day if past 20:00).
  const date = activeRoundDate();
  await ensureRoundExists(env, date);
  const round = await env.DB.prepare(
    "SELECT date, stocks_json, status, prev_closes_json, results_json FROM rounds WHERE date=?"
  )
    .bind(date)
    .first();

  // Votes for the active round in this room.
  const voteRows = await env.DB.prepare(
    "SELECT member_name, stock_code, pick FROM votes WHERE room_id=? AND date=?"
  )
    .bind(roomId, date)
    .all();
  const votes = voteRows.results || [];

  // Counts per stock.
  const counts = {};
  for (const v of votes) {
    const c = counts[v.stock_code] || (counts[v.stock_code] = { up: 0, down: 0 });
    c[v.pick] += 1;
  }

  // My picks.
  const myPicks = {};
  if (me) {
    for (const v of votes) {
      if (v.member_name === me) myPicks[v.stock_code] = v.pick;
    }
  }

  // Per-stock public detail. Hide individual picks until status >= 'closed'
  // (after lock the field counts already make individual picks deducible
  // for small rooms, but reveal=resolved keeps the suspense for the result).
  const stocks = round ? JSON.parse(round.stocks_json) : GAME_STOCKS;
  const results = round?.results_json ? JSON.parse(round.results_json) : null;
  const prevCloses = round?.prev_closes_json ? JSON.parse(round.prev_closes_json) : null;

  const stockState = stocks.map((s) => {
    const c = counts[s.code] || { up: 0, down: 0 };
    const total = c.up + c.down;
    const odds = {
      up: c.up > 0 ? Math.round((total / c.up) * 100) / 100 : null,
      down: c.down > 0 ? Math.round((total / c.down) * 100) / 100 : null,
    };
    const out = {
      code: s.code,
      name: s.name,
      counts: c,
      odds: round?.status === "open" ? null : odds, // hide odds during voting (changes constantly)
      my_pick: myPicks[s.code] || null,
    };
    if (round?.status === "resolved" && results?.[s.code]) {
      out.result = results[s.code];
    }
    if (prevCloses?.[s.code] != null) out.prev_close = prevCloses[s.code];
    return out;
  });

  // Reveal individual picks only after resolved.
  let votesByMember = null;
  if (round?.status === "resolved") {
    votesByMember = {};
    for (const v of votes) {
      const m = votesByMember[v.member_name] || (votesByMember[v.member_name] = {});
      m[v.stock_code] = v.pick;
    }
  }

  // Weekly leaderboard + hall of fame.
  // Single query over all scores for this room, then group in JS by ISO week.
  const allScores = await env.DB.prepare(
    `SELECT member_name, date, hits, total, points
     FROM scores WHERE room_id=?`
  ).bind(roomId).all();
  const todayKst = nowKstDate();
  const thisWeek = weekKey(todayKst);
  const byWeek = new Map();
  for (const r of allScores.results || []) {
    const wk = weekKey(r.date);
    if (!byWeek.has(wk)) byWeek.set(wk, []);
    byWeek.get(wk).push(r);
  }
  function aggregate(rows, withBest) {
    const m = new Map();
    for (const r of rows) {
      let s = m.get(r.member_name);
      if (!s) {
        s = { hits: 0, total: 0, points: 0, days: 0, best_day: 0 };
        m.set(r.member_name, s);
      }
      s.hits += r.hits || 0;
      s.total += r.total || 0;
      s.points += r.points || 0;
      s.days += 1;
      if (withBest && r.points > s.best_day) s.best_day = r.points;
    }
    return [...m.entries()]
      .map(([name, s]) => ({
        member_name: name,
        hits: s.hits,
        total: s.total,
        points: Math.round(s.points * 100) / 100,
        days: s.days,
        best_day: Math.round(s.best_day * 100) / 100,
      }))
      .sort((a, b) => b.points - a.points || b.hits - a.hits);
  }
  const leaderboardWeek = aggregate(byWeek.get(thisWeek) || [], true);
  const thisWeekBounds = weekBounds(thisWeek);

  // Past weeks (top 3 each) — hall of fame, most recent 12 weeks.
  const pastWeeks = [...byWeek.keys()]
    .filter((w) => w !== thisWeek)
    .sort()
    .reverse()
    .slice(0, 12);
  const weeklyChampions = pastWeeks.map((wk) => {
    const top3 = aggregate(byWeek.get(wk) || [], false).slice(0, 3);
    const bounds = weekBounds(wk);
    return { week: wk, start: bounds.start, end: bounds.end, top3 };
  });

  // Most recent resolved round in this room — show yesterday's result alongside
  // active round so users can see how their previous picks did.
  const recentResolved = await getRecentResolved(env, roomId, date);

  return json({
    room: { id: room.id, name: room.name },
    me,
    members,
    today: {
      date,
      status: round?.status || "open",
      voting_open: round?.status === "open" && isVotingOpenFor(date),
      stocks: stockState,
      votes_by_member: votesByMember,
    },
    recent_resolved: recentResolved,
    this_week: { key: thisWeek, start: thisWeekBounds.start, end: thisWeekBounds.end },
    leaderboard_week: leaderboardWeek,
    weekly_champions: weeklyChampions,
  });
}

async function submitVotes(env, roomId, token, body) {
  const me = await whoAmI(env, roomId, token);
  if (!me) return json({ error: "invalid token" }, 401);

  const date = activeRoundDate();
  if (!isVotingOpenFor(date)) {
    return json({ error: "투표 시간이 아닙니다 (전날 20:00 ~ 당일 09:00 KST)" }, 403);
  }
  await ensureRoundExists(env, date);
  const round = await env.DB.prepare("SELECT status, stocks_json FROM rounds WHERE date=?")
    .bind(date)
    .first();
  if (!round || round.status !== "open") {
    return json({ error: "round not open" }, 403);
  }
  const stocks = JSON.parse(round.stocks_json);
  const validCodes = new Set(stocks.map((s) => s.code));

  const picks = body.picks || {};
  const stmts = [];
  const now = Date.now();
  for (const [code, pick] of Object.entries(picks)) {
    if (!validCodes.has(code)) continue;
    if (pick !== "up" && pick !== "down") continue;
    stmts.push(
      env.DB.prepare(
        `INSERT INTO votes (room_id, date, member_name, stock_code, pick, voted_at)
         VALUES (?, ?, ?, ?, ?, ?)
         ON CONFLICT(room_id, date, member_name, stock_code) DO UPDATE
           SET pick=excluded.pick, voted_at=excluded.voted_at`
      ).bind(roomId, date, me, code, pick, now)
    );
  }
  if (stmts.length === 0) return json({ error: "no valid picks" }, 400);
  await env.DB.batch(stmts);
  return json({ ok: true, count: stmts.length });
}

// ─── OG meta page (server-rendered, redirects to SPA) ──────────────────

const SPA_BASE = "https://yummyummyummy.github.io/k-ant-daily/game.html";
const OG_IMAGE = "https://yummyummyummy.github.io/k-ant-daily/og-image.png";

function escHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

async function renderOgPage(env, roomId) {
  const room = await env.DB.prepare("SELECT id, name FROM rooms WHERE id = ?")
    .bind(roomId).first();
  if (!room) {
    return new Response("room not found", { status: 404, headers: { "Content-Type": "text/plain" } });
  }
  // Current ISO week's leaderboard (resets weekly).
  const thisWeek = weekKey(nowKstDate());
  const wb = weekBounds(thisWeek);
  const lbRows = await env.DB.prepare(
    `SELECT member_name,
            SUM(points) AS points,
            SUM(hits) AS hits,
            SUM(total) AS total
     FROM scores WHERE room_id=? AND date >= ? AND date <= ?
     GROUP BY member_name
     ORDER BY points DESC, hits DESC
     LIMIT 5`
  ).bind(roomId, wb.start, wb.end).all();
  const lb = lbRows.results || [];

  const medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"];
  let desc;
  if (lb.length === 0) {
    desc = `${thisWeek} 이번주 — 아직 점수 없음 (월~금 데일리 결과로 누적)`;
  } else {
    desc = lb.map((r, i) => {
      const pts = (r.points || 0).toFixed(2);
      return `${medals[i]} ${r.member_name} ${pts}점`;
    }).join(" · ");
  }

  const title = `🎲 ${room.name} ${thisWeek} 리더보드 · 국장 예측`;
  const targetUrl = `${SPA_BASE}?room=${encodeURIComponent(roomId)}`;
  const escTitle = escHtml(title);
  const escDesc = escHtml(desc);
  const escTarget = escHtml(targetUrl);
  const escRoomName = escHtml(room.name);

  const html = `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>${escTitle}</title>
<meta name="description" content="${escDesc}">
<meta property="og:type" content="website">
<meta property="og:title" content="${escTitle}">
<meta property="og:description" content="${escDesc}">
<meta property="og:url" content="${escTarget}">
<meta property="og:image" content="${OG_IMAGE}">
<meta property="og:locale" content="ko_KR">
<meta property="og:site_name" content="국장 예측">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="${escTitle}">
<meta name="twitter:description" content="${escDesc}">
<meta name="twitter:image" content="${OG_IMAGE}">
<meta http-equiv="refresh" content="0; url=${escTarget}">
<link rel="canonical" href="${escTarget}">
<style>
  body { background: #0d1117; color: #e6edf3; font-family: -apple-system, sans-serif;
         display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
  .box { text-align: center; }
  a { color: #58a6ff; }
</style>
</head>
<body>
<div class="box">
  <h1>🎲 ${escRoomName} 리더보드</h1>
  <p>${escDesc}</p>
  <p><a href="${escTarget}">방으로 바로 가기 →</a></p>
</div>
<script>location.replace(${JSON.stringify(targetUrl)});</script>
</body>
</html>`;

  return new Response(html, {
    status: 200,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "public, max-age=60",
      ...CORS,
    },
  });
}

// ─── Public router entry ───────────────────────────────────────────────

export async function handleGameRequest(request, env, ctx) {
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: CORS });
  }
  if (!env.DB) {
    return json({ error: "D1 binding 'DB' not configured. Run wrangler d1 create k-ant-game and bind." }, 500);
  }

  const url = new URL(request.url);
  const path = url.pathname;
  const method = request.method;

  let body = {};
  if (method === "POST") {
    try { body = await request.json(); } catch { body = {}; }
  }

  // Routes
  // Admin: re-resolve a specific round (uses NXT + KRX fallback).
  // No auth — confirm token in body protects against accidental hits.
  if (path === "/game/admin/resolve" && method === "POST") {
    if (body.confirm !== "resolve") {
      return json({ error: "missing confirm: 'resolve'" }, 400);
    }
    const date = body.date;
    if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      return json({ error: "invalid date" }, 400);
    }
    await resolveRound(env, date, fetchNxtCloses, { force: true });
    const round = await env.DB.prepare(
      "SELECT date, status, results_json FROM rounds WHERE date = ?"
    ).bind(date).first();
    return json({ ok: true, round });
  }
  // OG meta page — for social link previews. Returns HTML with OG tags
  // populated from current leaderboard + JS redirect to the actual app.
  // Used as the canonical share URL since GitHub Pages can't render dynamic OG.
  const ogMatch = path.match(/^\/game\/og\/([A-Z0-9]+)$/);
  if (ogMatch && method === "GET") {
    return renderOgPage(env, ogMatch[1]);
  }
  if (path === "/game/rooms" && method === "POST") {
    return createRoom(env, body);
  }
  // /game/rooms/:id ...
  const m = path.match(/^\/game\/rooms\/([A-Z0-9]+)(\/.*)?$/);
  if (m) {
    const roomId = m[1];
    const rest = m[2] || "";
    const token = url.searchParams.get("token");
    if (rest === "" && method === "GET") {
      return getRoomState(env, roomId, token);
    }
    if (rest === "/claim" && method === "POST") {
      return claimMember(env, roomId, body);
    }
    if (rest === "/members" && method === "POST") {
      return addMember(env, roomId, body);
    }
    if (rest === "/vote" && method === "POST") {
      return submitVotes(env, roomId, token, body);
    }
  }

  return json({ error: "not found" }, 404);
}

// ─── Cron entry ────────────────────────────────────────────────────────
//
// Single daily cron at 20:10 KST (11:10 UTC). On a trading day:
//   1. Resolve today's round (fetch NXT closes, compute odds payouts, write scores)
//   2. Open next trading day's round (voting opens immediately at this point —
//      lazy creation in getRoomState/submitVotes also handles this if cron skipped)
//
// Voting eligibility is time-based (isVotingOpenFor) rather than status-based,
// so no separate 'lock' cron is needed at 09:00.

export async function handleGameCron(event, env, ctx) {
  if (!env.DB) return;
  const todayKst = nowKstDate();
  if (!isWeekend(todayKst)) {
    await resolveRound(env, todayKst, fetchNxtCloses);
  }
  const next = nextTradingDay(todayKst);
  await ensureRoundExists(env, next);
}
