# -*- coding: utf-8 -*-
r"""The match page's «أحداث المباراة» follows the live score (2026-11-13).

    python tests/test_live_timeline.py     (from the repo root)

User screenshot, Nigeria 3 - 1 Tanzania at 62': the row at the top (painted
from /live.json every 30 s) named three Nigerian goals, the events list under
it (baked at build time) held two and stopped at 45'. Two sources, two ages,
one page. The goal rows of the list now come from the same reply as the score;
the baked rows carry the hooks LIVE_JS needs to merge them in by minute.
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


from site_lib.tables import match_details_html              # noqa: E402

E = {"goals": [{"side": "h", "player": "الحسن يوسف", "minute": "2"},
               {"side": "a", "player": "ألفونس مسانغا", "minute": "32"},
               {"side": "h", "player": "تولو أروكوداري", "minute": "45+1", "tag": "ركلة جزاء"}],
     "cards": [{"side": "h", "player": "الحسن يوسف", "minute": "12", "color": "y"}],
     "subs": [{"side": "h", "in": "موسيس سيمون", "out": "أديمولا لوكمان", "minute": "45"}]}
html = match_details_html(E, False, "نيجيريا", "تنزانيا")
rows = re.findall(r'<div class="tl-r"([^>]*)>', html)
ck("1 every baked row carries its minute", len(rows) == 5 and all('data-m="' in r for r in rows), rows)
ck("2 only the goal rows are marked as goals", sum("data-g" in r for r in rows) == 3
   and [r for r in rows if "data-g" not in r] == [' data-m="45"', ' data-m="12"'], rows)
ck("3 the list stays newest first", [re.search(r'data-m="([^"]*)"', r).group(1) for r in rows]
   == ["45+1", "45", "32", "12", "2"])

js = io.open("site_src/snippets/live_js.html", encoding="utf-8").read()
fn = js.split("function paintTimeline(e,g){")[1].split("\n  }\n")[0]
ck("4 the timeline is painted from the match page's own row only",
   "e.closest('.mp-hero')" in fn and "paintTimeline(e,g);" in js.split("data-lv-state")[1])
ck("5 a reply without a goal list changes nothing", "if(!g.goals||!g.goals.length)return;" in fn)
ck("6 only goal rows are replaced; cards and substitutions stay",
   "if(r.hasAttribute('data-g'))tl.removeChild(r);" in fn)
ck("7 newest first, and in one minute the goal comes first",
   "all.sort(function(a,b){return b.k-a.k||a.o-b.o||a.i-b.i;});" in fn)
ck("8 a page built before the first event gets the list from the feed",
   "hero.insertAdjacentHTML('afterend'" in fn and "أحداث المباراة" in fn)
ck("9 player names are escaped", "escH(x.p)" in fn)
ck("10 the note about cards and substitutions shows only while the match is live",
   "if(note&&!g.live)" in fn and "if(g.live&&!note)" in fn)
ck("11 the same goal list is not repainted every 20 seconds", "tl.getAttribute('data-gs')===sig" in fn)
ck("12 «45+2» sorts after «45» and before «46»",
   "(parseInt(p[0],10)||0)+(parseInt(p[1],10)||0)/100" in js)

print()
if fails:
    print(f"{len(fails)} FAILED: " + "; ".join(fails))
    sys.exit(1)
print("all good")
