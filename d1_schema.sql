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

-- ===========================================================================
-- ANALYTICS WAREHOUSE (2026-09-09, user's ask: "كل الداتا التى تخص صفحة
-- التحليلات تكون موجودة فى الداتابيز ... عايز اروح على الداتا واعرف اتوقع
-- عن طريق الداتا")
--
-- The point is NOT to store the model's answers - those are in `predictions`
-- already. It is to store the FACTS the model reasons over, linked, so the
-- same question can be asked in SQL and the answer compared.
--
-- TEAM IDENTITY, the one real compromise: a team row is keyed
-- UNIQUE(comp_id, name), so a club that plays two competitions gets two rows
-- (Al Ahly in the Egyptian league and in the CAF Champions League). That is
-- not laziness - the model itself rates a club PER COMPETITION, because an Elo
-- built from mixed opposition means nothing. Group on `name_ar` to see a club
-- across competitions. It also sidesteps the «الأهلي» Egypt / Saudi collision
-- that has bitten this project twice.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS competitions (
  comp_id     TEXT PRIMARY KEY,            -- 'Egyptian Premier League' (the key used in code)
  slug        TEXT,                        -- 'egypt' - the URL segment
  name_ar     TEXT,
  sort_order  INTEGER
);

CREATE TABLE IF NOT EXISTS teams (
  team_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  comp_id     TEXT NOT NULL REFERENCES competitions(comp_id),
  name        TEXT NOT NULL,               -- source name, may be Latin
  name_ar     TEXT,                        -- what the site shows
  crest       TEXT,
  UNIQUE (comp_id, name)
);

CREATE TABLE IF NOT EXISTS matches (
  match_id    TEXT PRIMARY KEY,
  comp_id     TEXT REFERENCES competitions(comp_id),
  home_id     INTEGER REFERENCES teams(team_id),
  away_id     INTEGER REFERENCES teams(team_id),
  kickoff     TEXT,                        -- 'YYYY-MM-DD'
  koff_time   TEXT,                        -- 'HH:MM' Cairo
  status      TEXT,                        -- UPCOMING | LIVE | FINISHED | POSTPONED
  home_score  INTEGER,
  away_score  INTEGER,
  round       INTEGER
);
CREATE INDEX IF NOT EXISTS matches_comp_date ON matches (comp_id, kickoff);
CREATE INDEX IF NOT EXISTS matches_home ON matches (home_id);
CREATE INDEX IF NOT EXISTS matches_away ON matches (away_id);

-- Derived snapshot, fully rewritten by the warehouse refresh. Kept because
-- recomputing Elo in SQL is not reasonable - but every INPUT to it is in
-- `matches`, so the numbers can be checked rather than trusted.
CREATE TABLE IF NOT EXISTS team_strength (
  comp_id     TEXT NOT NULL REFERENCES competitions(comp_id),
  team_id     INTEGER NOT NULL REFERENCES teams(team_id),
  as_of       TEXT NOT NULL,
  elo         REAL,
  played      INTEGER, won INTEGER, draw INTEGER, lost INTEGER,
  gf          INTEGER, ga INTEGER, pts INTEGER, cs INTEGER,
  h_played    INTEGER, h_gf INTEGER, h_ga INTEGER, h_pts INTEGER,
  a_played    INTEGER, a_gf INTEGER, a_ga INTEGER, a_pts INTEGER,
  form        TEXT,                        -- 'WWDLW', oldest first
  attack      REAL,                        -- 1.00 = league average
  defence     REAL,                        -- lower is better
  PRIMARY KEY (comp_id, team_id)
);

CREATE TABLE IF NOT EXISTS league_params (
  comp_id     TEXT PRIMARY KEY REFERENCES competitions(comp_id),
  as_of       TEXT NOT NULL,
  n           INTEGER,                     -- finished matches behind these numbers
  mu_home     REAL, mu_away REAL, mu REAL, -- shrunk goal means
  home_win    REAL, draw REAL, gpm REAL    -- observed rates
);

-- --------------------------------------------------------------- views
-- These exist so the answer to "can I predict from the data?" is yes, in one
-- SELECT, without re-deriving the joins every time.

DROP VIEW IF EXISTS v_predictions;
CREATE VIEW v_predictions AS
SELECT p.*, th.team_id AS home_id, ta.team_id AS away_id,
       th.name_ar AS home_ar, ta.name_ar AS away_ar
  FROM predictions p
  LEFT JOIN teams th ON th.comp_id = p.comp AND th.name = p.home
  LEFT JOIN teams ta ON ta.comp_id = p.comp AND ta.name = p.away;

-- Everything the model looks at for one upcoming match, side by side: both
-- clubs' strength and the league's goal means. Write your own formula against
-- this and compare it with `predictions` for the same match_id.
DROP VIEW IF EXISTS v_upcoming;
CREATE VIEW v_upcoming AS
SELECT m.match_id, m.comp_id, c.name_ar AS comp_ar, m.kickoff, m.koff_time,
       th.name_ar AS home_ar, ta.name_ar AS away_ar,
       sh.elo AS home_elo, sa.elo AS away_elo,
       sh.attack AS home_attack, sh.defence AS home_defence,
       sa.attack AS away_attack, sa.defence AS away_defence,
       sh.played AS home_played, sa.played AS away_played,
       sh.form AS home_form, sa.form AS away_form,
       lp.mu_home, lp.mu_away, lp.mu,
       p.ph, p.pd, p.pa, p.score AS model_score, p.conf
  FROM matches m
  JOIN competitions  c  ON c.comp_id = m.comp_id
  LEFT JOIN teams    th ON th.team_id = m.home_id
  LEFT JOIN teams    ta ON ta.team_id = m.away_id
  LEFT JOIN team_strength sh ON sh.comp_id = m.comp_id AND sh.team_id = m.home_id
  LEFT JOIN team_strength sa ON sa.comp_id = m.comp_id AND sa.team_id = m.away_id
  LEFT JOIN league_params lp ON lp.comp_id = m.comp_id
  LEFT JOIN predictions   p  ON p.match_id = m.match_id
 WHERE m.status = 'UPCOMING';

-- The model's published track record, joined to the clubs.
DROP VIEW IF EXISTS v_accuracy;
CREATE VIEW v_accuracy AS
SELECT p.comp, c.name_ar AS comp_ar, COUNT(*) AS n,
       ROUND(AVG(CASE WHEN p.hit = 1 THEN 1.0 ELSE 0.0 END), 4) AS hit_rate,
       ROUND(AVG(p.brier), 4) AS brier,
       SUM(CASE WHEN p.outcome = 'H' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS home_rate
  FROM predictions p
  LEFT JOIN competitions c ON c.comp_id = p.comp
 WHERE p.hs IS NOT NULL
 GROUP BY p.comp;
