#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Per-match TEAM stats from 365scores - xG first (2026-10-07, step 2 of the
model plan the user approved: «نبدأ نجمع xG»).

WHY: the literature's strongest single predictor of future results, after
7-8 games, is expected goals - and our model reads goals only. Probed on
2026-10-07: 365scores' game/stats returns xG for EVERY Egyptian, Saudi and
Turkish league match sampled (12/12 each) and for the big five + the Champions
League; CAF Champions League has no stats at all (0/12), so it is not asked.

data/match_stats.json (in the data store, not git) - one row per FINISHED
match, insert-only:
    {"match_id", "comp", "kickoff", "home", "away", "s365_id", "status": "ok"|"none",
     "h": {"xg", "xgot", "shots", "sot", "big", "poss"}, "a": {...}, "fetched_utc"}
(status "unmapped": a European match whose 365 game could not be identified.)
Our match_id IS the 365scores id for the 365-sourced leagues; the European
leagues come from football-data, so their 365 id is found by date + the two
clubs' Arabic names (ar_team = 365scores spellings, the standing rule).

The stats are read by stable numeric ids, never by the Arabic labels.
A match is asked once, MIN_AGE_H after kick-off (stats settle after the
whistle); a match that still has none after NONE_AFTER_H is stored as
status "none" so it is never asked again. BUDGET caps the calls per run, so
the season backfill spreads over a few publish runs instead of one burst.

    python match_stats.py              # collect (what fetch_data.py calls)
    python match_stats.py --report     # coverage per competition, no network
"""
import datetime
import json
import os
import re
import sys
import time
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FILE = os.path.join(HERE, "data", "match_stats.json")
CAIRO = ZoneInfo("Africa/Cairo")

# competition -> 365scores competition id. CAF Champions League (624) is left
# out on purpose: 365scores carries no stats for it (0/12 on 2026-10-07).
COMPS = {
    "Egyptian Premier League": 552, "Saudi Pro League": 649, "Turkish Super Lig": 78,
    "Premier League": 7, "Primera Division": 11, "Serie A": 17, "Bundesliga": 25,
    "Ligue 1": 35, "UEFA Champions League": 572,
}
NATIVE = {"Egyptian Premier League", "Saudi Pro League", "Turkish Super Lig"}   # our id == 365 id
STAT_IDS = {76: "xg", 79: "xgot", 3: "shots", 4: "sot", 24: "big", 10: "poss"}
MIN_AGE_H = 3
NONE_AFTER_H = 48
BUDGET = 40            # game/stats calls per run (+ one date lookup per European match day)
PAUSE = 0.4


def _norm(s):
    s = (s or "").strip()
    s = re.sub("[أإآ]", "ا", s).replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    return re.sub(r"[\s\.\-']", "", s).lower()


def _num(v):
    """'53%' -> 53, '1.27' -> 1.27, '9' -> 9; None when it is not a number."""
    s = str(v if v is not None else "").replace("%", "").replace(",", ".").strip()
    try:
        f = float(s)
    except ValueError:
        return None
    return int(f) if f.is_integer() and "." not in s else f


def parse_stats(doc):
    """game/stats response -> ({"h": {...}, "a": {...}}, has_xg). Sides come
    from the game's homeCompetitor id, never from the order of the list."""
    games = doc.get("games") or []
    home_id = ((games[0] if games else {}).get("homeCompetitor") or {}).get("id")
    out = {"h": {}, "a": {}}
    for t in doc.get("statistics") or []:
        key = STAT_IDS.get(t.get("id"))
        if not key or home_id is None:
            continue
        side = "h" if t.get("competitorId") == home_id else "a"
        val = _num(t.get("value"))
        if val is not None:
            out[side][key] = val
    return out, ("xg" in out["h"] and "xg" in out["a"])


def load(path=FILE):
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        return {str(r["match_id"]): r for r in doc.get("results") or []}
    except Exception:                                       # noqa: BLE001
        return {}


