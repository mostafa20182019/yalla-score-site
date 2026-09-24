# -*- coding: utf-8 -*-
"""A partial article update must touch only what it carries.

Run from the site root:  python tests/test_partial_update.py

The sources-only pass (2026-09-17) sends a draft with `sources` and nothing
else. Before this was fixed, that draft would have:

  * deleted the article's FAQ  — `faq or []` treated "absent" as "empty";
  * deleted its club links     — clubs_of() on a bodyless draft returns [];
  * set words = 0, thin = 1    — true of the draft, false of the article.

Three silent losses, none of which would have shown up until a reader noticed
the FAQ had vanished. These tests hold the line by recording the SQL a partial
update issues, with no database involved.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import store
import article_put as AP

fails = []
def ok(n, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + n + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(n)

SEEN = []
def fake_sql(q, params=None):
    SEEN.append((" ".join(q.split()), params or []))
    if q.lstrip().upper().startswith("SELECT ARTICLE_ID"):
        return [{"article_id": "460"}]          # the article exists
    return []

store.sql = fake_sql
store.backend = lambda: "d1"

def run(rec, clubs=None):
    SEEN.clear()
    store.article_update("460", rec, clubs=clubs)
    return SEEN

def touched(table):
    return [q for q, _ in SEEN if table in q]

print("== a sources-only update ==")
run({"sources": [{"name": "في الجول", "url": "https://filgoal.com/x"}]})
ok("1 writes the sources", any("INSERT INTO article_sources" in q for q in touched("article_sources")))
ok("2 leaves the FAQ alone", not touched("article_faq"), touched("article_faq"))
ok("3 leaves the club links alone", not touched("article_clubs"), touched("article_clubs"))
ok("4 and touches no column on the article row",
   not any(q.startswith("UPDATE articles") for q, _ in SEEN),
   [q for q, _ in SEEN if q.startswith("UPDATE")])

print()
print("== an explicit empty list still means empty ==")
run({"faq": []})
ok("5 an empty faq clears the FAQ (not the same as absent)",
   any("DELETE FROM article_faq" in q for q in touched("article_faq")))

print()
print("== the full upgrade path is unchanged ==")
run({"body": "<p>x</p>", "sources": [{"name": "س"}], "faq": [{"q": "a", "a": "b"}]},
    clubs=["al-ahly"])
ok("6 it writes the body", any(q.startswith("UPDATE articles") for q, _ in SEEN))
ok("7 the sources, the FAQ", touched("article_sources") and touched("article_faq"))
ok("8 and replaces the club links", any("DELETE FROM article_clubs" in q
                                        for q in touched("article_clubs")))

print()
print("== the counters ==")
e = AP.enrich({"sources": [{"name": "س"}]}, 0)
ok("9 a bodyless draft carries no word count", "words" not in e and "thin" not in e, e)
ok("10 but does record that it now has sources", e.get("has_sources") == 1)
e2 = AP.enrich({"body": "<p>" + ("w " * 600) + "</p>"}, 600)
ok("11 a real rewrite still carries both", e2.get("words") == 600 and e2.get("thin") == 0)

print()
print("FAILED: " + ", ".join(fails) if fails else "ALL PARTIAL-UPDATE TESTS PASSED")
sys.exit(1 if fails else 0)
