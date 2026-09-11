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

-- Which model produced a frozen prediction: 'python' (analysis.py, the
-- default) or 'oracle' (the PL/SQL model in the side copy, delivered nightly
-- as data/oracle_predictions.json). A side table, not a column: the project
-- rule is no ALTER on a live table. Absent row = python.
CREATE TABLE IF NOT EXISTS prediction_source (
  match_id  TEXT PRIMARY KEY REFERENCES predictions(match_id),
  src       TEXT NOT NULL,                   -- python | oracle
  src_ts    TEXT                             -- the date the source computed it
);

-- Accuracy per model, so the two are never averaged into one number.
DROP VIEW IF EXISTS v_accuracy_by_src;
CREATE VIEW v_accuracy_by_src AS
SELECT COALESCE(s.src, 'python') AS src, COUNT(*) AS n,
       ROUND(AVG(CASE WHEN p.hit = 1 THEN 1.0 ELSE 0.0 END), 4) AS hit_rate,
       ROUND(AVG(p.brier), 4) AS brier,
       SUM(p.score_hit) AS exact_scores
  FROM predictions p
  LEFT JOIN prediction_source s ON s.match_id = p.match_id
 WHERE p.hs IS NOT NULL
 GROUP BY COALESCE(s.src, 'python');

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

-- ===========================================================================
-- Analytics warehouse, phase B: what happened INSIDE a match.
--
-- Phase A stored a match as a result. This stores the match itself: who
-- started, how they were rated, who scored, who was booked, who came on. It is
-- the layer that lets a question like "does an XI's average rating predict the
-- next result better than Elo does?" be asked in SQL instead of guessed.
--
-- The join key is `matches.match_id` (the 365scores game id). The detail
-- records in data/match_details.json now carry it; the ~250 records written
-- before that change are resolved by (name_ar, name_ar, date) instead, which
-- warehouse.py reports on every refresh so a silent drop is impossible.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS players (
  player_id  INTEGER PRIMARY KEY,          -- the 365scores athlete id, stable
  name       TEXT NOT NULL,                -- latest spelling seen
  pos        TEXT,                          -- latest position label (Arabic)
  seen_at    TEXT                           -- date of the latest appearance
);

-- One row per starter per match. Pre-match XIs land here too (rating NULL),
-- which is what makes «من غاب ومن عاد» checkable rather than anecdotal.
CREATE TABLE IF NOT EXISTS match_lineups (
  match_id   TEXT NOT NULL REFERENCES matches(match_id),
  side       TEXT NOT NULL,                 -- 'h' | 'a'
  player_id  INTEGER NOT NULL REFERENCES players(player_id),
  shirt      INTEGER,
  pos        TEXT,
  line       INTEGER,                       -- 1 keeper .. 5 attack
  side_pos   INTEGER,                       -- 0..100 left-to-right on the pitch
  rating     REAL,                          -- NULL when unrated (source sends -1)
  formation  TEXT,                          -- that side's shape, e.g. '4-2-3-1'
  PRIMARY KEY (match_id, side, player_id)
);
CREATE INDEX IF NOT EXISTS lineups_player ON match_lineups (player_id);

-- Events. `seq` is the position in the source's list for that match: the
-- refresh rewrites a match's rows together, so it is stable within a match.
-- player_id is filled in when the name can be matched to that side's XI, and
-- left NULL otherwise (a substitute who scored has no id in the source) -
-- player_name is always there, so nothing is lost either way.
CREATE TABLE IF NOT EXISTS match_goals (
  match_id    TEXT NOT NULL REFERENCES matches(match_id),
  seq         INTEGER NOT NULL,
  side        TEXT,
  minute      TEXT,                          -- '56', '90+1'
  player_name TEXT,
  player_id   INTEGER REFERENCES players(player_id),
  tag         TEXT,                          -- source marker, usually empty
  PRIMARY KEY (match_id, seq)
);

CREATE TABLE IF NOT EXISTS match_cards (
  match_id    TEXT NOT NULL REFERENCES matches(match_id),
  seq         INTEGER NOT NULL,
  side        TEXT,
  minute      TEXT,
  player_name TEXT,
  player_id   INTEGER REFERENCES players(player_id),
  color       TEXT,                          -- 'y' | 'r'
  PRIMARY KEY (match_id, seq)
);

