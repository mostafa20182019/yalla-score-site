#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The permanent archive in D1 (d1_archive.sql) - every season, kept.

    python archive_db.py              # the daily run: the last LOOKBACK_DAYS of
                                      # matches + today's tables / top players
    python archive_db.py --seed       # everything the data store holds
    python archive_db.py --check      # counts per season / competition

User, 2026-11-03: «عايز الداتا اللى عندى على الموقع زى نتائج المباريات تتحفظ
عندى فى الداتا بيز عشان الموسم اللى جاى مثلا لو عايز نتيجة مباراة من الموسم
الماضى اعرف اجيبها / عايز اعمل عندى داتا بيز فيها كل الداتا اللى على الموقع».
His choice: Cloudflare D1 (in the cloud, written by GitHub while his laptop is
off) + his Oracle copy pulling from it.

Why a daily job and not the 15-minute publish: what has to be KEPT changes
once a day at most - a finished match, the evening's tables - and the publish
run already spends the D1 quota on the live store. The files it reads are
seasons-deep (results_archive), 45 days (match_details) or rewritten every run
(standings, scorers), so a day the job misses is caught by the next one: the
lookback is LOOKBACK_DAYS, and only a table snapshot can be lost (one day's
table, never a result).

Nothing on the site reads these tables. A D1 quota day therefore costs at most
a day's snapshot, and the site never notices.
"""
import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import store                   # noqa: E402  - D1 (or a local SQLite for tests)
SCHEMA = os.path.join(HERE, "d1_archive.sql")
LOOKBACK_DAYS = 10


def season_of(day):
    """«2026-2027» for a July-June season (every league we cover runs so)."""
    try:
        d = datetime.date.fromisoformat((day or "")[:10])
    except ValueError:
        return ""
    y = d.year if d.month >= 7 else d.year - 1
    return f"{y}-{y + 1}"


def init_schema():
    n = 0
    with open(SCHEMA, encoding="utf-8") as f:
        for stmt in store._statements(f.read()):
            store.sql(stmt)
            n += 1
    return n


# ------------------------------------------------------------------ rows
def match_rows(since=None):
    """(matches, goals, details) rows for every FINISHED match the data store
    holds - results_archive (the whole season) overlaid with the day-window
    copies, kicked off on or after `since` (None = all)."""
    import build_site as b
    import results_archive as RA
    from site_lib.names import comp_label
    arch = RA.load()
    pool = {}
    for r in arch.values():
        pool[str(r["match_id"])] = dict(r, status="FINISHED")
    # fixtures.json is where 365scores' mislabelled games landed (Conference
    # League, Nov 2025 under the 2026-27 seasonNum): a fixture row from before
    # the season in progress is never taken from there
    from fetch_data import season_start
    start = season_start()
    for f in b.load("fixtures.json"):
        for rd in f.get("rounds") or []:
            for m in rd.get("matches") or []:
                if (m.get("kickoff") or "") < start:
                    continue
                if (m.get("status") or "").upper() == "FINISHED" and m.get("match_id"):
                    k = str(m["match_id"])
                    pool[k] = dict(pool.get(k) or {}, **dict(m, competition=m.get("competition") or f.get("competition")))
    for m in b.load("matches_archive.json") + b.load("matches.json"):
        if (m.get("status") or "").upper() == "FINISHED" and m.get("match_id"):
            k = str(m["match_id"])
            pool[k] = dict(pool.get(k) or {}, **m)
    gidx = b.goals_index()
    md = b.match_details_index(b.load("match_details.json"))
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    ms, gs, ds = [], [], []
    for k, m in pool.items():
        if m.get("home_score") is None or m.get("away_score") is None or not m.get("competition"):
            continue
        if since and (m.get("kickoff") or "") < since:
            continue
        season = season_of(m.get("kickoff"))
        ms.append({"match_id": k, "season": season, "competition": m["competition"],
                   "comp_label": comp_label(m["competition"]),
                   "round": m.get("round"), "stage": m.get("stage") or None,
                   "kickoff": m.get("kickoff"), "koff_time": m.get("koff_time"),
                   "home": m.get("home"), "away": m.get("away"),
                   "home_ar": b.ar_team(m.get("home")), "away_ar": b.ar_team(m.get("away")),
                   "home_score": int(m["home_score"]), "away_score": int(m["away_score"]),
                   "home_badge": m.get("home_badge"), "away_badge": m.get("away_badge"),
                   "updated_at": now})
        goals = m.get("goals") or b.match_goals(gidx, m) or []
        for i, g in enumerate(goals, 1):
            gs.append({"match_id": k, "seq": i, "side": g.get("side"), "player": g.get("player"),
                       "minute": str(g.get("minute") or ""), "tag": g.get("tag") or ""})
        det = b.match_details_for(md, m)
        if det:
            e, flipped = det
            ds.append({"match_id": k, "season": season, "updated_at": now,
                       "details_json": json.dumps(dict(e, flipped=flipped), ensure_ascii=False)})
    return ms, gs, ds


def table_rows(day):
    """Today's league tables and top players as snapshot rows."""
    import build_site as b
    st, tp = [], []
    season = season_of(day)
    for s in b.load("standings.json"):
        for r in s.get("table") or []:
            if not r.get("team"):
                continue
            st.append({"snap_date": day, "season": season, "competition": s.get("competition"),
                       "pos": r.get("pos"), "team": r["team"], "team_ar": b.ar_team(r["team"]),
                       "played": r.get("played"), "won": r.get("won"), "draw": r.get("draw"),
                       "lost": r.get("lost"), "gf": r.get("gf"), "ga": r.get("ga"),
                       "gd": r.get("gd"), "pts": r.get("pts")})
    for fname, field, kind in (("scorers.json", "scorers", "goals"), ("assists.json", "assists", "assists")):
        for s in b.load(fname):
            for i, x in enumerate(s.get(field) or [], 1):
                tp.append({"snap_date": day, "season": season, "competition": s.get("competition"),
                           "kind": kind, "rank": i, "name": x.get("name"), "team": x.get("team"),
                           "value": x.get("value") if x.get("value") is not None else x.get("goals")})
    return st, tp


