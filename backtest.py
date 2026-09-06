"""Walk-forward backtest for the Yalla Score prediction model (تحليلات).

Answers one question with numbers instead of opinion: **does a proposed change
actually predict better than what is live?**

Method — strictly no look-ahead. Matches are replayed per competition in
chronological order; for match i the model is rebuilt from matches[:i] ONLY
(that is why team_stats/league_params are recomputed each step rather than
carried forward: it guarantees the training set never contains the match being
predicted). The prediction is then scored against the real result.

Metrics
  hit      — share of matches whose most likely outcome was the real one
  brier    — mean sum over {H,D,A} of (p - actual)^2. 0 = perfect,
             0.667 = uniform 1/3 guessing. LOWER IS BETTER; this is the number
             to judge a change by (it grades the probabilities, not just the pick)
  logloss  — mean -ln(p assigned to the real outcome). Punishes confident misses
             much harder than brier; a second opinion on the same question
  calib    — mean |predicted - observed| over probability buckets: are the
             numbers honest (does "60%" happen 60% of the time)?

Baselines it must beat to be worth anything:
  always-home  — pick home every time, at the training set's base rates
  base-rates   — the league's own home/draw/away frequencies, ignoring the clubs
  uniform      — 1/3 each

Usage
  python backtest.py                    # live model vs baselines, overall + per league
  python backtest.py --calib            # add the calibration table
  python backtest.py --variants         # compare candidate factors/params
  python backtest.py --sweep prior      # scan one constant (prior|k|hfa|goalexp)
  python backtest.py --min-prior 2      # require N prior matches per club
  python backtest.py --json out.json

Adding a candidate: write a function in VARIANTS that returns a config dict
(params override and/or a `factor` callable). A factor gets
(match, ctx) and returns (mult_home, mult_away) applied to the expected goals —
so it can only move the numbers the live model already produces, never bypass
them. Ship it ONLY if it lowers brier AND logloss on a sample big enough to
mean something (see the warning printed under the results).
"""
import argparse
import collections
import copy
import datetime
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analysis as A

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    p = os.path.join(HERE, "data", name)
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    return d["results"][0]["items"] if isinstance(d, dict) and "results" in d else d


def outcome(hs, aw):
    return "H" if hs > aw else "D" if hs == aw else "A"


# ---------------------------------------------------------------- club-wide context
def rest_index(bycomp):
    """(team, kickoff) -> days since that club's previous match in ANY
    competition. Congestion is club-wide, so it cannot be read per league."""
    pool, seen = [], set()
    for ms in bycomp.values():
        for m in ms:
            k = m.get("match_id") or (m["home"], m["away"], m["kickoff"])
            if k not in seen:
                seen.add(k)
                pool.append(m)
    pool.sort(key=lambda m: (m["kickoff"], m.get("koff_time") or ""))
    idx, last = {}, {}
    for m in pool:
        d = datetime.date.fromisoformat(m["kickoff"])
        for t in (m["home"], m["away"]):
            if t in last:
                idx[(t, m["kickoff"])] = (d - last[t]).days
            last[t] = d
    return idx


