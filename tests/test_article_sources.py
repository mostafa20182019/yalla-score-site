# -*- coding: utf-8 -*-
"""The data credit on a match preview/report — build_site.match_data_sources.

Run from the site root:  python tests/test_article_sources.py

Why this exists: the match-article prompt asks the writer for `sources`, and 6
published pieces shipped without any. An article with no source line, under an
editorial policy that promises one, is the contradiction a reviewer reads as a
broken promise (found by an outside audit of the live site, 2026-09-16). The
renderer now guarantees the line — these tests pin WHAT it guarantees, because
a credit that names the wrong provider is worse than none.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import build_site as B

fails = []
def ok(n, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + f"{n}" + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(n)

print("== match_data_sources ==")

egy = B.match_data_sources({"match_id": "4804667"}, "Egyptian Premier League")
ok("1 an Egyptian match credits 365scores only", [s["name"] for s in egy] == ["بيانات المباريات — 365scores"], egy)
ok("2 and links the credit to that match's page",
   egy[0]["url"] == f"{B.SITE_BASE}/m/4804667.html", egy[0].get("url"))

eur = B.match_data_sources({"match_id": "575333"}, "Premier League")
ok("3 a European match credits football-data too",
   [s["name"] for s in eur] == ["بيانات المباريات — 365scores", "football-data.org"], eur)

for comp in B.S365_COMPETITIONS:
    ok(f"4 {comp} never names football-data",
       all("football-data" not in s["name"] for s in B.match_data_sources({"match_id": "1"}, comp)))

ok("5 an unknown competition stays with what we can prove",
   [s["name"] for s in B.match_data_sources({"match_id": "1"}, "")] == ["بيانات المباريات — 365scores"])

no_id = B.match_data_sources({}, "Premier League")
ok("6 a piece with no match_id still credits, without a dead link",
   all("url" not in s for s in no_id) and len(no_id) == 2, no_id)

print()
print("FAILED: " + ", ".join(fails) if fails else "ALL ARTICLE-SOURCE TESTS PASSED")
sys.exit(1 if fails else 0)
