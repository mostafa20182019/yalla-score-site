# -*- coding: utf-8 -*-
"""«توقع يلا سكور» — the button on a match row, and the popup it opens.

Run from the site root:  python tests/test_pred_btn.py

Three things have to hold or this feature is a net loss rather than a gain:

1. **It stays cheap.** /matches is already a 1 MB page with 13% of its LCP
   samples in the "poor" band. The feature's whole budget is ~110 bytes per
   row — five numbers, not a rendered block — and a dialog that ships once
   per page and only on pages that can open it.
2. **It is clickable.** .mstretch covers the entire row at z-index 1. A
   button that does not sit above it opens the match page instead of the
   popup, which is exactly the behaviour the button exists to replace.
3. **It says the whole truth.** Three probabilities, never two, and the
   "not betting advice" line travels with them — a prediction shown without
   its disclaimer is the AdSense problem we just spent a week closing.

Plus the collision guard: .pp / .pp-ava / .pp-fb are the PITCH graphic's
markers and they are position:absolute. The last two class collisions in
this stylesheet (.tl on 2026-09-16, .pp the same day) both shipped broken to
the user's phone, so the popup's hooks must stay out of that namespace.
"""
import os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import analysis as AN
import build_site as B

fails = []
def ok(n, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + n + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(n)

P = {"ph": 0.671, "pd": 0.219, "pa": 0.110, "top": [(2, 1, 0.12)], "conf": "mid"}
BTN = B.pred_btn(P)
POP = B.PRED_POP

print("== the button carries the prediction, and nothing else ==")
ok("1 all three probabilities travel, rounded to whole percents",
   'data-pp="67,22,11"' in BTN, BTN)
ok("2 so does the modal scoreline", 'data-ps="2-1"' in BTN, BTN)
ok("3 and the confidence key", 'data-pc="mid"' in BTN, BTN)
ok("4 no prediction, no button", B.pred_btn(None) == "")
# the ceiling, not the measurement: 90 rows x 140B is 12 KB on a page whose
# LCP is already hurting. If a future edit inlines the bar or the team names
# here, this is what catches it.
ok("5 and it stays under 140 bytes", len(BTN.encode("utf-8")) <= 140,
   len(BTN.encode("utf-8")))
ok("6 it is type=button — a bare <button> in a form would submit it",
   'type="button"' in BTN)

print()
print("== it has to be clickable through .mstretch ==")
css = B.CSS
m = re.search(r"\.pbtn\{([^}]*)\}", css)
ok("7 the button is positioned", bool(m) and "position:relative" in m.group(1),
   m.group(1) if m else "no .pbtn rule")
ok("8 above .mstretch, which covers the whole row at z-index 1",
   bool(m) and "z-index:2" in m.group(1), m.group(1) if m else "")
ok("9 .mstretch is still the thing being cleared (z-index 1)",
   re.search(r"\.mstretch\{[^}]*z-index:1", css) is not None)

print()
print("== the popup states the whole prediction ==")
ok("10 three swatched probabilities are built, not two",
   POP.count('class="prb-') == 3, POP.count('class="prb-'))
ok("11 the bar has all three segments",
   all(f'pb-{k}"' in POP for k in "hda"))
ok("12 the favourite is named", 'ppop-fav' in POP and 'الأرجح' in POP)
ok("13 the modal scoreline is stated", 'النتيجة الأكثر احتمالًا' in POP)
# the first version wrote `cf.className = "conf conf-" + c`, which threw the
# hook class away — the very next lookup returned null, the handler died
# before showModal() and the popup never opened at all. Only a render caught
# it, so the assertion is on the hook surviving, not on the chip existing.
ok("14 the confidence chip reuses the site's own classes AND keeps its hook",
   '"ppop-cf conf conf-"' in POP)
ok("15 and its Arabic comes from AN.CONF_AR, so it cannot drift",
   all(v in POP for v in AN.CONF_AR.values()), list(AN.CONF_AR.values()))
ok("16 the disclaimer travels with the numbers",
   "ليست نصيحة للمراهنة" in POP)
ok("17 and it ends with the way into the full reading",
   "لماذا رجّح النموذج" in POP and "ppop-go" in POP)

print()
print("== the namespace guard ==")
# .pp is the pitch player marker (position:absolute) and .pp-ava/.pp-fb are
# its children. A hook that shares that prefix is the .pp bug again.
hooks = re.findall(r'class="([a-z0-9 _-]+)"', POP) + re.findall(r'q\("\.([a-z0-9-]+)"\)', POP)
bad = sorted({c for line in hooks for c in line.split()
              if c == "pp" or (c.startswith("pp-") and not c.startswith("ppop"))})
ok("18 no popup hook lives in the .pp (pitch marker) namespace", not bad, bad)
ok("19 and the pitch marker itself is untouched",
   ".pp-ava{" in css and ".pp{" in css or ".pp-ava{" in css)

print()
print("== it ships once per page, and only where it can be used ==")
ok("20 the dialog is a single element", POP.count('id="ppop"') == 1)
ok("21 a page with no button gets no dialog", B.pred_pop(["<div>x</div>"]) == "")
ok("22 a page with one does", B.pred_pop(["<div>", BTN, "</div>"]) == POP)

print()
print("== and the row itself ==")
M = {"match_id": 1, "home": "A", "away": "B", "status": "UPCOMING",
     "kickoff": "2026-09-20", "koff_time": "20:00", "competition": "X"}
row_on = B.match_row(M, link="/m/1.html", pred=P)
row_off = B.match_row(M, link="/m/1.html")
ok("23 a row with a prediction shows the button", 'class="pbtn"' in row_on)
ok("24 a row without one is unchanged", 'pbtn' not in row_off)
ok("25 the popup reads the team names off the row, so they are not duplicated",
   'data-h="A"' in row_on and 'data-a="B"' in row_on
   and ">A<" not in BTN)

print()
print("== the RTL score rule, which a render caught twice ==")
# "2-1" as a single text run is one LTR run: in an RTL line the HOME number
# lands on the AWAY side and the reader gets the prediction backwards. The
# record page was fixed for this on 2026-09-16; the popup and /analysis were
# still doing it on 2026-09-18, measured in the browser (home 2 sitting under
# the away club).
ok("26 the popup builds every scoreline as a pill, not one text run",
   '"<span>"+x[0]+"</span><i>-</i><span>"+x[1]+"</span>"' in POP
   and POP.count("pill(q(") == 2, POP.count("pill(q("))
ok("27 and it carries .sc-in, which is what orders the two halves",
   'ppop-val sc-in' in POP)
_pr = B.pred_row({"home": "A", "away": "B", "match_id": 1,
                  "kickoff": "2026-09-20", "koff_time": "20:00"}, P)
ok("28 /analysis states the same scoreline the same way",
   "<span>2</span><i>-</i><span>1</span>" in _pr and "<b>2-1</b>" not in _pr,
   _pr[-220:])

print()
print("== the same button on a match that is OVER ==")
E = {"ph": 0.42, "pd": 0.24, "pa": 0.33, "score": "1-1",
     "hs": 3, "as": 2, "hit": True, "conf": "mid"}
DONE = B.done_btn(E)
ok("29 it carries the frozen probabilities, the called scoreline and the result",
   all(x in DONE for x in ('data-pp="42,24,33"', 'data-ps="1-1"', 'data-pr="3-2"')),
   DONE)
ok("30 and the verdict", 'data-hit="1"' in DONE, DONE)
ok("31 it stays under 160 bytes", len(DONE.encode("utf-8")) <= 160,
   len(DONE.encode("utf-8")))
ok("32 a logged match that has not been played yet gets no button",
   B.done_btn(dict(E, hs=None, as_=None, **{"as": None})) == ""
   and B.done_btn(None) == "")

# THE INTEGRITY TEST. `hit` must come from the log, which froze it when the
# match was scored — never be re-derived here from today's numbers. This
# record is deliberately self-contradictory: the home side was favourite and
# the away side won, so any renderer doing its own arithmetic would call it a
# miss. The button must report what the log says.
_odd = {"ph": 0.60, "pd": 0.25, "pa": 0.15, "score": "2-0",
        "hs": 0, "as": 1, "hit": True}
ok("33 the verdict is READ from the frozen record, never recomputed",
   'data-hit="1"' in B.done_btn(_odd), B.done_btn(_odd))
ok("34 and a miss is rendered as loudly as a hit (21 of 54 were misses)",
   'data-hit="0"' in B.done_btn(dict(_odd, hit=False))
   and '"ppop-cf hit "+(w?"ok":"no")' in POP)

# 42% on a home win that then happens IS a hit even when the 1-1 we called
# closest ended 3-2. A green tick beside «توقعنا 1-1 · 3-2» reads as a joke
# at the reader's expense, so the claim line states the OUTCOME and the
# scoreline is demoted and relabelled.
ok("35 the verdict is on the outcome; the scoreline is relabelled below it",
   "أقرب نتيجة رجّحها النموذج" in POP and 'قلنا: ' in POP, POP[:0])
ok("36 a finished popup shows the real result too", 'ppop-rv' in POP and 'ppop-res' in POP)
ok("37 and offers the full record, so one lucky week is not read as the season",
   'ppop-rec' in POP and '/predictions' in POP)

M_FIN = dict(M, status="FINISHED", home_score=3, away_score=2)
ok("38 a finished row with a frozen record shows the button",
   'class="pbtn"' in B.match_row(M_FIN, link="/m/1.html", done=E))
ok("39 and one without a record does not",
   "pbtn" not in B.match_row(M_FIN, link="/m/1.html", done=None))
ok("40 both kinds open the same single dialog",
   B.pred_pop(["x", DONE]) == POP and B.pred_pop(["x", BTN]) == POP)

print()
print("== each label wears its segment's colour ==")
# user, 2026-09-18: «خلى لون كلمة الشرقية انبى باللبنى نفس لون الخط بتاعها اللى
# فى البار» — the word takes the colour of its slice, so the eye pairs them
# without hunting for the swatch. One CSS rule per segment covers all three
# places the legend appears (the popup, /analysis, /m/).
for _k, _c in (("h", "var(--green)"), ("d", "#94a3b8"), ("a", "#334155")):
    ok(f"41 the {_k} label is painted like the {_k} segment",
       f".prb:has(.prb-{_k})" in css
       and re.search(r"\.prb:has\(\.prb-" + _k + r"\)\{color:" + re.escape(_c) + r"\}", css)
       is not None,
       _c)
# the swatch is what a browser without :has() (and a colour-blind reader) is
# left with, so it must not be "tidied away" now that the text is coloured
ok("42 the swatch stays — it is the fallback and the accessible cue",
   'class="prb-h"' in B.prob_legend(P) and ".prb-h{background:" in css)
# and the two names in the popup head, so the header line and the legend
# under the bar do not say the same thing in two different colours
ok("43 the home name in the head is painted like the home segment",
   ".ppop-nh{color:var(--green)}" in css)
ok("44 and the away name like the away segment",
   ".ppop-na{color:#334155}" in css)
# The bar is RTL like the rest of the page, so the HOME segment sits under
# the home club's name. It carried direction:ltr from the days when the
# percentages were printed inside the segments; those moved out to
# prob_legend on 2026-09-16 and the override stayed behind, putting the home
# side on the wrong end of its own bar until the user caught it.
_pbar = re.search(r"\.pbar\{([^}]*)\}", css)
ok("45 the bar reads right-to-left, home segment first",
   bool(_pbar) and "direction:rtl" in _pbar.group(1)
   and "direction:ltr" not in _pbar.group(1),
   _pbar.group(1) if _pbar else "no .pbar rule")
ok("46 and the home segment really is the first child",
   B.prob_bar(P).index("pb-h") < B.prob_bar(P).index("pb-a"))
# the prediction ROW (home page block + /analysis) gets the same treatment:
# the club name was the one neutral thing left in a row where the slice and
# the label under it were already coloured
ok("47 a prediction row's home club is painted like the home segment",
   ".pr-teams>.pr-t:first-child bdi{color:var(--green)}" in css)
ok("48 and its away club like the away segment",
   ".pr-teams>.pr-t:last-child bdi{color:#334155}" in css)
ok("49 and the row still puts home first, which is what those selectors rely on",
   _pr.index("pr-t") < _pr.index("pr-vs") < _pr.rindex("pr-t"))

# user, 2026-09-18: «خلى هنا اسماء الفرق». Making the reader map «الأرض» onto
# a club written two lines up is work the page can do for them.
_named = B.prob_legend(P, home="الأهلي", away="الزمالك")
ok("50 the legend names the clubs when the caller knows them",
   "الأهلي" in _named and "الزمالك" in _named
   and "الأرض" not in _named and "الضيف" not in _named, _named)
ok("51 تعادل is still تعادل — it is not a club", "تعادل" in _named)
ok("52 الأرض/الضيف stay as the fallback for a caller with only numbers",
   "الأرض" in B.prob_legend(P) and "الضيف" in B.prob_legend(P))
ok("53 a club name is escaped like any other untrusted string",
   "&lt;b&gt;" in B.prob_legend(P, home="<b>", away="x"),
   B.prob_legend(P, home="<b>", away="x"))
ok("54 the prediction row passes them through",
   "A" in _pr.split('pr-bw')[1] and "B" in _pr.split('pr-bw')[1])
# three club names do not fit one 268px line, so the legend must be allowed
# to wrap - with a gap, not a margin that would indent a wrapped item
_lg = re.search(r"\.prow \.pr-probs\{([^}]*)\}", css)
ok("55 and the legend may wrap instead of overflowing its column",
   bool(_lg) and "flex-wrap:wrap" in _lg.group(1)
   and "white-space:nowrap" not in _lg.group(1),
   _lg.group(1) if _lg else "no rule")

print()
print("FAILED: " + ", ".join(fails) if fails else "ALL PRED-BUTTON TESTS PASSED")
sys.exit(1 if fails else 0)
