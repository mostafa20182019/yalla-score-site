# -*- coding: utf-8 -*-
"""End-to-end proof of the analytics warehouse on the sqlite backend.

Same SQL dialect as D1, so a green run here means the statements, the FKs, the
views and the incremental diff all work before a single D1 write is spent.
"""
import os, sys, tempfile

sys.stdout.reconfigure(encoding="utf-8")
SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SITE)
DB = os.path.join(tempfile.mkdtemp(), "wh.db")
os.environ["D1_SQLITE"] = DB
for k in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_D1_ID"):
    os.environ.pop(k, None)

import store        # noqa: E402
import warehouse    # noqa: E402

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

print(f"backend: {store.backend()}  db: {DB}")
ck("1 backend is sqlite", store.backend() == "sqlite")

n = store.init_schema()
ck("2 schema applies", n >= 54, f"{n} statements")

# --- first refresh: everything is new -------------------------------------
c1 = warehouse.refresh(verbose=False)
ck("3 competitions loaded", c1["competitions"] > 0, str(c1["competitions"]))
ck("4 teams loaded", c1["teams_written"] > 50, str(c1["teams_written"]))
ck("5 matches loaded", c1["matches_written"] > 500, str(c1["matches_written"]))
ck("6 strength loaded", c1["strength_written"] > 50, str(c1["strength_written"]))

# --- second refresh: the diff must make it nearly free --------------------
c2 = warehouse.refresh(verbose=False)
moved = c2["teams_written"] + c2["matches_written"] + c2["strength_written"]
ck("7 second refresh writes ~nothing", moved == 0, f"{moved} rows")
ck("8 and it saw the same rows", c2["matches_same"] == c1["matches_written"],
   f"{c2['matches_same']} vs {c1['matches_written']}")

# --- D1's bind-parameter ceiling ------------------------------------------
# D1 allows 100 bound parameters per statement, far below SQLite's 999. A fixed
# chunk size passed here and then failed on the real D1 with "too many SQL
# variables", so the batch width is now derived - guard that.
_sent = []
_orig_sql = store.sql
store.sql = lambda st, params=None: (_sent.append(len(params or [])), _orig_sql(st, params))[1]
try:
    store.upsert_many("teams", ["comp_id", "name", "name_ar", "crest"],
                      [{"comp_id": "X", "name": f"t{i}", "name_ar": "س", "crest": None}
                       for i in range(80)], ["comp_id", "name"])
    wide = ["comp_id", "team_id"] + [c for c in
            ("elo", "played", "won", "draw", "lost", "gf", "ga", "pts", "cs",
             "h_played", "h_gf", "h_ga", "h_pts", "a_played", "a_gf", "a_ga",
             "a_pts", "form", "attack", "defence", "as_of")]
    store.upsert_many("team_strength", wide,
                      [dict.fromkeys(wide, 0) | {"comp_id": "X", "team_id": -i}
                       for i in range(1, 30)], ["comp_id", "team_id"])
finally:
    store.sql = _orig_sql
ck("15 no statement exceeds D1's 100 bound variables", max(_sent) <= 100, f"max {max(_sent)}")
store.sql("DELETE FROM team_strength WHERE comp_id = 'X'")
store.sql("DELETE FROM teams WHERE comp_id = 'X'")

# --- the links the user asked for ----------------------------------------
orphan = store.sql("SELECT COUNT(*) n FROM matches m "
                   "LEFT JOIN teams t ON t.team_id = m.home_id "
                   "WHERE m.home_id IS NOT NULL AND t.team_id IS NULL")[0]["n"]
ck("9 no orphan home_id", orphan == 0, str(orphan))
both = store.sql("SELECT COUNT(*) n FROM matches WHERE home_id IS NOT NULL "
                 "AND away_id IS NOT NULL")[0]["n"]
ck("10 most matches resolve both sides", both > 500, str(both))
dup = store.sql("SELECT COUNT(*) n FROM (SELECT comp_id, name FROM teams "
                "GROUP BY comp_id, name HAVING COUNT(*) > 1)")[0]["n"]
ck("11 one team row per (comp, name)", dup == 0, str(dup))

