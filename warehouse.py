"""Load the analytics facts into the D1 warehouse.

The user's ask (2026-09-09): "كل الداتا التى تخص صفحة التحليلات تكون موجودة فى
الداتابيز ... عايز اروح على الداتا واعرف اتوقع عن طريق الداتا". So this is not
about storing the model's answers - `predictions` already holds those. It is
about storing the FACTS the model reasons over, linked, so the same question can
be asked in SQL and the answer compared against ours.

Run through d1_admin.py (`--warehouse`), which the d1-admin workflow calls on an
hourly cron. Deliberately NOT part of build_site:

  * the build must keep working when the store is unreachable, and adding
    ~1200 writes to it would make that promise harder to keep;
  * D1's free tier allows 100k row-writes/day. A full refresh is ~1200 rows;
    hourly is ~29k/day, comfortable. Doing it on every 15-minute publish would
    be ~115k/day - over the limit for data nobody reads during a build.

Hourly is far fresher than any analysis needs, and `predictions` (the part that
must be per-build, because a prediction is frozen before kick-off) is written by
build_site as before.
"""
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analysis as AN     # noqa: E402
import build_site as b    # noqa: E402  - data loaders, ar_team, COMP_SLUG/ORDER
import store              # noqa: E402


def _changed_only(table, key_cols, columns, rows):
    """Drop rows already stored identically. Returns (to_write, unchanged).

    D1's free tier gives 100k row-WRITES a day but 5M row-READS, so reading the
    table back once (one query) and writing only what moved is ~50x cheaper than
    blind upserts. A full match refresh is 2113 rows; on an hour when nothing
    was played, this makes it zero. That is the difference between fitting the
    quota with headroom and living at 62k/day.
    """
    if store.backend() == "json":
        return [], 0
    sel = ", ".join(dict.fromkeys(list(key_cols) + list(columns)))
    have = {}
    for r in store.sql(f"SELECT {sel} FROM {table}"):
        have[tuple(str(r[k]) for k in key_cols)] = r
    out, same = [], 0
    for row in rows:
        cur = have.get(tuple(str(row[k]) for k in key_cols))
        if cur is not None and all(cur.get(c) == row.get(c) for c in columns):
            same += 1
            continue
        out.append(row)
    return out, same


def _comp_rows():
    rows = []
    for i, comp in enumerate(b.COMP_ORDER):
        rows.append({"comp_id": comp, "slug": b.COMP_SLUG.get(comp),
                     "name_ar": b.comp_label(comp), "sort_order": i})
    known = {r["comp_id"] for r in rows}
    return rows, known


def _collect_teams(all_matches, standings):
    """(comp, source_name) -> {name_ar, crest}. Crests come from whatever the
    data offers: the standings row first (cleanest), else a match badge."""
    out = {}
    for s in standings or []:
        comp = s.get("competition")
        for r in s.get("table") or []:
            if comp and r.get("team"):
                out[(comp, r["team"])] = {"name_ar": b.ar_team(r["team"]),
                                          "crest": r.get("crest")}
    for m in all_matches:
        comp = m.get("competition")
        if not comp:
            continue
        for side in ("home", "away"):
            nm = m.get(side)
            if not nm:
                continue
            rec = out.setdefault((comp, nm), {"name_ar": b.ar_team(nm), "crest": None})
            rec["crest"] = rec["crest"] or m.get(side + "_badge")
    return out