CREATE TABLE IF NOT EXISTS match_subs (
  match_id  TEXT NOT NULL REFERENCES matches(match_id),
  seq       INTEGER NOT NULL,
  side      TEXT,
  minute    TEXT,
  in_name   TEXT,
  out_name  TEXT,
  out_id    INTEGER REFERENCES players(player_id),   -- the starter, so resolvable
  PRIMARY KEY (match_id, seq)
);

-- The published leaderboards (data/scorers.json, data/assists.json). One table
-- with a `kind` discriminator rather than two near-identical ones.
-- player_id is recovered from the athlete photo URL (.../Athletes/87904),
-- which is the same id space as a lineup's `aid` - verified on محمد الشيبي.
-- It is NULL rather than guessed when that URL is missing.
CREATE TABLE IF NOT EXISTS top_players (
  comp_id   TEXT NOT NULL REFERENCES competitions(comp_id),
  kind      TEXT NOT NULL,                   -- 'goals' | 'assists'
  rank      INTEGER NOT NULL,
  name      TEXT,
  team      TEXT,                             -- club name as the source spells it
  player_id INTEGER,                          -- no FK: a leader may never have
                                              -- appeared in a stored lineup
  value     INTEGER,                          -- goals, or assists
  played    INTEGER,                          -- NULL when the source sends 0
  as_of     TEXT,
  PRIMARY KEY (comp_id, kind, rank)
);

-- --------------------------------------------------------------- views

-- Every rated appearance with its club and competition attached: the table
-- you actually want when asking about players.
DROP VIEW IF EXISTS v_player_ratings;
CREATE VIEW v_player_ratings AS
SELECT l.match_id, m.comp_id, c.name_ar AS comp_ar, m.kickoff,
       p.player_id, p.name AS player, l.pos, l.shirt, l.rating, l.formation,
       l.side,
       CASE l.side WHEN 'h' THEN th.name_ar ELSE ta.name_ar END AS club_ar,
       CASE l.side WHEN 'h' THEN ta.name_ar ELSE th.name_ar END AS opponent_ar,
       CASE l.side WHEN 'h' THEN m.home_score ELSE m.away_score END AS gf,
       CASE l.side WHEN 'h' THEN m.away_score ELSE m.home_score END AS ga
  FROM match_lineups l
  JOIN players       p  ON p.player_id = l.player_id
  JOIN matches       m  ON m.match_id  = l.match_id
  JOIN competitions  c  ON c.comp_id   = m.comp_id
  LEFT JOIN teams    th ON th.team_id  = m.home_id
  LEFT JOIN teams    ta ON ta.team_id  = m.away_id;

-- Squad quality as the source rates it, per club: the feature to test against
-- Elo. `matches_rated` matters - an average over two matches is not evidence.
DROP VIEW IF EXISTS v_squad_rating;
CREATE VIEW v_squad_rating AS
SELECT comp_ar, club_ar, COUNT(DISTINCT match_id) AS matches_rated,
       COUNT(*) AS appearances,
       ROUND(AVG(rating), 3) AS avg_xi_rating,
       ROUND(MAX(rating), 2) AS best_rating
  FROM v_player_ratings
 WHERE rating IS NOT NULL
 GROUP BY comp_ar, club_ar;

-- The leaderboards with the competition's Arabic name.
DROP VIEW IF EXISTS v_top_players;
CREATE VIEW v_top_players AS
SELECT c.name_ar AS comp_ar, t.kind, t.rank, t.name, t.team, t.value,
       t.played, t.player_id, t.as_of
  FROM top_players t JOIN competitions c ON c.comp_id = t.comp_id;

-- ===========================================================================
-- The OFFICIAL league table, as published (data/standings.json).
--
-- `team_strength` already holds our own numbers - Elo, attack, defence, all
-- computed from results. This is the other thing: the table the competition
-- itself publishes. Keeping both is the point. Without it there is no way to
-- ask in SQL whether our model's order agrees with reality, which is the
-- first question anyone should ask of a model.
--
-- Note the two sources genuinely differ: the official table counts matches we
-- may not hold, and a pre-season table is published with every stat zeroed.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS standings (
  comp_id  TEXT NOT NULL REFERENCES competitions(comp_id),
  team_id  INTEGER NOT NULL REFERENCES teams(team_id),
  pos      INTEGER,
  played   INTEGER,
  won      INTEGER,
  draw     INTEGER,
  lost     INTEGER,
  gf       INTEGER,
  ga       INTEGER,
  gd       INTEGER,
  pts      INTEGER,
  as_of    TEXT,
  PRIMARY KEY (comp_id, team_id)
);