def save(rows, path=FILE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    items = sorted(rows.values(), key=lambda r: (r.get("kickoff") or "", str(r["match_id"])))
    doc = {"meta": {"generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "count": len(items),
                    "with_xg": sum(1 for r in items if r.get("status") == "ok")},
           "results": items}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def _age_h(r, now):
    try:
        t = r.get("koff_time") or "23:59"
        ko = datetime.datetime.fromisoformat(f'{r["kickoff"]}T{t}:00').replace(tzinfo=CAIRO)
    except Exception:                                       # noqa: BLE001
        return -1
    return (now - ko).total_seconds() / 3600


def due(finished, have, now):
    """Finished matches of the covered competitions we have not settled yet."""
    out = []
    for r in finished:
        mid = str(r.get("match_id") or "")
        if not mid or r.get("competition") not in COMPS or mid in have:
            continue
        if r.get("home_score") is None or _age_h(r, now) < MIN_AGE_H:
            continue
        out.append(r)
    # newest first: the matches people read about today come before the backfill
    return sorted(out, key=lambda r: (r.get("kickoff") or "", r.get("koff_time") or ""), reverse=True)


def euro_ids(rows, s365, ar_team):
    """365 game id for each European row, by date (+-1 day) and both names.
    Returns (ids, calls, looked): `looked` holds the rows whose day lookup
    actually answered - a row whose lookup FAILED is not "unmapped", it is
    simply not known yet, and must not be settled as such."""
    want = {}
    for r in rows:
        want.setdefault(r["kickoff"], []).append(r)
    ids, calls, looked = {}, 0, set()
    comps = ",".join(str(COMPS[c]) for c in COMPS if c not in NATIVE)
    for day, rs in want.items():
        d = datetime.date.fromisoformat(day)
        a, b = (d - datetime.timedelta(days=1)).strftime("%d/%m/%Y"), (d + datetime.timedelta(days=1)).strftime("%d/%m/%Y")
        try:
            games = s365(f"games/allscores/?appTypeId=5&langId=27&timezoneName=Africa/Cairo"
                         f"&competitions={comps}&startDate={a}&endDate={b}&showOdds=false").get("games") or []
        except Exception:                                   # noqa: BLE001
            calls += 1
            time.sleep(PAUSE)
            continue
        calls += 1
        time.sleep(PAUSE)
        games = [g for g in games if g.get("homeCompetitor") and g.get("awayCompetitor")]
        by_pair = {(_norm(g["homeCompetitor"]["name"]), _norm(g["awayCompetitor"]["name"])): g["id"] for g in games}
        for r in rs:
            looked.add(str(r["match_id"]))
            h, a = _norm(ar_team(r["home"])), _norm(ar_team(r["away"]))
            gid = by_pair.get((h, a))
            if not gid:
                # a Champions League opponent we have no Arabic spelling for
                # (Sabah FK, FC Porto...): accept the ONE game that day where
                # one club's name AND the exact score both agree
                hit = [g["id"] for g in games
                       if (_norm(g["homeCompetitor"]["name"]) == h or _norm(g["awayCompetitor"]["name"]) == a)
                       and g["homeCompetitor"].get("score") == r.get("home_score")
                       and g["awayCompetitor"].get("score") == r.get("away_score")]
                gid = hit[0] if len(hit) == 1 else None
            if gid:
                ids[str(r["match_id"])] = gid
    return ids, calls, looked


def collect(finished, s365, ar_team, now=None, budget=BUDGET, path=FILE):
    """Fetch what is due, within the budget; returns a debug dict."""
    now = now or datetime.datetime.now(CAIRO)
    rows = load(path)
    todo = due(finished, rows, now)
    dbg = {"due": len(todo), "fetched": 0, "ok": 0, "none": 0, "unmapped": 0, "errors": 0}
    batch = todo[:budget]
    eu = [r for r in batch if r["competition"] not in NATIVE]
    ids, dbg["date_calls"], looked = euro_ids(eu, s365, ar_team) if eu else ({}, 0, set())
    for r in batch:
        mid = str(r["match_id"])
        gid = int(mid) if r["competition"] in NATIVE else ids.get(mid)
        old = _age_h(r, now) >= NONE_AFTER_H
        if not gid:
            dbg["unmapped"] += 1
            if old and mid in looked:      # never found (2 of 268 on 2026-10-07): stop asking, but say so
                rows[mid] = _row(r, None, "unmapped", {}, now)
            continue
        try:
            doc = s365(f"game/stats/?appTypeId=5&langId=27&timezoneName=Africa/Cairo&games={gid}")
        except Exception:                                   # noqa: BLE001
            dbg["errors"] += 1
            continue
        finally:
            time.sleep(PAUSE)
        dbg["fetched"] += 1
        st, has_xg = parse_stats(doc)
        if has_xg:
            rows[mid] = _row(r, gid, "ok", st, now)
            dbg["ok"] += 1
        elif old:
            rows[mid] = _row(r, gid, "none", st, now)
            dbg["none"] += 1
    save(rows, path)
    dbg["stored"] = len(rows)
    dbg["with_xg"] = sum(1 for x in rows.values() if x.get("status") == "ok")
    return dbg


def _row(r, gid, status, st, now):
    return {"match_id": str(r["match_id"]), "comp": r.get("competition"), "kickoff": r.get("kickoff"),
            "home": r.get("home"), "away": r.get("away"), "s365_id": gid, "status": status,
            "h": st.get("h") or {}, "a": st.get("a") or {},
            "fetched_utc": now.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def report(path=FILE):
    rows = load(path)
    by = {}
    for r in rows.values():
        c = by.setdefault(r.get("comp"), [0, 0])
        c[0] += 1
        c[1] += r.get("status") == "ok"
    for comp, (n, ok) in sorted(by.items(), key=lambda kv: -kv[1][0]):
        print(f"  {comp:28} {ok:4}/{n:<4} with xG")
    print(f"  total {sum(v[1] for v in by.values())}/{len(rows)}")


def finished_pool():
    """Every finished match we hold: the frozen results archive + the feed."""
    import results_archive as RA
    from site_lib.config import load as dload
    seen, out = set(), []
    for r in list(RA.load().values()) + list(dload("matches_archive.json")) + list(dload("matches.json")):
        mid = str(r.get("match_id") or "")
        if mid and mid not in seen and (r.get("status") in (None, "FINISHED") or r.get("frozen")) \
                and r.get("home_score") is not None:
            seen.add(mid)
            out.append(r)
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--report" in sys.argv:
        report()
        sys.exit(0)
    import fetch_data as F
    from site_lib.names import ar_team
    print(json.dumps(collect(finished_pool(), F._s365, ar_team), ensure_ascii=False))
