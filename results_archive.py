# -*- coding: utf-8 -*-
"""data/results_archive.json - every FINISHED match of the season, kept for good.

    python results_archive.py                # what publish.yml runs after the fetch
    python results_archive.py --seed-oracle  # ONE-TIME: take over Oracle's archive
    python results_archive.py --stats

WHY (2026-09-24). The user chose ONE model, Python, and the laptop out of the
site's path (the senior plan, step 2). The Oracle copy was giving the site two
things Python did not have, and both must survive the hand-over:

  1. A COMPLETE SEASON POOL. matches_archive.json started on 2026-08-17 and
     prunes after 120 days; Oracle's MATCHES kept everything from the opening
     weekend. Without it python's Elo drifted (Saudi league 51 vs 60 matches,
     16 Elo points) - the reason for the old «Oracle first» rule. This file is
     never pruned within a season.
  2. A FROZEN RESULT. Oracle's MATCH_RESULTS froze a finished match once its
     scorers accounted for its score, and a frozen match was never overwritten
     again (31_results_archive.sql). goal_events.json is a rolling window that
     forgets a match within hours and match_details.json keeps 45 days, so
     without a freeze the scorers of a September match are gone by November.

Same rule as Oracle's yalla_results.freeze, in python:
    FINISHED, both scores known, and len(goals) == home_score + away_score
    (a 0-0 therefore freezes at once). Frozen = insert-only: score and scorers
    are never touched again. Not yet complete = kept (the score still feeds the
    pool) and re-checked on every run until the goals add up.

Rows are stored in matches.json shape (the feed's names and ids) with the goals
oriented to that row's home/away, so the season pool reads them directly and
the goals index gets them through frozen_entries().

Written under data/ and carried by publish.yml's commit-back like every other
data file; step 3 of the plan moves data out of git as a whole.
"""
import argparse
import io
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FILE = os.path.join(HERE, "data", "results_archive.json")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path=FILE):
    """{match_id(str): entry}. Missing/broken file = empty (the pool then falls
    back to matches_archive.json, exactly as before this file existed)."""
    try:
        with io.open(path, encoding="utf-8") as f:
            rows = json.load(f).get("results") or []
    except (OSError, ValueError):
        return {}
    return {str(r["match_id"]): r for r in rows if r.get("match_id") is not None}


def save(arch, path=FILE):
    rows = sorted(arch.values(), key=lambda r: (r.get("kickoff") or "", r.get("koff_time") or "",
                                                str(r.get("match_id"))))
    doc = {"meta": {"generated_at": _now(), "count": len(rows),
                    "frozen": sum(1 for r in rows if r.get("frozen"))},
           "results": rows}
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=0)
    os.replace(tmp, path)            # never leave a half-written file behind


def _fin(m):
    return ((m.get("status") or "").upper() == "FINISHED"
            and m.get("home_score") is not None and m.get("away_score") is not None)


def _row(m):
    """The matches.json fields the pool and the pages need, nothing else."""
    return {k: m.get(k) for k in ("match_id", "competition", "kickoff", "koff_time", "home", "away",
                                  "home_badge", "away_badge", "home_score", "away_score", "round")}


def complete(goals, hs, as_):
    """Oracle's completeness gate: the scorers account for the score."""
    if hs is None or as_ is None:
        return False
    if hs + as_ == 0:
        return True
    return goals is not None and len(goals) == hs + as_


# The feed saying a match was NOT played outranks anything in the archive,
# frozen included. Found during the hand-over itself: Levante - Athletic
# (2026-09-16) was POSTPONED and rescheduled to 10-21, but one Oracle export
# listed it FINISHED 0-0 - and 0-0 passes the completeness gate instantly, so it
# landed frozen, a draw that never happened, in the table and the Elo. A played
# match never goes back to postponed or upcoming, so dropping on these is safe.
NOT_PLAYED = {"POSTPONED", "UPCOMING", "SCHEDULED", "TIMED", "CANCELLED", "CANCELED", "SUSPENDED"}


def update(arch, rows, goals_for, now=None):
    """Fold the current rows into the archive. `goals_for(row)` returns the goal
    list for a row (or None). Returns (added, froze, updated, removed).

    A frozen entry is never changed - except that it is REMOVED when the feed's
    newest row says the match was not played (see NOT_PLAYED). An unfrozen one
    takes the newest score, goals and fields, and freezes the moment the goals
    add up."""
    now = now or _now()
    added = froze = updated = removed = 0
    for m in rows:
        if (m.get("status") or "").upper() in NOT_PLAYED and str(m.get("match_id")) in arch:
            del arch[str(m["match_id"])]
            removed += 1
            continue
        if not _fin(m) or m.get("match_id") is None:
            continue
        mid = str(m["match_id"])
        old = arch.get(mid)
        if old and old.get("frozen"):
            continue
        goals = goals_for(m)
        new = dict(_row(m), match_id=mid, goals=goals if goals else None,
                   frozen=False, src=(old or {}).get("src") or "python")
        if complete(goals, m["home_score"], m["away_score"]):
            new["frozen"], new["frozen_at"] = True, now
            froze += 1
        if old is None:
            added += 1
        elif any(old.get(k) != new.get(k) for k in ("home_score", "away_score", "goals", "frozen")):
            updated += 1
        arch[mid] = new
    return added, froze, updated, removed


