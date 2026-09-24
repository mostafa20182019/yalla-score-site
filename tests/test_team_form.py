r"""«آخر 5» reconciled with the official table (2026-09-13).

    python tests/test_team_form.py     (from the repo root)
"""
import os, sys
sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8")
import build_site as BS

def m(kick, home, away, hs, aw, status):
    return {"kickoff": kick, "koff_time": "20:00", "home": home, "away": away,
            "home_score": hs, "away_score": aw, "status": status}

fixtures = [{"competition": "Primera Division", "rounds": [
    {"round": 4, "matches": [m("2026-09-06", "Valencia CF", "FC Barcelona", 0, 5, "FINISHED")]},
    {"round": 5, "matches": [m("2026-09-13", "Levante UD", "FC Barcelona", 1, 3, "LIVE"),
                             m("2026-09-13", "Sevilla FC", "Getafe CF", 0, 0, "LIVE")]},
    {"round": 6, "matches": [m("2026-09-16", "FC Barcelona", "Real Racing Club de Santander", None, None, "UPCOMING")]},
]}]

# 1) without a table, a LIVE match is not a result yet (the old behaviour)
f0 = BS.team_form(fixtures)["Primera Division"]
assert f0["FC Barcelona"] == ["W"] and "Sevilla FC" not in f0, f0
print("1 OK: no table -> only FINISHED matches count")

# 2) the table already counts the match (played 2) while the fixture says LIVE -> the live result counts
table = [{"competition": "Primera Division", "table": [
    {"team": "FC Barcelona", "played": 2}, {"team": "Levante UD", "played": 2},
    {"team": "Sevilla FC", "played": 0}, {"team": "Getafe CF", "played": 0}]}]   # the table has NOT counted Sevilla x Getafe yet
f1 = BS.team_form(fixtures, table)["Primera Division"]
assert f1["FC Barcelona"] == ["W", "W"] and f1["Levante UD"] == ["L"], f1
assert "Sevilla FC" not in f1 and "Getafe CF" not in f1, f1                    # table says 1 played & we have 0 finished...
print("2 OK: table ahead of the fixture -> the LIVE result is counted; a genuinely live game is not")

# 3) once the fixture flips to FINISHED nothing is counted twice
fixtures[0]["rounds"][1]["matches"][0]["status"] = "FINISHED"
f2 = BS.team_form(fixtures, table)["Primera Division"]
assert f2["FC Barcelona"] == ["W", "W"], f2
print("3 OK: after the flip the match is counted once")

# 4) form_dots shows the last five, newest last
assert BS.form_dots(["W", "D", "L", "W", "W", "W"]).count("fm-w") == 3 and BS.form_dots([]).startswith("<span")
print("4 OK: dots")

# 5) a TRUNCATED fixtures file (2026-09-13: La Liga arrived as rounds [4, 5] only) - the season pool
#    carries the finished matches, the rounds data only adds the LIVE one, the table reconciles
trunc = [{"competition": "Primera Division", "rounds": [
    {"round": 5, "matches": [m("2026-09-13", "Levante UD", "FC Barcelona", 1, 3, "LIVE")]}]}]
pool = {"Primera Division": [m(f"2026-08-{15 + 3 * i:02d}", "FC Barcelona", f"Club {i}", 2, 1, "FINISHED") for i in range(4)]
        + [m("2026-09-06", "Deportivo Alavés", "Real Betis", 0, 0, "FINISHED")]}
f3 = BS.team_form(trunc, None, pool)["Primera Division"]
assert f3["FC Barcelona"] == ["W"] * 4 and f3["Deportivo Alavés"] == ["D"] and f3["Real Betis"] == ["D"], f3
table2 = [{"competition": "Primera Division", "table": [{"team": "FC Barcelona", "played": 5}, {"team": "Levante UD", "played": 5}]}]
f4 = BS.team_form(trunc, table2, pool)["Primera Division"]
assert f4["FC Barcelona"] == ["W"] * 5 and f4["Levante UD"] == ["L"], f4
print("5 OK: with a truncated fixtures file the pool supplies the season and the table reconciles the live game")

# 6) the fallback Elo reads the same pool; a pool match that the rounds data ALSO lists is not doubled
pool2 = {"Primera Division": pool["Primera Division"] + [m("2026-09-06", "Valencia CF", "FC Barcelona", 0, 5, "FINISHED")]}
e = BS.compute_elo(fixtures, pool2)["Primera Division"]
assert e["FC Barcelona"][1] == 5 and e["Valencia CF"][1] == 1, e
f5 = BS.team_form(fixtures, None, pool2)["Primera Division"]
assert f5["FC Barcelona"] == ["W"] * 5, f5
print("6 OK: fallback Elo and form read the pool; nothing counted twice")
print("ALL TEAM FORM TESTS PASSED")
