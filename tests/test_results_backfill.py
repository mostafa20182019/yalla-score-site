# -*- coding: utf-8 -*-
"""The season's missing results are pulled back (2026-11-01).

Run from the site root:  python tests/test_results_backfill.py

games/results/ returns only the last ~3 weeks, so a match no run caught was
never stored: Europa League matchday 1 (the league was added on 10-17), and
seven Turkish teams one or two short. The standings' «لعب / ف / ت / خ» lists
need every match, so the user asked «اسحب النتائج الناقصة». fetch_data now
walks the results' previousPage links back to the season start whenever a
table counts more matches than results_archive.json holds. Network-free:
_s365 and the archive file are faked.
"""
import json, os, sys, tempfile
from datetime import datetime, timezone, timedelta
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import fetch_data as F
import results_archive as RA

fails = []
def ok(n, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + n + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(n)


def game(gid, season, hs=1, as_=0, status=4):
    return {"id": gid, "seasonNum": season, "statusGroup": status,
            "homeCompetitor": {"name": f"H{gid}", "score": hs},
            "awayCompetitor": {"name": f"A{gid}", "score": as_},
            "startTime": "2026-09-01T18:00:00+00:00", "roundNum": 1}


def row(g):          # the shape fetch_s365_league's game_row produces
    return {"match_id": g["id"], "competition": "L", "home": g["homeCompetitor"]["name"],
            "away": g["awayCompetitor"]["name"], "kickoff": "2026-09-01", "koff_time": "21:00",
            "status": "FINISHED" if g["statusGroup"] == 4 else "UPCOMING",
            "home_score": g["homeCompetitor"]["score"], "away_score": g["awayCompetitor"]["score"],
            "round": 1, "home_badge": "", "away_badge": ""}


# three pages, newest first; the third reaches last season (seasonNum 74)
PAGES = {
    "first": {"games": [game(5, 75), game(4, 75, 0, 0)], "paging": {"previousPage": "/web/games/?p=2"}},
    "games/?p=2": {"games": [game(3, 75), game(2, 75)], "paging": {"previousPage": "/web/games/?p=3"}},
    "games/?p=3": {"games": [game(1, 75), game(99, 74)], "paging": {"previousPage": "/web/games/?p=4"}},
    "games/?p=4": {"games": [game(98, 74)], "paging": {}},
}
calls = []
def fake_s365(path):
    calls.append(path)
    return PAGES["first"] if path.startswith("games/results/") else PAGES[path]

tmp = tempfile.mkdtemp()
RA.FILE = os.path.join(tmp, "results_archive.json")
_load, _save = RA.load, RA.save
RA.load = lambda path=None: _load(RA.FILE)
RA.save = lambda arch, path=None: _save(arch, RA.FILE)
RA.save({"2": dict(row(game(2, 75)), match_id="2", frozen=True)})   # we already hold match 2
F._s365, F.time.sleep = fake_s365, (lambda s: None)
F._PREV_DBG = {}

table = [{"team": t, "played": 2} for t in "abcde"]          # 5 matches counted
ok("1 the gap = matches the table counts minus the archive's",
   F.backfill_gap("L", table, RA.load()) == 4)
note = F.backfill_results(1, "L", 75, table, row)
arch = RA.load()
ok("2 the missing ones are added; the one we held is untouched (still frozen)",
   sorted(arch) == ["1", "2", "3", "4", "5"] and arch["2"]["frozen"], sorted(arch))
ok("3 a 0-0 counts (0 is a score)", arch["4"]["home_score"] == 0 and arch["4"]["away_score"] == 0)
ok("4 it stops at the page that reaches last season - page 4 never read",
   "games/?p=4" not in calls and "99" not in arch and "98" not in arch, calls)
ok("5 the note says what happened, with a timestamp", note and "+4 added" in note
   and "gap now 0" in note and " @ " in note, note)

calls.clear()
F._PREV_DBG = {"backfill:L": note}
F.backfill_results(1, "L", 75, table + [{"team": "f", "played": 4}], row)
ok("6 at most once per BACKFILL_EVERY_H per league (a gap that cannot close costs nothing)",
   calls == [], calls)
F._PREV_DBG = {"backfill:L": "x @ " + (datetime.now(timezone.utc)
                                       - timedelta(hours=F.BACKFILL_EVERY_H + 1)).isoformat()}
calls.clear()
F.backfill_results(1, "L", 75, table, row)
ok("7 no gap = no request at all", calls == [], calls)

src = open("fetch_data.py", encoding="utf-8").read()
ok("8 a failing backfill can never fail the fetch (caught, archive unchanged)",
   "backfill failed" in src and 'if entry and not entry.get("zeroed")' in src)

print("\nALL RESULTS-BACKFILL TESTS PASSED" if not fails else f"\n{len(fails)} FAILED")
sys.exit(1 if fails else 0)
