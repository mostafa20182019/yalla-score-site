"""Yalla Score data-analysis layer (تحليلات): team strength model, match
outcome probabilities, prediction log + accuracy, player insights.

Pure computation on the JSON files fetch_data.py already produces — no network,
no invented numbers. build_site.py imports this and renders /analysis pages and
the «توقع يلا سكور» block on match pages.

Model (documented on the site's «كيف يعمل النموذج» section):
  * strength   — Elo per competition over this season's finished matches
                 (fixtures rounds ∪ matches archive, deduped, chronological;
                 start 1500, K=28, home advantage +70).
  * scoring    — Poisson goals: attack/defence indices per team = goals for/
                 against per match relative to the league mean, shrunk toward
                 the mean with a 5-match prior so 2-3 early matches cannot make
                 a club look invincible; league home/away means shrunk toward
                 1.5/1.2 with a 20-match prior.
  * outcome    — expected goals λ_home/λ_away = league side mean × attack ×
                 opponent defence, nudged by the Elo gap (±~12% per 100 pts);
                 a 0-7 × 0-7 Poisson grid gives P(home win / draw / away win),
                 the most likely scorelines, P(over 2.5) and P(both score).
  * confidence — the smaller of the two clubs' match counts this season:
                 <4 small sample, 4-9 medium, ≥10 good.
  * accuracy   — every prediction is frozen at the last build before kick-off
                 (data/predictions.json, committed back by the pipeline) and
                 scored after full time: 1X2 hit rate + Brier score, against a
                 naive "always home" baseline.
"""
import collections
import datetime
import json
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
PRED_LOG = os.path.join(HERE, "data", "predictions.json")

ELO_K, ELO_HFA = 28.0, 70.0
PRIOR_TEAM = 5.0        # matches of league-average strength blended into each club
PRIOR_LEAGUE = 20.0     # matches blended into the league home/away means
DEF_HOME_MU, DEF_AWAY_MU = 1.5, 1.2
MAX_GOALS = 7
ELO_GOAL_EXP = 6.0      # λ nudge: 10 ** (elo_gap/400 / ELO_GOAL_EXP), split between the sides
PRED_WINDOW_DAYS = 10   # log predictions for matches this far ahead
PRUNE_DAYS = 150


# ---------------------------------------------------------------- data prep
def _fin(m):
    return (m.get("status") == "FINISHED" and m.get("home_score") is not None
            and m.get("away_score") is not None)


def season_matches(fixtures, archive):
    """competition -> chronological finished matches (deduped by match_id,
    else by (home, away, kickoff))."""
    by_comp = {}
    seen = set()
    pool = []
    for f in fixtures or []:
        for rd in f.get("rounds", []):
            for m in rd.get("matches", []):
                pool.append(dict(m, competition=m.get("competition") or f.get("competition")))
    pool.extend(archive or [])
    for m in pool:
        if not _fin(m) or not m.get("competition"):
            continue
        key = m.get("match_id") or (m.get("home"), m.get("away"), m.get("kickoff"))
        if key in seen:
            continue
        seen.add(key)
        by_comp.setdefault(m["competition"], []).append(m)
    for ms in by_comp.values():
        ms.sort(key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""))
    return by_comp


