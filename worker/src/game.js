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

async function resolveRound(env, date, fetchClosesFn) {
  // Compute directions, write results, compute scores.
  // Accept 'open' status too — with the new voting window (yesterday 20:00 ~
  // today 09:00) we no longer have a separate 'closed' transition; voting
  // eligibility is enforced by time. So a round may go open → resolved.
  const round = await env.DB.prepare("SELECT * FROM rounds WHERE date = ?")
    .bind(date)
    .first();
  if (!round || (round.status !== "open" && round.status !== "closed")) return;

  const stocks = JSON.parse(round.stocks_json);
  const codes = stocks.map((s) => s.code);
  const prevCloses = JSON.parse(round.prev_closes_json || "{}");
  const todayCloses = await fetchClosesFn(codes);

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

  // Leaderboard — cumulative.
  const lbRows = await env.DB.prepare(
    `SELECT member_name,
            SUM(hits) AS hits,
            SUM(total) AS total,
            SUM(points) AS points,
            COUNT(*) AS days,
            MAX(points) AS best_day
     FROM scores
     WHERE room_id=?
     GROUP BY member_name
     ORDER BY points DESC, hits DESC`
  )
    .bind(roomId)
    .all();
  const leaderboard = (lbRows.results || []).map((r) => ({
    member_name: r.member_name,
    hits: r.hits || 0,
    total: r.total || 0,
    points: Math.round((r.points || 0) * 100) / 100,
    days: r.days || 0,
    best_day: Math.round((r.best_day || 0) * 100) / 100,
  }));

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
    leaderboard,
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
