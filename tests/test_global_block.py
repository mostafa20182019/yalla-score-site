# -*- coding: utf-8 -*-
"""«الأندية العالمية» on the home (2026-10-22): one tile per big club with
its last result, next match and latest story; CSS-tab mini tables.

    python tests/test_global_block.py     (from the repo root)
"""
import io, os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

import site_lib.cards as C
from site_lib.clubs import GLOBAL_CLUBS, GLOBAL_TABLES
from site_lib.config import REF_TODAY

T = REF_TODAY
fx = [{"competition": "Bundesliga", "rounds": [
        {"round": 7, "matches": [{"match_id": 1, "competition": "Bundesliga", "home": "FC Bayern München", "away": "VfB Stuttgart", "kickoff": "2026-10-18", "koff_time": "17:30", "status": "FINISHED", "home_score": 3, "away_score": 1, "home_badge": "https://crests.football-data.org/5.png"}]},
        {"round": 8, "matches": [{"match_id": 2, "competition": "Bundesliga", "home": "1. FC Köln", "away": "FC Bayern München", "kickoff": T, "koff_time": "19:30", "status": "UPCOMING", "away_badge": "https://crests.football-data.org/5.png"}]}]},
      {"competition": "Serie A", "rounds": [
        {"round": 8, "matches": [{"match_id": 3, "competition": "Serie A", "home": "Juventus FC", "away": "AC Milan", "kickoff": "2026-10-19", "koff_time": "21:45", "status": "FINISHED", "home_score": 0, "away_score": 0}]}]}]
arts = [{"article_id": "900", "title": "بايرن ميونخ يحسم ملف كين قبل مواجهة كولن", "summary": ""},
        {"article_id": "901", "title": "خبر عن الأهلي", "summary": ""}]
std = [{"competition": "Premier League", "table": [{"pos": i, "team": t, "played": 8, "pts": 24 - i, "crest": ""} for i, t in enumerate(["Arsenal FC", "Manchester City FC", "Liverpool FC", "Chelsea FC", "Tottenham Hotspur FC", "Everton FC"], 1)]},
       {"competition": "Serie A", "table": [{"pos": 1, "team": "SSC Napoli", "played": 8, "pts": 20}]},
       {"competition": "Ligue 1", "table": []}]
html = C.global_clubs_block([], fx, arts, std)
ck("1 the block renders with the heading and a swipe row", html.startswith('<section class="gc"') and "الأندية العالمية" in html and 'class="gc-row"' in html)
tiles = html.split('class="gc-tile')[1:]
ck("2 only clubs with a match in the pool get a tile (Bayern, Juventus, Milan)", len(tiles) == 3, str(len(tiles)))
bay = next(t for t in tiles if "بايرن ميونخ" in t)
ck("3 Bayern: last result WON 3-1 over Stuttgart, next TODAY 19:30 at Köln, the story linked, playing-today first",
   "فاز" in bay and "3" in bay and "1" in bay and "شتوتجارت" in bay and "اليوم · 19:30" in bay and "كولن" in bay
   and 'href="/a/900.html"' in bay and "gc-today" in bay and tiles[0] is bay, bay[:300])
ck("4 a non-curated club's head links to its match page; a curated one to its club page",
   'href="/m/2' in bay.split("gc-last")[0] and 'href="/team/' not in bay, bay[:160])
juv = next(t for t in tiles if "يوفنتوس" in t)
ck("5 Juventus: drew 0-0 with Milan, no next match, no story -> no next/news rows", "تعادل" in juv and "ميلان" in juv and "gc-next" not in juv and "gc-news" not in juv)
ck("6 the Bayern crest comes from the away badge of its next match", 'crests.football-data.org' in bay.split("gc-last")[0] or "/assets/crests/" in bay.split("gc-last")[0])
mt = html[html.find('<div class="mt">'):]
ck("7 mini tables: a tab per league WITH a table, in GLOBAL_TABLES order, five rows max, a link to the full table",
   mt.count('class="mt-tab"') == 2 and mt.find("الدوري الإنجليزي") < mt.find("الدوري الإيطالي") and mt.count("<tr>") == 2 + 5 + 1
   and 'href="/standings/england.html"' in mt and "إيفرتون" not in mt and "أرسنال" in mt, str(mt.count("<tr>")))
ck("8 the first tab is checked and the inputs carry no script", 'id="mt-0" checked' in mt and "<script" not in mt)
ck("9 nothing in the pool -> no block", C.global_clubs_block([], [], arts, std) == "")
ck("10 eighteen clubs listed, every one with a token and a league", len(GLOBAL_CLUBS) == 18 and all(c["match_tokens"] and c["league"] for c in GLOBAL_CLUBS) and GLOBAL_TABLES[0] == "Egyptian Premier League" and len(GLOBAL_TABLES) == 8 and "#mt-7:checked~.mt-panels .mt-p:nth-child(8)" in io.open("site_src/style.css", encoding="utf-8").read())
home_py = io.open("site_pages/home.py", encoding="utf-8").read()
ck("11 the home builds the block first among the blocks", "blocks.append(global_clubs_block(matches, fixtures, articles, standings))" in home_py
   and home_py.find("global_clubs_block(matches") < home_py.find("home_insights(articles"))
css = io.open("site_src/style.css", encoding="utf-8").read()
ck("12 the stylesheet knows the tiles and the tabs", ".gc-row{display:flex" in css and "#mt-0:checked~.mt-panels" in css)

# the swipe rows get desktop arrows (user, 2026-10-22: «على الكمبيوتر مبعرفش اتحرك ازاى»)
from site_lib.shell import foot, SWIPE_JS
ft = foot()
ck("13 every page's foot carries the swipe script, armed only on hover devices and only on an overflowing row",
   SWIPE_JS in ft and "matchMedia('(hover:hover)')" in SWIPE_JS and "row.scrollWidth<=row.clientWidth+8" in SWIPE_JS and ".gc-row,.lq,.ts-row" in SWIPE_JS)
ck("14 the arrows are RTL-aware and the stylesheet draws them at the inline edges", "rtl?-d:d" in SWIPE_JS and ".sw-back{inset-inline-start" in css and ".sw-fwd{inset-inline-end" in css)

ck("15 the «see all» links sit under their blocks (user, 2026-10-23)",
   html.find('class="gc-row"') < html.find('class="blk-more"') < html.find("كل المباريات ←") < html.find('<div class="mt">')
   and html.find("كل المباريات ←") > html.find("</h2>"))

print()
print("ALL OK" if not fails else f"{len(fails)} FAILED: " + ", ".join(fails))
sys.exit(1 if fails else 0)
