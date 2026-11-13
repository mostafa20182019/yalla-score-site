# -*- coding: utf-8 -*-
r"""The standings tables' team card (2026-11-13).

    python tests/test_team_card.py     (from the repo root)

User: «فى جداول الترتيب لما اضغط على نادى او منتخب يجيب بيانات عنه». The team
name in every standings table is a button; the card shows the row's numbers
and the row's data-tc: last result, next match, top scorer, club page - all
from our data, never a guess.
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


import site_lib.tables as T                                  # noqa: E402

COMP = "Turkish Super Lig"
FX = {COMP: {"rounds": [
    {"round": 10, "matches": [
        {"match_id": 1, "home": "ألانيا سبور", "away": "طرابزون سبور", "kickoff": "2026-11-08",
         "status": "FINISHED", "home_score": 0, "away_score": 2},
        {"match_id": 2, "home": "طرابزون سبور", "away": "قاسم باشا", "kickoff": "2026-11-01",
         "status": "FINISHED", "home_score": 1, "away_score": 1}]},
    {"round": 12, "matches": [
        {"match_id": 3, "home": "طرابزون سبور", "away": "أيوب سبور", "kickoff": "2026-11-22",
         "koff_time": "18:00", "status": "UPCOMING"},
        {"match_id": 4, "home": "فنربخشة", "away": "طرابزون سبور", "kickoff": "2026-12-13",
         "status": "UPCOMING"}]}]}}
SC = {COMP: [{"name": "جيفت أوربان", "team": "غوزتبه", "goals": 10},
             {"name": "محمد صلاح", "team": "طرابزون سبور", "goals": 9}]}
T.set_team_info(FX, SC, {COMP: True}, [1, 3])

d = T.team_card_data(COMP, "طرابزون سبور", today="2026-11-13")
ck("1 last result: the newest finished match, the team's own result, its page",
   d.get("ls") == {"h": "ألانيا سبور", "a": "طرابزون سبور", "s": "0 - 2", "r": "w",
                   "d": d["ls"]["d"], "u": "/m/1"} and "8 نوفمبر" in d["ls"]["d"], d.get("ls"))
ck("2 next match: the nearest upcoming one, with its kick-off and page",
   d.get("nx", {}).get("a") == "أيوب سبور" and d["nx"]["t"] == "18:00" and d["nx"]["u"] == "/m/3", d.get("nx"))
ck("3 top scorer: the team's first name on the chart, goals in words",
   d.get("sc") == {"n": "محمد صلاح", "g": "9 أهداف"}, d.get("sc"))
ck("4 a curated club links its club page", d.get("tp") == "/team/trabzonspor")
f = T.team_card_data(COMP, "فنربخشة", today="2026-11-13")
ck("5 a match without a page has no link", f.get("nx", {}).get("u") == "", f.get("nx"))
ck("6 no scorer on the chart = no scorer line; no club page = no link",
   "sc" not in f and "tp" not in f, f)
ck("7 a draw is a draw", T.team_card_data(COMP, "قاسم باشا", today="2026-11-13")["ls"]["r"] == "d")
ck("8 a chart that failed its freshness check gives no scorer",
   (T.set_team_info(FX, SC, {COMP: False}, [1, 3]) or True)
   and "sc" not in T.team_card_data(COMP, "طرابزون سبور", today="2026-11-13"))
T.set_team_info(FX, SC, {COMP: True}, [1, 3])

rows = [{"pos": 2, "team": "طرابزون سبور", "played": 11, "won": 8, "draw": 1, "lost": 2,
         "gf": 26, "ga": 8, "gd": 18, "pts": 25}]
out = T.standings_table(COMP, rows, embedded=True)
ck("9 the team name is a button", '<td class="lt-team"><button type="button" class="lt-tb">' in out)
m = re.search(r'<tr data-tc="([^"]*)"', out)
ck("10 the row carries the card data, escaped JSON", bool(m) and json.loads(html.unescape(m.group(1))).get("tp") == "/team/trabzonspor")
ck("11 the table names its competition for the card", 'data-cl="الدوري التركي"' in out)
zero = T.standings_table(COMP, rows, embedded=True, zeroed=True)
ck("12 a pre-season zeroed table carries no card context", "data-tc" not in zero and "lt-tb" in zero)

js = io.open("site_src/snippets/team_card_js.html", encoding="utf-8").read()
ck("13 the card reads the row's numbers from the END (the form column is optional)",
   "pts:txt(td[n-1])" in js and "p:txt(td[n-8])" in js)
ck("14 every value written into the card is escaped",
   "esc(c.ls.h)" in js and "esc(c.nx.a)" in js and "esc(c.sc.n)" in js and "esc(name)" in js)
ck("15 Escape, × and the backdrop close it; focus goes back to the name",
   "e.key==='Escape'" in js and "if(last) last.focus();" in js)
sh = io.open("site_lib/shell.py", encoding="utf-8").read()
ck("16 the script ships once, in app.js", "(REL_JS, LIVE_JS, SWIPE_JS, TEAM_CARD_JS)" in sh)
bs = io.open("build_site.py", encoding="utf-8").read()
ck("17 build() registers the context before the first table is drawn",
   bs.index("set_team_info(") < bs.index("comp_order = matches_page("))

# the live line (same day, user: «خلى ... البطاقة لحظية كمان»)
from site_lib.competitions import LIVE_COMP_ID                # noqa: E402
ck("18 every table names its competition's id in the live feed",
   'data-cid="78"' in out and LIVE_COMP_ID["Premier League"] == 7 and LIVE_COMP_ID["Egyptian Premier League"] == 552)
lj = io.open("site_src/snippets/live_js.html", encoding="utf-8").read()
ck("19 LIVE_JS shares its reply and announces each one",
   "window.__lvGames=last.gs;" in lj and "new CustomEvent('lv:update')" in lj)
ck("20 the card's live line stays inside the table's own competition (no Saudi «الأهلي» on Al Ahly)",
   "if(String(x.c)!==String(cid)) continue;" in js and "if(!cid) return '';" in js)
ck("21 a match already shown as the last result is not repeated as «انتهت للتو»",
   "c.ls.s===(g.hs+' - '+g.as)" in js)
ck("22 the live line follows the feed while the card is open",
   "document.addEventListener('lv:update',function(){ if(!pop.hidden) paintLive(); });" in js)
ck("23 the card names the teams the way LIVE_JS does", "replace(/[أإآ]/g,'ا').replace(/ة/g,'ه')" in js)

print()
if fails:
    print(f"{len(fails)} FAILED: " + "; ".join(fails))
    sys.exit(1)
print("all good")
