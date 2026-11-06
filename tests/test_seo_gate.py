# -*- coding: utf-8 -*-
r"""The SEO gate (seo_gate.py, audit 2026-11-06): the rules the prompts ask for,
refused by article_put --check when a draft ignores them.

    python tests/test_seo_gate.py         (from the repo root)

A compliant news draft and a compliant report pass; each rule is then broken
on its own and must be named. The link-target checks run against the data in
this checkout (data/articles.json, data/matches.json) - a slug that does not
exist is refused, a real one is not.
"""
import copy
import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import seo_gate as G

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

def has(probs, needle):
    return any(needle in p for p in probs)

NEWS = {
    "title": "بن بوعلي يعود لبيراميدز منتصف نوفمبر قبل مباراة الأهلي",
    "summary": "يعود المهاجم بن بوعلي إلى تدريبات بيراميدز منتصف نوفمبر بعد إصابة في العضلة الخلفية أبعدته ثلاثة أسابيع، قبل مواجهة الأهلي في الدوري.",
    "body": ("<p>يستعد بيراميدز لعودة مهاجمه بن بوعلي في منتصف نوفمبر بعد غياب ثلاثة أسابيع.</p>"
             "<h2>إصابة بن بوعلي: ماذا حدث؟</h2><p>أصيب اللاعب في العضلة الخلفية.</p>"
             "<h2>الخلفية: انتقال بن بوعلي إلى بيراميدز</h2><p>انضم في الصيف.</p>"
             "<h2>ما التالي لبيراميدز قبل مباراة الأهلي؟</h2>"
             '<p>يواجه <a href="/team/pyramids">بيراميدز</a> الأهلي، ويتصدر '
             '<a href="/standings/egypt">ترتيب الدوري المصري</a>، وصفحة <a href="/team/al-ahly">الأهلي</a>.</p>'),
    "faq": [{"q": "متى يعود بن بوعلي لبيراميدز؟", "a": "منتصف نوفمبر."},
            {"q": "كم مباراة غاب بن بوعلي؟", "a": "ثلاث مباريات."}],
}
BRIEF_R = {"kind": "report", "match": {"match_id": 1, "home": "برشلونة", "away": "أستون فيلا", "score": "3-0"}}
REPORT = {
    "kind": "report", "match_id": 1,
    "title": "نتيجة مباراة برشلونة وأستون فيلا 3-0: ثنائية رافينيا تقود الفوز",
    "summary": "انتهت مباراة برشلونة وأستون فيلا بنتيجة 3-0 في دوري أبطال أوروبا بثنائية رافينيا وهدف ليفاندوفسكي، ليبقى برشلونة في صدارة الجدول.",
    "body": ("<p>انتهت مباراة برشلونة وأستون فيلا بنتيجة 3-0 مساء الثلاثاء في دوري الأبطال.</p>"
             "<h2>كيف سارت مباراة برشلونة وأستون فيلا</h2><p>سيطرة كاملة.</p>"
             "<h2>أرقام اللاعبين</h2><p>رافينيا هدفان.</p>"
             '<h2>ترتيب دوري أبطال أوروبا بعد المباراة</h2><p><a href="/team/barcelona">برشلونة</a> أول، '
             '<a href="/standings/champions-league">الترتيب الكامل</a>.</p>'),
    "faq": [{"q": "ما نتيجة مباراة برشلونة وأستون فيلا؟", "a": "3-0."},
            {"q": "من سجل أهداف مباراة برشلونة وأستون فيلا؟", "a": "رافينيا وليفاندوفسكي."}],
}

print("== compliant drafts pass ==")
p = G.seo_problems(NEWS)
ck("1 a compliant news draft has no SEO problem", not p, "; ".join(p))
p = G.seo_problems(REPORT, BRIEF_R)
ck("2 a compliant report has no SEO problem", not p, "; ".join(p))

print()
print("== each rule refuses on its own ==")
d = copy.deepcopy(NEWS); d["title"] = "تقرير: " + d["title"]
ck("3 a colon prefix is refused", has(G.seo_problems(d), "colon prefix"))
d = copy.deepcopy(NEWS); d["title"] = "قمة"
ck("4 a too-short title is refused", has(G.seo_problems(d), "characters"))
d = copy.deepcopy(NEWS); d["summary"] = d["summary"] + " " + d["summary"]
ck("5 a summary over 160 chars is refused", has(G.seo_problems(d), "meta description"))
d = copy.deepcopy(NEWS); d["body"] = f"<p>{d['summary']}</p>" + d["body"]
ck("6 a lead that repeats the summary is refused", has(G.seo_problems(d), "repeats the summary"))
d = copy.deepcopy(NEWS)
d["body"] = d["body"].replace("إصابة بن بوعلي: ماذا حدث؟", "ماذا حدث؟") \
                     .replace("الخلفية: انتقال بن بوعلي إلى بيراميدز", "الخلفية") \
                     .replace("ما التالي لبيراميدز قبل مباراة الأهلي؟", "ما التالي؟")
