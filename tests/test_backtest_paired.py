r"""The paired verdict + the odds benchmark (backtest.py / odds_bench.py, 2026-10-07).

    python tests/test_backtest_paired.py   (from the repo root)

Pure: synthetic replay rows, a hand-written odds table. Pins: the paired
interval says BETTER only when both brier and logloss are below zero, the
seed makes it reproducible, identical models are "no proven difference";
odds become probabilities with the margin removed; a match finds its odds by
league + date (+-1) + exact score + names, and a wrong score finds nothing;
the backtest's "live" is the site's model (seeds + the model_core pool).
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


import datetime                                             # noqa: E402
import backtest as BT                                       # noqa: E402
import odds_bench as OB                                     # noqa: E402

s = BT.Score()
mb, mll = s.add({"H": 0.5, "D": 0.3, "A": 0.2}, "H")
ck("Score.add returns the match's brier and logloss", abs(mb - 0.38) < 1e-9 and abs(mll - 0.6931) < 1e-3, (mb, mll))


def rows(n, shift_b=0.0, shift_l=0.0, wobble=0.0):
    return [{"comp": "X", "date": f"2026-09-{i % 28 + 1:02d}", "home": f"h{i}", "away": f"a{i}",
             "brier": 0.6 + shift_b + (wobble if i % 2 else -wobble), "ll": 1.0 + shift_l + (wobble if i % 2 else -wobble)}
            for i in range(n)]


ref = rows(300)
same = BT.paired(ref, rows(300), n_boot=300)
ck("identical models: zero difference, not shippable", same["brier"] == 0 and "no proven" in same["verdict"], same)
better = BT.paired(ref, rows(300, -0.004, -0.006, wobble=0.01), n_boot=300)
ck("a small CONSISTENT gain is proven (the old 0.9/sqrt(n) rule needed 0.052)", better["verdict"].startswith("BETTER"), better)
half = BT.paired(ref, rows(300, -0.004, +0.006, wobble=0.01), n_boot=300)
ck("better brier but worse logloss is NOT shippable", not half["verdict"].startswith("BETTER"), half)
noisy = BT.paired(ref, rows(300, -0.004, -0.006, wobble=0.2), n_boot=300)
ck("the same gain drowned in noise is not proven", "no proven" in noisy["verdict"], noisy)
ck("seeded: the same data gives the same interval",
   BT.paired(ref, rows(300, -0.004, -0.006, wobble=0.05), n_boot=200) ==
   BT.paired(ref, rows(300, -0.004, -0.006, wobble=0.05), n_boot=200))
part = BT.paired(ref, rows(300)[:120], n_boot=100)
ck("only matches BOTH scored are compared", part["n"] == 120)

pr, src = OB._probs({"AvgCH": "2.00", "AvgCD": "3.50", "AvgCA": "4.00"})
ck("odds -> probabilities sum to 1, margin removed", abs(sum(pr.values()) - 1) < 1e-9 and pr["H"] > pr["D"] > pr["A"] and src == "AvgC")
ck("closing missing -> falls back to Bet365 closing", OB._probs({"B365CH": "2.1", "B365CD": "3.4", "B365CA": "3.6"})[1] == "B365C")
ck("no usable odds -> None", OB._probs({"AvgCH": "", "AvgCD": "x"})[0] is None)

odds = {"Premier League": [
    {"date": datetime.date(2026, 9, 20), "home": "Fulham", "away": "Man United", "hs": 1, "as": 1, "probs": {"H": .3, "D": .3, "A": .4}},
    {"date": datetime.date(2026, 9, 20), "home": "Chelsea", "away": "Brighton", "hs": 1, "as": 1, "probs": {"H": .6, "D": .25, "A": .15}},
    {"date": datetime.date(2025, 10, 4), "home": "Nott'm Forest", "away": "Wolves", "hs": 2, "as": 0, "probs": {"H": .5, "D": .3, "A": .2}}]}
r1 = {"comp": "Premier League", "date": "2026-09-20", "home": "Fulham FC", "away": "Manchester United FC", "score": "1-1"}
r2 = {"comp": "Premier League (2025/26)", "date": "2025-10-05", "home": "Nottingham Forest FC",
      "away": "Wolverhampton Wanderers FC", "score": "2-0"}
r3 = dict(r1, score="2-1")
got = OB.match([r1, r2, r3], odds)
ck("same date + score: the names pick Fulham-Man United, not Chelsea-Brighton",
   got.get(BT._key(r1)) == {"H": .3, "D": .3, "A": .4}, got)
ck("last season's tagged league + a date one day off still matches", BT._key(r2) in got)
ck("a different score finds nothing", OB.match([r3], odds) == {})

src = io.open("backtest.py", encoding="utf-8").read()
ck("live = the site's model: carry-over seeds + the model_core pool (results archive included)",
   'LIVE = {"seeds": A.load_elo_seeds() or None}' in src and "RA.season_rows(RA.load())" in src
   and "run(bycomp, LIVE," in src)
ck("a candidate keeps the live seeds unless it brings its own", 'cfg.setdefault("seeds", LIVE["seeds"])' in src)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
