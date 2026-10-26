r"""Phones look and open like FotMob (2026-10-26).

    python tests/test_phone_home.py   (from the repo root)

The user asked for FotMob's mobile site: slim top bar, tabs at the bottom,
one card per league with one-line rows, and the site OPENING ON THE MATCHES.
The home page carries today's matches (today_strip.today_list) for phones
only; the bottom bar puts المباريات first and lights it on «/», and the phone
«أخبار» tab is /news. Desktop keeps its own tabs and the «أهم مباريات اليوم»
cards.
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


from site_lib.today_strip import today_list   # noqa: E402
from site_lib import shell                    # noqa: E402

T = "2026-10-26"
ms = [
    {"match_id": 1, "kickoff": T, "koff_time": "21:30", "status": "UPCOMING", "home": "Galatasaray", "away": "Fenerbahce",
     "competition": "Turkish Super Lig"},
    {"match_id": 2, "kickoff": T, "koff_time": "19:00", "status": "FINISHED", "home": "Besiktas", "away": "Basaksehir",
     "competition": "Turkish Super Lig", "home_score": 2, "away_score": 1},
    {"match_id": 3, "kickoff": T, "koff_time": "23:00", "status": "UPCOMING", "home": "Sevilla", "away": "Osasuna",
     "competition": "Primera Division"},
    {"match_id": 4, "kickoff": "2026-10-27", "koff_time": "20:00", "status": "UPCOMING", "home": "A", "away": "B",
     "competition": "Primera Division"},
]
h = today_list(ms, today=T)
ck("1 only today's matches, one row each", h.count('class="mrow ') == 3, str(h.count('class="mrow ')))
ck("2 one card per league", h.count('<div class="comp">') == 2)
ck("3 rows open the match page (stretch link) and carry the LIVE_JS hooks",
   h.count('class="mstretch"') == 3 and h.count("data-lv") == 3)
ck("4 inside a league, kick-off order (the 19:00 result before the 21:30 kick-off)", 0 <= h.find("2 - 1") < h.find("21:30"))
ck("5 the section links to the full /matches", 'href="/matches.html"' in h)
ck("6 a day with no match says so instead of an empty block", "لا توجد مباريات اليوم" in today_list([], today=T))

def nav(active):
    page = shell.head("t", "d", "https://x/", active=active)
    return page[page.find('<nav class="site-nav"'):page.find("</nav>")]

n = nav("home")
ck("7 the phone news tab is /news, the desktop one stays «/»",
   'href="/news.html" class="navtab nt-ph' in n and 'href="/" class="navtab nt-desk is-active' in n)
ck("8 on «/» the phone bar lights المباريات", re.search(r'href="/matches.html" class="navtab nt-match[^"]*ph-on', n) is not None)
ck("9 /news lights the phone «أخبار» tab, not المباريات",
   re.search(r'href="/news.html" class="navtab nt-ph[^"]*ph-on', nav("news")) is not None
   and "ph-on" not in re.search(r'href="/matches.html" class="([^"]*)"', nav("news")).group(1))
ck("10 matches_js still finds exactly one /matches tab", n.count('href="/matches.html"') == 1)

css = open("site_src/style.css", encoding="utf-8").read()
m = css.find("@media(max-width:760px){\n  body{padding-bottom")
block = css[m:]
ck("11 phone-only pieces are hidden on desktop", ".nt-ph,.ph-today{display:none}" in css[:m])
ck("12 on phones the list shows and the day cards hide",
   ".ph-today{display:block}" in block and ".tc{display:none}" in block and ".nt-desk{display:none}" in block)

print("\nALL PHONE HOME TESTS PASSED" if not fails else f"\n{len(fails)} FAILED")
sys.exit(1 if fails else 0)
