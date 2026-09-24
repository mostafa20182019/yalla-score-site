r"""سجل التوقعات — /predictions.html (2026-09-14).

    python tests/test_pred_history.py     (from the repo root)

The record exists to show the model failing as clearly as it succeeds, so the
tests guard exactly that: the misses are counted and shown, the naive baseline
sits next to the hit rate, the calibration buckets are honest, small samples
are flagged, the two models are not raced against each other, and the page
never drifts into betting language.

Regression in here: `hit` comes back from D1 as 0/1, not False/True. The first
version of extremes() filtered with «is False» and the "most confident misses"
column - the whole point of the page - silently rendered empty.
"""
import os, re, sys, tempfile
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import analysis as AN
import build_site as B

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


def entry(mid, home, away, ph, pd, pa, hs, as_, comp="Premier League",
          kick="2026-09-10", src="python", score="1-0", hit=None):
    """A scored log row in the shape D1 hands back (hit/score_hit as 0/1)."""
    out = "H" if hs > as_ else "D" if hs == as_ else "A"
    pick = max((("H", ph), ("D", pd), ("A", pa)), key=lambda x: x[1])[0]
    probs = {"H": ph, "D": pd, "A": pa}
    return (str(mid), {
        "home": home, "away": away, "comp": comp, "kickoff": kick, "koff_time": "20:00",
        "ph": ph, "pd": pd, "pa": pa, "score": score, "hs": hs, "as": as_,
        "outcome": out, "pick": pick,
        "hit": (1 if pick == out else 0) if hit is None else hit,
        "score_hit": 1 if score == f"{hs}-{as_}" else 0,
        "brier": round(sum((probs[k] - (1.0 if k == out else 0.0)) ** 2 for k in probs), 4),
        "src": src, "conf": "low", "ts": kick})


LOG = dict([
    entry(1, "Arsenal FC", "Chelsea FC", 0.75, 0.15, 0.10, 2, 0, score="2-0"),
    entry(2, "Liverpool FC", "Fulham FC", 0.70, 0.20, 0.10, 0, 1, kick="2026-09-11"),
    entry(3, "Everton FC", "Brentford FC", 0.40, 0.30, 0.30, 1, 1, kick="2026-09-12"),
    entry(4, "Real Madrid", "Getafe CF", 0.65, 0.20, 0.15, 3, 0,
          comp="Primera Division", kick="2026-09-13", src="oracle"),
    entry(5, "FC Barcelona", "Levante UD", 0.60, 0.25, 0.15, 1, 2,
          comp="Primera Division", kick="2026-09-09", src="oracle"),
])
LOG["9"] = {"home": "x", "away": "y", "comp": "Premier League", "kickoff": "2026-09-20",
            "ph": 0.5, "pd": 0.3, "pa": 0.2, "hs": None, "as": None, "src": "python"}

# ---------------------------------------------------------------- 1 the maths
cal = AN.calibration(LOG)
ck("1 every prediction contributes three probability statements",
   cal["statements"] == 15 and cal["matches"] == 5, (cal["statements"], cal["matches"]))
ck("2 an unscored prediction is not in the record at all",
   all(b["n"] for b in cal["buckets"]) and cal["matches"] == 5)
b60 = next((b for b in cal["buckets"] if b["lo"] == 60), None)
ck("3 the 60-69% band holds the two 60-65% calls and reports what happened",
   b60 and b60["n"] == 2 and abs(b60["stated"] - 0.625) < 1e-6 and b60["actual"] == 0.5, b60)
ck("4 ECE is the size-weighted distance between what we said and what happened",
   0 <= cal["ece"] <= 1, cal["ece"])

ex = AN.extremes(LOG)
ck("5 the most confident MISS is found even though `hit` is 0/1 from D1",
   ex["worst"] and ex["worst"][0]["home"] == "Liverpool FC", ex["worst"])
ck("6 hits and misses are both ordered by how confident we were",
   ex["best"][0]["home"] == "Arsenal FC"
   and [e["home"] for e in ex["worst"]][:2] == ["Liverpool FC", "FC Barcelona"],
   [e["home"] for e in ex["worst"]])

hist = AN.history(LOG)
ck("7 the record is newest-first and carries the match id for the link",
   len(hist) == 5 and hist[0]["match_id"] == "4" and hist[-1]["match_id"] == "5",
   [e["match_id"] for e in hist])
ck("8 an unscored prediction never enters the record", "9" not in [e["match_id"] for e in hist])

# ---------------------------------------------------------------- 2 the page
tmp = tempfile.mkdtemp()
B.DIST = tmp
acc = AN.accuracy(LOG)
url = B.prediction_history_page(LOG, acc)
page = open(os.path.join(tmp, "predictions.html"), encoding="utf-8").read()
ck("9 the page is written and returns its url", url == "/predictions.html" and len(page) > 3000)
ck("10 every scored prediction is a row in the HTML (the record is complete)",
   page.count('data-hit="') == 5 and page.count('data-hit="0"') == 3, page.count('data-hit="0"'))
ck("11 the naive baseline sits next to our hit rate, not hidden",
   "معيار ساذج" in page and "إصابة الاتجاه" in page)
ck("12 the misses column is rendered with the same heading weight as the hits",
   "أخطأ النموذج وهو واثق" in page and "أصاب النموذج وهو واثق" in page
   and page.count("<h3>") >= 2)
