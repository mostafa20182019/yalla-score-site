r"""/analysis hub: the Egyptian league shows only the focus clubs (2026-10-07).

    python tests/test_hub_focus.py   (from the repo root)

User ask: on the hub, only الأهلي / الزمالك / بيراميدز / المصري fixtures for the
Egyptian league; the rest one click away («كل توقعات الدوري المصري»). Names
are matched exactly - «الأهلي» must not pull in «البنك الاهلي».
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


import site_pages.predictions as SP                        # noqa: E402

f = SP.HUB_FOCUS.get("Egyptian Premier League")
ck("the four focus clubs", f == ("الأهلي", "الزمالك", "بيراميدز", "المصري"), f)
ck("exact names: «البنك الاهلي» is not a focus club", "البنك الاهلي" not in f)
e = SP.HUB_FOCUS.get("Premier League")
ck("England: the big six, in the site's Arabic spellings",
   e == ("أرسنال", "ليفربول", "تشيلسي", "مانشستر يونايتد", "مانشستر سيتي", "توتنهام هوتسبر"), e)
from site_lib.names import ar_team                          # noqa: E402
ck("England: every name is what ar_team returns for the football-data club",
   [ar_team(n) for n in ("Arsenal FC", "Liverpool FC", "Chelsea FC", "Manchester United FC",
                         "Manchester City FC", "Tottenham Hotspur FC")] == list(e))
src = io.open("site_pages/predictions.py", encoding="utf-8").read()
ck("the hub filters by exact membership (home OR away)",
   'ar_team(m.get("home")) in focus or ar_team(m.get("away")) in focus' in src)
ck("the «all predictions» link shows whenever something was held back",
   "more = len(rows) if len(shown) < len(rows)" in src)
tpl = io.open("site_src/templates/analysis.html", encoding="utf-8").read()
ck("a week without focus matches says so instead of an empty list", "لا مباريات هذا الأسبوع لـ{{ w.focus }}" in tpl)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
