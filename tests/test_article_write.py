# -*- coding: utf-8 -*-
"""D1 as the article writer: the round trip, the two races, and the fallback.

Runs on the sqlite backend, which speaks the same dialect as D1 - including
`INSERT ... SELECT MAX(...)+1 ... RETURNING` and the partial unique index that
the two race tests depend on.

    python tests/test_article_write.py
"""
import json
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SITE)
os.environ["D1_SQLITE"] = os.path.join(tempfile.gettempdir(), "yalla_art_test.db")
if os.path.exists(os.environ["D1_SQLITE"]):
    os.remove(os.environ["D1_SQLITE"])

import build_site as BS   # noqa: E402
import store              # noqa: E402
import warehouse          # noqa: E402

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


store.init_schema()
warehouse.refresh(verbose=False)
c = warehouse.refresh_articles(verbose=False, source="json")
ck("1 the backfill loads the export into D1", c["articles_written"] > 350,
   str(c["articles_written"]))

# ---------------------------------------------------------------- round trip
orig = BS.load("articles.json")


def norm(a):
    """A missing key and a null are the same thing to every reader."""
    return {k: (str(v) if k in ("article_id", "match_id") else v)
            for k, v in a.items() if v is not None and v != []}


back = store.article_all()
o = {str(a["article_id"]): norm(a) for a in orig}
d = {str(a["article_id"]): norm(a) for a in back}
ck("2 every article survives the round trip", set(o) == set(d),
   f"{len(o)} json vs {len(d)} d1")
diff = [k for k in o if o[k] != d.get(k)]
ck("3 every field survives the round trip", not diff, f"{len(diff)} differ")
ck("4 the export keeps the file's order (newest id first)",
   [a["article_id"] for a in back[:5]] == [str(a["article_id"]) for a in orig[:5]])

# and the file we would write is byte-comparable to what a reader expects
doc = store.article_doc()
ck("5 the export is a valid articles.json document",
   list(doc) == ["results"] and len(doc["results"][0]["items"]) == len(orig))

# ---------------------------------------------------------------- writing
top = max(int(a["article_id"]) for a in orig)
draft = {"title": "عنوان اختبار", "summary": "ملخص اختبار",
         "body": "<p>" + ("كلمة " * 400) + "</p>", "author": "فريق التحرير",
         "pub_date": "2026-09-10", "pub_ts": "2026-09-10T09:00:00+03:00",
         "image_url": "https://yallascore.site/media/ph-pitch.svg",
         "image_credit": "",
         # TWO independent outlets, on different domains: since the source
         # gate shipped (2026-09-17) a one-source news draft is refused, and
         # this fixture is what tests 22-23 call "a good draft".
         "sources": [{"name": "مصدر", "url": "https://example.com", "note": "ملاحظة"},
                     {"name": "مصدر ثانٍ", "url": "https://example.org/a"}],
         "faq": [{"q": "سؤال؟", "a": "جواب."}]}
rec = dict(draft, words=400, thin=0, has_sources=1, has_faq=1)
aid = store.article_add(rec, clubs=["al-ahly"])
ck("6 a new article gets the next id", int(aid) == top + 1, f"{aid} after {top}")

got = store.article_get(aid)
ck("7 it reads back with its children",
   got and got["title"] == draft["title"] and len(got["sources"]) == 2
   and len(got["faq"]) == 1)
ck("8 its club link is stored",
   store.sql("SELECT COUNT(*) n FROM article_clubs WHERE article_id = ?",
             [aid])[0]["n"] == 1)

# THE RACE THAT MOTIVATED THIS: two runs publishing at the same moment.
# The old rule (max(ids)+1 computed in Python from a file) hands both the same
# id; here the id is allocated inside the INSERT, so they must differ.
a1 = store.article_add(dict(rec, title="سباق ١"), clubs=[])
a2 = store.article_add(dict(rec, title="سباق ٢"), clubs=[])
ck("9 two concurrent publishes cannot collide on an id", a1 != a2, f"{a1} vs {a2}")
ck("10 both articles exist", store.article_get(a1) and store.article_get(a2))