# --- the views ------------------------------------------------------------
for v in ("v_predictions", "v_upcoming", "v_accuracy"):
    try:
        store.sql(f"SELECT * FROM {v} LIMIT 3")
        ck(f"12 view {v} runs", True)
    except Exception as e:                                  # noqa: BLE001
        ck(f"12 view {v} runs", False, str(e)[:80])

# v_upcoming is the whole point: every input the model sees, side by side
rows = store.sql("SELECT * FROM v_upcoming LIMIT 1")
if rows:
    cols = set(rows[0])
    need = {"home_elo", "away_elo", "home_attack", "away_defence", "mu_home", "mu_away"}
    ck("13 v_upcoming carries the model inputs", need <= cols, str(sorted(need - cols)))
else:
    print("  note  v_upcoming empty (no scheduled matches in the data right now)")

# a hand-written prediction in SQL, which is exactly what the user wants to do
q = store.sql("""SELECT t.name_ar, s.elo, s.attack, s.defence,
                        ROUND(s.attack * p.mu_home, 2) AS exp_goals_home
                   FROM team_strength s
                   JOIN teams          t ON t.team_id = s.team_id AND t.comp_id = s.comp_id
                   JOIN competitions   c ON c.comp_id = s.comp_id
                   JOIN league_params  p ON p.comp_id = s.comp_id
                  WHERE c.slug = 'egypt' ORDER BY s.elo DESC LIMIT 5""")
ck("14 a hand-written SQL prediction works", len(q) > 0, f"{len(q)} rows")
for r in q:
    print(f"        {r['name_ar']:<22} elo={r['elo']:<8} att={r['attack']:<7} "
          f"def={r['defence']:<7} xG(home)={r['exp_goals_home']}")


# ================================================= the official league table
# measured against the FILE, not against a snapshot count: football-data's
# 10-req/min limit means a refresh can legitimately come back with 7 of the 9
# competitions (it did, on 2026-09-10 06:23), and a test that hard-codes 188
# would then fail for a reason that is not a bug
import build_site as _BS                                       # noqa: E402
_file_rows = sum(len(x.get("table") or []) for x in _BS.load("standings.json"))
st = store.sql("SELECT COUNT(*) n FROM standings")[0]["n"]
ck("34 every published table row in the file is loaded", st == _file_rows,
   f"{st} of {_file_rows}")
ck("35 every table row resolves to a club",
   c1.get("standings_unresolved", 0) == 0,
   str(c1.get("standings_unresolved")))
orph = store.sql("SELECT COUNT(*) n FROM standings s "
                 "LEFT JOIN teams t ON t.team_id = s.team_id "
                 "WHERE t.team_id IS NULL")[0]["n"]
ck("36 no table row hangs off an unknown club", orph == 0, str(orph))

again = warehouse.refresh(verbose=False)
ck("37 a second pass rewrites no table rows",
   again["standings_written"] == 0, str(again["standings_written"]))

# the source's own arithmetic - if this ever breaks, the feed changed
for label, q in (
        ("pts = 3*won + draw", "SELECT COUNT(*) n FROM standings WHERE pts <> won*3 + draw"),
        ("gd = gf - ga", "SELECT COUNT(*) n FROM standings WHERE gd <> gf - ga"),
        ("played = won+draw+lost",
         "SELECT COUNT(*) n FROM standings WHERE played <> won+draw+lost")):
    bad = store.sql(q)[0]["n"]
    ck(f"38 the table is internally consistent ({label})", bad == 0, f"{bad} bad rows")

# a published table SHARES a position between identical records (Liverpool and
# Newcastle both 6th, next club 8th). That is not corruption, and comparing it
# against a strict RANK() without saying so overstates the gap - so the view
# has to report it.
shared = store.sql("SELECT COUNT(*) n FROM v_table_vs_model WHERE tied > 1")[0]["n"]
ck("39 shared positions are flagged, not hidden", shared > 0, f"{shared} tied rows")

zc = store.sql("SELECT COUNT(*) n FROM standings_meta")[0]["n"]
ck("40 a snapshot row exists per competition in the file",
   zc == len(_BS.load("standings.json")), f"{zc} rows")
