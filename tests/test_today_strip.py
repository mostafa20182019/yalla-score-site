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

# ---- the home cards (2026-10-22): the same pick, one card per match, the match page behind it
cards = TS.today_cards(M, today=T)
ck("14 the home block carries the heading, the all-matches link and one card per picked match",
   cards.startswith('<section class="tc"') and "مباريات اليوم" in cards and 'href="/matches.html"' in cards
   and cards.count('class="tc-card tk-item') == len(rows), str(cards.count('class="tc-card tk-item')))
ck("15 every card is a link to its match page in the live contract (data-lv, the two names, a .tk-mid)",
   cards.count("data-lv") == len(rows) and cards.count('class="tc-mid tk-mid"') == len(rows)
   and all(f'href="/m/{m["match_id"]}' in cards for m in rows))
live_card = cards[cards.find("tc-live"):cards.find("</a>", cards.find("tc-live"))]
fin_card = cards[cards.find("tc-fin"):cards.find("</a>", cards.find("tc-fin"))]
up_card = cards[cards.find('href="/m/4'):cards.find("</a>", cards.find('href="/m/4'))]
ck("16 live: «مباشر الآن», dashes and the dot, never a baked score", "مباشر الآن" in live_card and "tk-dot" in live_card and "0 - 1" not in live_card and "1 - 0" not in live_card)
ck("17 finished: «انتهت» and the final score; upcoming: «اليوم · time» and the time pill",
   "انتهت" in fin_card and ("2" in fin_card and "0" in fin_card) and 'class="tc-when">اليوم<' in up_card and 'class="tk-t">18:30' in up_card)
ck("18 the foot: the TV channel when known and the «بطاقة المباراة» link", "بطاقة المباراة ←" in up_card and ("📺" in up_card or "<span></span>" in up_card))
ck("19 nothing today -> no block", TS.today_cards(M, today="2026-10-20") == "")
ck("20 the cap is six", len(TS.pick_today(M + [dict(M[0], match_id=str(i)) for i in range(10, 20)], today=T, limit=TS.CARDS)) == 6)
home_tpl = io.open("site_src/templates/home.html", encoding="utf-8").read()
ck("21 the home template places the cards right after the live card and before «تحت المجهر»",
   0 < home_tpl.find('id="favLive"') < home_tpl.find("{{ today_cards }}") < home_tpl.find("{{ news_filter }}"))
home_py = io.open("site_pages/home.py", encoding="utf-8").read()
ck("22 home.py builds the block from the matches and hands it to the template", "today_cards(matches)" in home_py and "today_cards=Markup(_today_cards)" in home_py)
ck("23 the stylesheet knows the cards, two columns on tablets, a swipe row on phones", ".tc-row{display:grid" in css and "@media(max-width:560px){.tc-row{display:flex" in css)

print()
print("ALL OK" if not fails else f"{len(fails)} FAILED: " + ", ".join(fails))
sys.exit(1 if fails else 0)
