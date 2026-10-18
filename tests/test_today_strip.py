r"""«مباريات اليوم» inside every article (2026-10-18).

    python tests/test_today_strip.py   (from the repo root)

The first automatic visitor reading: 1.18 pages per visit. Every article now
carries today's matches under its body - live first, curated clubs next, the
rest by competition order and kick-off, each a link to its match page, rows
in the ticker's live-score contract so LIVE_JS paints them.
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not fails or True:
        pass
    if not cond:
        fails.append(name)


import site_lib.today_strip as TS                       # noqa: E402

T = "2026-10-18"
M = [
    {"match_id": "1", "kickoff": T, "koff_time": "22:00", "status": "UPCOMING", "competition": "Primera Division", "home": "Real Madrid CF", "away": "Sevilla FC"},
    {"match_id": "2", "kickoff": T, "koff_time": "16:00", "status": "LIVE", "competition": "Premier League", "home": "Leeds United FC", "away": "Manchester United FC", "home_score": 0, "away_score": 1},
    {"match_id": "3", "kickoff": T, "koff_time": "13:30", "status": "FINISHED", "competition": "Serie A", "home": "Udinese Calcio", "away": "US Lecce", "home_score": 2, "away_score": 0},
    {"match_id": "4", "kickoff": T, "koff_time": "18:30", "status": "UPCOMING", "competition": "Premier League", "home": "Nottingham Forest FC", "away": "Arsenal FC"},
    {"match_id": "5", "kickoff": "2026-10-19", "koff_time": "20:00", "status": "UPCOMING", "competition": "Premier League", "home": "Liverpool FC", "away": "Villarreal CF"},
    {"match_id": "6", "kickoff": T, "koff_time": "20:00", "status": "POSTPONED", "competition": "Ligue 1", "home": "Lille OSC", "away": "Stade Brestois 29"},
    {"match_id": "7", "kickoff": T, "koff_time": "16:00", "status": "UPCOMING", "competition": "Ligue 1", "home": "Angers SCO", "away": "Olympique de Marseille"},
]
rows = TS.pick_today(M, today=T)
ids = [m["match_id"] for m in rows]
ck("1 only today's matches, postponed left out, tomorrow left out", set(ids) == {"1", "2", "3", "4", "7"}, str(ids))
ck("2 live first", ids[0] == "2")
ck("3 then the curated clubs (Real Madrid, Arsenal) before the others", ids[1:3] == ["1", "4"] or ids[1:3] == ["4", "1"], str(ids))
from site_lib.competitions import COMP_ORDER             # noqa: E402
_o = lambda c: COMP_ORDER.index(c) if c in COMP_ORDER else len(COMP_ORDER)
ck("4 the rest follow COMP_ORDER", (ids.index("3") < ids.index("7")) == (_o("Serie A") <= _o("Ligue 1")), str(ids))
ck("5 the cap holds", len(TS.pick_today(M * 3, today=T, limit=4)) == 4)

html = TS.today_strip(M, today=T)
ck("6 the section links to /matches and names itself", 'href="/matches.html"' in html and "مباريات اليوم" in html)
ck("7 every row links to its match page", html.count('href="/m/') == 5, str(html.count('href="/m/')))
ck("8 rows carry the live-score contract (data-lv + Arabic names + tk-mid)", html.count("data-lv") == 5 and 'data-h="ليدز يونايتد"' in html and html.count('class="tk-mid"') == 5)
ck("9 a live row shows dashes, never a baked score; a finished one its score; an upcoming one its time",
   '<b class="tk-s tk-live"><span>-</span><i>-</i><span>-</span></b>' in html and "<span>2</span><i>-</i><span>0</span>" in html and 'class="tk-t">22:00' in html)
ck("10 nothing today -> no strip at all", TS.today_strip(M, today="2026-10-20") == "")

# wiring
src = io.open("site_pages/articles.py", encoding="utf-8").read()
tpl = io.open("site_src/templates/article.html", encoding="utf-8").read()
css = io.open("site_src/style.css", encoding="utf-8").read()
ck("11 article_pages builds the strip once and hands it to the template",
   "_today_strip = today_strip(matches)" in src and "today_strip=Markup(_today_strip)" in src)
ck("12 the template places it right under the body", 0 < tpl.find('<div class="a-body">{{ body }}</div>') < tpl.find("{{ today_strip }}") < tpl.find("{% if sources %}"))
ck("13 the stylesheet knows the block", ".ts-row{" in css and ".ts .ts-item{" in css)

print()
print("ALL OK" if not fails else f"{len(fails)} FAILED: " + ", ".join(fails))
sys.exit(1 if fails else 0)
