# -*- coding: utf-8 -*-
r"""«توقّع وشارك» (2026-11-25): the button beside «صورة» on a league heading.

    python tests/test_pick.py      (from the repo root)

What it guards: which matches the reader may call (never a played, a live or
a postponed one); which round a league's sheet opens on; that a heading gets
the button only on a day with something left to call, and the ROUND only on a
day that belongs to it; and that the script writes no name as HTML and sends
nothing anywhere.
"""
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

from site_lib import pick as P          # noqa: E402

fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


def m(i, h, a, **kw):
    d = {"match_id": i, "home": h, "away": a, "kickoff": "2026-12-01", "koff_time": "20:00", "status": "TIMED"}
    d.update(kw)
    return d


FX = {"rounds": [
    {"round": 5, "matches": [m(1, "أ", "ب", status="FINISHED", home_score=1, away_score=0),
                             m(2, "ج", "د", status="FINISHED", home_score=0, away_score=0)]},
    {"round": 6, "matches": [m(3, "أ", "ج", status="FINISHED", home_score=2, away_score=1),
                             m(4, "ب", "د"), m(5, "هـ", "و"), m(6, "ز", "ح", status="POSTPONED"),
                             m(7, "ط", "ي", status="IN_PLAY")]},
    {"round": 7, "matches": [m(8, "أ", "د"), m(9, "ب", "ج")]},
    {"round": 1, "label": "دور الـ16", "matches": [m(10, "أ", "هـ"), m(11, "ب", "و")]},
]}

ck("1 open = not played, not live, not postponed",
   P.is_open(m(1, "أ", "ب")) and not P.is_open(m(1, "أ", "ب", status="FINISHED", home_score=1))
   and not P.is_open(m(1, "أ", "ب", status="IN_PLAY")) and not P.is_open(m(1, "أ", "ب", status="POSTPONED"))
   and not P.is_open(m(1, "أ", "ب", home_score=0)))
rd = P.pick_round(FX)
ck("2 the nearest numbered round with open matches, and only its open matches",
   rd and rd["r"] == 6 and [x["id"] for x in rd["m"]] == ["4", "5"], str(rd))
ck("3 each match carries what the sheet and the image need", rd and set(rd["m"][0]) == {"id", "h", "a", "hc", "ac", "w"}
   and rd["m"][0]["h"] and "20:00" in rd["m"][0]["w"])
ck("4 a season that is over, a cup stage, one match left: no round",
   P.pick_round({"rounds": FX["rounds"][:1]}) is None and P.pick_round({"rounds": FX["rounds"][3:]}) is None
   and P.pick_round({"rounds": [{"round": 9, "matches": [m(1, "أ", "ب")]}]}) is None and P.pick_round(None) is None)

P._ROUNDS.clear()
P._ROUNDS["L"] = {"slug": "l", "r": 6, "ids": {"4", "5"}, "pairs": {("ب", "د"), ("هـ", "و")}}
ck("5 a day with nothing left to call: no button", P.pick_door("L", [m(3, "أ", "ج", status="FINISHED", home_score=2)]) is None
   and P.pick_door("", [m(4, "ب", "د")]) is None)
ck("6 a day of the round: the round", P.pick_door("L", [m(4, "ب", "د")]) == "l")
ck("7 the same match under another id is still the round's (the two feeds do not always share ids)",
   P.pick_door("L", [m(999, "هـ", "و")]) == "l")
ck("8 a later day of the same league: that day's own rows, never a round the reader is not looking at",
   P.pick_door("L", [m(8, "أ", "د")]) == "")
ck("9 a cup, the national teams: that day's own rows", P.pick_door("CUP", [m(20, "أ", "ب")]) == "")
ck("9b a league whose round has a predictions page sends the button there; any other opens the sheet",
   P.pick_page("L") == "" and P.pick_page("CUP") == ""
   and (P._ROUNDS["L"].update(page=True) or P.pick_page("L")) == "/calc/l.html#r")
P._ROUNDS.clear()

js = io.open("site_src/snippets/shot_js.html", encoding="utf-8").read()
tpl = io.open("site_src/templates/_day.html", encoding="utf-8").read()
css = io.open("site_src/style.css", encoding="utf-8").read()
bs = io.open("build_site.py", encoding="utf-8").read()
ck("10 the button sits after «صورة» on both kinds of heading, only where the day has something to call",
   tpl.count('<button type="button" class="comp-pick"') == 2 and tpl.count('<a class="comp-pick" href="{{ c.pick_href }}"') == 2
   and tpl.count("{% if c.pick %}") == 2
   and tpl.index('class="comp-shot"') < tpl.index('class="comp-pick"'))
ck("11 no script, no canvas: no button", ".comp-pick{display:none}" in css and ".shot-on .comp-pick{display:inline-flex" in css)
ck("12 the buttons are finger-sized and two fit a phone heading",
   "min-height:48px" in css.split(".pick-b{")[1].split("}")[0] and ".comp-h:has(.comp-pick) .comp-shot span{display:none}" in css)
sheet = js.split("«توقّع وشارك»: the sheet")[1].split("/* a chart's button")[0]
ck("13 no name is written as HTML, and the picks leave the browser only inside the image",
   "innerHTML" not in sheet and "insertAdjacentHTML" not in sheet and "sendBeacon" not in js and "XMLHttpRequest" not in js
   and js.count("fetch(") == 1 and "fetch('/pick/'+slug+'.json')" in js)
ck("14 the slug is checked before it is put in a path, and a failed fetch falls back to the day's rows",
   "/^[a-z0-9-]{1,40}$/.test(slug)" in js and "}).catch(day);" in js)
ck("14b a link is left to the browser; the sheet stays open after the image so a pick can be changed",
   "b&&b.tagName!=='A'" in js and "name:'elgoon-picks.png'},shut)" not in js)
ck("15 a row that has started is not offered", "!r.classList.contains('mrow-live')&&!r.classList.contains('mrow-fin')" in js)
ck("16 the rounds are registered before the first page with a day list",
   bs.index("set_pick_rounds(") < bs.index("    home_page(articles, fixtures"))
ck("17 the round files are kept out of the index", "/pick/*\n  X-Robots-Tag: noindex" in
   io.open("root-extras/_headers", encoding="utf-8").read().replace("\r\n", "\n"))

dist = os.path.join(os.getcwd(), "dist")
if os.path.isdir(os.path.join(dist, "pick")):
    import re
    files = sorted(os.listdir(os.path.join(dist, "pick")))
    bad = []
    for f in files:
        d = json.load(io.open(os.path.join(dist, "pick", f), encoding="utf-8"))
        if not (isinstance(d.get("r"), int) and len(d["m"]) >= P.MIN_MATCHES
                and all(x["id"] and x["h"] and x["a"] for x in d["m"])):
            bad.append(f)
    ck(f"18 every built round file ({len(files)}) is valid", not bad, str(bad))
    home = io.open(os.path.join(dist, "index.html"), encoding="utf-8").read()
    slugs = set(re.findall(r'class="comp-pick" data-pick="([a-z0-9-]+)"', home))
    miss = [s for s in slugs if s + ".json" not in files]
    ck(f"19 every round a home-page button names ({len(slugs)}) was written", not miss, str(miss))

print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