def absence_index(details, comp_of, min_prior=2, core_rate=0.6, replacement=6.3):
    """((comp, club), date) -> 0..1 'how much of the usual XI is missing today'.

    A club's regulars are the players who started >= core_rate of its EARLIER
    matches; today's XI is compared against them and each missing regular is
    weighted by how far his average rating sits above replacement level, so
    losing a 7.6 starter counts more than losing a 6.4 one.

    Clubs are keyed by (competition, name) on purpose: «الأهلي» is both Al Ahly
    of Egypt and Al-Ahli of Saudi in the feed, and keying by name alone mixed
    their squads — every Egyptian regular then looked absent (score 1.00) in a
    Saudi match. Same class of bug as the favourite-club card, 2026-08-22.

    Only useful once clubs have several stored lineups; returns None while a
    club has fewer than min_prior earlier ones.
    """
    det = [e for e in (details or [])
           if (e.get("lineups") or {}).get("h", {}).get("xi")
           and (e.get("lineups") or {}).get("a", {}).get("xi")
           and comp_of(e.get("home"), e.get("away"), e.get("date"))]
    det.sort(key=lambda e: e["date"])
    hist, xi_at, rating = collections.defaultdict(list), {}, {}
    for e in det:
        comp = comp_of(e["home"], e["away"], e["date"])
        for side, club in (("h", e["home"]), ("a", e["away"])):
            key = (comp, club)
            xi = e["lineups"][side]["xi"]
            aids = {p["aid"] for p in xi}
            xi_at[(key, e["date"])] = aids
            hist[key].append((e["date"], aids))
            for p in xi:
                if p.get("rt") is not None:
                    rating.setdefault((key, p["aid"]), []).append(float(p["rt"]))

    def weight(key, aid):
        rs = rating.get((key, aid)) or [replacement + 0.5]
        return max(0.0, sum(rs) / len(rs) - replacement)

    out = {}
    for (key, date), today in xi_at.items():
        prior = [a for d, a in hist[key] if d < date]
        if len(prior) < min_prior:
            continue
        cnt = collections.Counter(a for s in prior for a in s)
        core = {a for a, n in cnt.items() if n / len(prior) >= core_rate}
        if not core:
            out[(key, date)] = 0.0
            continue
        tot = sum(weight(key, a) for a in core) or 1.0
        out[(key, date)] = sum(weight(key, a) for a in core - today) / tot
    return out


def f_absence(alpha=0.25, beta=0.15):
    """User's idea (2026-09-06): once the XI is published (~1h before kick-off)
    a club missing its regulars — or getting them back — should move the numbers.
    A club with absence score s scores less (x 1-alpha*s) and concedes more
    (opponent x 1+beta*s)."""
    def f(m, ctx):
        ai, comp = ctx.get("absence") or {}, m.get("_comp")
        sh = ai.get(((comp, m["home"]), m["kickoff"]), 0.0)
        sa = ai.get(((comp, m["away"]), m["kickoff"]), 0.0)
        return ((1 - alpha * sh) * (1 + beta * sa),
                (1 - alpha * sa) * (1 + beta * sh))
    return f


def red_index(details):
    """(team, date) -> players sent off in that club's match on that date, so a
    factor can ask 'did this club have a man sent off in its previous game?'"""
    idx = collections.defaultdict(list)
    for e in details or []:
        for c in e.get("cards") or []:
            if c.get("color") == "r":
                club = e["home"] if c.get("side") == "h" else e["away"]
                idx[(club, e.get("date"))].append(c.get("player"))
    return idx


# ---------------------------------------------------------------- scoring
class Score:
    def __init__(self):
        self.n = 0
        self.hits = 0
        self.brier = 0.0
        self.logloss = 0.0
        self.buckets = collections.defaultdict(lambda: [0, 0.0, 0])  # n, sum_p, hits

    def add(self, probs, real):
        self.n += 1
        pick = max(probs, key=probs.get)
        self.hits += pick == real
        self.brier += sum((probs[k] - (1.0 if k == real else 0.0)) ** 2 for k in "HDA")
        self.logloss += -math.log(max(probs[real], 1e-9))
        for k in "HDA":
            b = self.buckets[min(9, int(probs[k] * 10))]
            b[0] += 1
            b[1] += probs[k]
            b[2] += (k == real)

    def calib(self):
        """mean |predicted - observed| across non-empty probability buckets."""
        tot = err = 0
        for n, sp, hit in self.buckets.values():
            if n >= 10:
                err += abs(sp / n - hit / n) * n
                tot += n
        return (err / tot) if tot else float("nan")

    def row(self):
        if not self.n:
            return None
        return {"n": self.n, "hit": self.hits / self.n, "brier": self.brier / self.n,
                "logloss": self.logloss / self.n, "calib": self.calib()}