# five matches make fifteen probability statements - no band reaches ten, so
# the calibration table must NOT be drawn at all rather than drawn on noise
ck("13 a sample this small draws no calibration table", 'id="calibration"' not in page)
BIG = dict(LOG)
for i in range(30):
    k, v = entry(100 + i, f"h{i}", f"a{i}", 0.55, 0.25, 0.20,
                 (2 if i % 3 else 0), (0 if i % 3 else 1), kick="2026-09-08")
    BIG[k] = v
tmp2 = tempfile.mkdtemp(); B.DIST = tmp2
B.prediction_history_page(BIG, AN.accuracy(BIG))
big = open(os.path.join(tmp2, "predictions.html"), encoding="utf-8").read()
ck("13b with enough statements the calibration table appears, with its ECE",
   'id="calibration"' in big and "ECE" in big and "حدث فعلًا" in big)
B.DIST = tmp
ck("14 a small competition sample is flagged", "عيّنة صغيرة" in page)
ck("15 the two models are shown apart and explicitly NOT as a race",
   "ليست مباراة بين النموذجين" in page and "نموذج Oracle" in page)
ck("16 the limits are stated (start date, retention, sample, no betting)",
   "حدود هذا السجل" in page and "150 يومًا" in page
   and "ليست نصيحة للمراهنة" in page)
# the site publishes extensionless URLs (2026-09-01); write() rewrites the
# links, so the row must point at /m/1 and not /m/1.html
ck("17 rows link to their match page, extensionless", 'href="/m/1"' in page
   and 'href="/m/1.html"' not in page)
ck("18 the page carries FAQ structured data", '"@type": "FAQPage"' in page)
ck("19 no betting language beyond the disclaimer",
   not any(w in page for w in ("أودز", "توصية مراهنة", "نصيحة مراهنة", "bet365", "رهانات مضمونة")))
ck("20 the filter script ships with the page", "pf-chip" in page and "عرض المزيد" in page)

# --------------------------------------------------- 2b the score reads right
# «النتيجة متشقلبة» (user, 2026-09-16): "2-0" between two names in an RTL row
# is ONE left-to-right bidi run, so the home number lands next to the AWAY
# club - الأهلي 0-2 أبو قير for a 2-0 home win. The old dir="ltr" forced that
# reversal even where Arabic names would otherwise have fixed it. The cure is
# score_pill(): two elements in an inline-flex box, ordered by the RTL flow.
AR = dict([entry(7, "الأهلي", "أبو قير للأسمدة", 0.67, 0.20, 0.13, 2, 0,
                 comp="Egyptian Premier League", kick="2026-09-13")])
tmp3 = tempfile.mkdtemp(); B.DIST = tmp3
B.prediction_history_page(dict(BIG, **AR), AN.accuracy(dict(BIG, **AR)))
arp = open(os.path.join(tmp3, "predictions.html"), encoding="utf-8").read()
B.DIST = tmp
ck("22 the record's score is a pill, not a glued bidi run",
   '<b class="sc-in"><span>2</span><i>-</i><span>0</span></b>' in arp)
ck("23 no dir=\"ltr\" is forced on a score anywhere on the page",
   'dir="ltr">2-0' not in arp and 'dir="ltr">3-0' not in arp)
ck("24 the confident-calls cards use the same pill",
   arp.count('class="sc-in"') >= 2 and "قلنا" in arp)
ck("26 no rule turns a .tl table cell into a flex box (the timeline is .mtl)",
   ".tl{display:flex" not in B.CSS and ".mtl{display:flex" in B.CSS
   and ".ptable .tl{text-align:start}" in B.CSS)
ck("27 the record is a day-grouped list, and every day appears once",
   arp.count('class="rec-day"') == len({e["kickoff"] for e in AN.history(dict(BIG, **AR))})
   and 'id="predlist"' in arp and "<table" not in arp.split('id="record"')[1].split("</section>")[0],
   arp.count('class="rec-day"'))
ck("27b the verdict leads the item and the pick says which side won",
   'class="rec-v"' in arp and "قلنا <b>فوز الأهلي</b>" in arp)
ck("27c the filter hides a day header once its matches are filtered out",
   "days.forEach" in B.PRED_FILTER_JS and "dataset.day" in B.PRED_FILTER_JS
   and 'id="pf-none"' in arp)
rec_sec = arp.split('id="record"')[1].split("</section>")[0]
ck("28 no score is printed as bare text in the record - every one is a pill",
   rec_sec.count('class="sc-in') >= 2 and not re.search(r">\s*\d+-\d+\s*<", rec_sec),
   re.findall(r">\s*\d+-\d+\s*<", rec_sec)[:3])
ck("25 the pill's CSS ships - inline-flex IS the fix",
   ".sc-in{display:inline-flex" in B.CSS.replace(",.sc-in{", ";.sc-in{")
   or ".sc-in{display:inline-flex" in B.CSS
   or ".tk-s,.sc-in{display:inline-flex" in B.CSS)

# ---------------------------------------------------------------- 3 silence
ck("21 nothing scored yet -> no page at all",
   B.prediction_history_page({"9": LOG["9"]}, AN.accuracy({"9": LOG["9"]})) is None)

print()
print(f"{len(fails)} FAILED: {', '.join(fails)}" if fails else "ALL PREDICTION-HISTORY TESTS PASSED")
sys.exit(1 if fails else 0)
