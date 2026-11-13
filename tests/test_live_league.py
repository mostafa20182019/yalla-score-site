# -*- coding: utf-8 -*-
r"""The league view's «الأرقام» tab follows live matches (2026-11-14,
user: «خلى الاحصائيات فى صفحة الدورى لحظية»).

    python tests/test_live_league.py     (from the repo root)

Checked in the browser with a fake reply on the Turkish view (18 matches, 63
goals, biggest 7 goals): a live 3-3 and a live 5-3 made it 20 / 77 / 3.85,
the four percentages recounted (70% / 15% / 45% / 50%) and the 5-3 the
biggest result, «مباشر الآن», with both crests.
"""
import html
import io
import json
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


pr = io.open("site_pages/prep.py", encoding="utf-8").read()
ck("1 the numbers tab carries its live id and the counts its tiles are made of",
   '<div class="lg-num"{_live_attr}>' in pr and '"over":' in pr.replace(" ", "") or '"over": sum(' in pr)
ck("2 the base counts come from FINISHED matches only (a live match is never in them twice)",
   '"n": played, "g": goals' in pr and 'for _, m in fin if' in pr)
ck("3 each tile and percentage names what it is", all(f'data-s="{k}"' in pr for k in ("n", "g", "avg", "big")))
st = io.open("site_lib/stats.py", encoding="utf-8").read()
ck("4 the four percentages are tagged", 'data-s="{key}"' in st and '("over", "draws", "homes", "clean")' in st)
ck("5 the view's scorers and assists tabs pass their competition (they follow live goals too)",
   'scorers_list(sc, "أهداف", comp)' in pr and 'scorers_list(asst, "صناعة", comp)' in pr)

js = io.open("site_src/snippets/live_league_js.html", encoding="utf-8").read()
ck("6 only the tab's own competition", "g.c===cid" in js)
ck("7 every recount starts from the built counts", "var n=B.n,g=B.g,over=B.over" in js)
ck("8 the rules of the build: 3+ goals, a draw, a home win, a clean sheet",
   "if(h+a>=3) over++; if(h===a) draws++; if(h>a) homes++; if(Math.min(h,a)===0) clean++;" in js)
ck("9 the biggest result changes only when a live score beats it (goals, then the bigger side)",
   "key[0]>B.big[0]||(key[0]===B.big[0]&&key[1]>B.big[1])" in js)
ck("10 a match seen live keeps its last score after the whistle (the page is older than the whistle)",
   "else if(SEEN[g.id]){" in js)
ck("11 the tab says «مباشر» while anything is added; the built numbers otherwise",
   "lg-lvb" in js and "t.innerHTML=el.__html[s]" in js)
ck("12 names and scores written into the tile are escaped", "esc(big.x.h)" in js and "esc(big.x.hs)" in js)
sh = io.open("site_lib/shell.py", encoding="utf-8").read()
ck("13 it ships once, in app.js", "LIVE_LEAGUE_JS)" in sh)
lj = io.open("site_src/snippets/live_js.html", encoding="utf-8").read()
ck("14 the live script starts on a page whose only live part is this tab", ".lg-num[data-cid]" in lj)

# the built fragment, when there is one
f = "dist/matches/l/turkey.html"
if os.path.exists(f):
    t = io.open(f, encoding="utf-8").read()
    m = re.search(r'<div class="lg-num" data-cid="78" data-b="([^"]*)">', t)
    b = json.loads(html.unescape(m.group(1))) if m else {}
    ck("15 the Turkish view's numbers carry consistent counts",
       b and b["n"] >= b["over"] and b["n"] >= b["draws"] + b["homes"] and len(b["big"]) == 2, b)

print()
if fails:
    print(f"{len(fails)} FAILED: " + "; ".join(fails))
    sys.exit(1)
print("all good")
