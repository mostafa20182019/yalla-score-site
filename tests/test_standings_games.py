# -*- coding: utf-8 -*-
"""«لعب / ف / ت / خ» on /standings open the team's matches (2026-11-01).

Run from the site root:  python tests/test_standings_games.py

The user: «عايز ارقام الخاصة ب لعب و فاز وتعادل وخسر تكون لينكات ولما نضغط
عليها يجيب المباريات دى». The rule that makes it safe: a team's four numbers
become buttons ONLY when the matches we hold give the same four numbers - a
«لعب 10» that opens four matches is worse than a plain number. Checking that
rule on the real data found a match counted twice (an id stored as a number in
one file and as text in another, the club respelt in between).
"""
import os, re, sys, glob
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
from site_lib.tables import standings_table, team_results, team_key
import analysis as AN

fails = []
def ok(n, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + n + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(n)


def g(mid, h, a, hs, as_, day):
    return {"match_id": mid, "home": h, "away": a, "home_score": hs, "away_score": as_,
            "kickoff": day, "status": "FINISHED", "competition": "X"}


games = [g(1, "A", "B", 2, 0, "2026-10-01"), g(2, "B", "C", 1, 1, "2026-10-08"),
         g(3, "C", "A", 0, 0, "2026-10-15"), g(4, "A", "C", 1, 3, "2026-10-22")]
res = team_results(games)
ok("1 results from each side: A won, drew, lost in kick-off order",
   [x for _, x in res["A"]] == ["w", "d", "l"], res["A"])
ok("2 0-0 counts as a draw for both (0 is a score, not «missing»)",
   ("d" in [x for _, x in res["C"]]) and len(res["C"]) == 3)

rows = [{"pos": 1, "team": "A", "played": 3, "won": 1, "draw": 1, "lost": 1, "pts": 4},
        {"pos": 2, "team": "B", "played": 3, "won": 0, "draw": 1, "lost": 1, "pts": 1}]
html = standings_table("X", rows, embedded=True, games=games,
                       pages=lambda m: m["match_id"] if m["match_id"] != 3 else None)
ok("3 a team whose numbers match gets buttons", 'data-tn="A"' in html and 'data-k="w"' in html)
ok("4 a team whose numbers do NOT match stays plain (B: table says 3 played, we hold 2)",
   'data-tn="B"' not in html)
ok("5 a zero is never a button (nothing to open)",
   html.count('class="lt-n"') == 4)  # A: played, won, draw, lost - all non-zero
ok("6 each match is stored once, linked when it has a page, plain when not",
   len(re.findall(r'class="lgm" data-id="1"', html)) == 1
   and '<div class="lgm" data-id="3"' in html and 'href="/m/4"' in html)
ok("6b only the clickable teams' matches are stored (B-C is nobody's list)",
   'data-id="2"' not in html)
ok("7 without games the table is unchanged (match page, club pages)",
   "lt-n" not in standings_table("X", rows, embedded=True) and "lt-games" not in
   standings_table("X", rows, embedded=True))

ok("8 one club under two spellings is ONE team for the count",
   team_key("غلطة سراي") == team_key("جلطة سراي"))

# the duplicate: same match, id as number in fixtures and as text in the archive,
# club respelt in between - season_matches must keep ONE
fx = [{"competition": "X", "rounds": [{"round": 1, "matches": [
    dict(g(4764313, "جلطة سراي", "قاسم باشا", 3, 1, "2026-10-09"))]}]}]
arch = [dict(g("4764313", "غلطة سراي", "قاسم باشا", 3, 1, "2026-10-09"))]
ok("9 an id stored as 4764313 and as \"4764313\" is the same match",
   len(AN.season_matches(fx, arch)["X"]) == 1)

# the built pages: no popup link may point at a page that does not exist
pages = sorted(glob.glob("dist/standings/*.html"))
if pages:
    dead = [(os.path.basename(f), u) for f in pages
            for u in re.findall(r'<a class="lgm" data-id="\d+" href="(/m/\d+)"',
                                open(f, encoding="utf-8").read())
            if not os.path.exists("dist" + u + ".html")]
    ok("10 every match link in the popups opens a real /m page", not dead, dead[:3])
    eg = open("dist/standings/egypt.html", encoding="utf-8").read()
    ok("11 the script ships with the page", "lt-pop" in eg and "data-gm" in eg)

print("\nALL STANDINGS-GAMES TESTS PASSED" if not fails else f"\n{len(fails)} FAILED")
sys.exit(1 if fails else 0)
