r"""articles_sig - the build reads ONE row, not every article table (2026-09-20).

    python tests/test_articles_sig.py   (from the repo root)

The read quota ran out on 2026-09-16, 09-19 and 09-20. After the warehouse
left the pipeline, the next standing spender was the build's article pull:
store.article_all() scans articles + article_sources + article_faq +
article_embeds on every one of ~48-96 runs a day, and D1 bills rows SCANNED.

The fix is the warehouse's own signature pattern: every article write
(article_add / article_update in store.py, POST / PUT in the Worker's admin
API) replaces ONE live_meta row, article_export records that value inside
data/articles.json, and the build compares the two - a match means the
committed export IS the store's current content and no table is read.
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


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_source import build_source  # noqa: E402  build_site.py + site_lib/*.py
bs = build_source()
wk = io.open("worker.js", encoding="utf-8").read()

# ---- the build side ------------------------------------------------------
ck("1 the build asks articles_current(), not article_all() directly",
   "articles_current()" in bs
   and not re.search(r"articles_all = store\.article_all\(\)", bs))
ck("2 the gate compares the export's sig to the store's one-row marker",
   'doc.get("sig") == sig' in bs and "store.articles_sig()" in bs)
ck("3 ARTICLES_FULL=1 is the escape hatch",
   'os.environ.get("ARTICLES_FULL")' in bs)
ck("4 the unreachable-store fallback to the committed export survives",
   "article store unreachable" in bs)

# ---- the Worker side (the admin page writes AROUND store.py) -------------
_post = wk.split('parts[0] === "article") {', 1)[1]
ck("5 the admin POST bumps the sig", _post.count("bumpArticlesSig") >= 1)
_put = wk.split('request.method === "PUT"', 1)[1]
ck("6 the admin PUT bumps the sig (a column-only edit too, not just children)",
   "bumpArticlesSig" in _put)
ck("7 the bump is a fresh value every time, on the table the schema owns",
   "crypto.randomUUID()" in wk and 'bind("articles_sig"' in wk
   and "ensureStore(env)" in wk.split("async function bumpArticlesSig", 1)[1])

# ---- behaviour, on the sqlite backend ------------------------------------
for k in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_D1_ID"):
    os.environ.pop(k, None)
os.environ["D1_SQLITE"] = os.path.join(tempfile.mkdtemp(prefix="sig-"), "sig.db")
import store                                             # noqa: E402

store.init_schema()
ck("8 no write yet -> no sig (callers then pull everything)",
   store.articles_sig() is None)

aid = store.article_add({"title": "t", "summary": "s", "body": "<p>b</p>",
                         "author": "a", "pub_date": "2026-09-20",
                         "words": 1, "thin": 1})
s1 = store.articles_sig()
ck("9 article_add bumps the sig", bool(s1))

exp = os.path.join(tempfile.mkdtemp(prefix="sig-"), "articles.json")
store.article_export(exp)
doc = json.load(io.open(exp, encoding="utf-8"))
ck("10 the export records the sig it was cut at", doc.get("sig") == s1)
ck("11 ...and keeps the shape every reader parses",
   doc["results"][0]["items"][0]["article_id"] == aid)

# the invariant the build's gate rests on: export current <=> sigs equal
ck("12 export sig == store sig -> the export IS current",
   doc.get("sig") == store.articles_sig())
store.article_update(aid, {"title": "t2"})
s2 = store.articles_sig()
ck("13 article_update replaces the sig", bool(s2) and s2 != s1)
ck("14 ...so the stale export no longer matches (the build would full-pull)",
   doc.get("sig") != s2)

# fix-images goes through article_update, so it inherits the bump; a
# children-only update must bump too (it changes what the site renders)
store.article_update(aid, {"sources": [{"name": "n", "url": "https://x", "note": None}]})
ck("15 a children-only update bumps as well", store.articles_sig() != s2)

print()
print(f"{len(fails)} FAILED: {', '.join(fails)}" if fails else "ALL ARTICLES_SIG TESTS PASSED")
sys.exit(1 if fails else 0)
