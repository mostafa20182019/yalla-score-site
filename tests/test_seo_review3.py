# -*- coding: utf-8 -*-
r"""The SEO review's last list (2026-11-19): the scorers beyond the feed's ten
and each club's top scorer, headings + list data on /goals, one sameAs list.

    python tests/test_seo_review3.py      (from the repo root)

site_lib/full_scorers.py counts goals from the archive, and a count shown on
a page must be RIGHT: so it is shown only when every finished match has its
goals, an own goal is nobody's goal, and the count agrees with the feed's own
chart. Each of those guards is a case here.
"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

import site_lib.full_scorers as FS                      # noqa: E402
from site_lib.matchdata import match_details_index     # noqa: E402

fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


XI = {"أ": ["أ1", "أ2", "أ3"], "ب": ["ب1", "ب2", "ب3"], "ج": ["ج1", "ج2"], "د": ["د1"]}


def lineups(h, a):
    return {"h": {"xi": [{"name": x} for x in XI[h]]}, "a": {"xi": [{"name": x} for x in XI[a]]}}


def league(n=22, own_at=None, drop_goal_at=None, no_lineup_at=None, more=False):
    """n matches أ × ب, each 2-1 (أ1 + أ2/أ3 for أ, ب1 for ب); more = eight
    matches ج × د 1-1 on top (ج1 five times, ج2 three, د1 eight)."""
    games, det = [], []
    for i in range(n):
        day = f"2026-09-{i + 1:02d}"
        goals = [{"side": "h", "player": "أ1", "minute": "10", "tag": ""},
                 {"side": "h", "player": "أ2" if i % 2 == 0 else "أ3", "minute": "50", "tag": ""},
                 {"side": "a", "player": "ب1", "minute": "70", "tag": ""}]
        if own_at == i:
            goals[2] = {"side": "a", "player": "أ3", "minute": "70", "tag": ""}     # أ3 in his own net
        if drop_goal_at == i:
            goals = goals[:2]
        games.append({"match_id": i + 1, "home": "أ", "away": "ب", "home_score": 2, "away_score": 1,
                      "status": "FINISHED", "kickoff": day})
        det.append({"match_id": i + 1, "home": "أ", "away": "ب", "date": day, "goals": goals, "cards": [],
                    "subs": [], "lineups": {} if no_lineup_at == i else lineups("أ", "ب")})
    if more:
        for j in range(8):
            day = f"2026-10-{j + 1:02d}"
            games.append({"match_id": 100 + j, "home": "ج", "away": "د", "home_score": 1, "away_score": 1,
                          "status": "FINISHED", "kickoff": day})
            det.append({"match_id": 100 + j, "home": "ج", "away": "د", "date": day, "cards": [], "subs": [],
                        "goals": [{"side": "h", "player": "ج1" if j < 5 else "ج2", "minute": "5", "tag": ""},
                                  {"side": "a", "player": "د1", "minute": "80", "tag": ""}],
                        "lineups": lineups("ج", "د")})
    return games, match_details_index(det)


OFFICIAL = [{"name": "أ1", "team": "أ", "goals": 22}, {"name": "ب1", "team": "ب", "goals": 22},
            {"name": "أ2", "team": "أ", "goals": 11}, {"name": "أ3", "team": "أ", "goals": 11},
            {"name": "د1", "team": "د", "goals": 8}]

tally, unsure = FS.count_goals(*league())
ck("1 every goal of every match, per player and club",
   tally == {("أ1", "أ"): 22, ("أ2", "أ"): 11, ("أ3", "أ"): 11, ("ب1", "ب"): 22} and not unsure, str(tally))
ck("2 a chart name the archive never saw score -> the two disagree, nothing is shown",
   FS.full_scorers(*league(), OFFICIAL) is None)

games, idx = league(more=True)
fs = FS.full_scorers(games, idx, OFFICIAL)
ck("3 the rest of the list: outside the chart, two goals or more, most first",
   fs and fs["rest"] == [("ج1", "ج", 5), ("ج2", "ج", 3)] and fs["ones"] == 0, str(fs))
ck("4 each club's top scorer", fs and {t: (ps, n) for t, ps, n in fs["clubs"]} ==
   {"أ": (["أ1"], 22), "ب": (["ب1"], 22), "د": (["د1"], 8), "ج": (["ج1"], 5)}, str(fs and fs["clubs"]))
bad = [dict(x) for x in OFFICIAL]
bad[4]["goals"] = 9
ck("5 the chart says 9, the archive counts 8 -> nothing is shown", FS.full_scorers(games, idx, bad) is None)
low = [dict(x) for x in OFFICIAL[:4]] + [{"name": "ج2", "team": "ج", "goals": 3}]
ck("6 somebody outside the chart with MORE than its last name (د1: 8 > 3) -> nothing", FS.full_scorers(games, idx, low) is None)

t, u = FS.count_goals(*league(own_at=3))
ck("7 an own goal (a name from the OTHER side's line-up) is nobody's goal",
   t[("ب1", "ب")] == 21 and ("أ3", "ب") not in t and t[("أ3", "أ")] == 11 and not u, str(t))
ck("8 a match whose goal list does not add up to its score -> no count at all", FS.count_goals(*league(drop_goal_at=5)) is None)
g, i = league(no_lineup_at=2, more=True)
t, u = FS.count_goals(g, i)
ck("9 a goal nobody can judge (no line-up): its scorers are marked unsure", u == {("أ1", "أ"), ("أ2", "أ"), ("ب1", "ب")}, str(u))
ck("10 ...and an unsure name in the chart means nothing is shown", FS.full_scorers(g, i, OFFICIAL) is None)
ck("11 fewer than 20 finished matches: no count", FS.count_goals(*league(n=12)) is None)

# ---------------------------------------------------------------- the pages
dist = os.path.join(os.getcwd(), "dist")
if os.path.isdir(os.path.join(dist, "scorers")):
    eg = io.open(os.path.join(dist, "scorers", "egypt.html"), encoding="utf-8").read()
    if "بقية هدافي" in eg:
        rest = [int(x) for x in re.findall(r'<td class="nb-v">(\d+)</td>', eg.split("بقية هدافي")[1].split("</table>")[0])]
        ck("12 /scorers/egypt: the rest of the list, sorted, two goals or more",
           rest and rest == sorted(rest, reverse=True) and min(rest) >= 2, str(rest))
        ck("13 ...and «هداف كل نادٍ» as a table and as a question", "<h2>هداف كل نادٍ في" in eg and "من هداف كل نادٍ في" in eg)
    gl = io.open(os.path.join(dist, "goals.html"), encoding="utf-8").read()
    if 'class="gl-card"' in gl:
        ck("14 /goals: a heading per highlight, the list as data, breadcrumbs - and no VideoObject (the videos are on YouTube)",
           gl.count('<h2 class="gl-h">ملخص وأهداف مباراة ') == gl.count('class="gl-card"') and '"ItemList"' in gl
           and '"BreadcrumbList"' in gl and "VideoObject" not in gl)
        urls = re.findall(r'"url":\s*"https://elgoon\.com/m/([^"/]+)"', gl)
        ck("15 ...every listed URL is a match page the build wrote",
           urls and all(os.path.exists(os.path.join(dist, "m", u.replace(".html", "") + ".html")) for u in urls), str(urls[:3]))

import site_lib.config as CFG        # noqa: E402
src = io.open("site_pages/home.py", encoding="utf-8").read() + io.open("site_pages/articles.py", encoding="utf-8").read()
ck("16 one sameAs list for the home page and every article; a new profile is one line in config",
   src.count('"sameAs": SAME_AS') == 2 and CFG.SAME_AS[:2] == [CFG.FB_PAGE_URL, CFG.TG_CHANNEL_URL]
   and CFG.SAME_AS[2:] == CFG.EXTRA_PROFILES and all(u.startswith("https://") for u in CFG.SAME_AS))

print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
