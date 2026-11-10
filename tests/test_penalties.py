r"""Penalty shoot-outs on the site (2026-11-10).

    python tests/test_penalties.py

The user, on Wadi Degla 0-0 Kahraba Ismailia (Egypt Cup): «المباراة دى ظاهرة
انها تعادل مع انها مباراة كاس لازم حد يفوز ... عايز ضربات الجزاء تظهر وتظهر
لها نتيجة». 365scores sends each competitor's `penaltyScore`; football-data
sends score.penalties and folds them into fullTime. The row shows the kicks
under the score in the same «home - away» order; the match page's title,
description and FAQ name the shoot-out.
"""
import os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import fetch_data as F                                     # noqa: E402
import results_archive as RA                               # noqa: E402
from site_lib.tables import match_row                      # noqa: E402

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

# ---------------------------------------------------------------- 365scores
h, a = {"score": 0.0, "penaltyScore": 2.0}, {"score": 0.0, "penaltyScore": 3.0}
ck("1 365scores: the competitors' penaltyScore become home_pens / away_pens",
   F.s365_pens(h, a, "FINISHED") == {"home_pens": 2, "away_pens": 3})
ck("2 no shoot-out (missing or -1) and a live game: nothing",
   F.s365_pens({"score": 1}, {"score": 0}, "FINISHED") == {}
   and F.s365_pens({"penaltyScore": -1}, {"penaltyScore": -1}, "FINISHED") == {}
   and F.s365_pens(h, a, "LIVE") == {})

# ---------------------------------------------------------------- football-data
pso = {"duration": "PENALTY_SHOOTOUT", "fullTime": {"home": 5, "away": 4},
       "regularTime": {"home": 1, "away": 1}, "extraTime": {"home": 0, "away": 0},
       "penalties": {"home": 4, "away": 3}}
ck("3 football-data: a shoot-out's score is regular + extra time, not fullTime (which adds the kicks)",
   F.fd_score(pso) == (1, 1, {"home_pens": 4, "away_pens": 3}), F.fd_score(pso))
ck("4 without regularTime the kicks are taken back out of fullTime",
   F.fd_score({k: v for k, v in pso.items() if k not in ("regularTime", "extraTime")}) == (1, 1, {"home_pens": 4, "away_pens": 3}))
ck("5 a normal match: fullTime, no pens", F.fd_score({"duration": "REGULAR", "fullTime": {"home": 2, "away": 1}}) == (2, 1, {}))

# ---------------------------------------------------------------- archive
row = {"match_id": 1, "competition": "Egypt Cup", "kickoff": "2026-11-09", "koff_time": "17:00",
       "home": "وادي دجلة", "away": "كهرباء الاسماعيلية", "home_score": 0, "away_score": 0,
       "round": None, "home_pens": 2, "away_pens": 3}
ck("6 the results archive keeps the kicks", RA._row(row).get("home_pens") == 2 and RA._row(row).get("away_pens") == 3)
ck("7 and a match without them keeps no empty pens keys",
   "home_pens" not in RA._row({k: v for k, v in row.items() if "pens" not in k}))

# ---------------------------------------------------------------- the row
html = match_row(dict(row, status="FINISHED"), show_time=True, show_comp=False)
ck("8 the row shows «ترجيح 2 - 3» under the score, home first like the score",
   '<span class="mpen" title="ركلات الترجيح">ترجيح <b>2 - 3</b></span>' in html
   and html.index('class="score"') < html.index('class="mpen"'), html[:400])
ck("9 no shoot-out, no line", "mpen" not in match_row(dict(row, status="FINISHED", home_pens=None, away_pens=None)))

# ---------------------------------------------------------------- page text
mp = open("site_pages/matches.py", encoding="utf-8").read()
ck("10 the match page title and description name the shoot-out",
   '{hs}-{as_}{_pens} — {comp}' in mp and '{_pen_win}. مسجلو' in mp and "بركلات الترجيح" in mp)
rd = open("site_lib/reads.py", encoding="utf-8").read()
ck("11 the FAQ's «كم انتهت» answer names the winner on penalties", "بركلات الترجيح" in rd and "{_pen}." in rd)

print(f"\n{len(fails)} FAILED" if fails else "\nALL OK")
sys.exit(1 if fails else 0)
