r"""The Egyptian national team in the ticker + the home live card (2026-09-27).

    python tests/test_egypt_nt.py      (from the repo root)

The trap this pins: the token «مصر» is a SUBSTRING of «المصري» (Al Masry), and
the ticker matches tokens by substring. The national-team competition scope
(NT_SCOPE) is what keeps Al Masry's league games out - these checks fail the
day someone drops the scope "because Egypt only plays Egypt games".
Also: the home card's entry is scoped to 365scores competition 588 (the card
matches names EXACTLY and by competition id), and the national team's results
are NOT posted to Facebook as result cards (not part of the ask).
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

src = open("fb_cards.py", encoding="utf-8").read()
ck("9 the national team's results are not posted as Facebook result cards",
   "in NT_SCOPE" in src and "from site_lib.clubs import NT_SCOPE" in src)

print()
print("FAILED:" if fails else "all national-team checks passed", ", ".join(fails))
sys.exit(1 if fails else 0)
