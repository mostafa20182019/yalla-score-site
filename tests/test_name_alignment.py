# -*- coding: utf-8 -*-
"""football-data club names vs 365scores' Arabic spellings (2026-11-04).

The live layer (LIVE_JS), the scorer lines and the cards find a game by its
Arabic NAME PAIR. On the Champions League night of 2026-11-04 four matches
stayed on «- - -» until full time: AR_TEAM had no Arabic name for Shakhtar,
Feyenoord and Slovan, and spelled Galatasaray «جالطة سراي» where the feed
says «جلطة سراي». fetch_data.check_name_alignment() now warns on the run.

Run from the site root:  python tests/test_name_alignment.py   (network-free)
"""
import os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import fetch_data as F
from site_lib.names import ar_team

fails = []
def ok(n, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + n + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(n)


# what 365scores called them on 2026-11-04 (games/results, competition 572)
FEED = ["فاينورد", "إنتر ميلان", "جلطة سراي", "شتوتجارت", "شاختار دونيتسك",
        "سبورتنج لشبونة", "لاسك لينز", "سلوفان براتيسلافا", "بورتو", "أيك أثينا",
        "سلافيا براغ", "برشلونة", "أستون فيلا"]
FD = {"Feyenoord Rotterdam": "فاينورد", "Galatasaray SK": "جلطة سراي",
      "FK Shakhtar Donetsk": "شاختار دونيتسك", "Sporting Clube de Portugal": "سبورتنج لشبونة",
      "ŠK Slovan Bratislava": "سلوفان براتيسلافا", "FC Porto": "بورتو",
      "PAE AEK": "أيك أثينا", "SK Slavia Praha": "سلافيا براغ"}

# 1. the eight clubs of that night carry the feed's spelling
for t, want in FD.items():
    ok(f"1 AR_TEAM[{t}] = «{want}»", ar_team(t) == want, ar_team(t))

# 2-4. the check, against a stubbed feed
calls = []
def fake(path):
    calls.append(path)
    return {"games": [{"homeCompetitor": {"name": FEED[i]},
                       "awayCompetitor": {"name": FEED[i + 1]}}
                      for i in range(0, len(FEED) - 1, 2)]}
F._s365 = fake
F.time.sleep = lambda s: None
UCL = "UEFA Champions League"
ms = [{"competition": UCL, "home": "Galatasaray SK", "away": "VfB Stuttgart"},
      {"competition": UCL, "home": "Feyenoord Rotterdam", "away": "FC Internazionale Milano"},
      {"competition": "Egyptian Premier League", "home": "الأهلي", "away": "الزمالك"}]
ok("2 today's names: nothing to report", F.check_name_alignment(ms) == [])
ok("3 only football-data competitions are asked about (one per comp, fixtures+results)",
   len(calls) == 2 and all("competitions=572" in c for c in calls), calls)
import site_lib.clubs as C
C.AR_TEAM["Galatasaray SK"] = "جالطة سراي"
bad = F.check_name_alignment(ms)
ok("4 the old Galatasaray spelling is reported", bad == [(UCL, "Galatasaray SK", "جالطة سراي")], bad)
C.AR_TEAM["Galatasaray SK"] = "جلطة سراي"

# 5. an empty feed reply reports nothing (no false alarm when 365 is down)
F._s365 = lambda p: {"games": []}
ok("5 an empty feed says nothing", F.check_name_alignment(ms) == [])

# 6. _name_key is the same normalisation as norm() in LIVE_JS
js = open("site_src/snippets/live_js.html", encoding="utf-8").read()
ok("6 LIVE_JS norm() still folds أإآ/ة/ى and strips dots, quotes, spaces",
   "replace(/[أإآ]/g,'ا')" in js and "replace(/ة/g,'ه').replace(/ى/g,'ي').replace(/[.'’]/g,'').replace(/\\s+/g,'')" in js)
ok("6b _name_key folds the same way", F._name_key("أيك  أثينا.") == F._name_key("ايك اثينا")
   and F._name_key("جلطة سراى") == F._name_key("جلطه سراي"))

print()
if fails:
    print(f"{len(fails)} FAILED: " + ", ".join(fails)); sys.exit(1)
print("ALL NAME-ALIGNMENT TESTS PASSED")
