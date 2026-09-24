# -*- coding: utf-8 -*-
"""«قراءة في صدارة الهدافين» — build_site.scorers_read.

Run from the site root:  python tests/test_scorers_read.py

Ten names is a list; what makes it a page is what the list means. These tests
pin the two things that are easy to get wrong in Arabic and in logic: a SHARED
lead must never be written as if one player owned it, and every counted noun
must agree with its number (3 تمريرات، not 3 تمريرة). They also pin the rule
that decides indexability — under three facts the page stays out of the index,
which is what it was before this block existed.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import build_site as B

fails = []
def ok(n, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + n + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(n)

SC = [{"name": "لاعب أ", "team": "الأهلي", "value": 5},
      {"name": "لاعب ب", "team": "بيراميدز", "value": 3},
      {"name": "لاعب ج", "team": "بيراميدز", "value": 2}]
TIE = [{"name": "لاعب أ", "team": "الأهلي", "value": 3},
       {"name": "لاعب ب", "team": "القناة", "value": 3},
       {"name": "لاعب ج", "team": "الزمالك", "value": 1}]
AS = [{"name": "صانع أ", "team": "الزمالك", "value": 3}]
TBL = [{"team": "الأهلي", "gf": 9, "played": 5}, {"team": "بيراميدز", "gf": 7, "played": 5},
       {"team": "القناة", "gf": 4, "played": 5}, {"team": "الزمالك", "gf": 6, "played": 5}]
POOL = [{"home_score": 2, "away_score": 1} for _ in range(20)]

print("== the lead ==")
h, f, w = B.scorers_read("الدوري المصري", "2026-2027", SC, AS, TBL, POOL)
ok("1 a clear leader is named with his gap", "لاعب أ" in h and "بفارق" in h)
ok("2 and the FAQ answers who the top scorer is", "من هداف الدوري المصري الآن؟" in f)

h2, f2, w2 = B.scorers_read("الدوري المصري", "2026-2027", TIE, AS, TBL, POOL)
ok("3 a shared lead is written as shared",
   "تُقسَم" in h2 and "لاعب أ" in h2 and "لاعب ب" in h2, h2[:160])
ok("3b two leaders are «لاعبين», not «2 لاعبين»",
   "بين لاعبين" in h2 and "بين 2" not in h2, h2[:160])
ok("4 and is NEVER credited to one player as «وحده»", "وحده" not in h2, h2)
ok("5 the club-share line names the player it is about",
   "وسجّل <b>لاعب أ</b>" in h2, h2[h2.find("وسجّل"):][:80])

# the Zizo omission (ChatGPT audit 2026-09-21): «بين 4 لاعبين» then only
# three names — the sentence must name EVERY leader it counts (up to five),
# and past five must say «منهم» instead of posing as the full list
TIE4 = [{"name": f"لاعب {c}", "team": "الأهلي", "value": 3} for c in "أبجد"] + \
       [{"name": "لاعب هـ", "team": "الزمالك", "value": 1}]
h4, f4, _ = B.scorers_read("الدوري المصري", "2026-2027", TIE4, AS, TBL, POOL)
ok("5b four shared leaders are ALL named, in the fact and the FAQ",
   all(f"لاعب {c}" in h4 for c in "أبجد") and all(f"لاعب {c}" in f4 for c in "أبجد"),
   h4[:200])
TIE7 = [{"name": f"لاعب {i}", "team": "الأهلي", "value": 2} for i in range(7)]
h7, f7, _ = B.scorers_read("الدوري المصري", "2026-2027", TIE7, AS, TBL, POOL)
ok("5c past five leaders the sentence says «منهم» (a sample, not the list)",
   "منهم" in h7 and "وآخرون" in f7, h7[:200])

print()
print("== Arabic that has to agree with its number ==")
ok("6 three assists are تمريرات, not تمريرة", "3 تمريرات حاسمة" in h, h)
ok("7 the ل+ال elision: للأهلي, never لـالأهلي", "لـال" not in h, h)
ok("8 two players are لاعبين, not «2 من لاعبيه»",
   "لاعبين من صفوفه" in h and "2 من" not in h, h)
ok("9 goals out of a club total are counted too",
   "من أصل 9 أهداف" in h, h[h.find("وسجّل"):][:120])

print()
print("== what earns a place in the index ==")
ok("10 a full reading is worth indexing", w >= 3, w)
ok("11 a chart with nothing around it is not",
   B.scorers_read("دوري", "2026-2027", [{"name": "X", "value": 1}], None, None, None)[2] < 3)
ok("12 no chart at all renders nothing",
   B.scorers_read("دوري", "2026-2027", [], None, TBL, POOL) == ("", "", 0))

print()
print("== the league's own scale ==")
ok("13 the season total and rate come from the pool",
   "60 هدفًا" in h and "20 مباراة" in h, h[h.find("وللمقارنة"):][:140])
ok("14 and the FAQ repeats it for a search result",
   "كم هدفًا سُجّل في الدوري المصري هذا الموسم؟" in f)

print()
print("FAILED: " + ", ".join(fails) if fails else "ALL SCORERS-READ TESTS PASSED")
sys.exit(1 if fails else 0)
