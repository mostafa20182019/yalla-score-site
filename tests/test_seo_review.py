# -*- coding: utf-8 -*-
r"""The SEO review of 2026-11-19 (the seo-expert agent's list): the squad's
numbers on the club page, a real link to the club page in the standings
table, a fixtures title that fits, the scorers page's breadcrumb data.

    python tests/test_seo_review.py      (from the repo root)

The squad table is the one piece that ADDS numbers to a page, so most of
this file is about it never saying more than the archive holds: only the
club's own matches, only matches with its line-up, an own goal never a
scorer's goal, a booked coach never a player, a rating only from enough
rated starts, no table at all from too few matches.
"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

from site_lib import squad_stats as S                    # noqa: E402
from site_lib.clubs import TEAM_PAGES                    # noqa: E402
from site_lib.matchdata import match_details_index       # noqa: E402

fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


AHLY = next(tp for tp in TEAM_PAGES if tp["slug"] == "al-ahly")
EGY = "Egyptian Premier League"
NAMES = [f"لاعب {i}" for i in range(1, 12)]


def xi(names, rt=7.0):
    return [{"name": n, "num": i + 1, "pos": "الوسط", "rt": rt} for i, n in enumerate(names)]


def game(i, home, away, date, comp=EGY, status="FINISHED"):
    return {"match_id": i, "home": home, "away": away, "kickoff": date, "competition": comp,
            "status": status, "home_score": 1, "away_score": 0}


def det(i, home, away, date, hx, ax, goals=(), cards=(), subs=()):
    return {"match_id": i, "home": home, "away": away, "date": date, "flipped": False,
            "lineups": {"h": {"xi": hx}, "a": {"xi": ax}}, "goals": list(goals), "cards": list(cards), "subs": list(subs)}


OPP = [f"خصم {i}" for i in range(1, 12)]
ms, ds = [], []
for k in range(6):
    d = f"2026-10-{10 + k:02d}"
    home = k % 2 == 0                                    # Al Ahly at home in even games
    ms.append(game(100 + k, "الأهلي" if home else "سموحة", "سموحة" if home else "الأهلي", d))
    side = "h" if home else "a"
    other = "a" if home else "h"
    goals = [{"side": side, "player": "لاعب 9", "minute": "10", "tag": ""}]
    cards = [{"side": side, "player": "لاعب 4", "minute": "30", "color": "y"}]
    subs = [{"side": side, "in": "بديل 1", "out": "لاعب 11", "minute": "70"}]
    if k == 0:
        goals.append({"side": side, "player": "خصم 3", "minute": "50", "tag": "عكسية"})     # an own goal FOR us
        goals.append({"side": other, "player": "خصم 9", "minute": "60", "tag": ""})          # their goal
        cards.append({"side": side, "player": "المدرب", "minute": "80", "color": "r"})       # a sent-off coach
        cards.append({"side": side, "player": "لاعب 5", "minute": "85", "color": "r"})
        cards.append({"side": other, "player": "خصم 2", "minute": "20", "color": "y"})
    hx, ax = (xi(NAMES), xi(OPP)) if home else (xi(OPP), xi(NAMES))
    ds.append(det(100 + k, ms[-1]["home"], ms[-1]["away"], d, hx, ax, goals, cards, subs))
idx = match_details_index(ds)
r = S.squad_stats(AHLY, ms, idx)
by = {x["name"]: x for x in (r or {}).get("rows", [])}
ck("1 six matches with a line-up: a table from six matches", r and r["n"] == 6, str(r and r["n"]))
ck("2 a starter: six appearances, six starts - home or away", by.get("لاعب 1", {}).get("apps") == 6 and by["لاعب 1"]["starts"] == 6)
ck("3 a substitute: six appearances, no start", by.get("بديل 1", {}).get("apps") == 6 and by["بديل 1"]["starts"] == 0)
ck("4 goals: the scorer's six; an own goal and the opponent's goal belong to nobody here",
   by.get("لاعب 9", {}).get("goals") == 6 and "خصم 3" not in by and "خصم 9" not in by and sum(x["goals"] for x in by.values()) == 6)
ck("5 cards: the player's, by colour; a sent-off coach and the opponent's card are not in the table",
   by.get("لاعب 4", {}).get("yellow") == 6 and by.get("لاعب 5", {}).get("red") == 1 and "المدرب" not in by and "خصم 2" not in by)
ck("6 the average rating of the rated starts, one decimal; none for a player who never started",
   by["لاعب 1"]["rating"] == "7.0" and by["بديل 1"]["rating"] == "")
ck("7 the opponent's players never enter the club's table", not any(n.startswith("خصم") for n in by))

ck(f"8 fewer than {S.MIN_MATCHES} matches with a line-up: no table", S.squad_stats(AHLY, ms[:4], idx) is None)
ck("9 no details at all: no table", S.squad_stats(AHLY, ms, None) is None and S.squad_stats(AHLY, ms, {}) is None)
saudi = [game(200 + k, "الأهلي", "النصر", f"2026-10-{10 + k:02d}", comp="Saudi Pro League") for k in range(6)]
sidx = match_details_index([det(200 + k, "الأهلي", "النصر", f"2026-10-{10 + k:02d}", xi(NAMES), xi(OPP)) for k in range(6)])
ck("10 the Saudi «الأهلي» is not the Egyptian club: its matches give this page nothing", S.squad_stats(AHLY, saudi, sidx) is None)
few = [dict(x) for x in ds]
for x in few[:2]:
    x["lineups"] = {"h": {"xi": []}, "a": {"xi": []}}
ck("11 a match without a line-up gives no appearance (and here leaves too few matches)",
   S.squad_stats(AHLY, ms, match_details_index(few)) is None)
two = [det(100 + k, ms[k]["home"], ms[k]["away"], ms[k]["kickoff"],
           xi(NAMES, rt=8.0 if k < 2 else None) if k % 2 == 0 else xi(OPP),
           xi(OPP) if k % 2 == 0 else xi(NAMES, rt=8.0 if k < 2 else None)) for k in range(6)]
r2 = S.squad_stats(AHLY, ms, match_details_index(two))
ck(f"12 fewer than {S.MIN_RATED} rated starts: no average shown", r2 and all(x["rating"] == "" for x in r2["rows"]))
up = ms + [game(300, "الأهلي", "زد", "2026-12-01", status="UPCOMING")]
ck("13 a match not played yet changes nothing", S.squad_stats(AHLY, up, idx)["n"] == 6)
ck("14 the same match listed twice is counted once", S.squad_stats(AHLY, ms + ms, idx)["rows"][0]["apps"] == 6)

# ------------------------------------------------------------- the page and the links
club = io.open("site_src/templates/club.html", encoding="utf-8").read()
ck("15 the club page says how many matches the numbers come from, and what «شارك» means",
   "{% if squad %}" in club and "لدينا تشكيلها" in club and "«شارك» = أساسيًا أو بديلًا" in club)
ck("16 no minutes, no assists, no «suspended» column - the feed does not carry them",
   not re.search("دقائق|صناعة|موقوف", club.split('class="minfo squad"')[1].split("</section>")[0]))
tb = io.open("site_lib/tables.py", encoding="utf-8").read()
ck("17 a table row whose club has a page links it with a real <a>; the others keep the card button",
   '<a class="lt-tb" href="{esc(_tc["tp"])}.html">' in tb and '<button type="button" class="lt-tb">' in tb)
tc = io.open("site_src/snippets/team_card_js.html", encoding="utf-8").read()
ck("18 the card's script still takes the tap on that link", "closest('.lt-tb')" in tc and "e.preventDefault(); open(b);" in tc)
lg = io.open("site_pages/leagues.py", encoding="utf-8").read()
ck("19 the fixtures title drops the season before «مواعيد» or «المباريات القادمة»",
   lg.index('f"جدول مباريات {label}: مواعيد {_next} والنتائج {season}"') < lg.index('f"جدول مباريات {label}: مواعيد {_next} والنتائج",')
   and "len(t) <= 62" in lg)
ck("20 the scorers page carries its BreadcrumbList", "{{ crumbs_ld }}" in io.open("site_src/templates/scorers.html", encoding="utf-8").read()
   and 'crumbs_ld=Markup(breadcrumb_ld([' in lg)

dist = os.path.join(os.getcwd(), "dist")
if os.path.isdir(os.path.join(dist, "team")):
    def rd(*p):
        return io.open(os.path.join(dist, *p), encoding="utf-8").read()
    long_t = []
    for f in os.listdir(os.path.join(dist, "fixtures")):
        t = re.search(r"<title>(.*?)</title>", rd("fixtures", f)).group(1)
        if len(t) > 62 or "مواعيد" not in t:
            long_t.append((f, len(t)))
    ck("21 every built fixtures title fits 62 characters and still says «مواعيد»", not long_t, str(long_t[:5]))
    linked = set()
    for f in os.listdir(os.path.join(dist, "standings")):
        linked |= set(re.findall(r'<a class="lt-tb" href="/team/([a-z0-9-]+)"', rd("standings", f)))
    clubs = {tp["slug"] for tp in TEAM_PAGES if tp["slug"] not in ("egypt", "sudan")}
    ck("22 built standings pages link the club pages of the leagues we hold a table for", len(linked) >= 10 and linked <= clubs,
       str(sorted(linked)))
    tables = [f for f in os.listdir(os.path.join(dist, "team")) if 'class="minfo squad"' in rd("team", f)]
    bad = []
    for f in tables:
        h = rd("team", f).split('class="minfo squad"')[1].split("</section>")[0]
        rows = re.findall(r"<tr><td class=\"sq-n\">.*?</tr>", h, re.S)
        nums = [[int(x) for x in re.findall(r"<td>(\d+)</td>", r)[:5]] for r in rows]
        n = int((re.search(r"من (\d+) ", h) or [0, 0])[1] or 0)
        if not rows or any(len(x) < 5 or x[1] > x[0] or (n and x[0] > n) for x in nums):
            bad.append(f)
    ck(f"23 built squad tables ({len(tables)}): starts never above appearances, appearances never above the matches counted",
       tables and not bad, str(bad))

print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
