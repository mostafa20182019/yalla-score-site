# -*- coding: utf-8 -*-
"""The stale-chart guard, and the denominator it is fed.

Run from the site root:  python tests/test_scorers_guard.py

chart_is_current exists because 365scores keeps serving LAST season's top
scorers until the new season produces numbers, and publishing those names is
worse than publishing nothing. It decides by arithmetic: a list that accounts
for more goals than the competition has scored cannot be describing it.

On 2026-09-16 that arithmetic was fed the wrong total. `fixtures.json` carries
scores for only a few rounds of the 365scores leagues, so the Egyptian league
looked like an 11-goal season while it had actually scored 93 — and the top
five, with 13 between them, were rejected as last season's. The visible damage
was an empty scorers table on /scorers/egypt AND in the /matches league stats,
which is an indexed page. An outside HTML audit found the empty page; the
cause was this denominator.

So: unit tests for what the guard must keep rejecting, and a regression test on
the real data for what it must now accept.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import build_site as B
import analysis as AN

fails = []
def ok(n, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + n + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(n)

rows = [{"name": "A", "value": 7, "played": 3}, {"name": "B", "value": 6, "played": 3}]

print("== what the guard must keep rejecting ==")
ok("1 a list accounting for more goals than the season has scored",
   not B.chart_is_current(rows, 10, 5))
ok("2 a player with more appearances than the busiest team has played",
   not B.chart_is_current([{"value": 1, "played": 34}], 100, 6))
ok("3 an empty list is never 'current'", not B.chart_is_current([], 100, 6))

print()
print("== and what it must accept ==")
ok("4 a plausible list inside the season's own totals",
   B.chart_is_current(rows, 93, 5))

print()
print("== the denominator, on this repo's real data ==")
fx = B.load("fixtures.json")
arch = B.load("matches_archive.json")
st = B.load("standings.json")
sc = B.load("scorers.json")
pool = AN.season_matches(fx, arch)
fx_by = {f.get("competition"): f for f in fx if f.get("rounds")}
st_by = {s.get("competition"): s for s in st if s.get("table")}
sc_by = {s.get("competition"): (s.get("scorers") or []) for s in sc if s.get("scorers")}

def fixtures_goals(comp):
    f = fx_by.get(comp) or {}
    n = 0
    for rd in f.get("rounds", []):
        for m in rd.get("matches", []):
            if m.get("status") == "FINISHED" and m.get("home_score") is not None:
                n += m["home_score"] + m["away_score"]
    return n

def pool_goals(comp):
    return sum(int(m["home_score"]) + int(m["away_score"]) for m in pool.get(comp, []))

blocked = []
for comp, srows in sc_by.items():
    tbl = (st_by.get(comp) or {}).get("table") or []
    mx = max((r.get("played") or 0) for r in tbl) if tbl else 0
    if not B.chart_is_current(srows, max(pool_goals(comp), fixtures_goals(comp)), mx):
        blocked.append((comp, sum(B._pval(x) for x in srows), pool_goals(comp)))
ok("5 no league's current top-scorer list is rejected once the pool is the denominator",
   not blocked, blocked)

thin = [(c, fixtures_goals(c), pool_goals(c)) for c in sc_by
        if fixtures_goals(c) < pool_goals(c) / 2]
print(f"  note: {len(thin)} league(s) have a fixtures file too thin to be the denominator"
      + (f" — e.g. {thin[0][0]}: {thin[0][1]} goals in fixtures vs {thin[0][2]} in the season pool"
         if thin else ""))

print()
print("FAILED: " + ", ".join(fails) if fails else "ALL SCORERS-GUARD TESTS PASSED")
sys.exit(1 if fails else 0)
