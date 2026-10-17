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

# ---- the standings guard: BOTH multi-group shapes are skipped ------------
body = fds.split("def fetch_s365_league", 1)[1]
ck("12 shape 1: one standings entry per group -> skipped",
   "if len(sts) == 1 else []" in body)
ck("13 shape 2: one entry, rows spanning groups (AFCON quals) -> skipped",
   'len({r.get("groupNum") for r in srows}) > 1' in body)

print()
print(f"{len(fails)} FAILED: {', '.join(fails)}" if fails else "ALL S365-COMPS TESTS PASSED")
sys.exit(1 if fails else 0)
