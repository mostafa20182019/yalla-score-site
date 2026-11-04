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


# ------------------------------------------------------------------ details backfill
# User, 2026-11-03: «ايوه اعمله» - fill the scorers, lineups, cards and subs the
# archive lacks for matches played before it existed (match_details.json kept
# 45 days; the new leagues' season backfill brought scores only). 365scores
# still serves every game's detail. Runs after each nightly write, at most
# DETAILS_PER_RUN games a night, until nothing is missing - and afterwards it
# keeps catching any match that ends up without its detail.
DETAILS_PER_RUN = 400
# the leagues whose matches the site stores under football-data ids: their
# 365scores game ids are found by date + clubs in that league's results pages
FD_365 = {"Premier League": 7, "Primera Division": 11, "Serie A": 17, "Bundesliga": 25,
          "Ligue 1": 35, "UEFA Champions League": 572}


def _missing(limit):
    """Archived matches with no detail record, or with fewer named goals than
    the score - newest first."""
    return store.sql(
        "SELECT m.match_id, m.competition, m.kickoff, m.home_ar, m.away_ar, m.home_score, m.away_score "
        "FROM arch_matches m "
        "WHERE NOT EXISTS (SELECT 1 FROM arch_details d WHERE d.match_id = m.match_id) "
        "   OR (m.home_score + m.away_score) > "
        "      (SELECT COUNT(*) FROM arch_goals g WHERE g.match_id = m.match_id) "
        "ORDER BY m.kickoff DESC LIMIT ?", [limit])


def _fd_index(comps):
    """{competition: {(date, home, away) normalized: 365 game id}} from each
    league's season results pages (the walk fetch_data's backfill uses)."""
    import fetch_data as F
    from site_lib.names import _gnorm
    out = {}
    start = F.season_start()
    for comp in comps:
        lid = FD_365[comp]
        q = f"competitions={lid}&langId=27&timezoneName=Africa/Cairo"
        sn = (F._s365(f"competitions/?{q}").get("competitions") or [{}])[0].get("currentSeasonNum")
        idx, path = {}, f"games/results/?{q}&showOdds=false"
        for _ in range(F.BACKFILL_PAGES * 2):
            F.time.sleep(1)
            page = F._s365(path)
            games = page.get("games") or []
            for g in games:
                if g.get("seasonNum") != sn:
                    continue
                try:
                    day = F.datetime.fromisoformat(g["startTime"]).astimezone(F.CAIRO).strftime("%Y-%m-%d")
                except (KeyError, ValueError):
                    continue
                if day < start:
                    continue
                h = _gnorm((g.get("homeCompetitor") or {}).get("name"))
                a = _gnorm((g.get("awayCompetitor") or {}).get("name"))
                idx[(day, h, a)] = g["id"]
            prev = (page.get("paging") or {}).get("previousPage") or ""
            if not games or any(g.get("seasonNum") != sn for g in games) or not prev:
                break
            path = prev.split("/web/", 1)[-1]
        out[comp] = idx
    return out


def _find_365(row, idx):
    """(365 game id, flipped) for a football-data-id match, or (None, False)."""
    from site_lib.names import _gnorm
    h, a = _gnorm(row["home_ar"]), _gnorm(row["away_ar"])
    d0 = datetime.date.fromisoformat(row["kickoff"])
    for dd in (0, -1, 1):                       # a kick-off near midnight
        day = (d0 + datetime.timedelta(days=dd)).isoformat()
        if (day, h, a) in idx:
            return idx[(day, h, a)], False
        if (day, a, h) in idx:
            return idx[(day, a, h)], True
    return None, False


