r"""التوقيع: «فريق التحرير» على كل مقال (2026-10-07; was the named editor since 2026-09-15).

    python tests/test_byline.py           (from the repo root)

One of the two decisions left open after the AdSense content rejection: the
generic «فريق التحرير» becomes the named editor everywhere a byline is shown,
and the NewsArticle author becomes a Person that resolves to /editors.

The resolution is rendering-level - the stored rows keep whatever they carry -
so the tests check both directions: a generic byline is replaced, and a real
name (a guest, or a future second writer) is left alone.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import build_site as B

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

NAME = "مصطفى عبدالسلام"

TEAM = "فريق التحرير"
ck("1 the generic team byline stays the team",
   B.byline({"author": "فريق التحرير"}) == TEAM)
ck("1b the editor's own name, as the AI prompts store it, is signed as the team too",
   B.byline({"author": NAME}) == TEAM)
ck("2 so does the site name and the older variant",
   B.byline({"author": B.SITE_NAME}) == TEAM and B.byline({"author": "فريق يلا سكور"}) == TEAM)
ck("3 and a missing or empty author",
   B.byline({}) == TEAM and B.byline({"author": ""}) == TEAM)
ck("4 a real person's name is NOT overwritten",
   B.byline({"author": "أحمد شوقي"}) == "أحمد شوقي")

art = {"article_id": "1", "title": "خبر", "summary": "س", "author": "فريق التحرير",
       "pub_date": "2026-09-15", "body": "<p>نص</p>"}
ck("5 the card byline prints the team, not the name", TEAM in B.news_card(art) and NAME not in B.news_card(art))
ck("6 the FotMob-block byline prints the team", TEAM in B._art_meta(art) and NAME not in B._art_meta(art))

# the schema: the team is an Organization (a Person named «فريق التحرير» would be false)
import json, re
from site_lib.articles import author_ld
ld = author_ld(art)
ck("7 the author entity is the editorial team (Organization) pointing at /editors",
   ld["@type"] == "Organization" and TEAM in ld["name"] and ld["url"].endswith("/editors.html"))
ck("7b a real person's name stays a Person", author_ld({"author": "أحمد شوقي"})["@type"] == "Person")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_source import build_source  # noqa: E402  the whole build
src = build_source()
ck("8 no render path still prints the raw stored author",
   'esc(a.get("author"))' not in src and 'a.get("author") or SITE_NAME' not in src, )
ck("9 every article schema takes its author from author_ld()",
   src.count('"author": author_ld(a)') >= 2)
# (2026-09-25: the static pages' wording moved into site_src/templates/ -
# the checks below read it there; the rendered pages are byte-identical)
TPL = "site_src/templates/"
tpl = {n: open(TPL + n, encoding="utf-8").read()
       for n in ("editors.html", "editorial.html", "about.html")}
ck("10 the editors page says articles are signed «فريق التحرير» (no stale «يحمل توقيعه»)",
   "بتوقيع <b>«فريق التحرير»</b>" in tpl["editors.html"] and "يحمل توقيعه" not in tpl["editors.html"])

# the prompts must write the name into new rows too, or the data drifts from
# what the site renders
for f in (".github/prompts/daily-article.md", ".github/prompts/match-article.md"):
    t = open(f, encoding="utf-8").read()
    ck(f"11 {os.path.basename(f)} tells the writer to sign with the name",
       NAME in t and 'author "فريق التحرير"' not in t and '`author` = "فريق التحرير"' not in t)

# ---------------------------------------------------------------- the disclosure
# A named person signing every article makes the AI question sharper, not
# softer: the policy has to say how those articles are produced, and keep the
# three different things the site does apart.
# the page text is written as adjacent Python string literals, so a sentence
# can be split across two lines in the SOURCE while being one sentence in the
# OUTPUT - join them before asserting on wording
import re as _re
flat = _re.sub(r"'\s*\n\s*'", "", src) + "".join(tpl.values())
ed = tpl["editorial.html"]
ck("12 the editorial policy has its own AI section",
   "استخدام الذكاء الاصطناعي" in ed and "نفصح عن ذلك صراحةً" in ed)
ck("13 it says the articles are AI-ASSISTED, under the named editor's review",
   "تُصاغ مقالات الموقع بمساعدة أدوات ذكاء اصطناعي" in ed
   and "تحت إشراف ومراجعة" in ed and "{{ editor_name }}" in ed)
ck("14 it says the tool does not decide what is published",
   "لا تقرّر ما يُنشر" in ed and "لا تُسنِد خبرًا إلى مصدر لم نراجعه" in ed)
ck("15 the computed readings are explicitly NOT AI-written",
   "ليست مكتوبة بالذكاء الاصطناعي إطلاقًا" in ed and "تُبنى حسابيًا" in ed)
ck("16 the data and the model are named as a third, separate thing",
   "مزوّدي بيانات المباريات" in ed and "/predictions.html" in ed)
ck("17 the disclosure repeats where the person is introduced (/editors)",
   "تُصاغ المقالات بمساعدة أدوات ذكاء اصطناعي" in flat and "تحت إشرافي ومراجعتي" in flat)
ck("18 and on /about, next to the claim that we write our own copy",
   "بمساعدة أدوات ذكاء اصطناعي في الصياغة وتحت مراجعته" in flat)
ck("19 no leftover claim that a faceless team writes the articles",
   "فريق تحرير يلا سكور" not in flat)

print()
print(f"{len(fails)} FAILED: {', '.join(fails)}" if fails else "ALL BYLINE TESTS PASSED")
sys.exit(1 if fails else 0)