def team_stats(by_comp):
    """competition -> {team: {...}} with Elo, goals, splits, form, ppg."""
    out = {}
    for comp, ms in by_comp.items():
        t = {}
        def row(name):
            return t.setdefault(name, {"team": name, "elo": 1500.0, "played": 0, "won": 0, "draw": 0,
                                       "lost": 0, "gf": 0, "ga": 0, "pts": 0, "form": [],
                                       "h_played": 0, "h_gf": 0, "h_ga": 0, "h_pts": 0,
                                       "a_played": 0, "a_gf": 0, "a_ga": 0, "a_pts": 0,
                                       "cs": 0, "badge": None})
        for m in ms:
            h, a = row(m["home"]), row(m["away"])
            hs, aw = int(m["home_score"]), int(m["away_score"])
            h["badge"] = h["badge"] or m.get("home_badge")
            a["badge"] = a["badge"] or m.get("away_badge")
            e = 1.0 / (1 + 10 ** ((a["elo"] - (h["elo"] + ELO_HFA)) / 400))
            sc = 1.0 if hs > aw else 0.5 if hs == aw else 0.0
            # margin-aware K (2+ goal wins move ratings a little more)
            mult = 1.0 + 0.25 * max(0, abs(hs - aw) - 1)
            h["elo"] += ELO_K * mult * (sc - e)
            a["elo"] += ELO_K * mult * ((1 - sc) - (1 - e))
            for side, gf, ga, pre in ((h, hs, aw, "h_"), (a, aw, hs, "a_")):
                side["played"] += 1; side["gf"] += gf; side["ga"] += ga
                side[pre + "played"] += 1; side[pre + "gf"] += gf; side[pre + "ga"] += ga
                p = 3 if gf > ga else 1 if gf == ga else 0
                side["pts"] += p; side[pre + "pts"] += p
                side["won" if p == 3 else "draw" if p == 1 else "lost"] += 1
                side["form"].append("W" if p == 3 else "D" if p == 1 else "L")
                if ga == 0:
                    side["cs"] += 1
        out[comp] = t
    return out


def league_params(ms):
    n = len(ms)
    hg = sum(int(m["home_score"]) for m in ms)
    ag = sum(int(m["away_score"]) for m in ms)
    mu_h = (hg + PRIOR_LEAGUE * DEF_HOME_MU) / (n + PRIOR_LEAGUE)
    mu_a = (ag + PRIOR_LEAGUE * DEF_AWAY_MU) / (n + PRIOR_LEAGUE)
    return {"n": n, "mu_home": mu_h, "mu_away": mu_a, "mu": (mu_h + mu_a) / 2,
            "home_win": (sum(1 for m in ms if m["home_score"] > m["away_score"]) / n) if n else None,
            "draw": (sum(1 for m in ms if m["home_score"] == m["away_score"]) / n) if n else None,
            "gpm": ((hg + ag) / n) if n else None}


def strength(ts, mu):
    """attack/defence indices (1.0 = league average) with the 5-match prior."""
    p = ts["played"]
    att = ((ts["gf"] + PRIOR_TEAM * mu) / (p + PRIOR_TEAM)) / mu if mu else 1.0
    dfc = ((ts["ga"] + PRIOR_TEAM * mu) / (p + PRIOR_TEAM)) / mu if mu else 1.0
    return att, dfc


def _pois(lmb, k):
    return math.exp(-lmb) * lmb ** k / math.factorial(k)


def outcome_from_lambdas(lh, la):
    """Poisson grid over 0..MAX_GOALS for both sides -> outcome probabilities.
    The ONE place the grid is computed: predict() and backtest.py both call it,
    so a candidate factor that only rescales the expected goals cannot drift
    away from the live model."""
    lh, la = max(0.15, min(lh, 4.5)), max(0.15, min(la, 4.5))
    ph = pd = pa = over25 = btts = 0.0
    grid = []
    for i in range(MAX_GOALS + 1):
        for j in range(MAX_GOALS + 1):
            p = _pois(lh, i) * _pois(la, j)
            grid.append((p, i, j))
            if i > j: ph += p
            elif i == j: pd += p
            else: pa += p
            if i + j >= 3: over25 += p
            if i and j: btts += p
    tot = ph + pd + pa
    grid.sort(reverse=True)
    return {"ph": ph / tot, "pd": pd / tot, "pa": pa / tot, "lh": lh, "la": la,
            "top": [(i, j, p / tot) for p, i, j in grid[:3]],
            "over25": over25 / tot, "btts": btts / tot}