def backfill_details(limit=DETAILS_PER_RUN):
    """Fetch the missing details from 365scores into arch_details / arch_goals.
    Returns a note. Never raises on one game: it is skipped and retried later."""
    import fetch_data as F
    from site_lib.competitions import S365_COMPETITIONS
    rows = _missing(limit)
    if not rows:
        return "details: nothing missing"
    need_fd = sorted({r["competition"] for r in rows if r["competition"] in FD_365})
    try:
        fd_idx = _fd_index(need_fd) if need_fd else {}
    except Exception as e:                                    # noqa: BLE001
        print(f"  ! 365scores index failed ({e}) - football-data leagues skipped this run")
        fd_idx = {}
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    got = goals_n = unmatched = fails = 0
    for r in rows:
        flipped = False
        if r["competition"] in FD_365:
            gid, flipped = _find_365(r, fd_idx.get(r["competition"]) or {})
        elif r["competition"] in S365_COMPETITIONS:
            gid = r["match_id"]
        else:
            gid = None
        if not gid:
            unmatched += 1
            continue
        try:
            F.time.sleep(0.6)
            game = (F._s365(f"game/?appTypeId=5&langId=27&gameId={gid}").get("game") or {})
        except Exception:                                     # noqa: BLE001
            fails += 1
            continue
        fb_home = (game.get("homeCompetitor") or {}).get("id")
        goals, _health = F._goal_rows(game, fb_home)
        det = F._detail_rows(game, fb_home)
        if flipped:          # 365scores has the clubs the other way round
            sw = {"h": "a", "a": "h"}
            goals = [dict(g, side=sw.get(g.get("side"), g.get("side"))) for g in goals]
            det = dict(det, cards=[dict(c, side=sw.get(c.get("side"), c.get("side"))) for c in det["cards"]],
                       subs=[dict(s, side=sw.get(s.get("side"), s.get("side"))) for s in det["subs"]],
                       lineups={sw.get(k, k): v for k, v in (det.get("lineups") or {}).items()})
        if det["cards"] or det["subs"] or det["lineups"] or goals:
            entry = {"match_id": str(gid), "home": r["home_ar"], "away": r["away_ar"],
                     "date": r["kickoff"], "goals": goals, **det, "src": "backfill"}
            store.upsert_many("arch_details", ["match_id", "season", "details_json", "updated_at"],
                              [{"match_id": r["match_id"], "season": season_of(r["kickoff"]),
                                "details_json": json.dumps(entry, ensure_ascii=False), "updated_at": now}],
                              ["match_id"])
            got += 1
        # the scorers only when the list accounts for the score (a partial
        # list would read as the whole story)
        if goals and len(goals) == (r["home_score"] or 0) + (r["away_score"] or 0):
            store.sql("DELETE FROM arch_goals WHERE match_id = ?", [r["match_id"]])
            store.upsert_many("arch_goals", ["match_id", "seq", "side", "player", "minute", "tag"],
                              [{"match_id": r["match_id"], "seq": i, "side": g.get("side"),
                                "player": g.get("player"), "minute": str(g.get("minute") or ""),
                                "tag": g.get("tag") or ""} for i, g in enumerate(goals, 1)],
                              ["match_id", "seq"])
            goals_n += 1
    note = (f"details backfill: {len(rows)} missing looked at, {got} details stored, "
            f"{goals_n} scorer lists completed, {unmatched} not found on 365scores, {fails} failed")
    print(note)
    return note


# ------------------------------------------------------------------ export
def export_details(path):
    """data/details_archive.json - every arch_details record, in the shape of
    match_details.json's items, for the build (site_lib.matchdata.merge_details).
    The store keeps 45 days; this keeps the season, so a result older than that
    gets its lineups, its story and its reading back - and its page its index
    (SEO pass, 2026-11-04: 46 Egyptian league results were NOINDEX for lack of
    exactly this). Written by archive-db.yml after the nightly write and
    pushed to the data store on its own (data_store.py push --only)."""
    items = []
    for r in store.sql("SELECT match_id, details_json FROM arch_details ORDER BY match_id"):
        try:
            e = json.loads(r["details_json"])
        except (TypeError, ValueError):
            continue
        if e.get("date") and e.get("home") and e.get("away"):
            items.append(e)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"results": [{"items": items}]}, f, ensure_ascii=False)
    print(f"details export: {len(items)} entries -> {os.path.relpath(path, HERE)}")
    return len(items)


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
    ap.add_argument("--details", type=int, default=DETAILS_PER_RUN,
                    help="games to backfill details for after the write (0 = skip)")
    ap.add_argument("--export", metavar="PATH",
                    help="write arch_details as match_details items for the build (data/details_archive.json)")
    a = ap.parse_args()
    if store.backend() == "json":
        sys.exit("archive_db: no database - set CF_API_TOKEN + CF_ACCOUNT_ID + CF_D1_ID (or D1_SQLITE for a local file)")
    if a.check:
        check()
    elif a.export:
        export_details(a.export)
    else:
        run(seed=a.seed)
        if a.details:
            try:
                backfill_details(a.details)
            except Exception as e:                             # noqa: BLE001
                print(f"  ! details backfill stopped ({e}) - the next run carries on")
