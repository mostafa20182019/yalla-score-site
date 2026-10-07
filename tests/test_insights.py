r"""«التحليلات» (/insights) + the analysis article kind (2026-10-07).

    python tests/test_insights.py   (from the repo root)

User ask: rename /analysis to «التوقعات» and add a page «التحليلات» for match
analyses - written by the editor (admin page, kind="analysis") and by the AI
(previews with our prediction, post-match reports, «الجولة بالأرقام»).
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


import article_put as AP                                   # noqa: E402
from site_lib.articles import insight_kind                 # noqa: E402

ck("editor analysis", insight_kind({"kind": "analysis"}) == "analysis")
ck("AI preview / report of a match", insight_kind({"kind": "preview", "match_id": 1}) == "preview"
   and insight_kind({"kind": "report", "match_id": 1}) == "report")
ck("a round article (its data source note)", insight_kind({"sources": [{"note": "round:egypt:5"}]}) == "round")
ck("plain news is not an analysis", insight_kind({"kind": None, "sources": [{"name": "x", "note": "official"}]}) is None)

base = {"title": "t", "summary": "s", "body": "<p>" + "كلمة " * 320 + "</p>", "author": "a", "pub_date": "2026-10-07",
        "sources": [{"name": "A", "url": "https://a.com/1"}, {"name": "B", "url": "https://b.com/2"}]}
ok, _ = AP.validate(dict(base, kind="analysis"))
ck("article_put: kind=analysis without a match is valid", ok == [], ok)
bad, _ = AP.validate(dict(base, kind="preview"))
ck("article_put: a preview without its match is refused", any("match_id" in x for x in bad), bad)
bad2, _ = AP.validate(dict(base, kind="opinion"))
ck("article_put: an unknown kind is refused", any("kind must be" in x for x in bad2), bad2)

w = io.open("worker.js", encoding="utf-8").read()
ck("worker: the admin API accepts kind=analysis and checks the pairing", "function badKind(rec)" in w
   and '["preview", "report", "analysis"]' in w)
ck("worker: an edit can only set analysis (or empty)", 'only kind=analysis (or empty) can be set here' in w)
adm = io.open("admin-articles.html", encoding="utf-8").read()
ck("admin form: «نوع المقال» selector with «تحليل»", 'id="fkind"' in adm and 'value="analysis"' in adm)
ck("admin form: a match preview/report hides it (kind untouched)", 'a.kind==="preview"||a.kind==="report"' in adm)
b = io.open("build_site.py", encoding="utf-8").read()
ck("build() writes the page", "insights_page(articles, urls)" in b)
sh = io.open("site_lib/shell.py", encoding="utf-8").read()
ck("nav: «التوقعات» -> /analysis, «التحليلات» -> /insights",
   '📈</span> التوقعات' in sh and 'href="/insights.html" class="navtab{ia}"' in sh and "🧠</span> التحليلات" in sh)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
