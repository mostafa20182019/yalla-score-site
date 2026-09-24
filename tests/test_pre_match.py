r"""«قراءة قبل المباراة» — the pre-match reading on /m/<id> (2026-09-14, layer 1).

    python tests/test_pre_match.py        (from the repo root)

Layer 1 answers "how do these two arrive at this match" from the official
table, the form list and the season pool - and it also decides whether the
fixture page is worth indexing (`weight`). 87 of 483 match pages were fixtures
with nothing but a kick-off time, noindexed as thin since the AdSense
rejection; a page that now carries the table standing, both form lines, the
goal averages and the stakes is a guide, so the bar is four facts.

As with layer 2, most of the tests are about what must NOT be said: no place
in a table that has not kicked off, no stakes arithmetic that predicts a
position, no reading at all for a club we know nothing about.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")     # cp1252 console + Arabic output
sys.path.insert(0, os.getcwd())
import build_site as B

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

H, A = "الأهلي", "الزمالك"
COMP = "Egyptian Premier League"
M = {"home": "الأهلي", "away": "الزمالك", "kickoff": "2026-09-20",
     "koff_time": "20:00", "competition": COMP, "status": "UPCOMING"}
TABLE = {"competition": COMP, "table": [
    {"pos": 1, "team": "بيراميدز", "played": 5, "pts": 13, "gf": 10, "ga": 3},
    {"pos": 2, "team": "الأهلي", "played": 5, "pts": 11, "gf": 9, "ga": 4},
    {"pos": 3, "team": "الزمالك", "played": 5, "pts": 9, "gf": 6, "ga": 6},
    {"pos": 4, "team": "الاتحاد", "played": 5, "pts": 2, "gf": 1, "ga": 9},
]}
FORMS = {"الأهلي": ["W", "D", "W", "W", "W"], "الزمالك": ["L", "W", "D", "L", "L"]}
def fin(kick, home, away, hs, as_, comp=COMP):
    return {"kickoff": kick, "home": home, "away": away, "home_score": hs,
            "away_score": as_, "status": "FINISHED", "competition": comp}
POOL = [fin("2026-09-01", "الأهلي", "س", 2, 0), fin("2026-09-05", "ص", "الأهلي", 1, 1),
        fin("2026-09-09", "الأهلي", "ع", 3, 0), fin("2026-09-13", "ق", "الأهلي", 0, 1),
        fin("2026-09-02", "الزمالك", "س", 0, 1), fin("2026-09-06", "ص", "الزمالك", 2, 1),
        fin("2026-09-10", "الزمالك", "ع", 1, 1), fin("2026-09-14", "ق", "الزمالك", 2, 0)]
PRED = {"ph": 0.55, "pd": 0.25, "pa": 0.20, "lh": 1.8, "la": 1.0}

html, faq, w = B.pre_match_read(M, H, A, "الدوري المصري", TABLE, FORMS, POOL, POOL, PRED)
txt = B.strip_tags(html)

# ------------------------------------------------------------------ 1 content
ck("1 both clubs' current place and points open the reading",
   "يدخل الأهلي المباراة في المركز الثاني برصيد 11 نقطة من 5 مباريات" in txt
   and "الزمالك المركز الثالث برصيد 9 نقاط" in txt, txt[:150])
ck("2 the form line counts the last five and names the current run",
   "الأهلي في آخر 5 مباريات: 4 انتصارات وتعادل واحد (الفوز الثالث على التوالي)" in txt, txt)
ck("3 the other club's form is there too, with its own run",
   "الزمالك في آخر 5 مباريات" in txt and "الخسارة الثانية على التوالي" in txt, txt)
ck("4 goals scored and conceded per game come from the official table",
   "بمعدل 1.8 هدف في المباراة واستقبل 0.8" in txt, txt)
ck("5 clean sheets are counted off the season pool, in Arabic that agrees",
   "نظافة شباكه في 3 مباريات من أصل 4" in txt, txt)
ck("6 a short turnaround is flagged (Zamalek played six days... Ahly seven - neither)",
   "يلعب بعد" not in txt, txt)
ck("7 the stakes are arithmetic on CURRENT points, never a predicted position",
   "الفوز يرفع الأهلي إلى 14 نقطة" in txt and "بيراميدز (الأول)" in txt
   and "يرفع الفوز الزمالك إلى 12 نقطة" in txt, txt)
ck("8 the note says the numbers are live until kick-off", "حتى صافرة البداية" in txt)
ck("9 four facts or more = the page is worth indexing", w >= 4, w)

# ------------------------------------------------------------------- 2 the FAQ
ck("10 the FAQ answers when, on which channel, the form and the model",
   faq.count("<details>") == 4 and "FAQPage" in faq and "20:00" in faq
   and "يرجّح النموذج فوز الأهلي باحتمال 55%" in faq, faq.count("<details>"))
_, faq2, _ = B.pre_match_read(M, H, A, "الدوري المصري", TABLE, FORMS, POOL, POOL, None)
ck("11 no model output for this match -> no prediction question invented",
   faq2.count("<details>") == 3 and "النموذج" not in faq2)
ck("12 an unannounced channel is said to be unannounced, not guessed",
   "لم تتوفر بعد معلومات القناة" in faq2 or "تُنقل عبر" in faq2)

# -------------------------------------------------------------- 3 the silences
_, _, w0 = B.pre_match_read(
    {"home": "نادٍ مجهول", "away": "نادٍ آخر", "kickoff": "2026-09-20",
     "competition": "Some Cup", "status": "UPCOMING"},
    "نادٍ مجهول", "نادٍ آخر", "كأس", None, {}, [], [], None)
ck("13 a club we know nothing about produces no reading at all", w0 == 0, w0)
zero = dict(TABLE, zeroed=True)
h2, _, w2 = B.pre_match_read(M, H, A, "الدوري المصري", zero, {}, [], [], None)
ck("14 a pre-season table is never read (every place would be 'first')",
   "المركز" not in B.strip_tags(h2) and w2 == 0, w2)
ck("15 a fixture with only two form results and no table stays below the bar",
   B.pre_match_read(M, H, A, "الدوري المصري", None,
                    {"الأهلي": ["W", "D"], "الزمالك": ["L"]}, [], [], None)[2] < 4)

# a zero-point club: «برصيد دون نقاط» is not Arabic
T0 = {"competition": COMP, "table": [
    {"pos": 1, "team": "بيراميدز", "played": 4, "pts": 12, "gf": 8, "ga": 2},
    {"pos": 19, "team": "الأهلي", "played": 4, "pts": 0, "gf": 1, "ga": 9},
    {"pos": 18, "team": "الزمالك", "played": 4, "pts": 1, "gf": 2, "ga": 8}]}
t0 = B.strip_tags(B.pre_match_read(M, H, A, "الدوري المصري", T0, FORMS, POOL, POOL, None)[0])
ck("16 a club on zero points reads «دون أي نقاط», not «برصيد دون نقاط»",
   "دون أي نقاط من 4 مباريات" in t0 and "برصيد دون" not in t0, t0[:120])

# the club immediately above is often today's opponent
T1 = {"competition": COMP, "table": [
    {"pos": 1, "team": "الزمالك", "played": 5, "pts": 12, "gf": 9, "ga": 3},
    {"pos": 2, "team": "الأهلي", "played": 5, "pts": 11, "gf": 9, "ga": 4}]}
t1 = B.strip_tags(B.pre_match_read(M, H, A, "الدوري المصري", T1, FORMS, POOL, POOL, None)[0])
ck("17 when the club above IS the opponent it is named once, as «نفسه»",
   "فوق الزمالك نفسه" in t1 and "الزمالك (الأول)" not in t1, t1[-160:])

# the last meeting, when the season pool holds one
POOL2 = POOL + [fin("2026-08-20", "الزمالك", "الأهلي", 1, 2)]
t2 = B.strip_tags(B.pre_match_read(M, H, A, "الدوري المصري", TABLE, FORMS, POOL2, POOL2, None)[0])
ck("18 a previous meeting this season is reported with its winner and score",
   "آخر مواجهة بينهما" in t2 and "بفوز الأهلي 2-1" in t2, t2[-240:])
ck("19 and nothing is said when they have not met yet", "آخر مواجهة" not in txt)

# a club playing again within three days
M3 = dict(M, kickoff="2026-09-16")
t3 = B.strip_tags(B.pre_match_read(M3, H, A, "الدوري المصري", TABLE, FORMS, POOL, POOL, None)[0])
ck("20 a two-day turnaround is flagged with the opponent it just played",
   "الزمالك يلعب بعد يومين فقط من مباراته أمام ق" in t3, t3)

print()
print(f"{len(fails)} FAILED: {', '.join(fails)}" if fails else "ALL PRE-MATCH TESTS PASSED")
sys.exit(1 if fails else 0)
