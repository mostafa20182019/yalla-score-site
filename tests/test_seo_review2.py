# -*- coding: utf-8 -*-
r"""The rest of the SEO review of 2026-11-19: «أرقام الدوري» (/numbers/<slug>),
the CAF group tables with «في أي مجموعة X؟», ten more head-to-head pairs.

    python tests/test_seo_review2.py      (from the repo root)

Most of it guards the numbers page, the one that prints NEW numbers: a card
only for a player who was on the pitch, a match only when its goal list adds
up to its score, no page from too few matches or too thin a share of them.
"""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

from site_lib import league_numbers as L                 # noqa: E402
from site_lib.matchdata import match_details_index       # noqa: E402

fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


def xi(prefix):
    return [{"name": f"{prefix}{i}", "num": i, "pos": "الوسط"} for i in range(1, 12)]


def mk(i, hs=1, as_=0, goals=None, cards=(), with_details=True):
    # six pairs of sides, each match on its own day: the details are found by names + day
    import datetime as _dt
    d = (_dt.date(2026, 8, 1) + _dt.timedelta(days=i)).isoformat()
    home, away = f"فريق {i % 6} أ", f"فريق {i % 6} ب"
    m = {"match_id": i, "home": home, "away": away, "kickoff": d, "status": "FINISHED",
         "home_score": hs, "away_score": as_, "competition": "X"}
    if goals is None:
        goals = [{"side": "h", "player": "h9", "minute": "30", "tag": ""}] * hs + \
                [{"side": "a", "player": "a9", "minute": "80", "tag": ""}] * as_
    e = {"match_id": i, "home": home, "away": away, "date": d, "flipped": False,
         "lineups": {"h": {"xi": xi("h")}, "a": {"xi": xi("a")}}, "goals": goals, "cards": list(cards), "subs": []}
    return m, (e if with_details else None)


def run(pairs):
    return L.league_numbers([m for m, _ in pairs], match_details_index([e for _, e in pairs if e]))


base = [mk(i) for i in range(24)]
r = run(base)
ck("1 a league with enough matches: every match counted, every goal counted", r and r["n"] == 24 and r["of"] == 24 and r["goals"] == 24)

c = [mk(i, cards=[{"side": "h", "player": "h4", "minute": "20", "color": "y"},
                  {"side": "h", "player": "المدرب", "minute": "50", "color": "y"},
                  {"side": "a", "player": "a2", "minute": "70", "color": "r"},
                  {"side": "a", "player": "", "minute": "71", "color": "y"}]) for i in range(24)]
r = run(c)
ck("2 a card counts for a player who was on the pitch - not a coach, not an unnamed card",
   r["yellow"] == 24 and r["red"] == 24 and not any(p == "المدرب" for p, _, _ in r["booked"]))
ck("3 the most booked list is per player AND team, highest first",
   r["booked"][0][0] == "h4" and r["booked"][0][2] >= r["booked"][-1][2] and sum(n for _, _, n in r["booked"]) == 24)
ck("4 a red card names the player, his team, the opponent and the minute",
   all(len(s) == 4 and s[0] == "a2" and s[2] == "70" for s in r["sent_off"]) and len(r["sent_off"]) == L.TOP)
ck("5 the clubs' table adds up to the cards counted", sum(y for _, y, _ in r["teams"]) == 24 and sum(x for _, _, x in r["teams"]) == 24)

late = [mk(i, 1, 1) for i in range(24)]            # the away goal is at 80'
r = run(late)
ck("6 «آخر ربع ساعة»: a goal from the 76th minute on, credited to the side it counted for",
   r["late"] == 24 and r["goals"] == 48 and sum(n for _, n in r["late_teams"]) == 24)
ck("7 «90+3» is the 90th minute, a missing minute is not a late goal", L._minute("90+3") == 90 and L._minute(None) is None and L._minute("x") is None)

bad = [mk(i) for i in range(23)] + [mk(99, 2, 0, goals=[{"side": "h", "player": "h9", "minute": "10", "tag": ""}])]
r = run(bad)
ck("8 a match whose goal list does not add up to its score is left out", r and r["n"] == 23 and r["of"] == 24 and r["goals"] == 23)
ck(f"9 fewer than {L.MIN_MATCHES} finished matches: no page", run([mk(i) for i in range(19)]) is None)
thin = [mk(i) for i in range(20)] + [mk(100 + i, with_details=False) for i in range(10)]
ck(f"10 details for under {int(L.MIN_COVER * 100)}% of the finished matches: no page (half a season's «most booked» is wrong)",
   run(thin) is None)
