# -*- coding: utf-8 -*-
"""«أرقام الدوري» - /numbers/<slug> (SEO review 2026-11-19).

Search shows «احصائيات الدوري المصري», «إحصاءات الدوري الفرنسي / الإيطالي» with
no page of ours answering them; the archive holds every yellow and red card
with the player's name and minute, and every goal with its minute, for the
matches the site followed. This is that archive, added up per league.

COMPUTED, never generated - and guarded so it cannot say more than it holds:
  * only the league's own finished matches (the season pool), each tied to
    its details by the pair of names + the day, like the match page;
  * a card counts only for a name that was ON THE PITCH (a booked coach is
    not «the most booked player»);
  * an own goal is not a team's «late goal» scorer's goal, but it IS a goal
    of the match, so the late-goals count takes every goal by its minute;
  * the page states «N of M matches»; below MIN_MATCHES or below MIN_COVER
    of the finished matches there is NO page - a «most booked» list built
    from half a season would simply be wrong.
No «suspended next match» (the rules differ by competition) and no assists
(too few matches carry them).
"""
from site_lib.matchdata import _played_names, _side_of, match_details_for
from site_lib.names import ar_team

MIN_MATCHES = 20
MIN_COVER = 0.8
LATE_FROM = 76           # «آخر ربع ساعة»: 76' to the whistle
TOP = 10
# the competitions that get a page in THIS build - filled once by build_site
# before any page is written, so a hub page links /numbers/<slug> only when
# the page will exist (the builders run in an order that cannot ask it later)
READY = set()


def _minute(mn):
    """'90+3' -> 90, '45' -> 45, anything else -> None."""
    try:
        return int(str(mn).split("+")[0].strip())
    except (TypeError, ValueError):
        return None


def league_numbers(games, md_idx):
    """The league's numbers from its finished matches, or None.

    {"n", "of", "goals", "late", "yellow", "red",
     "booked": [(player, team, n)], "sent_off": [(player, team, minute, opponent)],
     "teams": [(team, yellow, red)], "late_teams": [(team, n)]}"""
    fin, _ids = [], set()
    for m in games or []:
        # each match once: «N of M» counts matches, and the season pool can
        # list one twice
        if (m.get("status") or "").upper() == "FINISHED" and m.get("home_score") is not None \
                and m.get("match_id") not in _ids:
            _ids.add(m.get("match_id"))
            fin.append(m)
    if not md_idx or len(fin) < MIN_MATCHES:
        return None
    booked, teams, late_t, sent = {}, {}, {}, []
    used = goals = late = yellow = red = 0
    seen = set()
    for m in fin:
        if m.get("match_id") in seen:
            continue
        seen.add(m.get("match_id"))
        got = match_details_for(md_idx, m)
        if not got:
            continue
        e, flipped = got
        # a match counts only when its goal list adds up to the score: an entry
        # with a goal missing would understate every «late goals» number
        n_goals = len(e.get("goals") or [])
        if n_goals != int(m.get("home_score") or 0) + int(m.get("away_score") or 0):
            continue
        used += 1
        sd = _side_of(flipped)
        name = {"h": ar_team(m.get("home")), "a": ar_team(m.get("away"))}
        on = {k: _played_names(e, flipped, k) for k in ("h", "a")}
        for t in name.values():
            teams.setdefault(t, [0, 0])
        for g in e.get("goals") or []:
            goals += 1
            mn = _minute(g.get("minute"))
            if mn is not None and mn >= LATE_FROM:
                late += 1
                side = sd(g.get("side"))
                if side in name:
                    late_t[name[side]] = late_t.get(name[side], 0) + 1
        for c in e.get("cards") or []:
            side = sd(c.get("side"))
            who = (c.get("player") or "").strip()
            if side not in name or not who or who not in on[side]:
                continue                  # a coach, a bench official, an unnamed card
            is_red = (c.get("color") or "") == "r"
            teams[name[side]][1 if is_red else 0] += 1
            if is_red:
                red += 1
                sent.append((who, name[side], str(c.get("minute") or ""), name["a" if side == "h" else "h"],
                             m.get("kickoff") or ""))
            else:
                yellow += 1
                k = (who, name[side])
                booked[k] = booked.get(k, 0) + 1
    if used < MIN_MATCHES or used < MIN_COVER * len(fin):
        return None
    return {
        "n": used, "of": len(fin), "goals": goals, "late": late, "yellow": yellow, "red": red,
        "booked": [(p, t, n) for (p, t), n in sorted(booked.items(), key=lambda x: (-x[1], x[0][0]))[:TOP]],
        "sent_off": [s[:4] for s in sorted(sent, key=lambda s: s[4], reverse=True)[:TOP]],
        "teams": [(t, y, r) for t, (y, r) in sorted(teams.items(), key=lambda x: (-(x[1][0] + x[1][1]), x[0]))],
        "late_teams": [(t, n) for t, n in sorted(late_t.items(), key=lambda x: (-x[1], x[0]))[:TOP]],
    }