zeroed = store.sql("""SELECT COUNT(*) n FROM v_table_vs_model v
                        JOIN competitions c ON c.name_ar = v.comp_ar
                        JOIN standings_meta m ON m.comp_id = c.comp_id
                       WHERE m.zeroed = 1""")[0]["n"]
ck("41 a pre-season table is excluded from the comparison", zeroed == 0, str(zeroed))

for v in ("v_standings", "v_table_vs_model"):
    try:
        store.sql(f"SELECT * FROM {v} LIMIT 3")
        ck(f"42 view {v} runs", True)
    except Exception as e:                                  # noqa: BLE001
        ck(f"42 view {v} runs", False, str(e)[:80])

agree = store.sql("""SELECT comp_ar, COUNT(*) clubs, ROUND(AVG(ABS(gap)), 2) off
                       FROM v_table_vs_model WHERE tied = 1
                      GROUP BY comp_ar ORDER BY off LIMIT 3""")
ck("43 the model tracks a settled table within a place or two",
   agree and agree[0]["off"] <= 1.5, str([(r["comp_ar"], r["off"]) for r in agree]))
for r in agree:
    print(f"        {r['comp_ar']:<22} {r['clubs']} clubs, off by {r['off']} places")


# ==================================================== phase B: the in-match layer
d1 = warehouse.refresh_details(verbose=False)
ck("16 detail records resolved to fixtures", d1["by_name"] + d1["by_id"] > 200,
   f"{d1['by_name'] + d1['by_id']} of {d1['details_seen']}")
ck("17 every detail record is accounted for",
   d1["by_id"] + d1["by_name"] + d1["by_name_offset"] + d1["ambiguous"]
   + d1["unmatched"] == d1["details_seen"])
ck("18 lineups loaded", d1["lineups_written"] > 4000, str(d1["lineups_written"]))
ck("19 players loaded", d1["players_written"] > 1500, str(d1["players_written"]))
ck("20 goals loaded", d1["goals_written"] > 500, str(d1["goals_written"]))

d2 = warehouse.refresh_details(verbose=False)
moved = sum(v for k, v in d2.items() if k.endswith("_written"))
ck("21 second detail pass writes nothing", moved == 0, f"{moved} rows")

orph = store.sql("SELECT COUNT(*) n FROM match_lineups l "
                 "LEFT JOIN matches m ON m.match_id = l.match_id "
                 "WHERE m.match_id IS NULL")[0]["n"]
ck("22 no lineup hangs off an unknown match", orph == 0, str(orph))
orph = store.sql("SELECT COUNT(*) n FROM match_lineups l "
                 "LEFT JOIN players p ON p.player_id = l.player_id "
                 "WHERE p.player_id IS NULL")[0]["n"]
ck("23 no lineup hangs off an unknown player", orph == 0, str(orph))

# the source sends -1 for "unrated"; storing that would poison every AVG
bad = store.sql("SELECT COUNT(*) n FROM match_lineups WHERE rating <= 0")[0]["n"]
ck("24 an unrated appearance is NULL, never -1", bad == 0, str(bad))
rated = store.sql("SELECT COUNT(*) n FROM match_lineups WHERE rating IS NOT NULL")[0]["n"]
ck("25 most appearances carry a rating", rated > 4000, str(rated))

# a goal by a starter should be attributed; a goal by a substitute cannot be
att = store.sql("SELECT COUNT(*) n, SUM(CASE WHEN player_id IS NOT NULL THEN 1 ELSE 0 END) "
                "AS named FROM match_goals")[0]
ck("26 most goals are attributed to a player row", att["named"] > att["n"] * 0.6,
   f"{att['named']}/{att['n']}")
noname = store.sql("SELECT COUNT(*) n FROM match_goals WHERE player_name IS NULL")[0]["n"]
ck("27 every goal keeps the scorer's name either way", noname == 0, str(noname))

# _trim: a shrinking event list must not leave a phantom row behind
mid = store.sql("SELECT match_id FROM match_goals GROUP BY match_id "
                "HAVING COUNT(*) >= 2 LIMIT 1")[0]["match_id"]