def highlight_rows(since=None):
    import highlights as HL
    out = []
    for v in HL.load()[0].values():
        if since and (v.get("kickoff") or "") < since:
            continue
        out.append({"vid": v["vid"], "match_id": str(v.get("match_id") or ""),
                    "channel": v.get("channel"), "title": v.get("title"),
                    "published": v.get("published"), "kickoff": v.get("kickoff")})
    return out


# ------------------------------------------------------------------ run
def run(seed=False, today=None):
    today = today or datetime.date.today().isoformat()
    since = None if seed else (datetime.date.fromisoformat(today)
                               - datetime.timedelta(days=LOOKBACK_DAYS)).isoformat()
    init_schema()
    if not seed and not store.sql("SELECT 1 AS x FROM arch_matches LIMIT 1"):
        # an empty archive (the first scheduled run) seeds itself: nobody has
        # to remember the manual seed=true dispatch
        seed, since = True, None
        print("archive: empty - seeding everything the data store holds")
    ms, gs, ds = match_rows(since)
    st, tp = table_rows(today)
    hl = highlight_rows(since)
    MATCH_COLS = ["match_id", "season", "competition", "comp_label", "round", "stage", "kickoff",
                  "koff_time", "home", "away", "home_ar", "away_ar", "home_score", "away_score",
                  "home_badge", "away_badge", "updated_at"]
    n = {
        "matches": store.upsert_many("arch_matches", MATCH_COLS, ms, ["match_id"]),
        "goals": store.upsert_many("arch_goals", ["match_id", "seq", "side", "player", "minute", "tag"],
                                   gs, ["match_id", "seq"]),
        "details": store.upsert_many("arch_details", ["match_id", "season", "details_json", "updated_at"],
                                     # 4 a statement: up to ~5.4 KB of Arabic JSON each,
                                     # sent u-escaped by store.sql (about x3) - D1 caps a
                                     # statement near 100 KB
                                     ds, ["match_id"], chunk=4),
        "standings": store.upsert_many("arch_standings", ["snap_date", "season", "competition", "pos", "team",
                                                          "team_ar", "played", "won", "draw", "lost", "gf",
                                                          "ga", "gd", "pts"],
                                       st, ["snap_date", "competition", "team"]),
        "top_players": store.upsert_many("arch_top_players", ["snap_date", "season", "competition", "kind",
                                                              "rank", "name", "team", "value"],
                                         tp, ["snap_date", "competition", "kind", "rank"]),
        "highlights": store.upsert_many("arch_highlights", ["vid", "match_id", "channel", "title",
                                                            "published", "kickoff"], hl, ["vid"]),
    }
    w, stmts = store.writes()
    note = (f"archive ({'seed' if seed else f'since {since}'}, backend {store.backend()}): "
            + ", ".join(f"{k} {v}" for k, v in n.items())
            + f" - {w} rows written in {stmts} statements")
    print(note)
    return n


def check():
    for r in store.sql("SELECT season, comp_label, COUNT(*) AS n, MIN(kickoff) AS first, MAX(kickoff) AS last "
                       "FROM arch_matches GROUP BY season, comp_label ORDER BY season, n DESC"):
        print(r)
    for t in ("arch_goals", "arch_details", "arch_standings", "arch_top_players", "arch_highlights"):
        print(t, store.sql(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if store.backend() == "json":
        sys.exit("archive_db: no database - set CF_API_TOKEN + CF_ACCOUNT_ID + CF_D1_ID (or D1_SQLITE for a local file)")
    if a.check:
        check()
    else:
        run(seed=a.seed)
