r"""365scores competitions stay in agreement across the three files (2026-09-20).

    python tests/test_s365_comps.py   (from the repo root)

Adding a competition touches fetch_data.py (S365_LEAGUES + S365_ALL_COMPS),
build_site.py (five maps) and worker.js (LIVE_COMPS + DETAIL_FIRST) - and
nothing used to check they agree. Written while adding the AFCON qualifiers
(588), which also exposed a second standings shape: ONE entry carrying every
group's rows (52 rows over nine groups), which the len(sts)==1 guard alone
would have rendered as "the table".
"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


import fetch_data as fd                                  # noqa: E402
import build_site as bs                                  # noqa: E402

wk = io.open("worker.js", encoding="utf-8").read()
fds = io.open("fetch_data.py", encoding="utf-8").read()

names = [n for _, n in fd.S365_LEAGUES]
ids = {n: i for i, n in fd.S365_LEAGUES}

# ---- one new competition must land in EVERY map, or fail loudly ----------
ck("1 every S365 league is in build_site.S365_COMPETITIONS (data credit)",
   all(n in bs.S365_COMPETITIONS for n in names),
   ", ".join(n for n in names if n not in bs.S365_COMPETITIONS) or "all")
ck("2 ...and has an Arabic label", all(n in bs.COMP_LABEL for n in names))
ck("3 ...and a place in the sidebar order", all(n in bs.COMP_ORDER for n in names))
ck("4 ...and its 365scores id in S365_COMP_IDS, matching fetch_data's",
   all(bs.S365_COMP_IDS.get(n) == ids[n] for n in names))
# EGY/TUR/KSA deliberately use flag emojis, not logos (comp_emoji); the two
# African cups have no flag, so they carry the 365scores emblem
ck("5 the flag-less competitions carry an emblem",
   all(n in bs.COMP_LOGO for n in
       ("CAF Champions League", "Africa Cup of Nations Qualification", "CAF Confederation Cup")))

all_comps = fd.S365_ALL_COMPS.split(",")
ck("6 S365_ALL_COMPS (details/lineups/goals) covers every S365 league",
   all(str(i) in all_comps for i in ids.values()))

live = re.search(r'const LIVE_COMPS = "([\d,]+)"', wk).group(1)
ck("7 worker LIVE_COMPS is the same list as S365_ALL_COMPS",
   live == fd.S365_ALL_COMPS, f"{live} vs {fd.S365_ALL_COMPS}")
first = set(re.search(r"DETAIL_FIRST = new Set\(\[([\d, ]+)\]\)", wk)
            .group(1).replace(" ", "").split(","))
ck("8 DETAIL_FIRST ⊆ LIVE_COMPS", first <= set(live.split(",")))
ck("9 the Egyptian-scope trio gets detail-first (552 league, 624 CAF, 588 AFCON quals)",
   {"552", "624", "588"} <= first)

# ---- slugs: /fixtures and /analysis URLs are indexed - never collide -----
slugs = list(bs.COMP_SLUG.values())
ck("10 COMP_SLUG values are unique", len(slugs) == len(set(slugs)))
ck("11 the AFCON qualifiers page slug exists",
   bs.COMP_SLUG.get("Africa Cup of Nations Qualification") == "afcon-qualifiers")
# the Europa League (user ask 2026-10-15): 573 everywhere, placed right after
# the UCL, with the UCL's featured clubs on the predictions hub
ck("11b the Europa League is 573 in fetch_data, build_site and the worker",
   ids.get("UEFA Europa League") == 573 and bs.S365_COMP_IDS.get("UEFA Europa League") == 573
   and "573" in live)
ck("11c ...sits right after the Champions League in the sidebar order",
   bs.COMP_ORDER.index("UEFA Europa League") == bs.COMP_ORDER.index("UEFA Champions League") + 1)
ck("11e the CAF Confederation Cup is 627 everywhere, after the CAF CL, inside the Egyptian scope and detail-first",
   ids.get("CAF Confederation Cup") == 627 and bs.S365_COMP_IDS.get("CAF Confederation Cup") == 627 and "627" in live
   and bs.COMP_ORDER.index("CAF Confederation Cup") == bs.COMP_ORDER.index("CAF Champions League") + 1
   and "CAF Confederation Cup" in __import__("site_lib.clubs", fromlist=["EGY_SCOPE"]).EGY_SCOPE and "627" in first
   and bs.COMP_SLUG.get("CAF Confederation Cup") == "caf-confederation-cup" and "CAF Confederation Cup" in bs.COMP_LOGO)
ck("11d ...has its slug, label, emblem and TV entry",
   bs.COMP_SLUG.get("UEFA Europa League") == "europa-league" and "UEFA Europa League" in bs.COMP_LABEL
   and "UEFA Europa League" in bs.COMP_LOGO and "UEFA Europa League" in bs.COMP_TV)
# 2026-11-02 (user ask): the four North African leagues + the Conference League
_NEW = {"Moroccan Botola Pro": (557, "morocco", "🇲🇦"), "Algerian Ligue 1": (560, "algeria", "🇩🇿"),
        "Tunisian Ligue 1": (554, "tunisia", "🇹🇳"), "Libyan Premier League": (559, "libya", "🇱🇾"),
        "UEFA Conference League": (7685, "conference-league", "🇪🇺")}
from site_lib.names import comp_emoji as _ce
ck("11f the North African leagues + the Conference League: same id in fetch_data, build and the worker; slug, label, emblem, flag",
   all(ids.get(n) == i and bs.S365_COMP_IDS.get(n) == i and str(i) in live.split(",")
       and bs.COMP_SLUG.get(n) == s and n in bs.COMP_LABEL and n in bs.COMP_LOGO
       and _ce(n) == f and _ce(bs.COMP_LABEL[n]) == f for n, (i, s, f) in _NEW.items()),
   {n: (ids.get(n), bs.S365_COMP_IDS.get(n), _ce(n)) for n in _NEW})
_CUPS = {"Egypt Cup": (553, "egypt-cup"), "Egyptian League Cup": (7808, "egypt-capital-cup")}
from site_lib.clubs import EGY_SCOPE as _EGY
ck("11h the Egyptian cups (2026-11-03): same id everywhere, right after the league, inside the Egyptian scope, detail-first, «كأس عاصمة مصر» as the label",
   all(ids.get(n) == i and bs.S365_COMP_IDS.get(n) == i and str(i) in live.split(",") and str(i) in first
       and bs.COMP_SLUG.get(n) == s and n in bs.COMP_LOGO and n in _EGY and _ce(n) == "🇪🇬"
       for n, (i, s) in _CUPS.items())
   and bs.COMP_ORDER[1:3] == ["Egypt Cup", "Egyptian League Cup"]
   and bs.COMP_LABEL["Egyptian League Cup"] == "كأس عاصمة مصر" and bs.COMP_LABEL["Egypt Cup"] == "كأس مصر")
# «اعمل صفحة لكأس مصر مقسمة بالأدوار» (2026-11-03): a knock-out cup's page is
# split by its STAGES - 365scores gives it no round numbers
from site_lib.tables import league_rounds_panel as _lrp
from site_lib.league_desc import fixtures_desc as _fd
_cup = {"current": 2, "rounds": [
    {"round": 1, "label": "تصفيات", "matches": [{"home": "A", "away": "B", "kickoff": "2026-10-24", "status": "FINISHED", "home_score": 1, "away_score": 0}]},
    {"round": 2, "label": "دور الـ 32", "matches": [{"home": "C", "away": "D", "kickoff": "2026-11-04", "status": "UPCOMING"}]}]}
_p = _lrp("Egypt Cup", _cup, embedded=True)
ck("11i the Egypt Cup page is split by stages: named rounds, «دور» in the description",
   553 in fd.STAGE_ROUNDS and 'data-label="تصفيات"' in _p and 'data-label="دور الـ 32"' in _p
   and "(دور الـ 32)" in _fd("كأس مصر", "2026-2027", _cup["rounds"], 2) and "2 دور" in _fd("كأس مصر", "2026-2027", _cup["rounds"], 2)
   and 'data-label="الجولة 3"' in _lrp("X", {"current": 3, "rounds": [{"round": 3, "matches": []}]}, embedded=True))
# 2026-11-11 (user ask): the U-17 World Cup and the Egyptian second division
_N11 = {"Egyptian Second Division": (6994, "egypt-second-division", "🇪🇬", "دوري المحترفين المصري"),
        "FIFA U-17 World Cup": (5582, "u17-world-cup", "🏆", "كأس العالم تحت 17 سنة")}
ck("11j the U-17 World Cup + «دوري المحترفين المصري»: same id in fetch_data, build, the worker and match_brief; slug, label, emblem, icon, scorers",
   all(ids.get(n) == i and bs.S365_COMP_IDS.get(n) == i and str(i) in live.split(",")
       and str(i) in __import__("match_brief").S365_ALL.split(",")
       and (i, n) in fd.S365_SCORER_COMPS
       and bs.COMP_SLUG.get(n) == s and bs.COMP_LABEL.get(n) == l and n in bs.COMP_LOGO
       and _ce(n) == f and _ce(l) == f and n not in _EGY and str(i) not in first
       for n, (i, s, f, l) in _N11.items()),
   {n: (ids.get(n), bs.S365_COMP_IDS.get(n), _ce(n)) for n in _N11})
ck("11k ...the second division after the Arab first divisions (right after Libya) and under «الدوريات العربية»; the national teams (AFCON quals, Nations League, U-17 World Cup) above the Arab leagues",
   bs.COMP_ORDER[1:3] == ["Egypt Cup", "Egyptian League Cup"]
   and bs.COMP_ORDER.index("Egyptian Second Division") == bs.COMP_ORDER.index("Libyan Premier League") + 1
   and bs.COMP_ORDER.index("Egyptian Second Division") > bs.COMP_ORDER.index("Tunisian Ligue 1")
   and max(bs.COMP_ORDER.index(n) for n in ("Africa Cup of Nations Qualification", "UEFA Nations League", "FIFA U-17 World Cup"))
       < min(bs.COMP_ORDER.index(n) for n in ("Moroccan Botola Pro", "Algerian Ligue 1", "Tunisian Ligue 1", "Libyan Premier League"))
   and "egypt-second-division" in __import__("site_pages.leagues", fromlist=["ARAB_SLUGS"]).ARAB_SLUGS
   and not any(n in bs.COMP_TV for n in _N11))
from site_lib.competitions import comp_season as _cs
ck("11l the U-17 World Cup is a one-year tournament: its pages say «2026», a league keeps «2026-2027»",
   _cs("FIFA U-17 World Cup", "2026-2027", [{"matches": [{"kickoff": "2026-11-21"}, {"kickoff": "2026-11-19"}]}]) == "2026"
   and _cs("Egyptian Second Division", "2026-2027", [{"matches": [{"kickoff": "2026-11-19"}]}]) == "2026-2027")
ck("11g ...the Conference League right after the Europa League; no TV channel claimed without a source",
   bs.COMP_ORDER.index("UEFA Conference League") == bs.COMP_ORDER.index("UEFA Europa League") + 1
   and not any(n in bs.COMP_TV for n in _NEW))

# ---- the standings guard: BOTH multi-group shapes are skipped ------------
body = fds.split("def fetch_s365_league", 1)[1]
ck("12 shape 1: one standings entry per group -> skipped",
   "if len(sts) == 1 else []" in body)
ck("13 shape 2: one entry, rows spanning groups (AFCON quals) -> skipped",
   'len({r.get("groupNum") for r in srows}) > 1' in body)

print()
print(f"{len(fails)} FAILED: {', '.join(fails)}" if fails else "ALL S365-COMPS TESTS PASSED")
sys.exit(1 if fails else 0)
