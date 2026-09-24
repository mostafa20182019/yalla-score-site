# -*- coding: utf-8 -*-
"""Who the upgrade queue picks, and in what order — upgrade_pick.candidates.

Run from the site root:  python tests/test_upgrade_pick.py

Two rules, both paid for:

  * ORDER (2026-09-16): the articles the site still SHOWS come first. 246 of
    the 276 "thin" articles are already noindexed and out of every listing, so
    a newest-first queue spent the whole daily budget on pages nobody sees.
  * ELIGIBILITY (2026-09-17): an article can be long enough to pass the word
    test and still carry NO sources. Thirteen of the sourceless September
    articles were 450-560 words, so the queue was never going to reach them
    while /editorial went on promising the reader something those pages did
    not have.
"""
import os, sys, datetime
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import upgrade_pick as U

fails = []
def ok(n, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + n + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(n)

TODAY = datetime.date(2026, 9, 17)
OLD = "2026-09-01"
SRC = [{"name": "في الجول", "url": "https://filgoal.com/x"}]


def art(aid, w, pub=OLD, **kw):
    a = {"article_id": aid, "title": f"t{aid}", "pub_date": pub,
         "body": "<p>" + ("كلمة " * w) + "</p>"}
    a.update(kw)
    return a


ids = lambda rows: [r["article_id"] for r in rows]

print("== who qualifies ==")
ok("1 a thin article with sources still qualifies",
   ids(U.candidates([art("1", 200, sources=SRC)], TODAY)) == ["1"])
ok("2 a long article WITH sources does not",
   U.candidates([art("2", 600, sources=SRC)], TODAY) == [])
ok("3 a long article with NO sources does (the 2026-09-17 rule)",
   ids(U.candidates([art("3", 600)], TODAY)) == ["3"])
ok("4 an empty sources list counts as none",
   ids(U.candidates([art("4", 600, sources=[])], TODAY)) == ["4"])
ok("5 a nameless source entry counts as none (the renderer drops it)",
   ids(U.candidates([art("5", 600, sources=[{"url": "https://x"}])], TODAY)) == ["5"])

print()
print("== who never qualifies ==")
ok("6 a match preview/report is out (built to 650-900 by construction)",
   U.candidates([art("6", 200, kind="preview", match_id="9")], TODAY) == [])
ok("7 an article already upgraded is out",
   U.candidates([art("7", 200, upgraded_ts="2026-09-16T10:00:00+03:00")], TODAY) == [])
ok("8 today's article is out — it was written to the current standard",
   U.candidates([art("8", 200, pub="2026-09-17")], TODAY) == [])

print()
print("== the order ==")
rows = U.candidates([art("9", 120), art("10", 350), art("11", 90), art("12", 500)], TODAY)
listed = [r for r in rows if r["listed"]]
ok("9 everything still listed comes before anything unlisted",
   ids(rows)[:len(listed)] == ids(listed) and len(listed) == 2, ids(rows))
ok("10 and the reason is carried with each row",
   {r["article_id"]: r["why"] for r in rows}["12"] == "no sources",
   [(r["article_id"], r["why"]) for r in rows])
ok("11 newest-first survives inside each group",
   ids(U.candidates([art("13", 120, pub="2026-09-01"),
                     art("14", 120, pub="2026-09-02")], TODAY)) == ["13", "14"])

print()
print("== the sources-only queue ==")
# --sources-only narrows the SAME queue to the one thing /editorial promises
# out loud, so a run can clear many more articles than a rewrite run does.
rows = U.candidates([art("15", 120), art("16", 600), art("17", 520, sources=SRC)], TODAY)
only = [r for r in rows if r["why"] == "no sources"]
ok("12 it keeps the long unsourced ones", ids(only) == ["16"], ids(only))
ok("13 and drops the thin-but-sourced ones from that view",
   all(r["article_id"] != "15" for r in only))

print()
print("FAILED: " + ", ".join(fails) if fails else "ALL UPGRADE-PICK TESTS PASSED")
sys.exit(1 if fails else 0)
