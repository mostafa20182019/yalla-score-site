# -*- coding: utf-8 -*-
r"""The live scorers / assists charts (2026-11-14, user: «خلى الهدافين لحظيين كمان»).

    python tests/test_live_scorers.py     (from the repo root)

The chart is the 365scores list as of the last build; live goals of the
competition are added to players already on it. The rule a reader cannot see:
a goal is never counted twice - only goals scored after the page was built are
added. Checked in the browser with a fake reply: Salah's 69' goal counted
(9 → 10, «+1»), his 20' goal (before the build) and an own goal did not.
"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


import site_lib.tables as T                                  # noqa: E402

sc = [{"name": "محمد صلاح", "team": "طرابزون سبور", "goals": 9}, {"name": "أ\"ب", "team": "x", "goals": 2}]
g = T.scorers_list(sc, "أهداف", "Turkish Super Lig")
ck("1 a goals chart names its live id, its kind and the build moment",
   re.search(r'<div class="sc-list sc-nom" data-cid="78" data-k="g" data-at="\d{13}">', g) is not None, g[:120])
ck("2 an assists chart is kind «a»", 'data-k="a"' in T.scorers_list(sc, "صناعة", "Turkish Super Lig"))
ck("3 each row names its player and club, escaped",
   'data-n="محمد صلاح" data-t="طرابزون سبور"' in g and 'data-n="أ&quot;ب"' in g)
ck("4 without a competition (or one the live feed lacks) the chart stays still",
   "data-cid" not in T.scorers_list(sc) and "data-cid" not in T.scorers_list(sc, "أهداف", "Nowhere League"))

js = io.open("site_src/snippets/live_scorers_js.html", encoding="utf-8").read()
ck("5 only goals scored after the build count (two minutes of margin)", "e.w<at+120000" in js)
ck("6 a goal's time comes from the match minute, a first-half goal seen later crosses the break",
   "(g.hf===2&&mm[0]<=45)?15:0" in js and "var when=now-ago*60000;" in js)
ck("7 only live matches are read; what was counted stays counted for the page's life",
   "if(!g.live||!(g.gt>0)||!g.goals) return;" in js and "var MEM={};" in js)
ck("8 an own goal never counts for the scorer", "x.t!=='عكسية'" in js)
ck("9 assists from the goal's assister", "if(x.a) MEM[" in js)
ck("10 only the chart's own competition, only players already on it, same club",
   "e.cid!==cid||e.k!==k" in js and "x.n===e.n&&(!x.t||!e.t||x.t===e.t)" in js)
ck("11 every recount starts from the built numbers", "v:parseInt(txt(g),10)||0" in js and "x.v+(add[x.i]||0)" in js)
ck("12 order: goals, then the built order; «+N» marks a live addition",
   "b.v-a.v||a.x.i-b.x.i" in js and "sc-lvp" in js)
lj = io.open("site_src/snippets/live_js.html", encoding="utf-8").read()
ck("13 the live script also runs on a page whose only live parts are a table or a chart",
   ".ltable[data-cid],.sc-list[data-cid]" in lj and "window.__lvAt=last.at;" in lj)
sh = io.open("site_lib/shell.py", encoding="utf-8").read()
ck("14 it ships once, in app.js", "LIVE_SCORERS_JS," in sh or "LIVE_SCORERS_JS)" in sh)
lp = io.open("site_pages/leagues.py", encoding="utf-8").read()
mp = io.open("site_pages/matches.py", encoding="utf-8").read()
ck("15 the standings, scorers and match pages pass the competition",
   lp.count('scorers_list(sc, "أهداف", comp)') == 2 and 'scorers_list(sc, "أهداف", comp)' in mp)

print()
if fails:
    print(f"{len(fails)} FAILED: " + "; ".join(fails))
    sys.exit(1)
print("all good")
