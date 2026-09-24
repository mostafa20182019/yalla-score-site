r"""The club-strength overlay from data/oracle_predictions.json (2026-09-12).

    python tests/test_oracle_strength.py   (from the repo root)
"""
import datetime, json, os, sys, tempfile
sys.path.insert(0, os.getcwd())
import analysis as AN

NOW = datetime.datetime(2026, 9, 12, 12, 0, tzinfo=datetime.timezone.utc)
doc = {"meta": {"generated_at": "2026-09-12T13:30:00+03:00"},
       "strength": {"Egyptian Premier League": [
           {"team": "الزمالك", "elo": 1543.2, "played": 4, "gf": 7, "ga": 1, "att": 1.24, "def": 0.65},
           {"team": "نادٍ غير معروف", "elo": 1500, "played": 0, "gf": 0, "ga": 0}],
                    "Ligue 1": [{"team": "AS Monaco FC", "elo": 1510, "played": 3, "gf": 5, "ga": 2}]},
       "predictions": {}}
fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
json.dump(doc, open(path, "w", encoding="utf-8"), ensure_ascii=False)

# 1) fresh file: strength parsed, typed, keyed by competition then team
preds, st = AN.load_oracle(path, now=NOW)
assert st["status"] == "ok" and preds == {}, st
assert st["strength"]["Egyptian Premier League"]["الزمالك"] == {"elo": 1543.2, "played": 4, "gf": 7, "ga": 1}
print("1 OK: strength parsed from a fresh file")

# 2) overlay: python's row keeps badge/form/pts, gets the four model numbers + src
tstats = {"Egyptian Premier League": {
    "الزمالك": {"team": "الزمالك", "elo": 1539.9, "played": 4, "gf": 6, "ga": 1, "pts": 10,
                "form": ["W", "W", "D", "W"], "badge": "z.png"},
    "الأهلي": {"team": "الأهلي", "elo": 1541.0, "played": 4, "gf": 7, "ga": 3, "pts": 10, "form": [], "badge": None}}}
ap, un = AN.apply_oracle_strength(tstats, st["strength"])
z = tstats["Egyptian Premier League"]["الزمالك"]
assert (ap, un) == (1, 2), (ap, un)          # Zamalek applied; unknown club + whole Ligue 1 unmatched
assert z["elo"] == 1543.2 and z["gf"] == 7 and z["src"] == "oracle"
assert z["pts"] == 10 and z["form"] == ["W", "W", "D", "W"] and z["badge"] == "z.png"
assert "src" not in tstats["Egyptian Premier League"]["الأهلي"]   # untouched
print("2 OK: overlay replaces elo/played/gf/ga only, keeps python's badge/form/points")

# 3) stale file: no strength, nothing applied
doc["meta"]["generated_at"] = "2026-09-10T00:00:00+03:00"
json.dump(doc, open(path, "w", encoding="utf-8"), ensure_ascii=False)
preds, st = AN.load_oracle(path, now=NOW)
assert st["status"] == "stale" and "strength" not in st
assert AN.apply_oracle_strength(tstats, st.get("strength")) == (0, 0)
print("3 OK: a stale file changes nothing")

# 4) a file without the key (last night's shape) is still fine
doc["meta"]["generated_at"] = "2026-09-12T13:30:00+03:00"; del doc["strength"]
json.dump(doc, open(path, "w", encoding="utf-8"), ensure_ascii=False)
preds, st = AN.load_oracle(path, now=NOW)
assert st["status"] == "ok" and st["strength"] == {}
print("4 OK: a file without strength is accepted")
os.remove(path)
print("ALL ORACLE_STRENGTH TESTS PASSED")

# 5) league params (2026-09-13): parsed under the same freshness rule, overlaid on
#    league_params() dicts; an unplayed league keeps None where python keeps None
doc2 = {"meta": {"generated_at": "2026-09-12T13:30:00+03:00"},
        "league": {"Premier League": {"n": 37, "mu_home": 1.4912, "mu_away": 1.2632, "mu": 1.3772,
                                      "home_win": 0.3243, "draw": 0.3784, "gpm": 2.7838},
                   "UEFA Champions League": {"n": 0, "mu_home": 1.5, "mu_away": 1.2, "mu": 1.35,
                                             "home_win": None, "draw": None, "gpm": None}},
        "predictions": {}}
fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
json.dump(doc2, open(path, "w", encoding="utf-8"), ensure_ascii=False)
preds, st = AN.load_oracle(path, now=NOW)
assert st["league"]["Premier League"]["gpm"] == 2.7838 and st["league"]["UEFA Champions League"]["gpm"] is None
lparams = {"Premier League": {"n": 30, "mu_home": 1.56, "mu_away": 1.22, "mu": 1.39, "home_win": 0.4, "draw": 0.3, "gpm": 2.9},
           "Serie A": {"n": 31, "mu_home": 1.4, "mu_away": 1.4, "mu": 1.4, "home_win": 0.35, "draw": 0.18, "gpm": 2.85}}
ap, un = AN.apply_oracle_league(lparams, st["league"])
assert (ap, un) == (1, 1), (ap, un)                         # PL applied; UCL not in python's dict -> unmatched
assert lparams["Premier League"]["n"] == 37 and lparams["Premier League"]["src"] == "oracle"
assert "src" not in lparams["Serie A"]                       # untouched
os.remove(path)
print("5 OK: league params from Oracle overlay league_params(), None stays None")
print("ALL ORACLE_STRENGTH TESTS PASSED (incl. league)")

# 6) the season pool (2026-09-13): Oracle's finished matches join the pool ahead of
#    the feed, de-duplicated by fixture, NOT age-gated; missing file -> []
doc3 = {"meta": {"generated_at": "2026-09-01T00:00:00+03:00"},          # old on purpose
        "season": [{"match_id": "1", "competition": "Saudi Pro League", "kickoff": "2026-08-13", "koff_time": "21:00",
                    "home": "الهلال", "away": "النصر", "home_score": 2, "away_score": 1, "status": "FINISHED"},
                   {"match_id": "2", "competition": "Saudi Pro League", "kickoff": "2026-08-20", "koff_time": "21:00",
                    "home": "الاتحاد", "away": "الهلال", "home_score": 0, "away_score": 3, "status": "FINISHED"}]}
fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
json.dump(doc3, open(path, "w", encoding="utf-8"), ensure_ascii=False)
rows, st3 = AN.load_oracle_season(path)
assert st3["status"] == "ok" and len(rows) == 2 and rows[0]["src"] == "oracle"      # stale meta does not matter
feed = [{"match_id": "2", "competition": "Saudi Pro League", "kickoff": "2026-08-20", "koff_time": "21:00",
         "home": "الاتحاد", "away": "الهلال", "home_score": 0, "away_score": 2, "status": "FINISHED"}]   # feed disagrees
pool = AN.season_matches([], rows + feed)["Saudi Pro League"]
assert len(pool) == 2 and pool[1]["away_score"] == 3 and pool[1]["src"] == "oracle"   # Oracle's row wins, fixture deduped
assert pool[0]["kickoff"] == "2026-08-13"                                             # the opening round is back
assert AN.load_oracle_season(os.path.join(tempfile.gettempdir(), "no-such.json"))[0] == []
os.remove(path)
print("6 OK: Oracle's season joins the pool first, dedup by fixture, not age-gated")
print("ALL ORACLE_STRENGTH TESTS PASSED (incl. league + season)")
