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
import site_lib.predictions as SL                          # noqa: E402

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
for comp, raw in (("Primera Division", ("Real Madrid CF", "FC Barcelona", "Club Atlético de Madrid")),
                  ("Serie A", ("FC Internazionale Milano", "AC Milan", "Juventus FC", "SSC Napoli", "AS Roma", "SS Lazio")),
                  ("Ligue 1", ("Paris Saint-Germain FC", "Olympique Lyonnais", "Olympique de Marseille", "AS Monaco FC"))):
    ck(f"{comp}: the asked clubs, in ar_team's spellings", SP.HUB_FOCUS.get(comp) == tuple(ar_team(n) for n in raw),
       SP.HUB_FOCUS.get(comp))
ck("Saudi: the big four (Al-Ahli = Jeddah, scoped to this league)",
   SP.HUB_FOCUS.get("Saudi Pro League") == ("الهلال", "النصر", "الاتحاد", "الأهلي"))
ck("Turkey: the big four in the feed's spellings",
   SP.HUB_FOCUS.get("Turkish Super Lig") == ("غلطة سراي", "بشكتاش", "طرابزون سبور", "فنربخشة"))
ck("Ligue 1: Paris FC is not PSG", ar_team("Paris FC") not in SP.HUB_FOCUS["Ligue 1"])
# league pages list the current/next round (2026-10-07)
def mm(mid, rnd, day, t="18:00", comp="Egyptian Premier League"):
    return {"match_id": mid, "competition": comp, "round": rnd, "kickoff": day, "koff_time": t}
preds = {str(i): {"x": i} for i in range(1, 10)}
up = [mm(1, 6, "2026-10-13", "20:00"), mm(2, 6, "2026-10-13", "17:00"), mm(3, 7, "2026-10-19"),
      mm(4, 7, "2026-10-20"), mm(5, 5, "2026-10-28"),           # a postponed round-5 game re-dated late
      mm(6, 6, "2026-10-14"), mm(7, 7, "2026-10-20", comp="Premier League")]
r, rows = SL.next_round("Egyptian Premier League", up, preds)
ck("round still being played: its remaining matches, earliest first", r == 6 and [m["match_id"] for m, _ in rows] == [2, 1, 6], (r, rows))
r2, rows2 = SL.next_round("Egyptian Premier League", [m for m in up if m["round"] != 6], preds)
ck("round over: the next one - a postponed game dated later does not capture the page",
   r2 == 7 and [m["match_id"] for m, _ in rows2] == [3, 4], (r2, rows2))
ck("other competitions never mix in", all(m["competition"] == "Egyptian Premier League" for m, _ in rows))
ck("a match without a prediction is left out", [m["match_id"] for m, _ in SL.next_round(
   "Egyptian Premier League", up, {"1": {}, "6": {}})[1]] == [1, 6])
ck("no round numbers -> (None, None): the page keeps the 14-day list",
   SL.next_round("CAF Champions League", [mm(8, None, "2026-10-12", comp="CAF Champions League")], preds) == (None, None))
ck("no fixtures -> (None, None)", SL.next_round("Serie A", up, preds) == (None, None))
ltpl = io.open("site_src/templates/analysis_league.html", encoding="utf-8").read()
ck("the league page heading names the round", "توقعات مباريات الجولة {{ round_no }} من {{ label }}" in ltpl)

src = io.open("site_pages/predictions.py", encoding="utf-8").read()
ck("the hub filters by exact membership (home OR away)",
   'ar_team(m.get("home")) in focus or ar_team(m.get("away")) in focus' in src)
ck("the «all predictions» link shows whenever something was held back",
   "if len(shown) < len(rows) and c in COMP_SLUG" in src)
tpl = io.open("site_src/templates/analysis.html", encoding="utf-8").read()
ck("a week without focus matches says so instead of an empty list", "لا مباريات هذا الأسبوع لـ{{ w.focus }}" in tpl)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