def refresh(verbose=True):
    """Rebuild competitions / teams / matches / team_strength / league_params.
    Returns a dict of row counts."""
    today = datetime.date.today().isoformat()
    matches = b.load("matches.json")
    archive = b.load("matches_archive.json")
    fixtures = b.load("fixtures.json")
    standings = b.load("standings.json")

    # every match we know of, deduped the same way the model dedupes
    pool, seen = [], set()
    for m in list(matches) + list(archive) + [
            mm for f in fixtures for rd in f.get("rounds", []) for mm in rd.get("matches", [])]:
        mid = m.get("match_id")
        if not mid or mid in seen:
            continue
        seen.add(mid)
        pool.append(m)

    comp_rows, known_comps = _comp_rows()
    n_comp = store.upsert_many("competitions",
                               ["comp_id", "slug", "name_ar", "sort_order"],
                               comp_rows, ["comp_id"])

    team_map = _collect_teams([m for m in pool if m.get("competition") in known_comps],
                              standings)
    trows = [{"comp_id": c, "name": n, "name_ar": v["name_ar"], "crest": v["crest"]}
             for (c, n), v in team_map.items()]
    t_write, t_same = _changed_only("teams", ["comp_id", "name"],
                                    ["comp_id", "name", "name_ar", "crest"], trows)
    n_team = store.upsert_many("teams", ["comp_id", "name", "name_ar", "crest"],
                               t_write, ["comp_id", "name"],
                               update_cols=["name_ar", "crest"])
    # read the ids back: they are generated, and matches need them as FKs
    ids = {(r["comp_id"], r["name"]): r["team_id"]
           for r in store.sql("SELECT team_id, comp_id, name FROM teams")}

    mrows = []
    for m in pool:
        comp = m.get("competition")
        if comp not in known_comps:
            continue
        h, a = ids.get((comp, m.get("home"))), ids.get((comp, m.get("away")))
        mrows.append({"match_id": str(m["match_id"]), "comp_id": comp,
                      "home_id": h, "away_id": a,
                      "kickoff": m.get("kickoff"), "koff_time": m.get("koff_time"),
                      "status": (m.get("status") or "").upper() or None,
                      "home_score": m.get("home_score"), "away_score": m.get("away_score"),
                      "round": m.get("round")})
    MCOLS = ["match_id", "comp_id", "home_id", "away_id", "kickoff", "koff_time",
             "status", "home_score", "away_score", "round"]
    to_write, unchanged = _changed_only("matches", ["match_id"], MCOLS, mrows)
    n_match = store.upsert_many("matches", MCOLS, to_write, ["match_id"])

    # the model's own view of each club, so its numbers can be checked
    bycomp = AN.season_matches(fixtures, archive)
    tstats = AN.team_stats(bycomp)
    srows, prows = [], []
    for comp, ms in bycomp.items():
        if comp not in known_comps:
            continue
        params = AN.league_params(ms)
        prows.append({"comp_id": comp, "as_of": today, "n": params["n"],
                      "mu_home": round(params["mu_home"], 4),
                      "mu_away": round(params["mu_away"], 4),
                      "mu": round(params["mu"], 4),
                      "home_win": params["home_win"], "draw": params["draw"],
                      "gpm": params["gpm"]})
        for name, ts in tstats.get(comp, {}).items():
            tid = ids.get((comp, name))
            if tid is None:
                continue          # a club with results but no row: skip, don't invent
            att, dfc = AN.strength(ts, params["mu"])
            srows.append({"comp_id": comp, "team_id": tid, "as_of": today,
                          "elo": round(ts["elo"], 2), "played": ts["played"],
                          "won": ts["won"], "draw": ts["draw"], "lost": ts["lost"],
                          "gf": ts["gf"], "ga": ts["ga"], "pts": ts["pts"], "cs": ts["cs"],
                          "h_played": ts["h_played"], "h_gf": ts["h_gf"],
                          "h_ga": ts["h_ga"], "h_pts": ts["h_pts"],
                          "a_played": ts["a_played"], "a_gf": ts["a_gf"],
                          "a_ga": ts["a_ga"], "a_pts": ts["a_pts"],
                          "form": "".join(ts["form"]),
                          "attack": round(att, 4), "defence": round(dfc, 4)})
    SCOLS = ["comp_id", "team_id", "elo", "played", "won", "draw", "lost",
             "gf", "ga", "pts", "cs", "h_played", "h_gf", "h_ga", "h_pts",
             "a_played", "a_gf", "a_ga", "a_pts", "form", "attack", "defence"]
    # as_of is excluded from the comparison on purpose: it changes every day and
    # would make every row look dirty, defeating the whole point
    s_write, s_same = _changed_only("team_strength", ["comp_id", "team_id"], SCOLS, srows)
    n_str = store.upsert_many("team_strength", SCOLS + ["as_of"], s_write,
                              ["comp_id", "team_id"])
    n_par = store.upsert_many(
        "league_params",
        ["comp_id", "as_of", "n", "mu_home", "mu_away", "mu", "home_win", "draw", "gpm"],
        prows, ["comp_id"])

    counts = {"competitions": n_comp, "teams_written": n_team, "teams_same": t_same,
              "matches_written": n_match, "matches_same": unchanged,
              "strength_written": n_str, "strength_same": s_same,
              "league_params": n_par}
    if verbose:
        print("warehouse:", ", ".join(f"{k}={v}" for k, v in counts.items()))
        print(f"  rows written this refresh: "
              f"{n_comp + n_team + n_match + n_str + n_par} "
              f"(D1 free tier allows 100k/day)")
    return counts