ck("7 bare template H2s with no entity are refused", has(G.seo_problems(d), "carries the story's entity"))
d = copy.deepcopy(NEWS); d["body"] = d["body"].replace('<a href="/team/al-ahly">الأهلي</a>', "الأهلي")
ck("8 fewer than 3 internal links in a news story is refused", has(G.seo_problems(d), "internal link"))
d = copy.deepcopy(NEWS); d["body"] = d["body"].replace("/team/pyramids", "/team/piramids")
ck("9 a club slug that does not exist is refused", has(G.seo_problems(d), "/team/piramids does not exist"))
d = copy.deepcopy(NEWS); d["body"] = d["body"].replace("/standings/egypt", "/standings/egyptian-league")
ck("10 a competition slug that does not exist is refused", has(G.seo_problems(d), "does not exist"))
d = copy.deepcopy(NEWS); d["faq"] = [{"q": "سبب الغياب", "a": "إصابة."}, d["faq"][1]]
ck("11 a first FAQ not in the searcher's words is refused", has(G.seo_problems(d), "must start with"))

d = copy.deepcopy(REPORT); d["title"] = "تقرير: برشلونة يسحق أستون فيلا في دوري أبطال أوروبا"
p = G.seo_problems(d, BRIEF_R)
ck("12 a report title without the result is refused", has(p, "carries the result") and has(p, "colon prefix"))
d = copy.deepcopy(REPORT); d["title"] = "نتيجة مباراة برشلونة × أستون فيلا 3-0: ثنائية رافينيا تقود الفوز"
ck("13 «×» between the clubs is refused", has(G.seo_problems(d, BRIEF_R), "«×»"))
d = copy.deepcopy(REPORT); d["body"] = d["body"].replace('<a href="/team/barcelona">برشلونة</a>', '<a href="/m/1">المباراة</a>')
ck("14 a match piece linking its own match page is refused", has(G.seo_problems(d, BRIEF_R), "its own match page"))
d = copy.deepcopy(REPORT); d["faq"] = [{"q": "متى لعبت مباراة برشلونة وأستون فيلا؟", "a": "الثلاثاء."}] + d["faq"]
p = G.seo_problems(d, BRIEF_R)
ck("15 «متى لعبت» after the whistle is refused, and the first question must ask the result",
   has(p, "nobody searches") and has(p, "asks the result"))
d = copy.deepcopy(REPORT); d["kind"] = "preview"; d["title"] = "برشلونة يواجه أستون فيلا في دوري أبطال أوروبا الليلة"
bp = {"kind": "preview", "match": {"match_id": 1, "home": "برشلونة", "away": "أستون فيلا"}}
p = G.seo_problems(d, bp)
ck("16 a preview title without «موعد» is refused, and its first FAQ must ask the kick-off",
   has(p, "«موعد مباراة") and has(p, "asks the kick-off"))
rb = {"kind": "round-review", "competition_ar": "الدوري المصري", "round": 8}
d = copy.deepcopy(NEWS); d["title"] = "الجولة 8 من الدوري المصري بالأرقام: بيراميدز يتصدر"
ck("17 a round review title not starting with «ترتيب» / «نتائج الجولة» is refused",
   has(G.seo_problems(d, rb), "round review's title"))
ck("18 an analysis piece is not gated", not G.seo_problems({"kind": "analysis", "title": "x", "body": "<p>y</p>"}))

print()
print("== wired into article_put.validate ==")
import article_put as AP
bad, _ = AP.validate(dict(NEWS, author="x", pub_date="2026-11-06", body=NEWS["body"] + " كلمة" * 320), updating=False)
ck("19 validate() carries the gate's refusals",
   not any("SEO" in x or "colon" in x or "internal link" in x for x in bad), "; ".join(bad))
d = dict(NEWS, author="x", pub_date="2026-11-06", body=NEWS["body"] + " كلمة" * 320, title="تقرير: " + NEWS["title"])
bad, _ = AP.validate(d, updating=False)
ck("20 a colon-prefixed title is refused by validate()", any("colon prefix" in x for x in bad))

print()
if fails:
    print(f"{len(fails)} FAILED: " + "; ".join(fails))
    sys.exit(1)
print("all ok")
