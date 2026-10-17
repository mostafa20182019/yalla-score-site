r"""The Egyptian national team in the ticker + the home live card (2026-09-27).

    python tests/test_egypt_nt.py      (from the repo root)

The trap this pins: the token «مصر» is a SUBSTRING of «المصري» (Al Masry), and
the ticker matches tokens by substring. The national-team competition scope
(NT_SCOPE) is what keeps Al Masry's league games out - these checks fail the
day someone drops the scope "because Egypt only plays Egypt games".
Also: the home card's entry is scoped to 365scores competition 588 (the card
matches names EXACTLY and by competition id), and the national team's results
get Facebook result cards like the curated clubs (switched on 2026-09-27).
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
from site_lib import ticker as T                                  # noqa: E402
from site_lib.clubs import NT_SCOPE, TICKER_TEAMS                 # noqa: E402
from site_lib.names import _is_ticker_team, fav_club_names         # noqa: E402

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


AFQ = "Africa Cup of Nations Qualification"
nt = {"match_id": "1", "home": "جنوب السودان", "away": "مصر", "competition": AFQ,
      "kickoff": "2099-09-29", "koff_time": "16:00", "status": "UPCOMING"}
masry = {"match_id": "2", "home": "القناة", "away": "المصري", "competition": "Egyptian Premier League",
         "kickoff": "2099-10-11", "koff_time": "17:00", "status": "UPCOMING"}
youth = dict(nt, match_id="3", competition="U-20 Africa Cup of Nations", away="مصر")

ck("1 the national team is a ticker team, scoped to national-team competitions",
   ("مصر", NT_SCOPE) in TICKER_TEAMS and AFQ in NT_SCOPE)
ck("2 an Egypt AFCON-qualifier match counts", _is_ticker_team(nt))
ck("3 Al Masry («المصري» contains «مصر») does NOT", not _is_ticker_team(masry))
ck("4 an Egypt match outside the scope (a youth tournament) does not", not _is_ticker_team(youth))
ck("5 no club competition is in the national-team scope",
   not set(NT_SCOPE) & {"Egyptian Premier League", "CAF Champions League", "Saudi Pro League"})

html = T.make_ticker([nt, masry])
ck("6 the ticker shows the Egypt match and not Al Masry's",
   'data-a="مصر"' in html and "المصري" not in html)

fav = fav_club_names([], [])
ck("7 the home live card gets Egypt scoped to 365scores competition 588",
   {"n": "مصر", "c": 588} in fav, [e for e in fav if "مصر" in e["n"]])
ck("8 ... and no UNscoped «مصر» entry (c=None would match any competition)",
   not any(e["n"] == "مصر" and e["c"] is None for e in fav))

import fb_cards as F                                              # noqa: E402
fin = dict(nt, status="FINISHED", home_score=0, away_score=2)
fin_masry = dict(masry, status="FINISHED", home_score=1, away_score=1)
ck("9 the national team's results get Facebook result cards (user ask 2026-09-27)",
   F.finished_matches([fin]) == [fin])
ck("10 ... and Al Masry's still do not", F.finished_matches([fin_masry]) == [])

# the Libyan namesake (2026-10-17): «الأهلي طرابلس» in the CAF Confederation
# Cup must never be the Egyptian club's match - Arabic tokens match exactly
CC = "CAF Confederation Cup"
ck("11 «الأهلي» (exact) in the Confederation Cup is the curated club",
   _is_ticker_team({"home": "كيتارا", "away": "الأهلي", "competition": CC}))
ck("12 «الأهلي طرابلس» in the same competition is NOT",
   not _is_ticker_team({"home": "جامعة ويلوالو أديجرات", "away": "الأهلي طرابلس", "competition": CC}))
ck("13 the European tokens still match as substrings (football-data names)",
   _is_ticker_team({"home": "FC Barcelona", "away": "Getafe CF", "competition": "Primera Division"}))
from site_lib.names import _team_match                               # noqa: E402
from site_lib.clubs import TEAM_PAGES                                # noqa: E402
ahly = next(tp for tp in TEAM_PAGES if tp["slug"] == "al-ahly")
ck("14 the club page matcher agrees (Tripoli out, Egypt in)",
   _team_match(ahly, {"home": "الأهلي", "away": "كيتارا", "competition": CC})
   and not _team_match(ahly, {"home": "الأهلي طرابلس", "away": "كيتارا", "competition": CC}))

print()
print("FAILED:" if fails else "all national-team checks passed", ", ".join(fails))
sys.exit(1 if fails else 0)
