# -*- coding: utf-8 -*-
r"""The rounds list shows a live match as live (user 2026-11-15: «فيه مباريات
فى الجولات بتكون مباشر بس مبتظهرش انها مباشر») and /fixtures pages open on
the groups, then the rounds - no «المباريات القادمة» block on top (same day:
«عايز لما ادخل على البطولات ميجبليش مباريات الجولة القادمة»).

    python tests/test_live_fx.py     (from the repo root)
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


from site_lib.config import REF_TODAY
from site_lib.tables import fixture_mini

live = fixture_mini({"status": "LIVE", "home": "Cyprus", "away": "Montenegro", "home_score": 0,
                     "away_score": 1, "kickoff": REF_TODAY}, link="/m/1")
ck("1 a LIVE row says «مباشر» when built", 'class="fx fx-live"' in live and "fx-lv" in live)
ck("2 a row around today carries its names and day for the live script",
   f'data-fd="{REF_TODAY}"' in live and "data-fh=" in live and "data-fa=" in live)
fin = fixture_mini({"status": "FINISHED", "home": "A", "away": "B", "home_score": 1, "away_score": 0,
                    "kickoff": REF_TODAY})
ck("3 a finished row is left alone", "data-fh" not in fin and "fx-live" not in fin)
far = fixture_mini({"status": "UPCOMING", "home": "A", "away": "B", "kickoff": "2099-01-01"})
ck("4 a far-off fixture carries nothing (the season's rows stay light)", "data-fh" not in far)

js = io.open("site_src/snippets/live_fx_js.html", encoding="utf-8").read()
ck("5 painted from every live reply", "addEventListener('lv:update',paint)" in js)
ck("6 either name order, same day only", "sw:true" in js and "g.d!==d" in js)
ck("7 written values are escaped", "esc(hs)" in js and "esc(g.min)" in js)
ck("8 an ended match drops the badge", "classList.toggle('fx-live',!!g.live)" in js)
sh = io.open("site_lib/shell.py", encoding="utf-8").read()
ck("9 it ships in app.js", "LIVE_FX_JS)) +" in sh)
lj = io.open("site_src/snippets/live_js.html", encoding="utf-8").read()
ck("10 the live script starts on a page whose only live part is the rounds list", ".fx[data-fh]" in lj)

tpl = io.open("site_src/templates/fixtures.html", encoding="utf-8").read()
ck("11 no «المباريات القادمة» block in the fixtures template", "next_rows" not in tpl)
f = "dist/fixtures/nations-league.html"
if os.path.exists(f):
    t = io.open(f, encoding="utf-8").read()
    ck("12 Nations League: the groups come before the rounds",
       0 < t.find("groups-panel") < t.find("fx-all-h"))

print()
if fails:
    print(f"{len(fails)} FAILED: " + "; ".join(fails))
    sys.exit(1)
print("all good")
