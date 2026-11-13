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
ck("5 with no goal list and no events reply nothing is touched",
   "if(!hasG&&!(ev&&(ev.cards.length+ev.subs.length)))return;" in fn)
ck("6 goal rows go only when the reply names the goals; card and change rows only when the events reply is in use",
   "if((isG&&hasG)||(!isG&&ev))tl.removeChild(r);" in fn)
ck("7 newest first, and in one minute the goal, then the card, then the change",
   "all.sort(function(a,b){return b.k-a.k||a.o-b.o||a.i-b.i;});" in fn)
ck("8 a page built before the first event gets the list from the feed",
   # after the stats block when there is one, else under the score row
   "(st0||hero).insertAdjacentHTML('afterend'" in fn and "أحداث المباراة" in fn)
ck("9 every name is escaped", "escH(x.p)" in fn and "escH(x.i)" in fn and "escH(x.o)" in fn)
ck("10 the «every few minutes» note shows only while live AND the events reply is not in use",
   "if(note&&(!g.live||ev))" in fn and "if(g.live&&!ev&&!note)" in fn)
ck("11 the same picture is not repainted every 20 seconds", "tl.getAttribute('data-gs')===sig" in fn)
# cards and substitutions from /live/ev/<gameId>.json (same day, user: «أيوه اعملها»)
ld = js.split("function loadEvents(g){")[1].split("\n  }\n")[0]
ck("11a the events of a match are asked only while it is live, by its feed id, at most every 25 s",
   "if(g.live)loadEvents(g);" in fn and "Date.now()-evAt<25000" in ld
   and "'/live/ev/'+g.id+'.json?b='" in ld)
ck("11b a failed or foreign reply is ignored", "d.ok===false||String(d.id)!==String(g.id)" in ld)
ck("11c live data moves forward only: fewer cards + changes than the page was built with is not painted",
   "(EV.cards.length+EV.subs.length)>=baked" in fn and "data-bk" in fn)
ck("11d a row matched reversed flips the event sides too", "g.sw?(s==='h'?'a':'h'):s" in fn
   and "id:g.id,sw:true" in js)
# stats and the lineup (same day, user: «خلى الاحصائيات والتشكيل يكونوا لحظيين»)
ex = js.split("function paintExtras(e,g){")[1].split("\n  }\n")[0]
ck("13 stats and the pitch are painted only from this match's own events reply",
   "if(!EV||String(EV.id)!==String(g.id))return;" in ex and "paintExtras(e,g);" in js)
ps = js.split("function paintStats(hero,g,ev){")[1].split("\n  }\n")[0]
ck("14 the stats bars follow the page's sides (a row matched reversed swaps them)",
   "var H=g.sw?ev.stats.a:ev.stats.h,A=g.sw?ev.stats.h:ev.stats.a;" in ps)
ck("15 the stats use the finished page's six rows and markup",
   all(k in js for k in ("'xg',2", "'xgot',2", "'shots',0", "'sot',0", "'big',0", "'poss','%'"))
   and 'class="sb-t" aria-hidden="true"' in ps and "mstats" in ps)
pp = js.split("function paintPitch(hero,g,ev,useEv){")[1].split("\n  }\n  function paintExtras")[0]
ck("16 pitch chips are found by name and get the same rating classes as the build",
   ".pitch .pp[data-n]" in pp and "r>=8?'r8':r>=7?'r7':r>=6.5?'r65':'r6'" in js)
ck("17 cards and changes on the pitch only from a reply the timeline would accept",
   "var useEv=(EV.cards.length+EV.subs.length)>=baked;" in ex and "if(useEv){" in pp)
ck("18 goal badges only from a reply that names the goals", "if(hasG){" in pp and "drop('.pp-evs')" in pp)
ck("19 a page without a pitch or a list gets the plain lineup list, page sides",
   "document.querySelector('.pitch,.lu')" in pp and "g.sw?lus.a:lus.h" in pp and 'class="lu-t"' in pp)
ck("20 every name and value written into the page is escaped",
   "escH(p.n)" in pp and "escH(hn)" in ps)
from site_lib.tables import match_details_html as _mdh   # noqa: E402
_xi = [{"name": f"لاعب {i}", "num": i, "ln": 1 + i // 3, "sd": i % 3, "rt": 7} for i in range(11)]
_e = {"lineups": {"h": {"formation": "4-3-3", "xi": _xi}, "a": {"formation": "4-3-3", "xi": _xi}}}
ck("21 every pitch chip carries its player's name for the live repaint",
   _mdh(_e, False, "أ", "ب").count('<div class="pp" data-n="لاعب ') == 22)
ck("12 «45+2» sorts after «45» and before «46»",
   "(parseInt(p[0],10)||0)+(parseInt(p[1],10)||0)/100" in js)

print()
if fails:
    print(f"{len(fails)} FAILED: " + "; ".join(fails))
    sys.exit(1)
print("all good")
