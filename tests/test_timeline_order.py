r"""«أحداث المباراة» reads newest first (user, 2026-11-06).

    python tests/test_timeline_order.py

«عايز تقلب احداث المباراة ... الدقايق تبدأ من تحت»: the last minute at the
top, kick-off at the bottom, like a live feed. Stoppage time sorts inside its
half (45+2 above 45, below 46) and events of the same minute keep their order.
"""
import os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
from site_lib.tables import match_details_html          # noqa: E402

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

ev = {
    "goals": [{"side": "h", "player": "لوكاس كوبلير", "minute": "14"},
              {"side": "a", "player": "هدف الوقت المحتسب", "minute": "45+2"}],
    "cards": [{"side": "a", "player": "نوح سافيولو", "minute": "27", "color": "y"},
              {"side": "h", "player": "جوردي ماكينجو", "minute": "84", "color": "y"}],
    "subs": [{"side": "h", "in": "فيليب تروي", "out": "لوكاس كوبلير", "minute": "87"},
             {"side": "a", "in": "بنيامين بوشواري", "out": "مصطفى اسكيهلاك", "minute": "87"},
             {"side": "a", "in": "أوزان توفان", "out": "باتيستا ميندي", "minute": "46"}],
}
html = match_details_html(ev, False, "فريق أ", "فريق ب")
mins = re.findall(r'<div class="tl-m"><span dir="ltr">([^<]+)′</span></div>', html)
ck("1 the timeline starts with the LAST minute and ends with the first",
   mins and mins[0] == "87" and mins[-1] == "14", mins)
ck("2 every row is at or before the one above it",
   mins == ["87", "87", "84", "46", "45+2", "27", "14"], mins)
ck("3 stoppage time sits inside its half: 45+2 below 46, above 27",
   mins.index("46") < mins.index("45+2") < mins.index("27"), mins)
_87 = [m.start() for m in re.finditer("فيليب تروي|بنيامين بوشواري", html)]
ck("4 two events of the same minute keep their order (home sub, then away sub)",
   len(_87) == 2 and html.index("فيليب تروي") < html.index("بنيامين بوشواري"))

print(f"\n{len(fails)} FAILED" if fails else "\nALL OK")
sys.exit(1 if fails else 0)