def lambdas(comp_stats, params, home, away):
    """Expected goals for both sides, before the Poisson grid. Unknown clubs
    (no finished match yet) get league-average strength and Elo 1500."""
    blank = {"elo": 1500.0, "played": 0, "gf": 0, "ga": 0}
    h = comp_stats.get(home, blank)
    a = comp_stats.get(away, blank)
    mu = params["mu"]
    att_h, def_h = strength(h, mu)
    att_a, def_a = strength(a, mu)
    lh = params["mu_home"] * att_h * def_a
    la = params["mu_away"] * att_a * def_h
    gap = (h["elo"] + ELO_HFA - a["elo"]) / 400.0
    f = 10 ** (gap / ELO_GOAL_EXP)
    return lh * math.sqrt(f), la / math.sqrt(f), h, a


def predict(comp_stats, params, home, away):
    """Outcome probabilities for home vs away in one competition."""
    lh, la, h, a = lambdas(comp_stats, params, home, away)
    out = outcome_from_lambdas(lh, la)
    n_min = min(h["played"], a["played"])
    out.update({"home": home, "away": away,
                "elo_h": h["elo"], "elo_a": a["elo"], "n_h": h["played"], "n_a": a["played"],
                "conf": "low" if n_min < 4 else "mid" if n_min < 10 else "high"})
    return out


CONF_AR = {"low": "عيّنة صغيرة", "mid": "ثقة متوسطة", "high": "ثقة جيدة"}


# ---------------------------------------------------------------- prediction log
def _outcome(hs, aw):
    return "H" if hs > aw else "D" if hs == aw else "A"


def update_log(log, upcoming, preds_by_id, finished, today):
    """Freeze/refresh predictions for upcoming matches, score finished ones.
    `upcoming`: matches with status UPCOMING within PRED_WINDOW_DAYS;
    `preds_by_id`: match_id -> predict() result; `finished`: all finished
    matches we know (matches ∪ archive). Mutates and returns log."""
    horizon = (today + datetime.timedelta(days=PRED_WINDOW_DAYS)).isoformat()
    for m in upcoming:
        mid = str(m.get("match_id") or "")
        p = preds_by_id.get(mid)
        if not mid or not p or (m.get("kickoff") or "") > horizon:
            continue
        old = log.get(mid) or {}
        if old.get("hs") is not None:          # already scored — never re-predict
            continue
        log[mid] = {"comp": m.get("competition"), "home": m.get("home"), "away": m.get("away"),
                    "kickoff": m.get("kickoff"), "koff_time": m.get("koff_time"),
                    "ph": round(p["ph"], 4), "pd": round(p["pd"], 4), "pa": round(p["pa"], 4),
                    "lh": round(p["lh"], 3), "la": round(p["la"], 3),
                    "score": f'{p["top"][0][0]}-{p["top"][0][1]}', "conf": p["conf"],
                    "ts": today.isoformat(), "hs": None, "as": None}
    fin_by_id = {str(m.get("match_id")): m for m in finished if m.get("match_id") and _fin(m)}
    for mid, e in log.items():
        if e.get("hs") is not None:
            continue
        m = fin_by_id.get(mid)
        if not m:
            continue
        hs, aw = int(m["home_score"]), int(m["away_score"])
        o = _outcome(hs, aw)
        probs = {"H": e["ph"], "D": e["pd"], "A": e["pa"]}
        pick = max(probs, key=probs.get)
        e.update({"hs": hs, "as": aw, "outcome": o, "pick": pick, "hit": pick == o,
                  "brier": round(sum((probs[k] - (1.0 if k == o else 0.0)) ** 2 for k in probs), 4),
                  "score_hit": e.get("score") == f"{hs}-{aw}"})
    cut = (today - datetime.timedelta(days=PRUNE_DAYS)).isoformat()
    for mid in [k for k, v in log.items() if (v.get("kickoff") or "") < cut]:
        del log[mid]
    return log


