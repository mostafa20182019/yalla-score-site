# -*- coding: utf-8 -*-
"""«لماذا رجّح النموذج هذا التوقع؟» — the decomposition and its guards.

Run from the site root:  python tests/test_why_block.py

The whole value of this block is that it is TRUE: every number in it is a term
of the λ the model actually used. So the first test is the one that matters —
explain() must reproduce lambdas() exactly, or the page is explaining a
prediction nobody made. The rest pin the guards: silence before a league has
played, silence when the published prediction came from a model whose λ does
not match, and no double negative in the defence line.
"""
import os, sys, math
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import analysis as AN
import build_site as B

fails = []
def ok(n, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + n + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(n)

STATS = {
    "Ahly":   {"elo": 1600.0, "played": 8, "gf": 16, "ga": 5},
    "Weak":   {"elo": 1400.0, "played": 8, "gf": 5,  "ga": 15},
    "Fresh":  {"elo": 1500.0, "played": 0, "gf": 0,  "ga": 0},
}
PAR = {"n": 40, "mu_home": 1.5, "mu_away": 1.2, "mu": 1.35,
       "home_win": 0.45, "draw": 0.25, "gpm": 2.7}

print("== the explanation describes the real model ==")
for hh, aa in (("Ahly", "Weak"), ("Weak", "Ahly"), ("Fresh", "Ahly")):
    lh, la, _, _ = AN.lambdas(STATS, PAR, hh, aa)
    ex = AN.explain(STATS, PAR, hh, aa)
    ok(f"1 {hh} v {aa}: explain() reproduces lambdas()",
       abs(ex["lh"] - lh) < 1e-9 and abs(ex["la"] - la) < 1e-9,
       (ex["lh"], lh, ex["la"], la))

ex = AN.explain(STATS, PAR, "Ahly", "Weak")
ok("2 a strong attack reads above the league average", ex["d_att_h"] > 0.2)
ok("3 a leaky defence reads above average too (it concedes MORE)", ex["d_def_a"] > 0.2)
ok("4 the Elo edge includes the home bonus", ex["elo_edge"] > 0 and ex["elo_hfa"] == AN.ELO_HFA)

print()
print("== what the block refuses to say ==")
m = {"home": "Ahly", "away": "Weak", "competition": "L"}
p = AN.predict(STATS, PAR, "Ahly", "Weak")
html = B.why_block(m, p, AN.explain(STATS, PAR, "Ahly", "Weak"), None)
ok("5 it renders for a normal fixture", "لماذا رجّح النموذج" in html)
ok("6 no double negative in the defence line",
   "−" not in html.split("يستقبل")[1].split("من المتوسط")[0] if "يستقبل" in html else True, html[:200])
blank = {"Fresh": STATS["Fresh"], "Other": dict(STATS["Fresh"])}
ok("7 silent before the league has played anything",
   B.why_block({"home": "Fresh", "away": "Other"},
               AN.predict(blank, PAR, "Fresh", "Other"),
               AN.explain(blank, PAR, "Fresh", "Other"), None) == "")
drifted = dict(p, lh=p["lh"] + 0.4)
ok("8 silent when the published prediction's λ disagrees with the decomposition",
   B.why_block(m, drifted, AN.explain(STATS, PAR, "Ahly", "Weak"), None) == "")

print()
print("== the track-record line ==")
cal = {"buckets": [{"lo": 60, "hi": 69, "n": 20, "hits": 12, "stated": .64, "actual": .60},
                   {"lo": 90, "hi": 99, "n": 3, "hits": 3, "stated": .93, "actual": 1.0}],
       "ece": 0.02, "statements": 23, "matches": 8}
ok("9 a populated band is quoted", AN.stated_bucket(cal, 0.63)["hits"] == 12)
ok("10 a band under 10 cases says nothing", AN.stated_bucket(cal, 0.95) is None)
ok("11 and a band we have never stated says nothing", AN.stated_bucket(cal, 0.15) is None)
ok("12 the record line reaches the page",
   "تحقّق ما قاله في" in B.why_block(m, dict(p, ph=0.63, pd=0.2, pa=0.17),
                                     AN.explain(STATS, PAR, "Ahly", "Weak"), cal))

print()
print("== the record line on the home page ==")
import datetime
_m = {"match_id": "1", "home": "Ahly", "away": "Weak", "kickoff": "2026-09-17",
      "koff_time": "20:00", "competition": "L"}
_acc = {"all": {"n": 166, "hit_rate": .48, "home_baseline": .43,
                "brier": .61, "score_hits": 22}}
_cal = {"buckets": [], "ece": .023, "statements": 498, "matches": 166}
_today = datetime.date(2026, 9, 16)
blk = B.pred_home_block([_m], {"1": p}, _today, acc=_acc, cal=_cal)
ok("13 the home block states the record", "pred-rec" in blk and "498" in blk and "166" in blk)
ok("14 calibration leads, and the naive baseline sits next to the hit rate",
   blk.index("المعايرة") < blk.index("إصابة الاتجاه") and "معيار ساذج" in blk)
ok("15 silent before anything has been scored",
   "pred-rec" not in B.pred_home_block([_m], {"1": p}, _today, acc=_acc,
                                       cal={"buckets": [], "ece": 0,
                                            "statements": 0, "matches": 0}))
ok("16 and silent when the log could not be read at all",
   "pred-rec" not in B.pred_home_block([_m], {"1": p}, _today))

print()
print("== the bar says the shape, the legend says the numbers ==")
_p = {"ph": .08, "pd": .20, "pa": .72}
bar = B.prob_bar(_p)
leg = B.prob_legend(_p)
ok("17 the bar prints no percentage at all", "%<" not in bar and "<b>" not in bar,
   bar[:160])
ok("18 but it still carries all three for a screen reader",
   "8%" in bar and "20%" in bar and "72%" in bar)
ok("19 the legend states all three with their labels",
   all(x in leg for x in ("الأرض", "تعادل", "الضيف", "8%", "20%", "72%")), leg)
ok("20 and carries the colour key back to the bar",
   'class="prb-h"' in leg and 'class="prb-d"' in leg and 'class="prb-a"' in leg)
# 2026-09-16: these three were first written as `.pp`, which the stylesheet
# already owned — it is the PLAYER MARKER on the pitch graphic, and it is
# position:absolute. The percentages inherited that and painted themselves
# on top of the bar on every card. Second class collision of the day (.tl
# was the first), hence a test that names the class it must NOT be.
ok("21 and never reuses .pp, which the pitch graphic owns",
   'class="pp"' not in leg and 'class="pp-' not in leg, leg[:120])

print()
print("FAILED: " + ", ".join(fails) if fails else "ALL WHY-BLOCK TESTS PASSED")
sys.exit(1 if fails else 0)