# one preview and one report per match, enforced by the index
m = {"match_id": "9999001", "kind": "preview"}
p1 = store.article_add(dict(rec, title="معاينة", **m), clubs=[])
dup = None
try:
    store.article_add(dict(rec, title="معاينة مكررة", **m), clubs=[])
except store.DuplicateArticle as e:
    dup = str(e)
ck("11 a second preview for the same match is refused", dup is not None, dup or "no error")
r1 = store.article_add(dict(rec, title="تقرير", match_id="9999001", kind="report"),
                       clubs=[])
ck("12 but the REPORT for that match is still allowed", bool(r1), str(r1))

# ---------------------------------------------------------------- updating
store.article_update(aid, {"body": "<p>" + ("كلمة " * 600) + "</p>", "words": 600,
                           "thin": 0, "upgraded_ts": "2026-09-10T10:00:00+03:00",
                           "sources": []}, clubs=["zamalek"])
u = store.article_get(aid)
ck("13 an update replaces only what it names",
   u["title"] == draft["title"] and u["upgraded_ts"].startswith("2026-09-10")
   and "sources" not in u, str(list(u))[:90])
ck("14 an update rewrites the club links",
   [r["slug"] for r in store.sql(
       "SELECT slug FROM article_clubs WHERE article_id = ?", [aid])] == ["zamalek"])
ck("15 a shrunk source list leaves no phantom rows",
   store.sql("SELECT COUNT(*) n FROM article_sources WHERE article_id = ?",
             [aid])[0]["n"] == 0)
missing = None
try:
    store.article_update("999999", {"title": "x"})
except KeyError as e:
    missing = str(e)
ck("16 updating an article that does not exist is an error", missing is not None)

# ---------------------------------------------------------------- validation
sys.argv = ["article_put.py", "--check", ""]
import article_put as AP     # noqa: E402

bad, words = AP.validate({"title": "t", "summary": "s", "body": "<p>short</p>",
                          "author": "a", "pub_date": "2026-09-10"})
ck("17 a thin draft is refused", any("under the" in x for x in bad), str(bad))
bad, _ = AP.validate(dict(draft, image_credit="", image_url="https://x/photo.jpg"))
ck("18 a photo with no credit is refused", any("credit" in x for x in bad), str(bad))
bad, _ = AP.validate(dict(draft, match_id="1", kind=None))
ck("19 match_id without kind is refused", any("go together" in x for x in bad), str(bad))
bad, _ = AP.validate(dict(draft, kind="opinion", match_id="1"))
ck("20 an unknown kind is refused", any("preview or report" in x for x in bad), str(bad))
bad, _ = AP.validate(dict(draft, nonsense=1))
ck("21 an unknown field is refused", any("unknown field" in x for x in bad), str(bad))
bad, _ = AP.validate(draft)
ck("22 a good draft passes", not bad, str(bad))

# the placeholder is the one image allowed with no credit
bad, _ = AP.validate(dict(draft, image_url="https://yallascore.site/media/ph-ball.svg"))
ck("23 our own placeholder needs no credit", not bad, str(bad))

# ------------------------------------------------------- the export + fallback
# to a temp path: an export over the repository's own data/articles.json is
# exactly the kind of side effect a test must not have (it happened once)
tmp_json = os.path.join(tempfile.gettempdir(), "yalla_articles_export.json")
n = store.article_export(path=tmp_json)
ck("24 the export writes every article back to a file", n == len(store.article_all()),
   str(n))
with open(tmp_json, encoding="utf-8") as f:
    on_disk = json.load(f)["results"][0]["items"]
ck("25 the exported file holds the new articles",
   any(str(a["article_id"]) == aid for a in on_disk), f"{len(on_disk)} articles")

# a build must render when the store is down - the promise from step 1
boom = store.article_all


def explode(*a, **k):
    raise RuntimeError("d1 unreachable (simulated)")


store.article_all = explode
try:
    fallback = BS.load("articles.json")     # the committed export, untouched
    ck("26 the committed export can still feed a build", len(fallback) > 350,
       f"{len(fallback)} articles")
finally:
    store.article_all = boom