def season_rows(arch):
    """Every archived match in matches.json shape, for AN.season_matches()."""
    return [dict(r, status="FINISHED") for r in arch.values()
            if r.get("competition") and r.get("home_score") is not None]


def frozen_entries(arch):
    """The frozen matches in the shape goal_events_index / frozen_scores_index
    read ({date, home, away, hs, as, goals}) - names converted to the
    365scores spellings those indexes normalise against."""
    import build_site as b
    out = []
    for r in arch.values():
        if not r.get("frozen"):
            continue
        out.append({"match_id": r["match_id"], "date": r.get("kickoff"),
                    "home": b.ar_team(r.get("home")), "away": b.ar_team(r.get("away")),
                    "hs": r.get("home_score"), "as": r.get("away_score"),
                    "goals": r.get("goals") or []})
    return out


# ------------------------------------------------------------------ the runs
def _feed_rows():
    import build_site as b
    seen, rows = set(), []
    # matches.json last: its copy of a match is the freshest
    for m in b.load("matches_archive.json") + b.load("matches.json"):
        mid = m.get("match_id")
        if mid is not None:
            if mid in seen:
                rows = [x for x in rows if x.get("match_id") != mid]
            seen.add(mid)
            rows.append(m)
    return rows


def run():
    """What publish.yml runs: fold today's finished matches in, freeze what is
    complete. Goals come from the python sources only (match_details +
    goal_events) - an entry this file already froze is never re-derived."""
    import build_site as b
    arch = load()
    idx = b.goals_index(frozen=[])
    a, f, u, rm = update(arch, _feed_rows(), lambda m: b.match_goals(idx, m))
    save(arch)
    fz = sum(1 for r in arch.values() if r.get("frozen"))
    print(f"results archive: {len(arch)} finished matches ({fz} frozen); "
          f"this run +{a} new, {f} frozen, {u} updated"
          + (f", {rm} REMOVED (the feed says not played)" if rm else ""))
    return 0


def seed_oracle():
    """ONE-TIME hand-over (2026-09-24): everything Oracle accumulated becomes
    python's. The season pool (oracle_predictions.json "season") gives the
    rows, the frozen archive (oracle_results.json) gives score + scorers for
    the matches Oracle froze. Idempotent: a match already in this file is
    left alone. Then the normal run() fills in the rest from the feed."""
    import build_site as b
    arch = load()
    feed_status = {str(m.get("match_id")): (m.get("status") or "").upper() for m in _feed_rows()}
    with io.open(os.path.join(HERE, "data", "oracle_predictions.json"), encoding="utf-8") as f:
        season = json.load(f).get("season") or []
    with io.open(os.path.join(HERE, "data", "oracle_results.json"), encoding="utf-8") as f:
        frozen = json.load(f).get("results") or []
    fidx = {}
    for e in frozen:
        fidx[(b._gnorm(e.get("home")), b._gnorm(e.get("away")), e.get("date"))] = e
    feed = {str(m.get("match_id")): m for m in _feed_rows()}

    added = froze = 0
    used = set()
    for r in season:
        mid = str(r.get("match_id"))
        if mid in arch or feed_status.get(mid) in NOT_PLAYED:
            continue
        row = dict(_row(dict(feed.get(mid) or {}, **{k: v for k, v in r.items() if v is not None})),
                   match_id=mid, goals=None, frozen=False, src="oracle-seed")
        h, a = b._gnorm(b.ar_team(row["home"])), b._gnorm(b.ar_team(row["away"]))
        e, flip = fidx.get((h, a, row["kickoff"])), False
        if e is None:
            e, flip = fidx.get((a, h, row["kickoff"])), True
        if e is not None:
            used.add(id(e))
            goals = [dict(g, side=("a" if g.get("side") == "h" else "h")) if flip else dict(g)
                     for g in (e.get("goals") or [])]
            hs, as_ = (e["as"], e["hs"]) if flip else (e["hs"], e["as"])
            row.update(home_score=hs, away_score=as_, goals=goals or None,
                       frozen=True, frozen_at=_now())
            froze += 1
        arch[mid] = row
        added += 1
    # frozen matches that are not in the season pool (a competition the pool
    # does not model): kept for their scorers, attached to the feed row by id
    orphans = 0
    for e in frozen:
        if id(e) in used or str(e.get("match_id")) in arch:
            continue
        m = feed.get(str(e.get("match_id")))
        if not m:
            continue
        arch[str(e["match_id"])] = dict(_row(m), match_id=str(e["match_id"]),
                                        home_score=e["hs"], away_score=e["as"],
                                        goals=e.get("goals") or None, frozen=True,
                                        frozen_at=_now(), src="oracle-seed")
        orphans += 1
    save(arch)
    print(f"seeded from Oracle: {added} season rows ({froze} frozen with scorers), "
          f"{orphans} frozen matches outside the pool; archive now {len(arch)}")
    return 0


def stats():
    import collections
    arch = load()
    c = collections.Counter(r.get("competition") for r in arch.values())
    print(f"{len(arch)} matches, {sum(1 for r in arch.values() if r.get('frozen'))} frozen")
    for k, v in c.most_common():
        print(f"  {v:4}  {k}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-oracle", action="store_true")
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()
    sys.exit(seed_oracle() if a.seed_oracle else stats() if a.stats else run())
