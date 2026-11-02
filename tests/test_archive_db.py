# -*- coding: utf-8 -*-
"""The permanent archive (archive_db.py -> d1_archive.sql), 2026-11-03.

Run from the site root:  python tests/test_archive_db.py

User: «عايز الداتا اللى عندى على الموقع زى نتائج المباريات تتحفظ عندى فى الداتا
بيز عشان الموسم اللى جاى ... اعرف اجيبها». Runs against a throwaway SQLite
file (the same SQL D1 runs), on the data the laptop holds.
"""
import os, sys, tempfile
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
os.environ.pop("CF_API_TOKEN", None)
os.environ["D1_SQLITE"] = os.path.join(tempfile.mkdtemp(), "arch.db")
import store
import archive_db as A
import fetch_data as F
from datetime import date

fails = []
def ok(n, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + n + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(n)


ok("1 a season runs July to June", A.season_of("2026-08-21") == "2026-2027"
   and A.season_of("2027-05-30") == "2026-2027" and A.season_of("2027-07-02") == "2027-2028")
ok("1b and fetch_data's guard starts it on July 1 (365scores filed Nov-2025 Conference games under the current season)",
   F.season_start(date(2026, 11, 3)) == "2026-07-01" and F.season_start(date(2027, 3, 1)) == "2026-07-01"
   and F.season_start(date(2027, 7, 1)) == "2027-07-01")

n1 = A.run(seed=False, today="2026-11-02")   # an EMPTY archive seeds itself
tables = {r["name"] for r in store.sql("SELECT name FROM sqlite_master WHERE type='table'")}
ok("2 every archive table exists", {"arch_matches", "arch_goals", "arch_details", "arch_standings",
                                    "arch_top_players", "arch_highlights"} <= tables, tables)
cnt = lambda t: store.sql(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"]
ok("3 the first (daily) run on an empty archive seeded the whole season, with scorers and details",
   store.sql("SELECT MIN(kickoff) AS k FROM arch_matches")[0]["k"] < "2026-09-01" and cnt("arch_matches") > 500
   and cnt("arch_goals") > 1000 and cnt("arch_details") > 100, (cnt("arch_matches"), cnt("arch_goals")))
ok("4 every match carries its season, its competition's Arabic label and both scores",
   store.sql("SELECT COUNT(*) AS n FROM arch_matches WHERE season = '' OR comp_label IS NULL "
             "OR home_score IS NULL OR away_score IS NULL")[0]["n"] == 0)
ok("5 nothing from before the season (the Conference League leak)",
   store.sql("SELECT COUNT(*) AS n FROM arch_matches WHERE kickoff < '2026-07-01'")[0]["n"] == 0)
ok("6 every goal belongs to an archived match",
   store.sql("SELECT COUNT(*) AS n FROM arch_goals g LEFT JOIN arch_matches m ON m.match_id = g.match_id "
             "WHERE m.match_id IS NULL")[0]["n"] == 0)
ok("7 the day's table snapshot is in, keyed by the day",
   store.sql("SELECT COUNT(DISTINCT snap_date) AS n FROM arch_standings")[0]["n"] == 1 and cnt("arch_standings") > 100)

before = {t: cnt(t) for t in ("arch_matches", "arch_goals", "arch_details", "arch_standings")}
A.run(seed=True, today="2026-11-02")
ok("8 running it again changes nothing (upserts, never duplicates)",
   {t: cnt(t) for t in before} == before, before)
A.run(seed=False, today="2026-11-03")
ok("9 the next day adds a new table snapshot and keeps yesterday's (nothing is pruned)",
   store.sql("SELECT COUNT(DISTINCT snap_date) AS n FROM arch_standings")[0]["n"] == 2
   and cnt("arch_matches") == before["arch_matches"])
q = store.sql("SELECT m.home_ar, m.away_ar FROM arch_matches m WHERE m.season = '2026-2027' "
              "AND (m.home_ar = 'الأهلي' OR m.away_ar = 'الأهلي') LIMIT 1")
ok("10 the question it exists for: a club's results by season, in Arabic", bool(q), q)

wf = open(".github/workflows/archive-db.yml", encoding="utf-8").read()
ok("11 a daily job writes it, with a seed switch, and reads only the data store",
   "schedule:" in wf and "seed" in wf and "python archive_db.py" in wf and "data_store.py pull" in wf)

print("\nALL ARCHIVE-DB TESTS PASSED" if not fails else f"\n{len(fails)} FAILED")
sys.exit(1 if fails else 0)
