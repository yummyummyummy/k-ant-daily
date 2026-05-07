-- Game schema — friend betting game ("맞춰봐")
--
-- Run once after `wrangler d1 create k-ant-game`:
--   wrangler d1 execute k-ant-game --file=migrations/0001_game_init.sql
--
-- Idempotent (CREATE TABLE IF NOT EXISTS) so re-running is safe.

CREATE TABLE IF NOT EXISTS rooms (
  id         TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS members (
  room_id   TEXT NOT NULL,
  name      TEXT NOT NULL,
  token     TEXT,           -- NULL until claimed; UNIQUE when set
  joined_at INTEGER,
  PRIMARY KEY (room_id, name)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_members_token ON members(token) WHERE token IS NOT NULL;

CREATE TABLE IF NOT EXISTS rounds (
  date              TEXT PRIMARY KEY,         -- YYYY-MM-DD (KST trading day)
  stocks_json       TEXT NOT NULL,            -- JSON [{code, name}, ...]
  status            TEXT NOT NULL DEFAULT 'open',  -- open | closed | resolved | void
  prev_closes_json  TEXT,                     -- captured at lock: {code: prev_close}
  results_json      TEXT,                     -- captured at resolve: {code: {direction, close, change_pct}}
  locked_at         INTEGER,
  resolved_at       INTEGER
);

CREATE TABLE IF NOT EXISTS votes (
  room_id     TEXT NOT NULL,
  date        TEXT NOT NULL,
  member_name TEXT NOT NULL,
  stock_code  TEXT NOT NULL,
  pick        TEXT NOT NULL,                  -- 'up' | 'down'
  voted_at    INTEGER NOT NULL,
  PRIMARY KEY (room_id, date, member_name, stock_code)
);
CREATE INDEX IF NOT EXISTS idx_votes_date_room ON votes(date, room_id);

-- Per-day per-member score row, written at resolve time.
CREATE TABLE IF NOT EXISTS scores (
  room_id     TEXT NOT NULL,
  member_name TEXT NOT NULL,
  date        TEXT NOT NULL,
  hits        INTEGER NOT NULL DEFAULT 0,
  total       INTEGER NOT NULL DEFAULT 0,
  points      REAL NOT NULL DEFAULT 0,
  PRIMARY KEY (room_id, member_name, date)
);
CREATE INDEX IF NOT EXISTS idx_scores_room_member ON scores(room_id, member_name);
