# -*- coding: utf-8 -*-
"""«أرقام لاعبي الفريق» on /team/<slug> (SEO review 2026-11-19).

Search shows the club page near position 10 with no clicks: the results box
already answers the score and the date. What it does not show is the squad's
own numbers - who played how often, who scored, who was booked, who rates
best - and the match-details archive holds exactly that for every match the
site followed (line-ups, substitutions, goals, cards, ratings).

COMPUTED, never generated, and never wider than what we hold:
  * only the club's OWN matches (the caller passes them, already scoped by
    competition - the Saudi «الأهلي» never lands on the Egyptian club);
  * only matches whose details carry a line-up for the club's side;
  * the page says how many matches the numbers come from;
  * no minutes (the feed has none), no «suspended next match» (rules differ
    by competition), no assists (too few matches carry them);
  * an average rating only from MIN_RATED rated starts.
"""
from site_lib.matchdata import _side_of, match_details_for

MIN_MATCHES = 5          # fewer matches with a line-up: no table at all
MIN_RATED = 3            # rated starts before an average is shown
TOP = 22


def _our_side(tp, m):
    """'h' / 'a': which side of match m is this club (the caller's matcher)."""
    from site_lib.names import _team_match
    if _team_match(tp, {"home": m.get("home"), "away": "", "competition": m.get("competition")}):
        return "h"
    if _team_match(tp, {"home": m.get("away"), "away": "", "competition": m.get("competition")}):
        return "a"
    return None


def squad_stats(tp, club_matches, md_idx):
    """{"n": matches used, "rows": [...]} or None. Each row: name, pos, apps,
    starts, goals, yellow, red, rating (str or "")."""
    if not md_idx:
        return None
    P = {}

    def row(name, pos=""):
        name = (name or "").strip()
        if not name:
            return None
        r = P.setdefault(name, {"name": name, "pos": pos or "", "apps": 0, "starts": 0, "goals": 0,
                                "yellow": 0, "red": 0, "_rt": []})
        if pos and not r["pos"]:
            r["pos"] = pos
        return r

    used = 0
    seen = set()
    for m in club_matches:
        if (m.get("status") or "").upper() != "FINISHED" or m.get("match_id") in seen:
            continue
        side = _our_side(tp, m)
        got = match_details_for(md_idx, m) if side else None
        if not got:
            continue
        e, flipped = got
        feed = ("a" if side == "h" else "h") if flipped else side      # the feed's key for OUR side
        xi = (((e.get("lineups") or {}).get(feed)) or {}).get("xi") or []
        if len(xi) < 11:
            continue                      # no line-up for our side: the match gives no appearance
        seen.add(m.get("match_id"))
        used += 1
        sd = _side_of(flipped)
        on_pitch = set()
        for p in xi:
            r = row(p.get("name"), p.get("pos"))
            if not r:
                continue
            r["apps"] += 1
            r["starts"] += 1
            on_pitch.add(r["name"])
            if isinstance(p.get("rt"), (int, float)) and p["rt"] > 0:
                r["_rt"].append(float(p["rt"]))
        for s in e.get("subs") or []:
            if sd(s.get("side")) != side:
                continue
            r = row(s.get("in"))
            if r and r["name"] not in on_pitch:
                r["apps"] += 1
                on_pitch.add(r["name"])
        for g in e.get("goals") or []:
            # an own goal is listed under the side it counted FOR, with the
            # opponent's player - not this club's scorer
            if sd(g.get("side")) != side or (g.get("tag") or "") == "عكسية":
                continue
            nm = (g.get("player") or "").strip()
            if nm in on_pitch:
                P[nm]["goals"] += 1
        for c in e.get("cards") or []:
            nm = (c.get("player") or "").strip()
            if sd(c.get("side")) != side or nm not in on_pitch:
                continue                  # a booked coach is not a player
            P[nm]["red" if (c.get("color") or "") == "r" else "yellow"] += 1
    if used < MIN_MATCHES:
        return None
    rows = sorted(P.values(), key=lambda r: (-r["apps"], -r["starts"], -r["goals"], r["name"]))[:TOP]
    for r in rows:
        rt = r.pop("_rt")
        r["rating"] = f"{sum(rt) / len(rt):.1f}" if len(rt) >= MIN_RATED else ""
    return {"n": used, "rows": rows}
