# -*- coding: utf-8 -*-
r"""The head-to-head page /h2h/<slug> - «مواجهات الأهلي والزمالك» (2026-11-13).

    python tests/test_h2h_page.py     (from the repo root)

The page is computed from a meetings list. These checks hold the rules that
keep it honest: an awarded result counts as a result but not its goals, a
draw settled on penalties stays a draw, a new derby from our own data joins
without a fetch, the saved history never shrinks, and the score between two
names is the RTL-safe pill.
"""
import io
import json
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


from site_lib import h2h as H                              # noqa: E402
import h2h_history as HH                                   # noqa: E402

A, B = "الأهلي", "الزمالك"
PAIR = H.PAIRS[0]
ck("1 the first pair is the Cairo derby, on its indexed slug",
   (PAIR["a"], PAIR["b"], PAIR["slug"]) == (A, B, "al-ahly-zamalek"))

HIST = [
    {"id": 5, "date": "2026-10-11", "comp": "الدوري المصري", "home": B, "away": A, "hg": 0, "ag": 2},
    {"id": 4, "date": "2025-03-11", "comp": "الدوري المصري - المرحلة النهائية", "home": B, "away": A, "hg": 3, "ag": 0},
    {"id": 3, "date": "2024-10-24", "comp": "كأس السوبر المصري - النهائي", "home": A, "away": B, "hg": 0, "ag": 0},
    {"id": 2, "date": "2023-07-13", "comp": "الدوري المصري", "home": A, "away": B, "hg": 4, "ag": 1},
    {"id": 1, "date": "2022-07-21", "comp": "كأس مصر - النهائي", "home": A, "away": B, "hg": 1, "ag": 2},
]
NOTES = {"2025-03-11": {"note": "قرار إداري", "played": False},
         "2024-10-24": {"note": "الأهلي بالترجيح", "winner": A}}
M_ALL = {
    5: {"match_id": 5, "home": B, "away": A, "kickoff": "2026-10-11", "status": "FINISHED",
        "home_score": 0, "away_score": 2, "competition": "Egyptian Premier League"},
    6: {"match_id": 6, "home": A, "away": B, "kickoff": "2026-11-01", "status": "FINISHED",
        "home_score": 1, "away_score": 1, "competition": "Egyptian Premier League"},
    7: {"match_id": 7, "home": B, "away": A, "kickoff": "2027-03-01", "koff_time": "20:00",
        "status": "UPCOMING", "competition": "Egyptian Premier League"},
    8: {"match_id": 8, "home": A, "away": "بيراميدز", "kickoff": "2026-11-05", "status": "FINISHED",
        "home_score": 9, "away_score": 0, "competition": "Egyptian Premier League"},
}

g = H.meetings(PAIR, HIST, M_ALL)
ck("2 our own finished derby joins the saved history, newest first",
   [x["id"] for x in g] == ["6", "5", "4", "3", "2", "1"], [x["id"] for x in g])
ck("3 a match already in the history is not doubled", sum(1 for x in g if x["date"] == "2026-10-11") == 1)
ck("4 a match against another club never joins", all({x["home"], x["away"]} == {A, B} for x in g))
ck("5 a meeting links to its page only when the site has one",
   {x["id"]: x["ours"] for x in g} == {"6": "6", "5": "5", "4": None, "3": None, "2": None, "1": None})

t = H.tally(g, PAIR, NOTES)
ck("6 an awarded result counts as a win", t["wins"] == {A: 2, B: 2} and t["draws"] == 2, t)
ck("7 ... but its goals are not counted", t["goals"] == {A: 2 + 0 + 4 + 1 + 1, B: 0 + 0 + 1 + 2 + 1}
   and t["awarded"] == 1, t["goals"])
ck("8 a draw settled on penalties stays a draw", H.winner(g[3]) is None)
ck("9 the biggest win ignores the awarded 3-0", H.biggest_win(g, NOTES)["date"] == "2023-07-13")
ck("10 competitions are grouped without their stage",
   H.by_competition(g, PAIR)[0] == ("الدوري المصري", 4, 2, 1, 1), H.by_competition(g, PAIR))
ck("11 the unbeaten run stops at the other club's win", H.unbeaten_run(g, PAIR) == (A, 2), H.unbeaten_run(g, PAIR))
ck("12 the next meeting is the scheduled one", H.next_meeting(PAIR, M_ALL, "2026-11-13")["match_id"] == 7)
ck("13 no next meeting when none is scheduled", H.next_meeting(PAIR, {5: M_ALL[5]}, "2026-11-13") is None)
ck("14 the score in a sentence keeps its spaces (RTL)", H.score_line(g[1]) == "الزمالك 0 - 2 الأهلي")
ck("15 a club page finds its pair", H.pair_for_club("zamalek") is PAIR and H.pair_for_club("barcelona") is None)

# the saved history only grows
merged, n = HH.merge(HIST[2:], HIST[:3] + [{"id": 99, "date": "2026-12-01", "comp": "x", "home": A, "away": B, "hg": 1, "ag": 0}])
ck("16 merge adds the new games and keeps every saved one",
   n == 3 and [x["id"] for x in merged] == [99, 5, 4, 3, 2, 1], [x["id"] for x in merged])
ck("17 merge never drops a game the feed stopped listing", len(HH.merge(HIST, HIST[:1])[0]) == len(HIST))

doc = json.load(io.open("data/h2h_history.json", encoding="utf-8"))
saved = (doc["pairs"].get(H.pair_key(A, B)) or {}).get("games") or []
ck("18 the committed history holds the derby (15 games or more, all between the two)",
   len(saved) >= 15 and all(H.is_pair(PAIR, x["home"], x["away"]) for x in saved), f"{len(saved)} games")