def load_log(path=PRED_LOG):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_log(log, path=PRED_LOG):
    new = json.dumps(log, ensure_ascii=False, indent=1, sort_keys=True)
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == new:
                return False
    except Exception:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    return True


def accuracy(log):
    """Scored predictions -> overall + per-competition metrics."""
    rows = [e for e in log.values() if e.get("hs") is not None]
    def agg(es):
        n = len(es)
        if not n:
            return None
        return {"n": n, "hits": sum(1 for e in es if e.get("hit")),
                "hit_rate": sum(1 for e in es if e.get("hit")) / n,
                "brier": sum(e.get("brier", 0) for e in es) / n,
                "score_hits": sum(1 for e in es if e.get("score_hit")),
                "home_baseline": sum(1 for e in es if e.get("outcome") == "H") / n,
                "draw_share": sum(1 for e in es if e.get("outcome") == "D") / n}
    comps = {}
    for e in rows:
        comps.setdefault(e.get("comp"), []).append(e)
    return {"all": agg(rows), "comps": {c: agg(es) for c, es in comps.items()},
            "recent": sorted(rows, key=lambda e: (e.get("kickoff") or "", e.get("koff_time") or ""),
                             reverse=True)[:12]}


# ---------------------------------------------------------------- players
def _minute(s):
    """'90+6' -> 96, '45+2' -> 47, '17' -> 17, junk -> None."""
    m = re.match(r"^\s*(\d+)(?:\+(\d+))?", str(s or ""))
    if not m:
        return None
    return int(m.group(1)) + int(m.group(2) or 0)


MINUTE_BUCKETS = [("1-15", 1, 15), ("16-30", 16, 30), ("31-45+", 31, 45), ("46-60", 46, 60),
                  ("61-75", 61, 75), ("76-90+", 76, 999)]


def _bucket(minute, first_half_max=45):
    if minute is None:
        return None
    # stoppage-time of the first half is reported as 45+X (46-50) — keep it in 31-45+
    if 45 < minute <= 50 and minute - 45 <= 5:
        # ambiguous with real 46-50 minutes; the raw string decides upstream, so
        # treat <=45 only via the raw form. Fall through to numeric buckets.
        pass
    for label, lo, hi in MINUTE_BUCKETS:
        if lo <= minute <= hi:
            return label
    return None


def bucket_of(raw):
    s = str(raw or "")
    if s.startswith("45+"):
        return "31-45+"
    if s.startswith("90+"):
        return "76-90+"
    return _bucket(_minute(s))


def player_insights(details, comp_of, ar):
    """details = data/match_details.json entries; comp_of(home_ar, away_ar, date)
    -> competition or None; ar = Arabic-name normalizer for club names.
    Returns {comp: {"ratings": [...], "timing": {bucket: n}, "club_timing": {club: {...}},
                    "n_matches": n}}."""
    out = {}
    for e in details or []:
        comp = comp_of(e.get("home"), e.get("away"), e.get("date"))
        if not comp:
            continue
        c = out.setdefault(comp, {"players": {}, "timing": {b[0]: 0 for b in MINUTE_BUCKETS},
                                  "club_timing": {}, "club_late": {}, "n_matches": 0})
        c["n_matches"] += 1
        for g in e.get("goals") or []:
            b = bucket_of(g.get("minute"))
            if not b:
                continue
            c["timing"][b] += 1
            club = e.get("home") if g.get("side") == "h" else e.get("away")
            ct = c["club_timing"].setdefault(club, {bb[0]: 0 for bb in MINUTE_BUCKETS})
            ct[b] += 1
        lu = e.get("lineups") or {}
        for side, club in (("h", e.get("home")), ("a", e.get("away"))):
            for pl in (lu.get(side) or {}).get("xi") or []:
                rt = pl.get("rt")
                if rt is None:
                    continue
                key = (pl.get("aid") or pl.get("name"), club)
                r = c["players"].setdefault(key, {"name": pl.get("name"), "club": club,
                                                  "pos": pl.get("pos"), "n": 0, "sum": 0.0, "best": 0.0})
                r["n"] += 1; r["sum"] += float(rt); r["best"] = max(r["best"], float(rt))
    for comp, c in out.items():
        rows = [dict(r, avg=r["sum"] / r["n"]) for r in c["players"].values() if r["n"] >= 2]
        rows.sort(key=lambda r: (-r["avg"], -r["n"]))
        c["ratings"] = rows[:15]
        c["ratings_n1"] = sorted([dict(r, avg=r["sum"]) for r in c["players"].values() if r["n"] == 1],
                                 key=lambda r: -r["avg"])[:5]
        late = {}
        for club, ct in c["club_timing"].items():
            tot = sum(ct.values())
            if tot >= 3:
                late[club] = {"total": tot, "late": ct["76-90+"], "early": ct["1-15"],
                              "late_share": ct["76-90+"] / tot, "first_half": ct["1-15"] + ct["16-30"] + ct["31-45+"]}
        c["club_late"] = late
        del c["players"]
    return out


