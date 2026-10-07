r"""Dropped article headings (2026-10-07): the «لماذا يهم الخبر؟» heading is no
longer shown - its paragraphs stay.

    python tests/test_drop_headings.py   (from the repo root)

The stored bodies keep the heading; build() strips it right after loading, so
the article page, RSS and the match-page embeds all read the same body. The
prompts must not write the heading again but still ask for the content.
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


from site_lib.articles import drop_headings                # noqa: E402
from site_lib.config import DROP_HEADINGS                  # noqa: E402

WHY = "لماذا يهم الخبر؟"
ck("the heading is configured", WHY in DROP_HEADINGS)

body = ("<p>مقدمة</p><h2>الأرقام</h2><p>أرقام</p>\n"
        f"<h2>{WHY}</h2>\n<p>يعني <a href=\"/team/zamalek\">الزمالك</a></p><ul><li>نقطة</li></ul>"
        "<h2>ما التالي؟</h2><p>المباراة القادمة</p>")
a = {"body": body}
n = drop_headings([a])
ck("one article changed", n == 1, n)
ck("the heading is gone", WHY not in a["body"])
ck("its content stays (paragraph, link, list)",
   "يعني" in a["body"] and 'href="/team/zamalek"' in a["body"] and "<li>نقطة</li>" in a["body"])
ck("exactly the heading went, nothing else",
   a["body"] == ("<p>مقدمة</p><h2>الأرقام</h2><p>أرقام</p>\n<p>يعني <a href=\"/team/zamalek\">الزمالك</a></p>"
                 "<ul><li>نقطة</li></ul><h2>ما التالي؟</h2><p>المباراة القادمة</p>"),
   a["body"])

attr = {"body": f"<p>مقدمة</p><h2 class=\"x\"> {WHY} </h2><p>آخر فقرة</p>"}
drop_headings([attr])
ck("a heading with attributes/spaces goes too", attr["body"] == "<p>مقدمة</p><p>آخر فقرة</p>", attr["body"])

other = {"body": "<p>نص</p><h2>ماذا يعني للنادي واللاعب؟</h2><p>يبقى</p>"}
ck("other headings are untouched", drop_headings([other]) == 0 and "<h2>ماذا يعني" in other["body"])
ck("an article without a body is fine", drop_headings([{"body": None}, {}]) == 0)
ck("an empty tuple switches it off", drop_headings([{"body": body}], headings=()) == 0)

# build() strips before anything reads the body.
src = io.open("build_site.py", encoding="utf-8").read()
ck("build() strips before the thin filter",
   0 < src.find("drop_headings(articles_all)") < src.find("not is_thin(a)"))

for p in (".github/prompts/daily-article.md", ".github/prompts/upgrade-article.md"):
    t = io.open(p, encoding="utf-8").read()
    ck(f"{p}: no {WHY} heading asked for", f"<h2>{WHY}</h2>" not in t and f"«{WHY}» / «" not in t)
    ck(f"{p}: says not to write it", "never" in t.lower() and WHY in t)
    ck(f"{p}: still asks for the content", "WITHOUT a heading of their own" in t)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
