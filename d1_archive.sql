-- The permanent archive (user, 2026-11-03: «عايز الداتا اللى عندى على الموقع
-- زى نتائج المباريات تتحفظ عندى فى الداتا بيز عشان الموسم اللى جاى مثلا لو
-- عايز نتيجة مباراة من الموسم الماضى اعرف اجيبها»).
--
-- Written by archive_db.py from a daily GitHub job (archive-db.yml) and NEVER
-- pruned: every table carries the season, so 2026-2027 stays queryable after
-- 2027-2028 starts. Nothing on the site reads these tables - the build keeps
-- reading the data store - so a quota day here can never take the site down.
-- The older warehouse tables (matches, standings, ... in d1_schema.sql) are
-- frozen since 2026-09-20 and left alone. Every statement is IF NOT EXISTS.

-- one row per finished match - the score as the site showed it
CREATE TABLE IF NOT EXISTS arch_matches (
  match_id     TEXT PRIMARY KEY,
  season       TEXT NOT NULL,          -- «2026-2027» (July to June)
  competition  TEXT NOT NULL,          -- the feed's name («Premier League»)
  comp_label   TEXT,                   -- the site's Arabic label («الدوري الإنجليزي»)
  round        INTEGER,
  stage        TEXT,                   -- a cup's stage («دور الـ 32»)
  kickoff      TEXT,                   -- YYYY-MM-DD, Cairo
  koff_time    TEXT,
  home         TEXT, away TEXT,        -- the feed's names
  home_ar      TEXT, away_ar TEXT,     -- the Arabic names the site shows
  home_score   INTEGER, away_score INTEGER,
  home_badge   TEXT, away_badge TEXT,
  updated_at   TEXT
);
CREATE INDEX IF NOT EXISTS arch_matches_season ON arch_matches (season, competition, kickoff);
CREATE INDEX IF NOT EXISTS arch_matches_home ON arch_matches (home_ar);
CREATE INDEX IF NOT EXISTS arch_matches_away ON arch_matches (away_ar);

-- the scorers, one row per goal, in match order
CREATE TABLE IF NOT EXISTS arch_goals (
  match_id  TEXT NOT NULL,
  seq       INTEGER NOT NULL,
  side      TEXT,                      -- h | a
  player    TEXT,
  minute    TEXT,
  tag       TEXT,                      -- «ركلة جزاء» / «هدف عكسي» / ''
  PRIMARY KEY (match_id, seq)
);
CREATE INDEX IF NOT EXISTS arch_goals_player ON arch_goals (player);

-- lineups (with ratings), cards and substitutions: the match page's detail
-- block as JSON - query it with json_extract / json_each
CREATE TABLE IF NOT EXISTS arch_details (
  match_id      TEXT PRIMARY KEY,
  season        TEXT,
  details_json  TEXT NOT NULL,
  updated_at    TEXT
);

-- the league table as it stood on a day - one snapshot per day per league
CREATE TABLE IF NOT EXISTS arch_standings (
  snap_date    TEXT NOT NULL,
  season       TEXT NOT NULL,
  competition  TEXT NOT NULL,
  pos          INTEGER,
  team         TEXT NOT NULL,
  team_ar      TEXT,
  played INTEGER, won INTEGER, draw INTEGER, lost INTEGER,
  gf INTEGER, ga INTEGER, gd INTEGER, pts INTEGER,
  PRIMARY KEY (snap_date, competition, team)
);
CREATE INDEX IF NOT EXISTS arch_standings_season ON arch_standings (season, competition, snap_date);

-- top scorers / assist makers as they stood on a day
CREATE TABLE IF NOT EXISTS arch_top_players (
  snap_date    TEXT NOT NULL,
  season       TEXT NOT NULL,
  competition  TEXT NOT NULL,
  kind         TEXT NOT NULL,          -- goals | assists
  rank         INTEGER NOT NULL,
  name         TEXT,
  team         TEXT,
  value        INTEGER,
  PRIMARY KEY (snap_date, competition, kind, rank)
);

-- the YouTube highlight each match got (highlights.py)
CREATE TABLE IF NOT EXISTS arch_highlights (
  vid        TEXT PRIMARY KEY,
  match_id   TEXT,
  channel    TEXT,
  title      TEXT,
  published  TEXT,
  kickoff    TEXT
);
CREATE INDEX IF NOT EXISTS arch_highlights_match ON arch_highlights (match_id);