# the page, rendered from the fixture
import site_lib.shell as SH                                # noqa: E402
import site_pages.h2h as P                                 # noqa: E402

out = {}
tmp = tempfile.mkdtemp()
P.DIST = tmp
P.write = lambda path, html: out.__setitem__(path, html)
P.REF_TODAY = "2026-11-13"
H.load_history = lambda pair: HIST
H.load_notes = lambda pair: NOTES
urls = []
P.h2h_pages([], M_ALL, urls)
page = out.get("h2h/al-ahly-zamalek.html", "")
ck("19 the page is written on its slug and joins the sitemap list",
   bool(page) and urls == ["/h2h/al-ahly-zamalek.html"], urls)
ck("20 the H1 carries the query and the honest count",
   "<h1 class=\"page-h\">تاريخ مواجهات الأهلي والزمالك: نتائج آخر 6 مباريات</h1>" in page)
ck("21 the lead says since when, one fact per sentence",
   "لعب الأهلي والزمالك 6 مباريات منذ يوليو 2022 في كل البطولات. فاز الأهلي في مباراتين. "
   "فاز الزمالك في مباراتين. انتهت مباراتان بالتعادل." in page)
ck("22 the score between two names is the pill, home number first",
   '<b class="h2h-sc"><span>0</span><i>-</i><span>2</span></b>' in page)
ck("23 the notes are printed on their rows", "قرار إداري" in page and "الأهلي بالترجيح" in page)
ck("24 the penalties winner is marked on a drawn row",
   '<b class="h2h-n w">الأهلي</b><b class="h2h-sc"><span>0</span><i>-</i><span>0</span></b><b class="h2h-n">الزمالك</b>' in page)
ck("25 the awarded goals are explained", "مباريات حُسمت بقرار إداري ولا تُحسب أهدافها: 1." in page)
ck("25b an awarded last win carries its note",
   "آخر فوز لفريق الزمالك: الزمالك 3 - 0 الأهلي يوم 11 مارس 2025 (قرار إداري)." in page)
ck("26 only our own matches link to a match page",
   page.count('class="h2h-l"') == 2 and 'href="/m/6"' in page.replace(".html", ""))
ck("27 the next meeting is a row and an FAQ answer", "الزمالك ضد الأهلي" in page and "20:00" in page)
ck("28 FAQPage and BreadcrumbList are on the page", '"FAQPage"' in page and '"BreadcrumbList"' in page)
ck("29 the page never claims an all-time record", "عبر التاريخ" not in page and "على مر التاريخ" not in page)
ck("30 it links to both club pages", 'href="/team/al-ahly' in page and 'href="/team/zamalek' in page)

out.clear()
P.h2h_pages([], {}, [])
none_page = out.get("h2h/al-ahly-zamalek.html", "")
ck("31 with no scheduled match the page says so plainly",
   "لم يُعلن موعد المباراة القادمة بعد" in none_page and "h2h-none" in none_page)
H.load_history = lambda pair: HIST[:3]
out.clear()
ck("32 fewer than four meetings on record = no page", P.h2h_pages([], {}, []) == 0 and not out)

tpl = io.open("site_src/templates/club.html", encoding="utf-8").read()
ck("33 the club page links to its head-to-head page", "h2h.href" in tpl)
src = io.open("build_site.py", encoding="utf-8").read()
ck("34 build() writes the pages after the club pages", src.index("club_pages(_plog") < src.index("h2h_pages(articles, m_all, urls)"))

# the links INTO the page and the hub triangle (SEO review 2026-11-13)
ck("35 a match between the two finds its pair, another match does not",
   H.pair_of_match(B, A) is PAIR and H.pair_of_match(A, "بيراميدز") is None)
ck("36 an article title naming both clubs finds the pair",
   H.pair_in_text("لجنة الحكام توافق على سماع الزمالك تسجيلات قمة الأهلي") is PAIR
   and H.pair_in_text("الأهلي يفوز على بيراميدز") is None)
ck("37 the Egyptian league hubs carry the pair", H.pairs_for_league("Egyptian Premier League") == [PAIR]
   and H.pairs_for_league("Premier League") == [])
T = lambda n: io.open("site_src/templates/" + n, encoding="utf-8").read()   # noqa: E731
ck("38 the match page links the pair's head-to-head page", "h2h.href" in T("match.html"))
ck("39 the standings page ends with its fixtures / scorers row", "for link in more" in T("standings.html"))
ck("40 the scorers page links the table and the fixtures", "for link in also" in T("scorers.html"))
lsrc = io.open("site_pages/leagues.py", encoding="utf-8").read()
ck("41 the fixtures page links the scorers page only when it was written",
   'os.path.exists(os.path.join(DIST, "scorers", f"{slug}.html"))' in lsrc)
asrc = io.open("site_pages/articles.py", encoding="utf-8").read()
ck("42 «للمتابعة» links a table only for a competition that has one",
   'in _with_table' in asrc and 'in _with_rounds' in asrc)
from site_lib.clubs import TEAM_PAGES                      # noqa: E402
from site_lib.names import _team_match                     # noqa: E402
tz = next(tp for tp in TEAM_PAGES if tp["slug"] == "trabzonspor")
ck("43 Trabzonspor's Conference League match is his match",
   _team_match(tz, {"home": "سيسكا - صوفيا", "away": "طرابزون سبور", "competition": "UEFA Conference League"})
   and not _team_match(tz, {"home": "x", "away": "طرابزون سبور", "competition": "Premier League"}))

print()
if fails:
    print(f"{len(fails)} FAILED: " + "; ".join(fails))
    sys.exit(1)
print("all good")