# ---------------------------------------------------------------- the replay
def run(bycomp, cfg, min_prior=1, min_league=5, ctx=None, only_active=False):
    """Walk-forward replay. Returns (overall Score, {comp: Score}, [rows])."""
    saved = {k: getattr(A, k) for k in ("PRIOR_TEAM", "PRIOR_LEAGUE", "ELO_K",
                                        "ELO_HFA", "ELO_GOAL_EXP", "DEF_HOME_MU",
                                        "DEF_AWAY_MU")}
    for k, v in (cfg.get("params") or {}).items():
        setattr(A, k, v)
    factor = cfg.get("factor")
    overall, per, rows = Score(), collections.defaultdict(Score), []
    try:
        for comp, ms in bycomp.items():
            for i, m in enumerate(ms):
                train = ms[:i]
                if len(train) < min_league:
                    continue
                stats = A.team_stats({comp: train})[comp]
                h, a = stats.get(m["home"]), stats.get(m["away"])
                if not h or not a or h["played"] < min_prior or a["played"] < min_prior:
                    continue          # cold start: no history for one of the clubs
                params = A.league_params(train)
                lh, la, _, _ = A.lambdas(stats, params, m["home"], m["away"])
                moved = False
                if factor:
                    fh, fa = factor(dict(m, _comp=comp), ctx or {})
                    moved = abs(fh - 1) > 1e-9 or abs(fa - 1) > 1e-9
                    lh, la = lh * fh, la * fa
                if only_active and not moved:
                    continue
                p = A.outcome_from_lambdas(lh, la)
                probs = {"H": p["ph"], "D": p["pd"], "A": p["pa"]}
                real = outcome(m["home_score"], m["away_score"])
                overall.add(probs, real)
                per[comp].add(probs, real)
                rows.append({"comp": comp, "date": m["kickoff"], "home": m["home"],
                             "away": m["away"], "real": real, "probs": probs,
                             "score": f'{m["home_score"]}-{m["away_score"]}'})
    finally:
        for k, v in saved.items():
            setattr(A, k, v)
    return overall, per, rows


def run_baselines(bycomp, min_prior=1, min_league=5):
    """Same match set as run(), scored by the three reference strategies."""
    out = {"always-home": Score(), "base-rates": Score(), "uniform": Score()}
    for comp, ms in bycomp.items():
        for i, m in enumerate(ms):
            train = ms[:i]
            if len(train) < min_league:
                continue
            stats = A.team_stats({comp: train})[comp]
            h, a = stats.get(m["home"]), stats.get(m["away"])
            if not h or not a or h["played"] < min_prior or a["played"] < min_prior:
                continue
            pr = A.league_params(train)
            real = outcome(m["home_score"], m["away_score"])
            hw, dr = pr["home_win"] or 0.45, pr["draw"] or 0.27
            aw = max(1e-6, 1 - hw - dr)
            out["base-rates"].add({"H": hw, "D": dr, "A": aw}, real)
            out["always-home"].add({"H": 0.999, "D": 0.0005, "A": 0.0005}, real)
            out["uniform"].add({"H": 1 / 3, "D": 1 / 3, "A": 1 / 3}, real)
    return out


# ---------------------------------------------------------------- candidates
def f_rest(threshold=3, penalty=0.92):
    """Congestion: a club playing again within `threshold` days scores less.
    Measured 2026-09-06 on 245 team-matches: congested clubs OVERperformed their
    own Elo expectation by +0.040 (SE ±0.090) — indistinguishable from zero, and
    the raw points/match advantage was pure selection bias (only strong clubs
    play every 3 days). Kept as the worked example of a REJECTED candidate."""
    def f(m, ctx):
        ri = ctx.get("rest") or {}
        rh, ra = ri.get((m["home"], m["kickoff"])), ri.get((m["away"], m["kickoff"]))
        return (penalty if rh is not None and rh <= threshold else 1.0,
                penalty if ra is not None and ra <= threshold else 1.0)
    return f