class SquadIndex:
    """Who a club normally starts, and who is missing from a given XI.

    Built from the lineups we store per match (data/match_details.json, now
    including PRE-match XIs published ~1h before kick-off). A club's regulars
    are the players who started at least `core_rate` of its EARLIER matches;
    each is weighted by how far his average rating sits above replacement
    level, so losing a 7.6 starter counts more than losing a 6.4 one.

    Clubs are keyed by (competition, name) deliberately: «الأهلي» is both Al
    Ahly of Egypt and Al-Ahli of Saudi in the feed, and keying by name alone
    mixed their squads — every Egyptian regular then read as absent in a Saudi
    match. Same same-name class of bug as the favourite-club card (2026-08-22).

    report() returns None while a club has fewer than `min_prior` earlier
    lineups. The bar is 3 on purpose: at 2 the site was printing "بدأ 2 من 2
    مباريات" as evidence that a player is a regular, which a single rotation
    call would produce — not something to publish as an absence.
    """

    def __init__(self, details, comp_of, min_prior=3, core_rate=0.6, replacement=6.3):
        self.min_prior, self.core_rate, self.replacement = min_prior, core_rate, replacement
        self.hist = {}        # (comp, club) -> [(date, {aid})], chronological
        self.xi = {}          # ((comp, club), date) -> {aid}
        self.names = {}       # ((comp, club), aid) -> display name
        self.ratings = {}     # ((comp, club), aid) -> [ratings]
        det = [e for e in (details or []) if comp_of(e.get("home"), e.get("away"), e.get("date"))]
        det.sort(key=lambda e: e.get("date") or "")
        for e in det:
            comp = comp_of(e["home"], e["away"], e["date"])
            for side, club in (("h", e.get("home")), ("a", e.get("away"))):
                xi = ((e.get("lineups") or {}).get(side) or {}).get("xi") or []
                if not xi:
                    continue
                key = (comp, club)
                aids = {p.get("aid") for p in xi if p.get("aid")}
                if not aids:
                    continue
                self.xi[(key, e["date"])] = aids
                self.hist.setdefault(key, []).append((e["date"], aids))
                for p in xi:
                    if not p.get("aid"):
                        continue
                    self.names[(key, p["aid"])] = p.get("name")
                    # ratings on a PRE-match entry are carried-over averages,
                    # not what the player did in that game — mixing them into
                    # the per-match history would corrupt the weighting
                    if p.get("rt") is not None and not e.get("pre"):
                        # kept WITH its date: a rating earned after the match
                        # being judged must never weigh on it (that leak would
                        # flatter any backtest of an absence factor)
                        self.ratings.setdefault((key, p["aid"]), []).append(
                            (e["date"], float(p["rt"])))

    def _rat(self, key, aid, before=None):
        rs = self.ratings.get((key, aid)) or []
        if before is not None:
            rs = [r for d, r in rs if d < before]
        else:
            rs = [r for _, r in rs]
        return rs

    def _weight(self, key, aid, before=None):
        rs = self._rat(key, aid, before) or [self.replacement + 0.5]
        return max(0.0, sum(rs) / len(rs) - self.replacement)

    def _avg(self, key, aid, before=None):
        rs = self._rat(key, aid, before)
        return (sum(rs) / len(rs)) if rs else None

    def has_xi(self, comp, club, date):
        return ((comp, club), date) in self.xi

    def report(self, comp, club, date):
        """{'missing': [...], 'back': [...], 'score': 0..1, 'prior': n} or None.
        `missing` = regulars not in today's XI; `back` = players starting today
        who did not start the club's previous match (returns from absence)."""
        key = (comp, club)
        today = self.xi.get((key, date))
        if today is None:
            return None
        prior = [(d, a) for d, a in self.hist.get(key, []) if d < date]
        if len(prior) < self.min_prior:
            return None
        counts = collections.Counter(a for _, s in prior for a in s)
        core = {a for a, n in counts.items() if n / len(prior) >= self.core_rate}
        if not core:
            return {"missing": [], "back": [], "score": 0.0, "prior": len(prior)}
        # every rating is read as of `date` — nothing later leaks in
        total = sum(self._weight(key, a, date) for a in core) or 1.0

        def row(aid):
            return {"aid": aid, "name": self.names.get((key, aid)),
                    "starts": counts.get(aid, 0), "of": len(prior),
                    "avg": self._avg(key, aid, date)}

        missing = sorted((row(a) for a in core - today),
                         key=lambda r: (-(r["avg"] or 0), -r["starts"]))
        prev_xi = prior[-1][1]
        back = sorted((row(a) for a in today - prev_xi if counts.get(a, 0)),
                      key=lambda r: (-(r["avg"] or 0), -r["starts"]))
        return {"missing": missing, "back": back, "prior": len(prior),
                "score": sum(self._weight(key, a, date) for a in core - today) / total}


