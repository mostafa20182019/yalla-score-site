# -*- coding: utf-8 -*-
r"""The live table (2026-11-13, user: «خلى ارقام الجدول لحظية كمان»).

    python tests/test_live_table.py     (from the repo root)

While a competition's matches are on, its standings tables are recalculated as
if those matches ended now. The rule that matters most is the one a reader
cannot see: a match is never counted twice. Checked in the browser with a fake
reply (Trabzonspor 2-0 live went top on goal difference; the guard dropped the
match when the official table already counted it; the official table came
back when nothing was live); these checks keep the code saying so.
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

rows = [{"pos": 1, "team": "جلطة سراي", "played": 2, "won": 1, "draw": 1, "lost": 0, "gf": 3, "ga": 1, "gd": 2, "pts": 4}]
games = [{"match_id": 1, "home": "جلطة سراي", "away": "x", "kickoff": "2026-01-01", "home_score": 2, "away_score": 0},
         {"match_id": 2, "home": "y", "away": "جلطة سراي", "kickoff": "2026-01-08", "home_score": 1, "away_score": 1}]
out = T.standings_table("Turkish Super Lig", rows, embedded=True, games=games)
ck("1 each row says how many finished matches our data holds (the double-count guard)",
   'data-pc="2"' in out)
ck("2 without the season's matches the row says nothing (the guard falls back to the last result)",
   "data-pc" not in T.standings_table("Turkish Super Lig", rows, embedded=True))
ck("3 a pre-season table and a last-season table never go live",
   " data-z" in T.standings_table("Turkish Super Lig", rows, embedded=True, zeroed=True)
   and " data-z" in T.standings_table("Turkish Super Lig", rows, embedded=True, past=True)
   and " data-z" not in out)

js = io.open("site_src/snippets/live_table_js.html", encoding="utf-8").read()
ck("4 it runs on the live reply's event, per table with a live id, never a data-z table",
   "document.addEventListener('lv:update',run);" in js and ".ltable[data-cid]" in js
   and "tbl.hasAttribute('data-z')" in js)
ck("5 only matches of the table's own competition, between two of its teams",
   "String(g.c)===String(cid)" in js and "if(!H||!A) return;" in js)
ck("6 a live match counts only while the official «لعب» equals our finished count",
   "if(g.live) return r.pc===null||r.v[0]===r.pc;" in js)
ck("7 a just-ended match counts only while the official table has not counted it",
   "return inPool?r.v[0]<r.pc:r.v[0]===r.pc;" in js)
ck("8 both sides must pass, or the match is left out", ".every(function(r){" in js)
ck("9 points: 3 a win, 1 a draw; played, W/D/L and goals both ways",
   "d[7]+=res===1?3:(res===2?1:0)" in js and "d[4]+=x[1];d[5]+=x[2];d[6]+=x[1]-x[2]" in js)
ck("10 order: points, difference, goals for, then the official order",
   "b.v[7]-a.v[7]||b.v[6]-a.v[6]||b.v[4]-a.v[4]||a.r.pos-b.r.pos" in js)
ck("11 the official table comes back when nothing is live", "if(!used.length){ if(B.sig) restore(tbl,B); return; }" in js
   and "c.innerHTML=r.html[i]" in js)
ck("12 every calculation starts from the official numbers, never from the last live picture",
   "var d=add[r.name], v=r.v.slice();" in js and "if(tbl.__lt) return tbl.__lt;" in js)
ck("13 a changed row drops the match-list buttons (they list the official matches)",
   "if(x.d) r.cells[k+1].textContent=String(x.v[k]);" in js)
ck("14 the table says «مباشر» while it is live", "lt-lvb" in js and ">مباشر<" in js)
sh = io.open("site_lib/shell.py", encoding="utf-8").read()
ck("15 it ships once, in app.js", "(REL_JS, LIVE_JS, SWIPE_JS, TEAM_CARD_JS, LIVE_TABLE_JS)" in sh)
lj = io.open("site_src/snippets/live_js.html", encoding="utf-8").read()
ck("16 LIVE_JS announces every reply", "new CustomEvent('lv:update')" in lj)

print()
if fails:
    print(f"{len(fails)} FAILED: " + "; ".join(fails))
    sys.exit(1)
print("all good")