before = store.sql("SELECT COUNT(*) n FROM match_goals WHERE match_id = ?", [mid])[0]["n"]
gone = warehouse._trim("match_goals", {mid: before - 1})
after = store.sql("SELECT COUNT(*) n FROM match_goals WHERE match_id = ?", [mid])[0]["n"]
ck("28 _trim drops rows a shrunken list left behind",
   gone == 1 and after == before - 1, f"{before} -> {after}")

ck("29 an athlete id is recovered from a photo url",
   warehouse._athlete_id(
       "https://imagecache.365scores.com/image/upload/f_png/v21/Athletes/87904") == 87904
   and warehouse._athlete_id("https://x/none.png") is None)

for v in ("v_player_ratings", "v_squad_rating", "v_top_players"):
    try:
        store.sql(f"SELECT * FROM {v} LIMIT 3")
        ck(f"30 view {v} runs", True)
    except Exception as e:                                  # noqa: BLE001
        ck(f"30 view {v} runs", False, str(e)[:80])

top = store.sql("SELECT kind, COUNT(*) n, SUM(CASE WHEN player_id IS NOT NULL "
                "THEN 1 ELSE 0 END) AS linked FROM top_players GROUP BY kind")
ck("31 both leaderboards loaded and linked to players",
   len(top) == 2 and all(r["linked"] == r["n"] for r in top),
   str([(r["kind"], r["linked"], r["n"]) for r in top]))

# regression: a semicolon inside a SQL comment used to split a statement in
# half, and the leftover prose was then executed as SQL
st = store._statements("-- carries it; the rest of the sentence\n"
                       "CREATE TABLE IF NOT EXISTS zz_probe (a INTEGER);")
ck("32 a semicolon inside a comment does not split a statement",
   len(st) == 1 and st[0].startswith("CREATE TABLE"), str(st))

# and the whole point of phase B: a player-level question, in SQL
q = store.sql("""SELECT player, club_ar, COUNT(*) apps, ROUND(AVG(rating), 2) avg_rt
                   FROM v_player_ratings
                  WHERE comp_ar = 'الدوري المصري' AND rating IS NOT NULL
                  GROUP BY player_id HAVING apps >= 3
                  ORDER BY avg_rt DESC LIMIT 5""")
ck("33 a player-level question answers in SQL", len(q) == 5, f"{len(q)} rows")
for r in q:
    print(f"        {r['player']:<22} {r['club_ar']:<16} apps={r['apps']}  avg={r['avg_rt']}")


# ======================================================== phase C: the articles
# source="json" is the BACKFILL path: json -> D1. The hourly refresh runs the
# other way round (D1 is the writer since 2026-09-10 and only the derived
# counters are recomputed) - test_article_write.py covers that direction.
ca = warehouse.refresh_articles(verbose=False, source="json")
ck("44 articles loaded", ca["articles_written"] > 350, str(ca["articles_written"]))
ck("45 the curated clubs are a table", ca["clubs"] == 11, str(ca["clubs"]))
ck("46 sources and FAQ rows loaded",
   ca["sources_written"] > 100 and ca["faq_written"] > 100,
   f"{ca['sources_written']} sources, {ca['faq_written']} faq")
ck("47 club links loaded", ca["club_links_written"] > 300, str(ca["club_links_written"]))

ca2 = warehouse.refresh_articles(verbose=False, source="json")
moved = sum(v for k, v in ca2.items() if k.endswith("_written"))
ck("48 a second article pass writes nothing", moved == 0, f"{moved} rows")

orph = store.sql("SELECT COUNT(*) n FROM article_clubs ac "
                 "LEFT JOIN articles a ON a.article_id = ac.article_id "
                 "WHERE a.article_id IS NULL")[0]["n"]
ck("49 no club link hangs off an unknown article", orph == 0, str(orph))
orph = store.sql("SELECT COUNT(*) n FROM article_clubs ac "
                 "LEFT JOIN clubs c ON c.slug = ac.slug WHERE c.slug IS NULL")[0]["n"]
ck("50 no club link points at an unknown club", orph == 0, str(orph))
orph = store.sql("SELECT COUNT(*) n FROM article_sources s "
                 "LEFT JOIN articles a ON a.article_id = s.article_id "
                 "WHERE a.article_id IS NULL")[0]["n"]
