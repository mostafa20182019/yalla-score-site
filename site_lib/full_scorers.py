# -*- coding: utf-8 -*-
"""The scorers BEYOND the feed's ten, and each club's top scorer (SEO review
2026-11-19: /scorers/egypt shows ten names while «هداف الدوري المصري هذا
الموسم» and «هداف <النادي>» are searched for).

The feed's chart stops at ten. The archive holds every goal of every match
the site followed, with the scorer's name - so the rest of the list can be
COUNTED. It is shown only when the count cannot be wrong:

  * EVERY finished match of the league has its goal list, and each list adds
    up to the score (one match missing and somebody's total is short);
  * a goal counts for a player only when he was ON THE PITCH for the side it
    is credited to. The feed credits an own goal to the side that benefits
    and does not flag it - a name from the OTHER side's line-up is an own
    goal and is nobody's goal; a name in neither line-up cannot be judged,
    and that player is left out of the list;
  * the count must AGREE with the feed's own chart: every one of the ten has
    exactly the goals the chart gives him, and nobody outside the ten has
    more than the tenth. One disagreement and nothing is shown.
"""
from site_lib.matchdata import _played_names, _side_of, match_details_for
from site_lib.names import ar_team

MIN_GOALS = 2          # the rest of the list: two goals or more
MIN_MATCHES = 20


def _norm(s):
    s = (s or "").strip()
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه"), ("ـ", "")):
        s = s.replace(a, b)
    return " ".join(s.split())


def count_goals(games, md_idx):
    """({(player, team): goals}, {uncertain (player, team)}) or None when a
    finished match has no goal list that adds up to its score."""
    fin, ids = [], set()
    for m in games or []:
        if (m.get("status") or "").upper() == "FINISHED" and m.get("home_score") is not None \
                and m.get("match_id") not in ids:
            ids.add(m.get("match_id"))
            fin.append(m)
    if not md_idx or len(fin) < MIN_MATCHES:
        return None
    tally, unsure = {}, set()
    for m in fin:
        total = int(m.get("home_score") or 0) + int(m.get("away_score") or 0)
        got = match_details_for(md_idx, m)
        if not got:
            if total:
                return None
            continue
        e, flipped = got
        goals = e.get("goals") or []
        if len(goals) != total:
            return None
        sd = _side_of(flipped)
        name = {"h": ar_team(m.get("home")), "a": ar_team(m.get("away"))}
        on = {k: {_norm(x) for x in _played_names(e, flipped, k)} for k in ("h", "a")}
        for g in goals:
            side = sd(g.get("side"))
            who = (g.get("player") or "").strip()
            if side not in name or not who:
                return None
            k = (who, name[side])
            if _norm(who) in on[side]:
                tally[k] = tally.get(k, 0) + 1
            elif _norm(who) in on["a" if side == "h" else "h"]:
                continue                   # an own goal: nobody's goal in a scorers list
            else:
                unsure.add(k)              # no line-up to judge it by
                tally[k] = tally.get(k, 0) + 1
    return tally, unsure


def full_scorers(games, md_idx, official):
    """{"rest": [(player, team, goals)], "clubs": [(team, [players], goals)],
    "ones": n} or None. rest = the scorers outside the feed's chart with
    MIN_GOALS or more; clubs = each club's top scorer(s); ones = how many more
    players scored once."""
    official = [x for x in official or [] if x.get("name")]
    if len(official) < 5:
        return None
    got = count_goals(games, md_idx)
    if not got:
        return None
    tally, unsure = got
    by_name = {}
    for (p, t), n in tally.items():
        by_name.setdefault(_norm(p), []).append((p, t, n))
    top_names = set()
    for x in official:
        rows = by_name.get(_norm(x["name"])) or []
        want = int(x.get("goals") or x.get("value") or 0)
        team = ar_team(x.get("team") or "")
        mine = [r for r in rows if r[1] == team] or rows
        if len(mine) != 1 or mine[0][2] != want or (mine[0][0], mine[0][1]) in unsure:
            return None                    # the count and the chart disagree: show nothing
        top_names.add((mine[0][0], mine[0][1]))
    floor = min(int(x.get("goals") or x.get("value") or 0) for x in official)
    rest = []
    for (p, t), n in tally.items():
        if (p, t) in top_names:
            continue
        if n > floor:
            return None                    # somebody the chart does not know has more than its tenth
        if (p, t) in unsure:
            continue
        rest.append((p, t, n))
    rest.sort(key=lambda r: (-r[2], r[0]))
    clubs = {}
    for (p, t), n in tally.items():
        if (p, t) in unsure:
            continue
        best = clubs.get(t)
        if not best or n > best[1]:
            clubs[t] = ([p], n)
        elif n == best[1]:
            best[0].append(p)
    # a club with an unsure scorer who could be its best is left out
    for (p, t) in unsure:
        if t in clubs and tally[(p, t)] >= clubs[t][1]:
            del clubs[t]
    return {"rest": [r for r in rest if r[2] >= MIN_GOALS],
            "ones": sum(1 for r in rest if r[2] == 1),
            "clubs": sorted(((t, sorted(ps), n) for t, (ps, n) in clubs.items()), key=lambda c: (-c[2], c[0]))}
