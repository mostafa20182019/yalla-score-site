r"""The site looks and opens like FotMob, phones and desktop (2026-10-26).

    python tests/test_phone_home.py   (from the repo root)

The user asked for FotMob's mobile site (slim top bar, tabs at the bottom,
one card per league with one-line rows, the site OPENING ON THE MATCHES),
then for FotMob's desktop site (one header row, the same rows, the home page
= leagues | today's matches | news - home.match_centre). The phone bottom bar
puts المباريات first and lights it on «/»; its «أخبار» tab is /news.
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
import re as _re
days = _re.findall(r'<section class="hd-day" data-day="([^"]+)"[^>]*?( hidden)?>', h)
ck("1 FotMob's day card: yesterday, today, tomorrow built in, only today shown without JS",
   [d for d, _ in days] == ["2026-10-25", T, "2026-10-27"] and [bool(x) for _, x in days] == [True, False, True], str(days))
today_sec = h[h.find(f'data-day="{T}"'):h.find('data-day="2026-10-27"')]
ck("2 today: one card per league, one row per match", today_sec.count('<div class="comp">') == 2 and today_sec.count('class="mrow ') == 3)
ck("2b tomorrow's match sits in tomorrow's section", h[h.find('data-day="2026-10-27"'):].count('class="mrow ') == 1)
ck("3 rows open the match page (stretch link) and carry the LIVE_JS hooks",
   h.count('class="mstretch"') == 4 and h.count("data-lv") == 4)
ck("4 inside a league, kick-off order (the 19:00 result before the 21:30 kick-off)", 0 <= today_sec.find("2 - 1") < today_sec.find("21:30"))
ck("5 the arrows step between the days and past either end open /matches",
   'class="dn-arrow hd-prev"' in h and 'class="dn-arrow hd-next"' in h and "location.href='/matches.html'" in h
   and 'href="/matches.html"' in h and "اليوم · " in h)
ck("6 a day with no match says so instead of an empty block", "لا توجد مباريات في هذا اليوم" in today_list([], today=T))

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
glob, block = css[:m], css[m:]
ck("11 everywhere: no crowd photo, no ticker; one-line rows without the «بطاقة المباراة» pill",
   ".head-crowd,.site-head .ticker{display:none!important}" in glob and ".mlist>.mrow .mgo-row{display:none}" in glob)
ck("12 the phone «أخبار» tab is hidden on desktop, the desktop one on phones",
   ".nt-ph{display:none}" in glob and ".nt-desk{display:none}" in block)
ck("13 phones: the bottom bar, and the home is the matches only (no columns, no blocks below)",
   "position:fixed" in block and ".home-mc .mp-leagues,.home-mc .mp-extra,.ph-today>.sec-h,.home-rest{display:none}" in block)

# ---- the desktop home (2026-10-26, «زى fotmob على الكمبيوتر»)
from site_lib.today_strip import match_centre         # noqa: E402
arts = [{"article_id": i, "title": f"خبر {i}", "slug": f"s{i}", "image_url": "/media/x.jpg" if i == 2 else None}
        for i in range(1, 9)]
st = [{"competition": "Primera Division", "table": [{"team": "x"}]},
      {"competition": "Turkish Super Lig", "table": [{"team": "y"}]},
      {"competition": "Some Cup", "table": [{"team": "z"}]}]
mc = match_centre(st, ms, arts)
ck("15 three columns: leagues | today's matches | news",
   0 <= mc.find("mp-leagues") < mc.find("ph-today") < mc.find("mp-extra"))
ck("16 the leagues column = the nine-league list with a table, each to its standings page",
   mc.count('class="lg-item"') == 2 and "/standings/" in mc and "Some Cup" not in mc, str(mc.count('class="lg-item"')))
ck("17 the news column: one featured story with a picture + the rest as rows, and /news",
   mc.count('class="mp-feat"') == 1 and mc.count('class="mn-item"') == 5 and 'href="/news.html"' in mc,
   f'{mc.count(chr(34) + "mp-feat" + chr(34))} {mc.count("mn-item")}')
ck("18 the day list is inside it (today + tomorrow's match here)", mc.count('class="mrow ') == 4)
home_src = open("site_src/templates/home.html", encoding="utf-8").read()
ck("19 the home template renders the match centre and no longer the day cards or the chips row",
   "{{ match_centre }}" in home_src and "{{ today_cards }}" not in home_src and "{{ league_bar }}" not in home_src)
ck("20 every block after the match centre is inside .home-rest (phones hide it)",
   home_src.find("{{ match_centre }}") < home_src.find('<div class="home-rest">') < home_src.find("{{ news_filter }}")
   < home_src.find("{{ clubs_strip }}") < home_src.find("</div>", home_src.find("{{ clubs_strip }}")) < home_src.find("{{ fav_script }}"))

print("\nALL PHONE HOME TESTS PASSED" if not fails else f"\n{len(fails)} FAILED")
sys.exit(1 if fails else 0)
