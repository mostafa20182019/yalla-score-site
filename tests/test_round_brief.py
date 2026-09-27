"""The «الجولة بالأرقام» data article: its numbers guard and its gate (2026-09-27).

    python tests/test_round_brief.py

A data article skips the two-independent-outlets rule because its story is our
own numbers. What replaces that rule must hold: every number in the text comes
from the facts pack (round_brief.py computes them; the model only phrases),
and the article carries the pack's source so the dedup can see the round is
covered. These checks use synthetic packs - no live data - so they gate.
"""
import os
import sys

sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8")
import round_brief as RB  # noqa: E402
import article_put as AP  # noqa: E402

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


BRIEF = {"first_day": "2026-09-14", "last_day": "2026-09-17", "as_of": "2026-09-27",
         "round_key": "round:egypt:5",
         "data_source": {"name": "بيانات يلا سكور", "url": "https://yallascore.site/fixtures/egypt",
                         "note": "round:egypt:5"},
         "allowed_numbers": sorted(RB.numbers_in("0 1 15 13 7 10 72 16 2.1 21 6 1577 5"))}
SRC = [dict(BRIEF["data_source"])]


def draft(body, **kw):
    d = {"title": "الجولة 5 بالأرقام", "summary": "7 انتصارات خارج الأرض من 10",
         "body": body, "author": "x", "pub_date": "2026-09-27", "sources": SRC}
    d.update(kw)
    return d


ck("1 numbers are normalised: Arabic-Indic digits and trailing zeros",
   RB.numbers_in("١٥ نقطة و2.10 هدف و3") == {"15", "2.1", "3"}, RB.numbers_in("١٥ نقطة و2.10 هدف و3"))
ck("2 a text using only pack numbers passes",
   RB.unknown_numbers(draft("<p>بيراميدز 15 نقطة، والموديل أصاب 6 من 10.</p>"), BRIEF) == [])
bad = RB.unknown_numbers(draft("<p>الأهلي بـ 14 نقطة ونسبة 70%.</p>"), BRIEF)
ck("3 an invented number is caught (14 points, a computed 70%)", bad == ["14", "70"], bad)
ck("4 a link's /m/<id> is not a claim (tags are stripped first)",
   RB.unknown_numbers(draft('<p><a href="/m/4804678">غزل المحلة</a> 0-1</p>'), BRIEF) == [])
ck("5 the pack's own dates are allowed (14 and 17 Sep, the as-of day, the year)",
   RB.unknown_numbers(draft("<p>من 14 سبتمبر إلى 17 سبتمبر 2026، وحتى 27 سبتمبر.</p>"), BRIEF) == [])
bad = RB.unknown_numbers(draft("<p>القمة يوم 11 أكتوبر.</p>"), BRIEF)
ck("5b a date the pack does not carry is caught as a date", bad == ["11 أكتوبر"], bad)
bad = RB.unknown_numbers(draft("<p>الأهلي في المركز 14.</p>"), BRIEF)
ck("5c a bare day-number is NOT excused by the round's dates", bad == ["14"], bad)
bad = RB.unknown_numbers(draft("<p>ok</p>", faq=[{"q": "كم؟", "a": "99 مرة"}]), BRIEF)
ck("6 the FAQ is checked too", bad == ["99"], bad)
bad = RB.unknown_numbers(draft("<p>ok</p>", title="الجولة 8"), BRIEF)
ck("7 the title is checked too", bad == ["8"], bad)

# article_put: the data rule REPLACES the two-source rule, it does not weaken it
body = "<p>" + " ".join(["كلمة"] * 320) + " بيراميدز 15 نقطة.</p>"
bad, _ = AP.validate(draft(body), brief=BRIEF)
ck("8 a clean data article validates with ONE source (ours)", bad == [], bad)
bad, _ = AP.validate(draft(body))
ck("9 the same draft WITHOUT --data-brief is refused by the two-source rule",
   any("independent source" in x for x in bad), bad)
bad, _ = AP.validate(draft(body, sources=[{"name": "بيانات يلا سكور", "url": "https://yallascore.site/x",
                                            "note": "round:egypt:4"}]), brief=BRIEF)
ck("10 the wrong round key is refused (the dedup would not see this round)",
   any("facts pack's source" in x for x in bad), bad)
bad, _ = AP.validate(draft(body, sources=[dict(BRIEF["data_source"], url="https://example.com/x")]),
                     brief=BRIEF)
ck("11 the data source must be OUR url", any("facts pack's source" in x for x in bad), bad)
bad, _ = AP.validate(draft(body.replace("15 نقطة", "16 نقطة و14 هدفًا")), brief=BRIEF)
ck("12 an invented number refuses the publish", any("NOT in the facts pack" in x for x in bad), bad)

ck("13 round_key is stable and slugged", RB.round_key("Egyptian Premier League", 5) == "round:egypt:5",
   RB.round_key("Egyptian Premier League", 5))
ck("14 covered_keys reads the note of our data source",
   RB.covered_keys([{"sources": SRC}, {"sources": [{"name": "x", "note": "hi"}]}]) == {"round:egypt:5"})

print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL OK")
sys.exit(1 if fails else 0)