-- Per-competition state of that snapshot. A separate table rather than
-- columns on `competitions`: this describes the TABLE (which season it is,
-- whether it is a pre-season placeholder with every stat zeroed), not the
-- competition itself. It also means no ALTER on a live table.
CREATE TABLE IF NOT EXISTS standings_meta (
  comp_id      TEXT PRIMARY KEY REFERENCES competitions(comp_id),
  season_label TEXT,
  zeroed       INTEGER,                    -- 1 = new season, not started yet
  rows         INTEGER,
  as_of        TEXT
);

-- The table as a reader sees it.
DROP VIEW IF EXISTS v_standings;
CREATE VIEW v_standings AS
SELECT c.name_ar AS comp_ar, c.slug, s.pos, t.name_ar AS club_ar,
       s.played, s.won, s.draw, s.lost, s.gf, s.ga, s.gd, s.pts,
       m.season_label, m.zeroed, s.as_of
  FROM standings s
  JOIN competitions   c ON c.comp_id = s.comp_id
  JOIN teams          t ON t.team_id = s.team_id
  LEFT JOIN standings_meta m ON m.comp_id = s.comp_id;

-- Our order against the real one. `gap` is positive when the model rates a
-- club higher than the table does - i.e. where it disagrees, and therefore
-- where it is worth looking.
--
-- Two traps, both handled here rather than left for the reader:
--   * a pre-season table (zeroed) has every club level on 0 points, so its
--     "order" is alphabetical and any comparison is noise -> excluded;
--   * the published table SHARES a position between clubs with identical
--     records (Liverpool and Newcastle both 6th, next club 8th). Against a
--     strict RANK() that inflates the gap - badly in a competition where one
--     matchday has been played and 16 clubs share 1st. `tied` says how many
--     clubs share that position, so a fair comparison is `WHERE tied = 1`.
DROP VIEW IF EXISTS v_table_vs_model;
CREATE VIEW v_table_vs_model AS
SELECT c.name_ar AS comp_ar, c.slug, t.name_ar AS club_ar,
       s.pos AS official_pos, s.pts, s.played,
       RANK() OVER (PARTITION BY s.comp_id ORDER BY ts.elo DESC) AS model_pos,
       ROUND(ts.elo, 1) AS elo,
       s.pos - RANK() OVER (PARTITION BY s.comp_id ORDER BY ts.elo DESC) AS gap,
       COUNT(*) OVER (PARTITION BY s.comp_id, s.pos) AS tied
  FROM standings s
  JOIN competitions    c  ON c.comp_id = s.comp_id
  JOIN teams           t  ON t.team_id = s.team_id
  JOIN team_strength   ts ON ts.team_id = s.team_id AND ts.comp_id = s.comp_id
  LEFT JOIN standings_meta m ON m.comp_id = s.comp_id
 WHERE COALESCE(m.zeroed, 0) = 0;

-- ===========================================================================
-- The articles, phase C.
--
-- Read-only mirror, loaded by the hourly refresh. data/articles.json stays the
-- source of truth and the build still reads it - making D1 the writer is the
-- separate step we agreed to take only after a month of measuring the state
-- store. Nothing here can stop an article from publishing.
--
-- What it buys today: the editorial questions become SQL. Which clubs are we
-- under-covering? Which archive pieces are still under the 300-word bar and in
-- what order should they be upgraded? Does every recent article carry sources
-- and an FAQ? How many match pieces never got their report?
-- ===========================================================================

CREATE TABLE IF NOT EXISTS articles (
  article_id   TEXT PRIMARY KEY,
  title        TEXT,
  summary      TEXT,
  author       TEXT,
  kind         TEXT,                      -- 'preview' | 'report' | NULL = news
  match_id     TEXT,                      -- set on match pieces; see v_articles
  pub_date     TEXT,
  pub_ts       TEXT,
  updated_ts   TEXT,
  upgraded_ts  TEXT,
  image_url    TEXT,
  image_credit TEXT,
  words        INTEGER,                   -- body with tags stripped
  thin         INTEGER,                   -- 1 = under ARTICLE_MIN_WORDS (unlisted)
  has_sources  INTEGER,
  has_faq      INTEGER,
  fb_post      TEXT,                      -- the condensed text posted to Facebook
  body         TEXT,                      -- the HTML, so the row is the article
  body_hash    TEXT,                      -- what the refresh diffs on, not the body
  as_of        TEXT
);
CREATE INDEX IF NOT EXISTS articles_pub   ON articles (pub_date);
CREATE INDEX IF NOT EXISTS articles_match ON articles (match_id);

