r"""The Shenawy triple-publish (2026-09-21): the delete tool and the cause fix.

    python tests/test_article_delete.py   (from the repo root)

On 2026-09-20 the same news draft published THREE times (articles 565, 566,
571 - identical body, one pub_ts). Cause: article_add inserted the ROW, the
read quota then killed the children writes, the generic "D1 refusing" handler
re-parked the draft, and every retry inserted again.

Two things came out of it, both asserted here:
- store.article_delete + the d1-admin `delete-article` task (there was no way
  to remove an article at all - admin-page delete is disabled by choice);
- store.PartialPublish: once the row exists, the failure carries the id out,
  the draft is re-parked WITH `published_id`, and the retry UPDATES in place.
"""
import io
import json
import os
import re
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


for k in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_D1_ID"):
    os.environ.pop(k, None)
os.environ["D1_SQLITE"] = os.path.join(tempfile.mkdtemp(prefix="del-"), "del.db")
import store                                             # noqa: E402

store.init_schema()
REC = {"title": "t", "summary": "s", "body": "<p>b</p>", "author": "a",
       "pub_date": "2026-09-21", "words": 1, "thin": 1,
       "sources": [{"name": "n", "url": "https://x", "note": None}]}

# ---- article_delete -------------------------------------------------------
aid = store.article_add(dict(REC))
s1 = store.articles_sig()
title = store.article_delete(aid)
ck("1 delete returns the title of what it removed", title == "t")
ck("2 the article is gone", store.article_get(aid) is None)
ck("3 ...children too",
   not store.sql("SELECT 1 FROM article_sources WHERE article_id = ?", [aid]))
ck("4 delete bumps articles_sig (or the build keeps serving the old export)",
   store.articles_sig() != s1)
try:
    store.article_delete("999999")
    ck("5 deleting an unknown id raises", False)
except KeyError:
    ck("5 deleting an unknown id raises", True)

# ---- PartialPublish: the row lands, the failure carries the id out --------
_real_children = store._article_children


def _dying_children(*a, **kw):
    raise RuntimeError("read limit")


store._article_children = _dying_children
try:
    store.article_add(dict(REC))
    ck("6 children failure raises PartialPublish", False)
    pp_aid = None
except store.PartialPublish as e:
    pp_aid = e.aid
    ck("6 children failure raises PartialPublish", True)
finally:
    store._article_children = _real_children
ck("7 ...carrying the id of the row that DID land",
   pp_aid is not None and store.sql(
       "SELECT 1 FROM articles WHERE article_id = ?", [pp_aid]) != [])
# the retry heals in place: same draft, as an update
store.article_update(pp_aid, dict(REC))
got = store.article_get(pp_aid)
ck("8 retrying as an update completes the children",
   len(got.get("sources") or []) == 1)

# ---- retry_pending publishes a published_id draft as an UPDATE ------------
import article_put                                       # noqa: E402

pend = tempfile.mkdtemp(prefix="pend-")
article_put.PENDING_DIR = pend
draft = dict(REC, published_id=pp_aid)
p = os.path.join(pend, "2026-09-21-abcd1234.json")
json.dump(draft, io.open(p, "w", encoding="utf-8"), ensure_ascii=False)

calls = {"add": 0, "update": 0}
_add, _upd, _exp = store.article_add, store.article_update, store.article_export
store.article_add = lambda *a, **k: calls.__setitem__("add", calls["add"] + 1) or "X"
store.article_update = lambda aid, *a, **k: calls.__setitem__("update", calls["update"] + 1) or aid
store.article_export = lambda *a, **k: 0
_val = article_put.validate
article_put.validate = lambda rec, updating=False: ([], 500)
try:
    rc = article_put.retry_pending()
finally:
    store.article_add, store.article_update, store.article_export = _add, _upd, _exp
    article_put.validate = _val
ck("9 a published_id draft is finished as an update, never re-inserted",
   rc == 0 and calls == {"add": 0, "update": 1}, str(calls))
ck("10 ...and the parked file is gone", not os.path.exists(p))

# ---- wiring ---------------------------------------------------------------
ap = io.open("article_put.py", encoding="utf-8").read()
ck("11 BOTH publish paths park a PartialPublish with its id",
   ap.count('rec["published_id"] = e.aid') == 2)
adm = io.open("d1_admin.py", encoding="utf-8").read()
ck("12 d1_admin has the delete task and re-cuts the export in the same run",
   "--delete-article" in adm
   and "article_export" in adm.split('"--delete-article" in args')[1]
                             .split('if "--export"')[0])
wf = io.open(".github/workflows/d1-admin.yml", encoding="utf-8").read()
ck("13 the workflow offers it, passes $ARGS, and commits the new export",
   '"delete-article"' in wf and "$ARGS" in wf
   and re.search(r"if: env\.TASK == 'export' \|\| env\.TASK == 'delete-article'", wf))

print()
print(f"{len(fails)} FAILED: {', '.join(fails)}" if fails else "ALL ARTICLE-DELETE TESTS PASSED")
sys.exit(1 if fails else 0)