ck("11 no details index at all: no page", L.league_numbers([m for m, _ in base], None) is None)
up = base + [({"match_id": 500, "home": "a", "away": "b", "kickoff": "2026-12-01", "status": "UPCOMING",
               "home_score": None, "away_score": None}, None)]
ck("12 a match not played yet is not part of «N of M»", run(up)["of"] == 24)
ck("13 the same match listed twice is counted once", run(base + base)["n"] == 24)

tpl = io.open("site_src/templates/numbers.html", encoding="utf-8").read()
ck("14 the page says from how many matches, and that a card is a player's", "من أصل {{ of_txt }}" in tpl and "شارك في المباراة فقط" in tpl)
ck("15 no «suspended», no assists on it", not re.search("موقوف|صناعة|أسيست", tpl))
bs = io.open("build_site.py", encoding="utf-8").read()
ck("16 the hub pages learn which leagues have the page BEFORE any page is written",
   bs.index("_LN.READY = {") < bs.index("_comps_with_table, season = league_pages(") < bs.index("numbers_pages(_bycomp, md_idx"))

# ------------------------------------------------------------- CAF groups + h2h pairs
import fetch_data as F                                   # noqa: E402
ck("17 the two CAF competitions take their group tables from the feed", {624, 627} <= F.GROUP_TABLES and {588, 7016} <= F.GROUP_TABLES)
lg = io.open("site_pages/leagues.py", encoding="utf-8").read()
ck("18 «في أي مجموعة X؟» is asked only for a club in exactly one row of a real group, and answered with the other sides",
   'f"في أي مجموعة {_tp[\'name\']} في {label}؟"' in lg and "if len(_mine) == 1 and len(_names) >= 3:" in lg)
from site_lib import h2h as H                            # noqa: E402
slugs = [p["slug"] for p in H.PAIRS]
ck("19 fourteen pairs, unique slugs, the four original ones first and unchanged",
   len(slugs) == 14 == len(set(slugs)) and slugs[:4] == ["al-ahly-zamalek", "al-ahly-pyramids", "zamalek-pyramids", "trabzonspor-fenerbahce"])
ck("20 no pair is named with the bare «الأهلي» outside Egypt (the name is the page's title)",
   not any("الأهلي" in (p["a"], p["b"]) and p["league"] != "Egyptian Premier League" for p in H.PAIRS))
hist = json.load(io.open("data/h2h_history.json", encoding="utf-8")).get("pairs") or {}
short = [p["slug"] for p in H.PAIRS if len((hist.get(H.pair_key(p["a"], p["b"])) or {}).get("games") or []) < 4]
ck("21 every pair has at least four saved meetings (fewer = no page, and a link to nothing)", not short, str(short))
from site_lib.clubs import TEAM_PAGES                    # noqa: E402
known = {tp["slug"] for tp in TEAM_PAGES}
ck("22 a pair's club slug is a real club page or None",
   all(s is None or s in known for p in H.PAIRS for s in (p["a_slug"], p["b_slug"])))

dist = os.path.join(os.getcwd(), "dist")
if os.path.isdir(os.path.join(dist, "numbers")):
    def rd(*p):
        return io.open(os.path.join(dist, *p), encoding="utf-8").read()
    sm = rd("sitemap.xml")
    pages = sorted(os.listdir(os.path.join(dist, "numbers")))
    bad = []
    for f in pages:
        h = rd("numbers", f)
        slug = f[:-5]
        mm = re.search(r"<b>(\d+) [^<]*</b> من أصل (\d+)", h)
        if not (h.count("<h1") == 1 and f"/numbers/{slug}<" in sm and mm and int(mm.group(1)) <= int(mm.group(2))
                and int(mm.group(1)) >= L.MIN_MATCHES and "FAQPage" in h):
            bad.append(slug)
    ck(f"23 built numbers pages ({len(pages)}): one H1, in the sitemap, «N of M» with N within the rule, a computed FAQ", pages and not bad, str(bad))
    linked = [f for f in pages if f'href="/numbers/{f[:-5]}"' in (rd("standings", f) if os.path.exists(os.path.join(dist, "standings", f)) else rd("fixtures", f))]
    ck("24 each one is linked from its league's hub page", len(linked) == len(pages), f"{len(linked)}/{len(pages)}")
    h2 = sorted(os.listdir(os.path.join(dist, "h2h")))
    ck(f"25 every pair has its built page ({len(h2)})", {s + ".html" for s in slugs} == set(h2), str(sorted(set(s + '.html' for s in slugs) ^ set(h2))))

print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