-- The sources block under an article (added 2026-09-06 for the AdSense work).
CREATE TABLE IF NOT EXISTS article_sources (
  article_id TEXT NOT NULL REFERENCES articles(article_id),
  seq        INTEGER NOT NULL,
  name       TEXT,
  url        TEXT,
  note       TEXT,
  PRIMARY KEY (article_id, seq)
);

CREATE TABLE IF NOT EXISTS article_faq (
  article_id TEXT NOT NULL REFERENCES articles(article_id),
  seq        INTEGER NOT NULL,
  q          TEXT,
  a          TEXT,
  PRIMARY KEY (article_id, seq)
);

-- The 11 curated clubs (build_site.TEAM_PAGES). They are site data, not
-- configuration: each one is an indexed /team/<slug> page, and the slug is a
-- published URL that must never change.
CREATE TABLE IF NOT EXISTS clubs (
  slug     TEXT PRIMARY KEY,
  name_ar  TEXT,
  league   TEXT
);

-- Which clubs an article is about, decided by the site's OWN matcher
-- (build_site.article_clubs, exclusions included - "الأهلي السعودي" is not
-- Al Ahly). Re-deriving that here would be a second, divergent answer.
CREATE TABLE IF NOT EXISTS article_clubs (
  article_id TEXT NOT NULL REFERENCES articles(article_id),
  slug       TEXT NOT NULL REFERENCES clubs(slug),
  PRIMARY KEY (article_id, slug)
);
CREATE INDEX IF NOT EXISTS article_clubs_slug ON article_clubs (slug);

-- ---------------------------------------------------------------- views

-- An article with the match it covers, when it covers one. LEFT JOIN on
-- purpose: a match older than the archive window is no longer in `matches`,
-- and the article must not vanish with it.
DROP VIEW IF EXISTS v_articles;
CREATE VIEW v_articles AS
SELECT a.article_id, a.pub_date, a.kind, a.title, a.words, a.thin,
       a.has_sources, a.has_faq,
       c.name_ar AS comp_ar, th.name_ar AS home_ar, ta.name_ar AS away_ar,
       m.kickoff, m.home_score, m.away_score, a.match_id
  FROM articles a
  LEFT JOIN matches      m  ON m.match_id = a.match_id
  LEFT JOIN competitions c  ON c.comp_id  = m.comp_id
  LEFT JOIN teams        th ON th.team_id = m.home_id
  LEFT JOIN teams        ta ON ta.team_id = m.away_id;

-- Are we covering the clubs we promised to cover?
DROP VIEW IF EXISTS v_club_coverage;
CREATE VIEW v_club_coverage AS
SELECT cl.slug, cl.name_ar, cl.league,
       COUNT(ac.article_id)                                   AS articles,
       SUM(CASE WHEN a.thin = 0 THEN 1 ELSE 0 END)            AS full_length,
       MAX(a.pub_date)                                        AS last_article,
       ROUND(AVG(a.words), 0)                                 AS avg_words
  FROM clubs cl
  LEFT JOIN article_clubs ac ON ac.slug = cl.slug
  LEFT JOIN articles      a  ON a.article_id = ac.article_id
 GROUP BY cl.slug;

-- The upgrade queue, in the order upgrade-articles.yml should work through it:
-- thinnest and oldest first, and never one that has already been upgraded.
DROP VIEW IF EXISTS v_thin_articles;
CREATE VIEW v_thin_articles AS
SELECT article_id, pub_date, words, title, upgraded_ts
  FROM articles
 WHERE thin = 1
 ORDER BY words ASC, pub_date ASC;

-- With D1 as the writer (2026-09-10), two duplicate-article races stop being
-- possible by construction rather than by convention:
--
--   * the id: it is allocated inside the INSERT statement itself
--     (SELECT MAX(...)+1), so two runs appending at the same moment cannot
--     both pick 459. The old rule - "new article_id = max(existing) + 1",
--     computed in Python from a file - could and did.
--   * the piece: one preview and one report per match, no more. The prompt
--     already said so; this index means the second attempt fails instead.
CREATE UNIQUE INDEX IF NOT EXISTS articles_match_kind
    ON articles (match_id, kind)
 WHERE match_id IS NOT NULL AND kind IS NOT NULL;
