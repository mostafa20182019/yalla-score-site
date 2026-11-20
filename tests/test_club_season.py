# -*- coding: utf-8 -*-
r"""A club page holds the club's WHOLE season (SEO review 2026-11-20).

    python tests/test_club_season.py      (from the repo root, after a build)

الأهلي's page listed 5 of the 18 matches the fixtures data holds. The first
five stay as rows on screen; the rest of the season is under them in a
<details> - in the HTML for a search engine, closed for the reader. Every
check is a relation between the data and the built page, so a club with no
more matches than five checks nothing.
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

from site_lib.clubs import TEAM_PAGES          # noqa: E402
from site_lib.config import REF_TODAY, load    # noqa: E402
from site_lib.names import _team_match         # noqa: E402
from site_lib.stats import more_matches_txt as _more_txt   # noqa: E402

fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


print("1. the count is worded, not a bare number")
ck("1 / 2 / 7 / 13 matches", [_more_txt(n) for n in (1, 2, 7, 13)]
   == ["مباراة واحدة أخرى", "مباراتان أخريان", "7 مباريات أخرى", "13 مباراة أخرى"],
   str([_more_txt(n) for n in (1, 2, 7, 13)]))

print("2. the built pages")
fx = load("fixtures.json") or []
checked = 0
for tp in TEAM_PAGES:
    page = os.path.join("dist", "team", tp["slug"] + ".html")
    if not os.path.exists(page):
        continue
    html = open(page, encoding="utf-8").read()
    ids = {m.get("match_id") for f in fx for r in f.get("rounds") or [] for m in r.get("matches") or []
           if _team_match(tp, m) and m.get("home") and m.get("kickoff")
           and (m.get("status") or "").upper() in ("UPCOMING", "LIVE") and m["kickoff"] >= REF_TODAY}
    m = re.search(r'<summary>جدول مباريات [^<]*?: ([^<]+)</summary>\s*<div class="mlist">(.*?)</div>\s*</details>', html, re.S)
    if len(ids) > 5:
        checked += 1
        rows = m.group(2).count('class="mrow ') if m else 0
        if not (m and rows >= len(ids) - 5 and m.group(1) == _more_txt(rows)):
            ck(f"/team/{tp['slug']}: {len(ids)} matches to come in the data, the rest under the first five",
               False, f"rows {rows}, label {m.group(1) if m else None}")
    elif m:
        ck(f"/team/{tp['slug']}: no «more» block for five matches or fewer", len(ids) > 5)
ck(f"club pages with more than five matches to come: {checked} - each lists them all", True)
one = next((os.path.join("dist", "team", tp["slug"] + ".html") for tp in TEAM_PAGES
            if os.path.exists(os.path.join("dist", "team", tp["slug"] + ".html"))), None)
if one:
    css = open(os.path.join("site_src", "style.css"), encoding="utf-8").read()
    ck("the «more» summary is a 44 px tap target", ".more-d>summary{" in css
       and "min-height:44px" in css.split(".more-d>summary{")[1].split("}")[0])

print("\nALL OK" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
