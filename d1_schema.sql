-- Yalla Score state store (Cloudflare D1 / SQLite dialect).
--
-- Replaces data/fb_posted.json + data/predictions.json as the SOURCE OF TRUTH.
-- Those files keep being written as an export, but only as a git-tracked audit
-- log and backup - nothing reads them once D1 is configured.
--
-- Why this exists: on 2026-09-07 article 422 went out to Facebook TWICE. Two
-- overlapping publish runs had each read the dedup state from their own
-- ~5-minute-old checkout and neither had recorded its post yet. Everything we
-- built to work around that (a serialised workflow, a concurrency queue, a
-- 5-retry git push, reading the file from origin/main first) was an attempt to
-- imitate what one PRIMARY KEY does for free.
--
-- The mechanism: posting is now CLAIM-THEN-POST. A run inserts its claim first;
-- if a concurrent run already holds it the INSERT fails on the primary key and
-- the loser simply does not post. No lock, no queue, no retry loop.

CREATE TABLE IF NOT EXISTS fb_posted (
  kind        TEXT    NOT NULL,            -- 'article' | 'card'
  ref_id      TEXT    NOT NULL,            -- article_id | match_id
  post_id     TEXT,                        -- NULL while the claim is still open
  title       TEXT,                        -- article title, or "home - away"
  score       TEXT,                        -- cards only, e.g. "1-0"
  og_ok       INTEGER NOT NULL DEFAULT 0,  -- 1 once Facebook confirmed the preview
  claimed_at  INTEGER NOT NULL,            -- epoch seconds, written by the claim
  posted_at   INTEGER,                     -- epoch seconds, written after the post
  PRIMARY KEY (kind, ref_id)
);

-- A run that claims and then dies leaves post_id NULL forever, which would
-- silence that article for good. This index makes the "reclaim a stale claim"
-- sweep cheap (see store.CLAIM_TTL_SEC).
CREATE INDEX IF NOT EXISTS fb_posted_open
  ON fb_posted (claimed_at) WHERE post_id IS NULL;

CREATE TABLE IF NOT EXISTS fb_failed (
  kind       TEXT    NOT NULL,
  ref_id     TEXT    NOT NULL,
  attempts   INTEGER NOT NULL DEFAULT 0,   -- fb_cards gives up at MAX_ATTEMPTS
  last_error TEXT,
  last_at    INTEGER,
  PRIMARY KEY (kind, ref_id)
);

-- Score-stability tracking for result cards: a score /live.json cannot confirm
-- must stay unchanged for STABLE_MIN minutes across runs before it is posted.
CREATE TABLE IF NOT EXISTS fb_seen (
  match_id  TEXT PRIMARY KEY,
  score     TEXT    NOT NULL,
  first_at  INTEGER NOT NULL
);

-- The prediction log. Frozen before kick-off, scored after full time.
-- This lands here for the same reason as fb_posted, but the damage was subtler:
-- a lost state write let a match be re-predicted LATER, with newer data, which
-- would silently inflate the published accuracy. The whole point of the
-- accuracy page is that it cannot be gamed - so the freeze has to be atomic.
CREATE TABLE IF NOT EXISTS predictions (
  match_id     TEXT PRIMARY KEY,
  comp         TEXT,
  home         TEXT,
  away         TEXT,
  kickoff      TEXT,
  koff_time    TEXT,
  ph           REAL,
  pd           REAL,
  pa           REAL,
  lh           REAL,
  la           REAL,
  score        TEXT,                       -- most likely scoreline, e.g. "1-0"
  conf         TEXT,                       -- low | mid | high
  predicted_on TEXT,                       -- date the prediction was frozen
  hs           INTEGER,                    -- real home score, NULL until scored
  away_score   INTEGER,                    -- real away score ("as" is reserved)
  outcome      TEXT,                       -- H | D | A
  pick         TEXT,                       -- what the model said
  hit          INTEGER,                    -- 1 when pick == outcome
  brier        REAL,
  score_hit    INTEGER
);

CREATE INDEX IF NOT EXISTS predictions_kickoff ON predictions (kickoff);
CREATE INDEX IF NOT EXISTS predictions_scored  ON predictions (hs);