ck("51 no source row hangs off an unknown article", orph == 0, str(orph))

# the word count and the thin flag must agree with the site's own rule, or the
# unlisting on the site and the upgrade queue here would disagree
import build_site as BS                                       # noqa: E402
mism = 0
for a in BS.load("articles.json")[:60]:
    row = store.sql("SELECT words, thin FROM articles WHERE article_id = ?",
                    [str(a.get("article_id"))])
    if not row:
        mism += 1
        continue
    if row[0]["words"] != BS.article_words(a) or bool(row[0]["thin"]) != BS.is_thin(a):
        mism += 1
ck("52 words and the thin flag match build_site's own rule", mism == 0, f"{mism} off")

# the body is stored, and the diff runs on its hash rather than on 800KB of html
b0 = store.sql("SELECT body, body_hash FROM articles WHERE body <> '' LIMIT 1")[0]
import hashlib                                                # noqa: E402
ck("53 the body is stored and its hash matches",
   b0["body_hash"] == hashlib.sha1(b0["body"].encode("utf-8")).hexdigest()[:16])

# a rewritten article must be re-stored even though every other column is equal
aid = store.sql("SELECT article_id FROM articles LIMIT 1")[0]["article_id"]
store.sql("UPDATE articles SET body_hash = 'stale', body = 'x' WHERE article_id = ?", [aid])
# An edit made BEHIND the warehouse's back is exactly what the signature
# (2026-09-20) cannot see - by design, and documented in _changed_only: the
# candidate rows did not change, so the table is not read back. This test
# predates the signature; it now asks the documented escape, WAREHOUSE_FULL=1,
# and separately proves the signature DOES skip without it (54a).
ca_sig = warehouse.refresh_articles(verbose=False, source="json")
ck("54a without WAREHOUSE_FULL an unchanged source is not re-read (the signature)",
   ca_sig["articles_written"] == 0, f"{ca_sig['articles_written']} rewritten")
os.environ["WAREHOUSE_FULL"] = "1"
ca3 = warehouse.refresh_articles(verbose=False, source="json")
os.environ.pop("WAREHOUSE_FULL")
ck("54 an edited body is detected through the hash",
   ca3["articles_written"] == 1, f"{ca3['articles_written']} rewritten")

# a shrinking sources list must not leave phantom rows
src = store.sql("SELECT article_id, COUNT(*) n FROM article_sources "
                "GROUP BY article_id HAVING n >= 2 LIMIT 1")
if src:
    a_id, n_before = src[0]["article_id"], src[0]["n"]
    # a partial map must touch ONLY the article it names
    gone = warehouse._trim_by("article_sources", "article_id", {a_id: n_before - 1})
    others = store.sql("SELECT COUNT(*) n FROM article_sources WHERE article_id <> ?",
                       [a_id])[0]["n"]
    n_after = store.sql("SELECT COUNT(*) n FROM article_sources WHERE article_id = ?",
                        [a_id])[0]["n"]
    ck("55 _trim_by drops rows a shrunken source list left behind",
       gone == 1 and n_after == n_before - 1, f"{n_before} -> {n_after}, gone={gone}")
    ck("55b _trim_by leaves every article it was not asked about alone",
       others > 100, f"{others} rows elsewhere")

for v in ("v_articles", "v_club_coverage", "v_thin_articles"):
    try:
        store.sql(f"SELECT * FROM {v} LIMIT 3")
        ck(f"56 view {v} runs", True)
    except Exception as e:                                    # noqa: BLE001
        ck(f"56 view {v} runs", False, str(e)[:80])

cov = store.sql("SELECT name_ar, articles, avg_words FROM v_club_coverage "
                "ORDER BY articles DESC LIMIT 3")
ck("57 club coverage answers in SQL", len(cov) == 3 and cov[0]["articles"] > 50,
   str([(r["name_ar"], r["articles"]) for r in cov]))
for r in cov:
    print(f"        {r['name_ar']:<18} {r['articles']} articles, avg {r['avg_words']} words")

print("\n" + ("ALL GREEN" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
