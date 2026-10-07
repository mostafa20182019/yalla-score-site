#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Closing betting odds as a BENCHMARK for backtest.py (2026-10-07, step 3 of
the model plan). Never an input to the model, never shown on the site.

WHY: the literature's honest ceiling. Closing odds are the most accurate
public forecast of a football match; a good statistical model sits a few
percent behind them in RPS/Brier. Knowing OUR gap says how much any factor
could possibly still win - and stops us chasing a 0.002 improvement when the
whole distance to the market is 0.02.

Source: football-data.co.uk season CSVs (free; big five + Turkey; closing
odds AvgCH/AvgCD/AvgCA, Bet365 closing as the fallback). Cached under
data/odds/ (gitignored) - a manual research tool, not part of any workflow.
Probabilities = 1/odds normalised to sum 1 (the simple margin removal).

Matching to our matches (football-data.org names: "Manchester United FC" vs
"Man United"): same league, kick-off date +-1 day, the EXACT final score,
then the best name similarity among those - a date + score pair almost always
leaves one candidate, and the names only break the rare tie.

    python odds_bench.py --fetch 2627 2526     # download the season files
"""
import csv
import datetime
import difflib
import io
import os
import re
import sys
import unicodedata
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, "data", "odds")
URL = "https://www.football-data.co.uk/mmz4281/{season}/{div}.csv"
DIVS = {"E0": "Premier League", "SP1": "Primera Division", "I1": "Serie A",
        "D1": "Bundesliga", "F1": "Ligue 1"}
# Turkey (T1) exists there too, but our Turkish matches carry Arabic names
# (365scores) - no reliable bridge to the English ones, so it is left out.
CLOSING = (("AvgCH", "AvgCD", "AvgCA"), ("B365CH", "B365CD", "B365CA"),
           ("PSCH", "PSCD", "PSCA"), ("AvgH", "AvgD", "AvgA"))
STOP = {"fc", "afc", "cf", "sc", "ac", "as", "ssc", "club", "de", "del", "la", "le", "1", "fk",
        "sv", "vfb", "vfl", "tsg", "rcd", "ca", "cd", "ud", "sd", "rc", "us", "ogc", "stade", "real", "hove"}


def fetch(seasons, divs=DIVS):
    os.makedirs(DIR, exist_ok=True)
    for s in seasons:
        for d in divs:
            req = urllib.request.Request(URL.format(season=s, div=d), headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
            with open(os.path.join(DIR, f"{s}-{d}.csv"), "wb") as f:
                f.write(body)
            print(f"  {s}-{d}: {len(body)} bytes")


def _date(s):
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _probs(row):
    for cols in CLOSING:
        try:
            o = [float(row[c]) for c in cols]
        except (KeyError, ValueError, TypeError):
            continue
        if min(o) <= 1.0:
            continue
        inv = [1 / x for x in o]
        t = sum(inv)
        return {"H": inv[0] / t, "D": inv[1] / t, "A": inv[2] / t}, cols[0][:-1]
    return None, None


def load(seasons):
    """{comp: [{date, home, away, hs, as, probs, src}]} from the cached files."""
    out = {}
    for s in seasons:
        for d, comp in DIVS.items():
            p = os.path.join(DIR, f"{s}-{d}.csv")
            if not os.path.exists(p):
                continue
            with open(p, encoding="utf-8-sig", errors="replace") as f:
                for row in csv.DictReader(io.StringIO(f.read())):
                    dt = _date(row.get("Date") or "")
                    pr, src = _probs(row)
                    try:
                        hs, as_ = int(row["FTHG"]), int(row["FTAG"])
                    except (KeyError, ValueError, TypeError):
                        continue
                    if dt and pr:
                        out.setdefault(comp, []).append({"date": dt, "home": row["HomeTeam"], "away": row["AwayTeam"],
                                                         "hs": hs, "as": as_, "probs": pr, "src": src})
    return out


def _toks(name):
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " ").replace("'", "").replace(".", " ").replace("-", " ")
    return [t for t in re.split(r"\s+", s) if t and t not in STOP]


def _sim(a, b):
    ta, tb = _toks(a), _toks(b)
    if not ta or not tb:
        return 0.0
    seq = difflib.SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()
    pre = max((1.0 if x.startswith(y[:4]) or y.startswith(x[:4]) else 0.0) for x in ta for y in tb)
    return max(seq, 0.6 * pre + 0.4 * seq)


def match(rows, odds):
    """{row key: market probs} for replay rows (backtest.run) that have odds.
    key = (comp, date, home, away) as backtest builds it."""
    idx = {}
    for comp, games in odds.items():
        for g in games:
            idx.setdefault((comp, g["date"]), []).append(g)
    out = {}
    for r in rows:
        try:
            d = datetime.date.fromisoformat(r["date"])
        except (KeyError, ValueError, TypeError):
            continue
        hs, as_ = (int(x) for x in r["score"].split("-"))
        comp = r["comp"].split(" (")[0]      # backtest tags last season "Premier League (2025/26)"
        cands = [g for k in (-1, 0, 1) for g in idx.get((comp, d + datetime.timedelta(days=k)), [])
                 if g["hs"] == hs and g["as"] == as_]
        if not cands:
            continue
        best = max(cands, key=lambda g: _sim(r["home"], g["home"]) + _sim(r["away"], g["away"]))
        if _sim(r["home"], best["home"]) + _sim(r["away"], best["away"]) < 0.9:
            continue
        out[(r["comp"], r["date"], r["home"], r["away"])] = best["probs"]
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--fetch" in sys.argv:
        fetch([a for a in sys.argv[sys.argv.index("--fetch") + 1:] if a.isdigit()] or ["2627", "2526"])
    else:
        print(__doc__)
