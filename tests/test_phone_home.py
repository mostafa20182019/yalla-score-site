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


from site_lib.daylist import day_sections     # noqa: E402
from site_lib.render import Markup, render     # noqa: E402
from site_lib.snippets import FILTERS_HTML, MATCHES_JS   # noqa: E402
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
# 2026-10-26 (third ask): the home's list IS the /matches day list - one
# builder (daylist.day_sections), one partial (_days.html), one script
days, rows = day_sections(ms, {})
ck("1 one section per day in the feed, in date order", [d["day"] for d in days] == [T, "2026-10-27"])
ck("2 today: one card per league in the sidebar order, one row per match",
   [c["comp"] for c in days[0]["comps"]] == ["Primera Division", "Turkish Super Lig"]
   and sum(len(c["rows"]) for c in days[0]["comps"]) == 3)
ck("3 rows open the match page and carry the LIVE_JS + filter hooks",
   all('class="mstretch"' in r and "data-lv" in r and "data-ko=" in r for r in rows) and len(rows) == 4)
h = render("_days.html", filters=Markup(FILTERS_HTML), today=T, days=days)
ck("4 the partial: day arrows, the filters, the days", all(x in h for x in ('id="daynav"', 'id="prevDay"', 'id="mfilters"', 'id="mfQ"', f'data-today="{T}"', 'class="day"')))
mt = open("site_src/templates/matches.html", encoding="utf-8").read()
ck("5 /matches renders the same partial", '{% include "_days.html" %}' in mt and 'id="daynav"' not in mt)
ck("6 the script leaves the home page's league LINKS and «المباريات» tab alone",
   "querySelectorAll('button.lg-item')" in MATCHES_JS and "!wrap.closest('.home-mc')" in MATCHES_JS)

def nav(active):
    page = shell.head("t", "d", "https://x/", active=active)
    return page[page.find('<nav class="site-nav"'):page.find("</nav>")]

n = nav("home")
# ONE tab set for phones and desktop (2026-10-26, «دى هتكون الرئيسية ...
# والاخبار ... تظهر فى تاب اسمها اخبار»)
tabs = re.findall(r'<a href="([^"]+)" class="navtab[^"]*"><span class="ico">[^<]*</span> ([^<]+)', n)
ck("7 the tabs, in order: المباريات (the home) · البطولات · أخبار (/news) · التحليلات",
   [(h, t.strip()) for h, t in tabs] == [("/", "المباريات"), ("/leagues.html", "البطولات"),
                                        ("/news.html", "أخبار"), ("/insights.html", "التحليلات")], str(tabs))
ck("8 «/» and /matches light المباريات", all(re.search(r'href="/" class="navtab nt-match is-active"', nav(a)) for a in ("home", "matches")))
ck("9 the news lists light أخبار, not المباريات",
   'href="/news.html" class="navtab nt-news is-active"' in nav("news") and 'nt-match is-active' not in nav("news"))
ck("10 no tab to /matches any more (MATCHES_JS then never hijacks one)", 'href="/matches.html"' not in n)

# «البطولات» tab (user, 2026-10-26: «عايز يكون فيه تاب اسمها البطولات»)
ck("10b the «البطولات» tab is on every page, to /leagues, lit on the league pages",
   'href="/leagues.html" class="navtab nt-leagues"' in n
   and 'href="/leagues.html" class="navtab nt-leagues is-active"' in nav("leagues"))
lg_py = open("site_pages/leagues.py", encoding="utf-8").read()
ck("10c /standings, /scorers and /fixtures light it; build() writes /leagues",
   lg_py.count('active="leagues"') == 4 and "leagues_page(_comps_with_table, fx_by_comp, urls)"
   in open("build_site.py", encoding="utf-8").read())

css = open("site_src/style.css", encoding="utf-8").read()
m = css.find("@media(max-width:760px){\n  body{padding-bottom")
glob, block = css[:m], css[m:]
ck("11 everywhere: no crowd photo, no ticker; one-line rows without the «بطاقة المباراة» pill",
   ".head-crowd,.site-head .ticker{display:none!important}" in glob and ".mlist>.mrow .mgo-row{display:none}" in glob)
ck("12 no phone/desktop tab split left in the stylesheet", "nt-ph" not in css and "nt-desk" not in css and "ph-on" not in css)
ck("12b «البطولات» is a phone tab: hidden on desktop, shown in the bottom bar (user 2026-10-26)",
   ".navtab.nt-leagues{display:none}" in glob and ".navtab.nt-leagues{display:inline-flex}" in block)
ck("13 phones: the bottom bar, and the home is the matches column only",
   "position:fixed" in block and ".home-mc .mp-leagues,.home-mc .mp-extra,.ph-today>.sec-h{display:none}" in block)

# ---- the desktop home (2026-10-26, «زى fotmob على الكمبيوتر»)
from site_lib.today_strip import match_centre         # noqa: E402
arts = [{"article_id": i, "title": f"خبر {i}", "slug": f"s{i}", "image_url": "/media/x.jpg" if i == 2 else None}
        for i in range(1, 9)]
st = [{"competition": "Primera Division", "table": [{"team": "x"}]},
      {"competition": "Turkish Super Lig", "table": [{"team": "y"}]},
      {"competition": "Some Cup", "table": [{"team": "z"}]}]
mc = match_centre(st, ms, arts, {})
ck("15 three columns: leagues | today's matches | news",
   0 <= mc.find("mp-leagues") < mc.find("ph-today") < mc.find("mp-extra"))
ck("16 the leagues column = the nine-league list with a table, each to its standings page",
   mc.count('class="lg-item"') == 2 and "/standings/" in mc and "Some Cup" not in mc, str(mc.count('class="lg-item"')))
ck("17 the news column: one featured story with a picture + the rest as rows, and /news",
   mc.count('class="mp-feat"') == 1 and mc.count('class="mn-item"') == 5 and 'href="/news.html"' in mc,
   f'{mc.count(chr(34) + "mp-feat" + chr(34))} {mc.count("mn-item")}')
ck("18 the whole /matches day list is inside it, with its filters and its script",
   mc.count('class="mrow ') == 4 and 'id="mfilters"' in mc and 'id="daynav"' in mc and MATCHES_JS in mc)
home_src = open("site_src/templates/home.html", encoding="utf-8").read()
ck("19 the home template renders the match centre and no longer the day cards or the chips row",
   "{{ match_centre }}" in home_src and "{{ today_cards }}" not in home_src and "{{ league_bar }}" not in home_src)
ck("20 the home page is the live card + the match centre, nothing below (desktop too)",
   all(x not in home_src for x in ("{{ news_filter }}", "{% for block in blocks %}", "{{ clubs_strip }}", "home-rest"))
   and home_src.find('id="favLive"') < home_src.find("{{ match_centre }}") < home_src.find("{{ fav_script }}"))

print("\nALL PHONE HOME TESTS PASSED" if not fails else f"\n{len(fails)} FAILED")
sys.exit(1 if fails else 0)