def f_red(penalty=0.90):
    """Suspension proxy: a club that had a man sent off in its previous match is
    missing him now. Coverage is thin (33 reds in 211 matches), so expect a tiny
    sample of affected matches — read the `n affected` line before believing it."""
    def f(m, ctx):
        reds, prev = ctx.get("reds") or {}, ctx.get("prev_date") or {}
        out = []
        for t in (m["home"], m["away"]):
            d = prev.get((t, m["kickoff"]))
            out.append(penalty if d and reds.get((t, d)) else 1.0)
        return tuple(out)
    return f


VARIANTS = {
    "live": lambda: {},
    "no-elo-nudge": lambda: {"params": {"ELO_GOAL_EXP": 1e9}},
    "no-shrinkage": lambda: {"params": {"PRIOR_TEAM": 0.0}},
    "heavy-shrinkage": lambda: {"params": {"PRIOR_TEAM": 10.0}},
    "elo-k-15": lambda: {"params": {"ELO_K": 15.0}},
    "elo-k-40": lambda: {"params": {"ELO_K": 40.0}},
    "hfa-0": lambda: {"params": {"ELO_HFA": 0.0}},
    "rest-penalty": lambda: {"factor": f_rest()},
    "absence": lambda: {"factor": f_absence()},
    "absence-strong": lambda: {"factor": f_absence(0.45, 0.30)},
    "red-card-penalty": lambda: {"factor": f_red()},
}

SWEEPS = {
    "prior": ("PRIOR_TEAM", [0, 2, 3, 5, 8, 12, 20]),
    "k": ("ELO_K", [10, 18, 28, 40, 60]),
    "hfa": ("ELO_HFA", [0, 35, 70, 110]),
    "goalexp": ("ELO_GOAL_EXP", [3, 4.5, 6, 9, 1e9]),
}