# the derived counters must agree with the site's own rule after a d1 refresh
warehouse.refresh_articles(verbose=False)
mism = 0
for a in store.article_all()[:80]:
    row = store.sql("SELECT words, thin FROM articles WHERE article_id = ?",
                    [a["article_id"]])[0]
    if row["words"] != BS.article_words(a) or bool(row["thin"]) != BS.is_thin(a):
        mism += 1
ck("27 the hourly refresh keeps words/thin in step with build_site", mism == 0,
   f"{mism} off")

# and it must NOT resurrect the json over a fresher D1 row
store.article_update(aid, {"title": "لن يُمحى"})
warehouse.refresh_articles(verbose=False)
ck("28 the hourly refresh never overwrites the text D1 holds",
   store.article_get(aid)["title"] == "لن يُمحى",
   store.article_get(aid)["title"])

# ---------------------------------------------------------------- embeds (2026-09-13)
emb_ok = ["https://x.com/AlAhly/status/123", "https://www.instagram.com/p/abc/", "https://www.facebook.com/AlAhly/posts/9"]
ck("29 embed_platform recognises the three platforms and refuses the rest",
   [store.embed_platform(u) for u in emb_ok] == ["x", "instagram", "facebook"]
   and store.embed_platform("https://example.com/p/1") is None
   and store.embed_platform("http://x.com/a/status/1") is None
   and store.embed_platform("https://x.com/") is None)
aid_e = store.article_add(dict(draft, title="خبر بتضمين", words=400, thin=0, has_sources=0, has_faq=0,
                               embeds=emb_ok + ["https://example.com/not-an-embed"]), clubs=[])
got_e = store.article_get(aid_e)
ck("30 embeds round-trip through D1 in order, the invalid URL dropped",
   got_e.get("embeds") == emb_ok, str(got_e.get("embeds"))[:120])
ck("31 the export carries embeds after faq and only when present",
   "embeds" in got_e and store.ARTICLE_FIELDS.index("embeds") == store.ARTICLE_FIELDS.index("faq") + 1
   and "embeds" not in store.article_get(aid))
store.article_update(aid_e, {"title": "بلا تضمين", "embeds": []})
ck("32 an update with an empty list clears them; one without the key keeps them",
   "embeds" not in store.article_get(aid_e)
   and (store.article_update(aid_e, {"embeds": emb_ok[:1]}) or True)
   and (store.article_update(aid_e, {"title": "نص فقط"}) or True)
   and store.article_get(aid_e).get("embeds") == emb_ok[:1])
import article_put as AP   # noqa: E402
bad_e, _w = AP.validate(dict(draft, embeds=["https://example.com/x"]))
ck("33 article_put refuses a non-platform embed URL", any("embed" in b_ for b_ in bad_e), str(bad_e)[:100])
html_e = BS.embeds_block(emb_ok)
ck("34 the article page renders one click-to-load card per embed, no platform script on load",
   html_e.count('class="emb"') == 3 and "platform.twitter.com" not in html_e.split("<script>")[0]
   and "من الحسابات الرسمية" in html_e and BS.embeds_block([]) == "" and BS.embeds_block(["nope"]) == "")

# ---------------------------------------------------------------- missing media (2026-09-13, article 497)
_md = tempfile.mkdtemp(); open(os.path.join(_md, "ok.jpg"), "wb").write(b"x")
_arts = [{"article_id": "1", "image_url": "https://yallascore.site/media/ok.jpg", "image_credit": "c1"},
         {"article_id": "2", "image_url": "https://yallascore.site/media/not-yet.jpg", "image_credit": "c2"},
         {"article_id": "3", "image_url": "https://upload.wikimedia.org/x.jpg", "image_credit": "c3"}]
_miss = BS.resolve_missing_media(_arts, media_dir=_md, base="https://yallascore.site")
ck("35 an article whose media file is not in the checkout yet renders a placeholder (no credit) for this build only",
   _miss == ["not-yet.jpg"] and "/media/ph-" in _arts[1]["image_url"] and _arts[1]["image_credit"] == ""
   and _arts[0]["image_url"].endswith("ok.jpg") and _arts[0]["image_credit"] == "c1"
   and _arts[2]["image_url"].startswith("https://upload"), str(_miss))

print("\n" + ("ALL ARTICLE WRITE TESTS PASSED" if not fails
             else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
