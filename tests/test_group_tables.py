r"""Group stages shown group by group (user ask 2026-11-13: «عايز فى بطولة
تصفيات امم افريقيا وبطولة الامم الاوروبية يجيب المجموعات زى مبجيب الجولات»).

    python tests/test_group_tables.py      (from the repo root)

365scores returns ONE standings entry holding every group's rows; the single-
table guard refuses it as «the table» (it would mix nine groups), so for the
AFCON qualifiers (588) and the Nations League (7016) the entry is kept split
as {"groups": [...]} - and "table" stays absent, so nothing that reads a
league table ever sees it.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import fetch_data as F
from site_lib.tables import group_tables_panel
from site_lib.clubs import TEAM_PAGES

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

def row(g, pos, name, pts, gp=2, w=1, d=1, l=0, f=3, a=1):
    return {"groupNum": g, "position": pos, "competitor": {"id": pos * 10 + (g or 0), "name": name, "imageVersion": 1},
            "gamePlayed": gp, "gamesWon": w, "gamesEven": d, "gamesLost": l, "for": f, "against": a, "points": pts}

AFQ = {"groups": [{"num": 1, "name": "المجموعة أ"}, {"num": 2, "name": "المجموعة ب"}],
       "rows": [row(None, 41, "جيبوتي", 0),                      # a preliminary-round team that went out
                row(1, 2, "غانا", 4), row(1, 1, "الكونغو", 6),
                row(2, 1, "مصر", 4, f=5, a=0), row(2, 2, "أنجولا", 4), row(2, 3, "مالاوي", 3), row(2, 4, "جنوب السودان", 0)]}
g = F.s365_group_tables(AFQ)
ck("1 one entry per group, in group order, named by the feed", [x["name"] for x in g] == ["المجموعة أ", "المجموعة ب"])
ck("2 a row with no group (preliminary round) is dropped", not any(r["team"] == "جيبوتي" for x in g for r in x["table"]))
ck("3 each table is in the feed's order and numbered 1..n",
   [r["team"] for r in g[0]["table"]] == ["الكونغو", "غانا"] and [r["pos"] for r in g[1]["table"]] == [1, 2, 3, 4])
ck("4 the row carries the same keys as a league table row",
   set(g[1]["table"][0]) == {"pos", "team", "crest", "played", "won", "draw", "lost", "gf", "ga", "gd", "pts"}
   and g[1]["table"][0]["gd"] == 5 and g[1]["table"][0]["pts"] == 4)
ck("5 the Nations League names read as level + group",
   F._group_name("دوري ا - بيت 1", 1) == "المستوى أ · المجموعة 1" and F._group_name("دوري د - بيت 2", 15) == "المستوى د · المجموعة 2")
ck("6 a plain group name passes through; none -> «المجموعة n»",
   F._group_name("المجموعة ب", 2) == "المجموعة ب" and F._group_name(None, 3) == "المجموعة 3")
ck("7 only the two group stages are split", F.GROUP_TABLES == {588, 7016})

comp = "Africa Cup of Nations Qualification"
html = group_tables_panel(comp, g, TEAM_PAGES)
ck("8 the panel is a rounds-panel (ROUNDS_JS drives ‹ ›) with one .round per group",
   'class="lg-fix rounds-panel groups-panel"' in html and html.count('class="round"') == 2
   and 'class="rn-prev"' in html and 'class="rn-label"' in html)
ck("9 it opens on the group of a team we follow (Egypt, group 2)", 'data-current="2"' in html)
ck("10 each group's table is titled by the group", "المجموعة ب</div>" in html and "جدول ترتيب" not in html)
ck("11 no followed team -> the first group", 'data-current="1"' in group_tables_panel("UEFA Nations League", g, TEAM_PAGES))
ck("12 nothing to show -> nothing", group_tables_panel(comp, [], TEAM_PAGES) == "" and group_tables_panel(comp, None, TEAM_PAGES) == "")

# «لعب / ف / ت / خ» open the group's matches (user 2026-11-15)
import site_lib.tables as T                                  # noqa: E402
tbl = [{"pos": 1, "team": "AA", "played": 1, "won": 1, "draw": 0, "lost": 0, "gf": 2, "ga": 0, "gd": 2, "pts": 3},
       {"pos": 2, "team": "BB", "played": 1, "won": 0, "draw": 0, "lost": 1, "gf": 0, "ga": 2, "gd": -2, "pts": 0}]
gm = [{"match_id": 11, "home": "AA", "away": "BB", "kickoff": "2026-09-25", "home_score": 2, "away_score": 0},
      # a play-off against a team of ANOTHER group is not a group match
      {"match_id": 12, "home": "AA", "away": "ZZ", "kickoff": "2026-03-20", "home_score": 1, "away_score": 1}]
ck("15 a group's matches are those between two of its own teams",
   [m["match_id"] for m in T._group_games(tbl, gm)] == [11] and T._group_games(tbl, None) is None)
gh = group_tables_panel(comp, [{"num": 1, "name": "المجموعة أ", "table": tbl}], (), games=gm,
                        pages=lambda m: m["match_id"])
ck("16 with the season's matches the numbers are buttons and the group carries its own store",
   gh.count('class="lt-n"') == 4 and 'data-gm="11:w"' in gh and 'data-gm="11:l"' in gh
   and gh.count('class="lt-games"') == 1 and 'data-id="11"' in gh and 'data-id="12"' not in gh)
ck("17 without them the table is as before: plain numbers, no count", 'class="lt-n"' not in html and "data-pc" not in html)
lg = open("site_src/snippets/lt_games_js.html", encoding="utf-8").read()
ck("18 the popup indexes EVERY store on the page (one per group)",
   "document.querySelectorAll('.lt-games')" in lg and "[].forEach.call(stores,function(s){" in lg)
lp = open("site_pages/leagues.py", encoding="utf-8").read()
ck("19 the season page ships the popup script where a button exists, fed from the season pool",
   "games_js=Markup(LT_GAMES_JS if 'class=\"lt-n\"' in groups_panel else \"\")" in lp
   and "games=(bycomp or {}).get(comp) if bycomp is not None else None" in lp
   and "{{ games_js }}" in open("site_src/templates/fixtures.html", encoding="utf-8").read()
   and "bycomp=_bycomp" in open("build_site.py", encoding="utf-8").read())

src = open("site_src/templates/fixtures.html", encoding="utf-8").read()
ck("13 the season page shows the groups above the rounds", src.index("{{ groups_panel }}") < src.index("{{ rounds_panel }}"))
bs = open("build_site.py", encoding="utf-8").read()
ck("14 build passes the groups to the season pages", 's["groups"] for s in standings' in bs)

print()
print(f"{len(fails)} FAILED: {', '.join(fails)}" if fails else "ALL GROUP-TABLE TESTS PASSED")
sys.exit(1 if fails else 0)