# ---------------------------------------------------------------- reporting
def fmt(name, r, ref=None):
    if not r:
        return f"{name:<18}       no matches"
    d = ""
    if ref and ref["n"]:
        gap = ref["brier"] - r["brier"]
        d = f"  {gap:+.4f} vs live" + ("  ✔ better" if gap > 0 else "  ✘ worse" if gap < 0 else "")
    return (f"{name:<18} n={r['n']:<4} hit={r['hit'] * 100:5.1f}%  brier={r['brier']:.4f}  "
            f"logloss={r['logloss']:.4f}  calib={r['calib']:.3f}{d}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", action="store_true")
    ap.add_argument("--sweep", choices=sorted(SWEEPS))
    ap.add_argument("--calib", action="store_true")
    ap.add_argument("--min-prior", type=int, default=1)
    ap.add_argument("--min-league", type=int, default=5)
    ap.add_argument("--probe", help="factor name whose active matches define the --only-active subset")
    ap.add_argument("--only-active", action="store_true",
                    help="score ONLY the matches a candidate factor actually moves")
    ap.add_argument("--json")
    args = ap.parse_args()

    bycomp = A.season_matches(load("fixtures.json"), load("matches_archive.json"))
    details = load("match_details.json")
    comp_idx = {}
    for comp, ms in bycomp.items():
        for m in ms:
            comp_idx[(m["home"], m["away"], m["kickoff"])] = comp
    ctx = {"rest": rest_index(bycomp), "reds": red_index(details),
           "absence": absence_index(details, lambda h, a, d: comp_idx.get((h, a, d)))}
    prev = {}
    last = {}
    pool = sorted({(m.get("match_id") or (m["home"], m["away"], m["kickoff"])): m
                   for ms in bycomp.values() for m in ms}.values(),
                  key=lambda m: (m["kickoff"], m.get("koff_time") or ""))
    for m in pool:
        for t in (m["home"], m["away"]):
            if t in last:
                prev[(t, m["kickoff"])] = last[t]
            last[t] = m["kickoff"]
    ctx["prev_date"] = prev

    total = sum(len(v) for v in bycomp.values())
    print(f"pool: {total} finished matches in {len(bycomp)} competitions "
          f"(walk-forward: each prediction is trained only on earlier matches)")
    print(f"filters: league needs >= {args.min_league} prior matches, "
          f"each club >= {args.min_prior}\n")

    live, per, rows = run(bycomp, {}, args.min_prior, args.min_league, ctx)
    lr = live.row()
    if not lr:
        print("Not enough history yet to score anything — come back after more rounds.")
        return
    base = run_baselines(bycomp, args.min_prior, args.min_league)
    print("=== model vs baselines (brier: LOWER is better)")
    print(fmt("live model", lr))
    for k, v in base.items():
        print(fmt(k, v.row(), lr))

    print("\n=== per competition")
    for comp, s in sorted(per.items(), key=lambda kv: -kv[1].n):
        print(fmt(comp[:18], s.row()))

    if args.calib:
        print("\n=== calibration (all H/D/A probabilities pooled)")
        print(f'{"bucket":>10} {"n":>5} {"predicted":>10} {"observed":>9}')
        for b in sorted(live.buckets):
            n, sp, hit = live.buckets[b]
            if n >= 10:
                print(f'{b * 10:>4}-{b * 10 + 10:<5} {n:5} {sp / n * 100:9.1f}% {hit / n * 100:8.1f}%')

    ref = None
    if args.variants:
        ref = lr
        if args.only_active:
            # A factor that leaves 80% of matches untouched has its effect diluted
            # to nothing when scored over all of them. --only-active scores just
            # the matches the probe factor actually moves, and rebuilds the live
            # reference over that same subset so the comparison stays like-for-like.
            probe = VARIANTS[args.probe or "absence"]()
            moved = run(bycomp, probe, args.min_prior, args.min_league, ctx, True)[2]
            keys = {(r["comp"], r["date"], r["home"], r["away"]) for r in moved}
            sub = Score()
            for r in rows:
                if (r["comp"], r["date"], r["home"], r["away"]) in keys:
                    sub.add(r["probs"], r["real"])
            ref = sub.row()
            print(f"\n(subset: the {ref['n'] if ref else 0} matches "
                  f"'{args.probe or 'absence'}' actually moves)")
        print("\n=== candidates (ship one ONLY if brier AND logloss both improve)")
        print(fmt("live", ref))
        for name, mk in VARIANTS.items():
            if name == "live":
                continue
            s, _, _ = run(bycomp, mk(), args.min_prior, args.min_league, ctx, args.only_active)
            print(fmt(name, s.row(), ref))

    if args.sweep:
        key, values = SWEEPS[args.sweep]
        print(f"\n=== sweep {key} (current live value: {getattr(A, key)})")
        for v in values:
            s, _, _ = run(bycomp, {"params": {key: v}}, args.min_prior, args.min_league, ctx)
            print(fmt(f"{key}={v}", s.row(), lr))

    # the warning must describe the sample actually scored above, not the full
    # pool: with --only-active the comparison ran on a much smaller subset and
    # quoting 145 there would understate the noise it has to beat.
    n_ref = (ref or lr)["n"]
    print(f"\nSample warning: {n_ref} scored matches. A brier difference smaller than "
          f"~{0.9 / math.sqrt(n_ref):.4f} is inside the noise of this sample — "
          "do not ship a change on it. Re-run as the season grows.")

    if args.json:
        json.dump({"live": lr, "per": {c: s.row() for c, s in per.items()},
                   "baselines": {k: v.row() for k, v in base.items()},
                   "rows": rows}, open(args.json, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("wrote", args.json)


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    main()
