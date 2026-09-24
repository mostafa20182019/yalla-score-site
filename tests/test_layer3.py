# -*- coding: utf-8 -*-
"""Layer 3 — a match preview/report lives INSIDE its match page.

Run from the site root:  python tests/test_layer3.py

Before 2026-09-16 one match produced two weak pages: prose with no numbers at
/a/<id>, numbers with no prose at /m/<match_id>, both chasing the same query.
They are one page now. What these tests pin is the part that is easy to break
silently: WHERE a link points (43 of the 44 moved pieces have a published
Facebook post on the old url), WHICH piece a match page shows, and the fact
that the embedded article does not emit a second FAQPage next to the match
page's own.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import build_site as B

fails = []
def ok(n, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + n + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(n)

news = {"article_id": 460, "title": "خبر"}
prev = {"article_id": 397, "title": "معاينة", "kind": "preview", "match_id": "4764281",
        "pub_ts": "2026-09-06T10:00:00+03:00", "body": "<p>نص</p>"}
rept = {"article_id": 398, "title": "تقرير", "kind": "report", "match_id": "4764281",
        "pub_ts": "2026-09-06T23:00:00+03:00", "body": "<p>نص</p>"}
orphan = {"article_id": 399, "title": "معاينة بلا مباراة", "kind": "preview"}

print("== where an article lives ==")
ok("1 a news article keeps its own page", B.article_href(news) == "/a/460.html")
ok("2 a preview points at its match page", B.article_href(prev) == "/m/4764281.html")
ok("3 a report points at the same match page", B.article_href(rept) == "/m/4764281.html")
ok("4 a match piece with no match_id cannot move", B.article_href(orphan) == "/a/399.html")
ok("5 the absolute form agrees with the relative one",
   B.article_url(prev) == B.SITE_BASE + "/m/4764281.html")
ok("6 is_match_piece needs BOTH the kind and the id",
   B.is_match_piece(prev) and not B.is_match_piece(orphan) and not B.is_match_piece(news))

print()
print("== which piece the match page shows ==")
ok("7 a finished match shows the report",
   B.pick_match_article([prev, rept], "FINISHED")["article_id"] == 398)
ok("8 an upcoming match shows the preview",
   B.pick_match_article([prev, rept], "UPCOMING")["article_id"] == 397)
ok("9 a finished match with only a preview still shows it",
   B.pick_match_article([prev], "FINISHED")["article_id"] == 397)
ok("10 no pieces, no block", B.pick_match_article([], "FINISHED") is None)

print()
print("== the embedded article ==")
blk = B.match_article_block(rept, "Egyptian Premier League")
ok("11 it carries the headline and the named byline",
   "تقرير" in blk and B.EDITOR_NAME in blk)
ok("12 it credits its data even when the writer left sources empty",
   "365scores" in blk and "المصادر" in blk)
ok("13 an Egyptian match is not credited to football-data",
   "football-data" not in blk)
ok("14 it declares itself a NewsArticle", '"@type": "NewsArticle"' in blk)
ok("15 and does NOT emit a second FAQPage beside the match page's own",
   "FAQPage" not in B.match_article_block(
       dict(rept, faq=[{"q": "س", "a": "ج"}]), "Egyptian Premier League"))
ok("16 the FAQ is still VISIBLE to a reader",
   "<details>" in B.match_article_block(
       dict(rept, faq=[{"q": "س", "a": "ج"}]), "Egyptian Premier League"))
ok("17 mainEntityOfPage is the match page, not the old url",
   "/m/4764281" in blk and '"mainEntityOfPage": "' + B.SITE_BASE + '/a/' not in blk)

print()
print("== what stays at the old url ==")
stub = B.article_moved_stub(prev)
ok("18 the stub is noindexed", 'content="noindex,follow"' in stub)
ok("19 it points canonical at the match page",
   f'rel="canonical" href="{B.SITE_BASE}/m/4764281.html"' in stub)
ok("20 a human lands there even if the 301 never fires",
   'http-equiv="refresh"' in stub and 'href="/m/4764281.html"' in stub)

print()
print("FAILED: " + ", ".join(fails) if fails else "ALL LAYER-3 TESTS PASSED")
sys.exit(1 if fails else 0)