def scorer_insights(scorers, assists, standings_tables):
    """Per competition: G+A leaders and each top scorer's share of his club's
    goals (club goals from the standings table)."""
    out = {}
    st_goals = {}
    for comp, table in (standings_tables or {}).items():
        st_goals[comp] = {r.get("team"): int(r.get("gf") or 0) for r in table}
    sc_by = {s.get("competition"): s.get("scorers") or [] for s in scorers or []}
    as_by = {s.get("competition"): s.get("assists") or [] for s in assists or []}
    for comp in set(sc_by) | set(as_by):
        ga = {}
        for p in sc_by.get(comp, []):
            k = (p.get("name"), p.get("team"))
            ga.setdefault(k, {"name": p.get("name"), "team": p.get("team"), "photo": p.get("photo"),
                              "crest": p.get("crest"), "g": 0, "a": 0})["g"] = int(p.get("goals") or p.get("value") or 0)
        for p in as_by.get(comp, []):
            k = (p.get("name"), p.get("team"))
            ga.setdefault(k, {"name": p.get("name"), "team": p.get("team"), "photo": p.get("photo"),
                              "crest": p.get("crest"), "g": 0, "a": 0})["a"] = int(p.get("assists") or p.get("value") or 0)
        rows = sorted(ga.values(), key=lambda r: (-(r["g"] + r["a"]), -r["g"]))
        tg = st_goals.get(comp, {})
        share = []
        for p in sc_by.get(comp, [])[:8]:
            club_goals = tg.get(p.get("team"))
            g = int(p.get("goals") or p.get("value") or 0)
            if club_goals:
                share.append({"name": p.get("name"), "team": p.get("team"), "g": g,
                              "club_goals": club_goals, "share": g / club_goals})
        out[comp] = {"ga": rows[:10], "share": share}
    return out
