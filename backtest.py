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
  python backtest.py --pool prev        # last season (big five, ~1,750 matches) instead
  python backtest.py --pool both        # this season + last season together
  python backtest.py --odds             # model vs closing odds (odds_bench.py --fetch first)

THE VERDICT IS PAIRED (2026-10-07). Every candidate is compared with the live
model match by match on the SAME matches, and the mean difference gets a
bootstrap 95% interval. The old rule ("beat 0.9/sqrt(n)") compared two noisy
totals and so needed a gap of ~0.05 - bigger than any published effect of a
single factor (0.003-0.02). A paired difference cancels the noise both models
share (a shock result hurts both), so a real 0.005 can now show. Ship a change
only when the interval for BOTH brier and logloss sits entirely below zero.

"live" is the model the site runs: the same pool as site_lib.model.model_core
(fixtures + the frozen results archive + matches_archive) and the season
carry-over Elo seeds. Until 2026-10-07 it ran without the seeds and without
the results archive, i.e. a slightly different model than production.

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
import random
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
            k = A.fixture_key(m)
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


def absence_index(details, comp_of):
    """((comp, club), date) -> 0..1 'how much of the usual XI is missing today'.
    Thin wrapper over analysis.SquadIndex so the harness and the live site score
    absences with exactly the same definition (see that class for the rules and
    for why clubs are keyed by competition as well as name)."""
    sq = A.SquadIndex(details, comp_of)
    out = {}
    for (key, date) in sq.xi:
        r = sq.report(key[0], key[1], date)
        if r is not None:
            out[(key, date)] = r["score"]
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
        """Score one match; returns its (brier, logloss) for the paired test."""
        self.n += 1
        pick = max(probs, key=probs.get)
        self.hits += pick == real
        mb = sum((probs[k] - (1.0 if k == real else 0.0)) ** 2 for k in "HDA")
        mll = -math.log(max(probs[real], 1e-9))
        self.brier += mb
        self.logloss += mll
        for k in "HDA":
            b = self.buckets[min(9, int(probs[k] * 10))]
            b[0] += 1
            b[1] += probs[k]
            b[2] += (k == real)
        return mb, mll

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
    seeds = cfg.get("seeds")          # {comp: {club: starting Elo}} - season carry-over
    overall, per, rows = Score(), collections.defaultdict(Score), []
    try:
        for comp, ms in bycomp.items():
            for i, m in enumerate(ms):
                train = ms[:i]
                if len(train) < min_league:
                    continue
                stats = A.team_stats({comp: train}, seeds)[comp]
                h, a = stats.get(m["home"]), stats.get(m["away"])
                if not h or not a or h["played"] < min_prior or a["played"] < min_prior:
                    continue          # cold start: no history for one of the clubs
                if cfg.get("stats"):
                    # a candidate that changes what the attack/defence indices
                    # are built from (xG instead of goals, recent matches
                    # weighted more) - it gets the training matches and returns
                    # a modified COPY of the club stats; Elo is left alone
                    stats = cfg["stats"](stats, train, m)
                params = A.league_params(train)
                lh, la, _, _ = A.lambdas(stats, params, m["home"], m["away"])
                moved = False
                if factor:
                    fh, fa = factor(dict(m, _comp=comp), ctx or {})
                    moved = abs(fh - 1) > 1e-9 or abs(fa - 1) > 1e-9
                    lh, la = lh * fh, la * fa
                if only_active and not moved:
                    continue
                p = (cfg["grid"](lh, la) if cfg.get("grid")
                     else A.outcome_from_lambdas(lh, la))
                probs = {"H": p["ph"], "D": p["pd"], "A": p["pa"]}
                real = outcome(m["home_score"], m["away_score"])
                # the exact scoreline the model called, for the score-hit rate
                # (the metric Dixon-Coles is supposed to move)
                top = (p.get("top") or [(None, None, 0)])[0]
                called = f"{top[0]}-{top[1]}"
                mb, mll = overall.add(probs, real)
                per[comp].add(probs, real)
                rows.append({"comp": comp, "date": m["kickoff"], "home": m["home"],
                             "away": m["away"], "real": real, "probs": probs,
                             "called": called, "brier": mb, "ll": mll,
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


def carry(shrink):
    """Season carry-over seeds (roadmap factor 1) at a given shrink toward 1500.
    Needs data/season_prev/*.json (season_carry.py --fetch on the runner)."""
    import season_carry
    seeds, _ = season_carry.seeds_from_raw(shrink=shrink)
    if not seeds:
        print("  ! no data/season_prev files - carry-over variant runs with flat 1500")
    return {"seeds": seeds}


# ---- step 4 candidates (2026-10-07): xG, time decay ----------------------
_XG = None


def xg_index():
    """{match_id: (home xG, away xG)} from data/match_stats.json."""
    global _XG
    if _XG is None:
        import match_stats
        _XG = {mid: (r["h"]["xg"], r["a"]["xg"]) for mid, r in match_stats.load().items()
               if r.get("status") == "ok" and "xg" in (r.get("h") or {}) and "xg" in (r.get("a") or {})}
    return _XG


def f_xg(w):
    """Attack/defence from a blend of goals and xG: on every training match that
    has xG, a club's goals for/against are replaced by w*xG + (1-w)*goals.
    w=1 is pure xG. The league means stay on goals (the model's scale)."""
    def hook(stats, train, m):
        xi = xg_index()
        acc = {}
        for t in train:
            x = xi.get(str(t.get("match_id")))
            if not x:
                continue
            hs, as_ = int(t["home_score"]), int(t["away_score"])
            for club, xf, xa, gf, ga in ((t["home"], x[0], x[1], hs, as_), (t["away"], x[1], x[0], as_, hs)):
                d = acc.setdefault(club, [0.0, 0.0])
                d[0] += w * (xf - gf)
                d[1] += w * (xa - ga)
        out = {}
        for club, st in stats.items():
            d = acc.get(club)
            out[club] = dict(st, gf=st["gf"] + d[0], ga=st["ga"] + d[1]) if d else st
        return out
    return {"stats": hook}


def f_decay(half_days):
    """Attack/defence with older matches weighted down: weight 0.5**(age/half).
    `played` becomes the weight sum, so the shrinkage prior counts it too."""
    def hook(stats, train, m):
        d0 = datetime.date.fromisoformat(m["kickoff"][:10])
        acc = {}
        for t in train:
            wt = 0.5 ** ((d0 - datetime.date.fromisoformat(t["kickoff"][:10])).days / half_days)
            hs, as_ = int(t["home_score"]), int(t["away_score"])
            for club, gf, ga in ((t["home"], hs, as_), (t["away"], as_, hs)):
                d = acc.setdefault(club, [0.0, 0.0, 0.0])
                d[0] += wt * gf
                d[1] += wt * ga
                d[2] += wt
        return {club: (dict(st, gf=acc[club][0], ga=acc[club][1], played=acc[club][2]) if club in acc else st)
                for club, st in stats.items()}
    return {"stats": hook}


def dixon_coles(rho):
    """Dixon & Coles (1997) low-score correction, as a grid hook.

    An independent Poisson treats the two scorelines as unrelated, and the
    literature (and our own record) says it underrates the low draws. tau
    multiplies four cells before renormalising:

        (0,0): 1 - lh*la*rho      (1,1): 1 - rho
        (0,1): 1 + lh*rho         (1,0): 1 + la*rho

    A NEGATIVE rho therefore lifts 0-0 and 1-1 and lowers 1-0 and 0-1. Dixon
    and Coles fitted about -0.13 on English league data.

    Why this matters to us: over the 209 scored predictions to 2026-09-19 the
    live model named a draw ONCE while 54 matches (25.8%) were drawn - the
    draw is almost never the single highest cell in an independent Poisson,
    so a quarter of all matches are unreachable for the direction metric."""
    def grid(lh, la):
        lh, la = max(0.15, min(lh, 4.5)), max(0.15, min(la, 4.5))
        ph = pd = pa = over25 = btts = 0.0
        cells = []
        for i in range(A.MAX_GOALS + 1):
            for j in range(A.MAX_GOALS + 1):
                q = A._pois(lh, i) * A._pois(la, j)
                if i == 0 and j == 0:
                    q *= 1 - lh * la * rho
                elif i == 0 and j == 1:
                    q *= 1 + lh * rho
                elif i == 1 and j == 0:
                    q *= 1 + la * rho
                elif i == 1 and j == 1:
                    q *= 1 - rho
                q = max(q, 0.0)                  # tau can go negative for extreme rho
                cells.append((q, i, j))
                if i > j: ph += q
                elif i == j: pd += q
                else: pa += q
                if i + j >= 3: over25 += q
                if i and j: btts += q
        tot = ph + pd + pa or 1.0
        cells.sort(reverse=True)
        return {"ph": ph / tot, "pd": pd / tot, "pa": pa / tot, "lh": lh, "la": la,
                "top": [(i, j, q / tot) for q, i, j in cells[:3]],
                "over25": over25 / tot, "btts": btts / tot}
    return grid


VARIANTS = {
    "live": lambda: {},
    "carry-over": lambda: carry(1 / 3),          # keep 2/3 of last season's edge (the proposal)
    "carry-over-half": lambda: carry(0.5),
    "carry-over-full": lambda: carry(0.0),       # no regression to the mean at all
    "carry-over-light": lambda: carry(2 / 3),
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
    # roadmap factor 2 - the draw correction, tested 2026-09-20
    "dixon-coles": lambda: {"grid": dixon_coles(-0.13)},      # the literature value
    # step 4 (2026-10-07) - xG needs data/match_stats.json, THIS season only
    "xg-25": lambda: f_xg(0.25),
    "xg-50": lambda: f_xg(0.5),
    "xg-75": lambda: f_xg(0.75),
    "xg-100": lambda: f_xg(1.0),
    "decay-60d": lambda: f_decay(60),
    "decay-120d": lambda: f_decay(120),
    "decay-240d": lambda: f_decay(240),
    "dc-05": lambda: {"grid": dixon_coles(-0.05)},
    "dc-10": lambda: {"grid": dixon_coles(-0.10)},
    "dc-18": lambda: {"grid": dixon_coles(-0.18)},
    "dc-25": lambda: {"grid": dixon_coles(-0.25)},
}

SWEEPS = {
    "prior": ("PRIOR_TEAM", [0, 2, 3, 5, 8, 12, 20]),
    "league-prior": ("PRIOR_LEAGUE", [0, 5, 10, 20, 40, 80]),   # how hard each league's home/away means are pulled to 1.5/1.2
    "k": ("ELO_K", [10, 18, 28, 40, 60]),
    "hfa": ("ELO_HFA", [0, 35, 70, 110]),
    "goalexp": ("ELO_GOAL_EXP", [3, 4.5, 6, 9, 1e9]),
}


# ---------------------------------------------------------------- the paired verdict
def _key(r):
    return (r["comp"], r["date"], r["home"], r["away"])


def paired(ref_rows, cand_rows, n_boot=2000, seed=7):
    """Candidate minus reference, match by match, on the matches BOTH scored.
    Negative = the candidate is better. Returns the mean differences with a
    bootstrap 95% interval (seeded: the same data gives the same verdict)."""
    ref = {_key(r): r for r in ref_rows}
    pairs = [(c["brier"] - ref[_key(c)]["brier"], c["ll"] - ref[_key(c)]["ll"])
             for c in cand_rows if _key(c) in ref]
    n = len(pairs)
    if n < 2:
        return None
    rng = random.Random(seed)
    boot_b, boot_l = [], []
    for _ in range(n_boot):
        sb = sl = 0.0
        for _ in range(n):
            x = pairs[rng.randrange(n)]
            sb += x[0]
            sl += x[1]
        boot_b.append(sb / n)
        boot_l.append(sl / n)
    boot_b.sort()
    boot_l.sort()
    lo, hi = int(0.025 * n_boot), int(0.975 * n_boot) - 1
    out = {"n": n, "moved": sum(1 for p in pairs if abs(p[0]) > 1e-12),
           "brier": sum(p[0] for p in pairs) / n, "brier_lo": boot_b[lo], "brier_hi": boot_b[hi],
           "ll": sum(p[1] for p in pairs) / n, "ll_lo": boot_l[lo], "ll_hi": boot_l[hi]}
    if out["brier_hi"] < 0 and out["ll_hi"] < 0:
        out["verdict"] = "BETTER (both intervals below 0) - shippable"
    elif out["brier_lo"] > 0 and out["ll_lo"] > 0:
        out["verdict"] = "WORSE (both intervals above 0)"
    else:
        out["verdict"] = "no proven difference"
    return out


def fmt_paired(pr):
    if not pr:
        return "    paired: no common matches"
    return (f"    paired on {pr['n']} ({pr['moved']} moved): brier {pr['brier']:+.4f} [{pr['brier_lo']:+.4f}, {pr['brier_hi']:+.4f}]  "
            f"logloss {pr['ll']:+.4f} [{pr['ll_lo']:+.4f}, {pr['ll_hi']:+.4f}]  -> {pr['verdict']}")


PREV_TAG = " (2025/26)"


def prev_pool():
    """Last season (big five, data/season_prev - season_carry.py) in the
    replay's shape. Its competitions carry PREV_TAG so they never collide with
    this season's, and the season seeds never apply to them."""
    import season_carry
    out = {}
    for comp, ms in season_carry.load_prev().items():
        rows = [{"competition": comp + PREV_TAG, "kickoff": m["date"], "home": m["home"], "away": m["away"],
                 "home_score": m["home_score"], "away_score": m["away_score"], "status": "FINISHED"}
                for m in ms if m.get("home_score") is not None]
        out[comp + PREV_TAG] = sorted(rows, key=lambda m: m["kickoff"])
    return out


def season_pool():
    """THIS season exactly as site_lib.model.model_core builds it."""
    import results_archive as RA
    return A.season_matches(load("fixtures.json"), RA.season_rows(RA.load()) + load("matches_archive.json"))


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
    ap.add_argument("--pool", choices=("season", "prev", "both"), default="season")
    ap.add_argument("--odds", action="store_true", help="score the live model against closing odds")
    ap.add_argument("--boot", type=int, default=2000, help="bootstrap resamples for the paired verdict")
    args = ap.parse_args()

    bycomp = {}
    if args.pool in ("season", "both"):
        bycomp.update(season_pool())
    if args.pool in ("prev", "both"):
        bycomp.update(prev_pool())
    # the site's model: season carry-over seeds (keyed by this season's
    # competition names, so they never touch the tagged previous-season pool)
    LIVE = {"seeds": A.load_elo_seeds() or None}
    details = load("match_details.json")
    comp_idx = {}
    for comp, ms in bycomp.items():
        for m in ms:
            comp_idx[(m["home"], m["away"], m["kickoff"])] = comp
    ctx = {"rest": rest_index(bycomp), "reds": red_index(details),
           "absence": absence_index(details, lambda h, a, d: comp_idx.get((h, a, d)))}
    prev = {}
    last = {}
    pool = sorted({A.fixture_key(m): m
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

    live, per, rows = run(bycomp, LIVE, args.min_prior, args.min_league, ctx)
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
        print("\n=== candidates (ship one ONLY if the PAIRED intervals of brier AND logloss are both below 0)")
        print(fmt("live", ref))
        for name, mk in VARIANTS.items():
            if name == "live":
                continue
            cfg = mk()
            cfg.setdefault("seeds", LIVE["seeds"])     # a candidate changes ONE thing
            s, _, crows = run(bycomp, cfg, args.min_prior, args.min_league, ctx, args.only_active)
            print(fmt(name, s.row(), ref))
            print(fmt_paired(paired(rows, crows, args.boot)))

    if args.sweep:
        key, values = SWEEPS[args.sweep]
        print(f"\n=== sweep {key} (current live value: {getattr(A, key)})")
        for v in values:
            s, _, crows = run(bycomp, {"params": {key: v}, "seeds": LIVE["seeds"]},
                              args.min_prior, args.min_league, ctx)
            print(fmt(f"{key}={v}", s.row(), lr))
            print(fmt_paired(paired(rows, crows, args.boot)))

    if args.odds:
        import odds_bench as OB
        mk = OB.match(rows, OB.load(["2627", "2526"]))
        print(f"\n=== live model vs CLOSING ODDS (benchmark only - never an input), "
              f"{len(mk)} matches with odds")
        if mk:
            ms_, os_ = Score(), Score()
            mrows, orows = [], []
            for r in rows:
                pr = mk.get(_key(r))
                if not pr:
                    continue
                ms_.add(r["probs"], r["real"])
                b, ll = os_.add(pr, r["real"])
                mrows.append(r)
                orows.append(dict(r, brier=b, ll=ll))
            print(fmt("live model", ms_.row()))
            print(fmt("closing odds", os_.row()))
            print("    model minus market:" + fmt_paired(paired(orows, mrows, args.boot))[len("    paired"):])
            print("    (positive = the market is better; that gap is the most any factor could still win)")

    # the warning must describe the sample actually scored above, not the full
    # pool: with --only-active the comparison ran on a much smaller subset and
    # quoting 145 there would understate the noise it has to beat.
    n_ref = (ref or lr)["n"]
    print(f"\nSample: {n_ref} scored matches. Two UNPAIRED totals would need a gap of "
          f"~{0.9 / math.sqrt(n_ref):.4f} to mean anything; judge candidates by the paired "
          "intervals above instead (both brier and logloss entirely below 0).")

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
