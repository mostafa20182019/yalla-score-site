#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The last meetings of the two sides of every COMING match (2026-11-26).

    python h2h_feed.py            # fetch what is missing, merge, write
    python h2h_feed.py --dry      # say what would be fetched, write nothing

The user, 2026-11-26, when the rewritten news was switched off: «نركز على
... احصائيات: آخر 10 مواجهات، آخر مواجهة، سلاسل». Our own archive holds this
season only, so the meetings of earlier years come from the 365scores
head-to-head feed of the coming game - the same feed h2h_history.py saves for
the fourteen pairs that have a page, here for ANY pair about to meet.

data/h2h_feed.json (in the data store, data_store.STORE_FILES):

    {"pairs": {"<raw name>|<raw name>" (sorted): {
        "fetched": "2026-11-26", "a": <raw name>, "b": <raw name>,
        "games": [{"id", "date", "comp", "hg", "ag", "home": "a"|"b", "status"}]}}}

`home` says which of the two was the home side THAT day - read from the
feed's competitor ids, never from a name (the feed's Arabic names are not
ours). A saved game is never dropped: the feed keeps a window of about 15.

Kind to the feed: a pair is asked once, then again only after REFRESH_D days
or once a meeting of its own has been played since; MAX_NEW pairs a run at
most. NEVER FAILS THE RUN: an unreachable feed leaves the file as it was -
site_lib/prefacts.py then says less, never something wrong.
"""
import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.path.join(HERE, "data", "h2h_feed.json")
WHY = ("Played meetings of the two sides of coming matches, from the 365scores head-to-head "
       "feed (h2h_feed.py). Keyed by the two raw names sorted and joined by '|'; `home` = "
       "which of a/b was at home that day. Only grows.")

AHEAD_D = 4            # matches kicking off within this many days
REFRESH_D = 21         # a pair is asked again after this long
MAX_NEW = 40           # pairs asked in one run
# our ids ARE the feed's ids for every competition fetch_data.py reads from
# 365scores; these come from football-data, so the coming game is looked up
# in the feed's own fixture list (one call a competition)
FD_COMPS = {"Premier League": 7, "Primera Division": 11, "Serie A": 17, "Bundesliga": 25,
            "Ligue 1": 35, "UEFA Champions League": 572}
# no table to stand on, or nobody asks: not fetched (site_lib/prefacts.NEWS_SKIP)
from site_lib.prefacts import NEWS_SKIP as SKIP_COMPS   # noqa: E402 - one list, the page's own


def pair_key(a, b):
    return "|".join(sorted([a or "", b or ""]))


def load(path=OUT):
    try:
        with open(path, encoding="utf-8") as f:
            return (json.load(f) or {}).get("pairs") or {}
    except (OSError, ValueError):
        return {}


def parse_feed(j):
    """(home id, away id, [game]) of a games/h2h answer; game = {id, date,
    comp, hg, ag, home_id, status}. Played games only."""
    g = (j or {}).get("game") or {}
    hid = (g.get("homeCompetitor") or {}).get("id")
    aid = (g.get("awayCompetitor") or {}).get("id")
    out = []
    for x in g.get("h2hGames") or []:
        sc = x.get("scores") or []
        if len(sc) < 2 or sc[0] is None or sc[1] is None or sc[0] < 0 or sc[1] < 0:
            continue
        xh, xa = (x.get("homeCompetitor") or {}).get("id"), (x.get("awayCompetitor") or {}).get("id")
        if {xh, xa} != {hid, aid} or hid is None or aid is None:
            continue                                   # not a meeting of these two
        out.append({"id": x.get("id"), "date": (x.get("startTime") or "")[:10],
                    "comp": x.get("competitionDisplayName") or "",
                    "hg": int(sc[0]), "ag": int(sc[1]), "home_id": xh,
                    "status": x.get("statusText") or ""})
    return hid, aid, out


def to_sides(games, hid, a_is_home):
    """feed games -> stored games: `home` = 'a' / 'b'. `a_is_home` says
    whether side a is the coming game's home side (whose id is `hid`)."""
    out = []
    for g in games:
        coming_home_was_home = g["home_id"] == hid
        side = "a" if coming_home_was_home == a_is_home else "b"
        out.append({k: g[k] for k in ("id", "date", "comp", "hg", "ag", "status")} | {"home": side})
    return out


def merge(old, new):
    """old + the games it does not hold (by id, then by date), newest first."""
    ids = {str(g.get("id")) for g in old}
    dates = {g.get("date") for g in old}
    add = [g for g in new if g.get("date") and str(g.get("id")) not in ids and g["date"] not in dates]
    return sorted(list(old) + add, key=lambda g: g.get("date") or "", reverse=True), len(add)


def wanted(matches, pairs, today, ahead=AHEAD_D, refresh=REFRESH_D):
    """The coming matches whose pair must be asked, soonest first."""
    lim = (today + datetime.timedelta(days=ahead)).isoformat()
    old = (today - datetime.timedelta(days=refresh)).isoformat()
    out, seen = [], set()
    for m in sorted(matches, key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or "")):
        d = str(m.get("kickoff") or "")[:10]
        if m.get("status") != "UPCOMING" or not (today.isoformat() <= d <= lim):
            continue
        if m.get("competition") in SKIP_COMPS or not m.get("home") or not m.get("away"):
            continue
        key = pair_key(m["home"], m["away"])
        if key in seen:
            continue
        cur = pairs.get(key)
        if cur and (cur.get("fetched") or "") >= old:
            continue
        seen.add(key)
        out.append(m)
    return out


def feed_ids(matches, fetch):
    """{our match_id: feed game id} for the football-data competitions, by
    the two names on the same day in the feed's fixture list."""
    import build_site as b
    import match_brief as MB
    out = {}
    for comp in sorted({m.get("competition") for m in matches} & set(FD_COMPS)):
        try:
            games = fetch(f"games/fixtures/?appTypeId=5&langId=27&timezoneName=Africa/Cairo"
                          f"&competitions={FD_COMPS[comp]}&showOdds=false").get("games") or []
        except Exception as e:                          # noqa: BLE001
            print(f"  ! {comp}: fixture list unreachable ({e})")
            continue
        idx = {}
        for g in games:
            names = frozenset((MB._norm((g.get("homeCompetitor") or {}).get("name") or ""),
                               MB._norm((g.get("awayCompetitor") or {}).get("name") or "")))
            idx[(names, (g.get("startTime") or "")[:10])] = g.get("id")
        for m in matches:
            if m.get("competition") != comp:
                continue
            names = frozenset((MB._norm(b.ar_team(m.get("home"))), MB._norm(b.ar_team(m.get("away")))))
            gid = idx.get((names, str(m.get("kickoff") or "")[:10]))
            if gid:
                out[m["match_id"]] = gid
    return out


def run(matches, pairs, today, fetch, max_new=MAX_NEW, log=print):
    """Ask the feed for the pairs that need it. Returns (pairs, changed)."""
    want = wanted(matches, pairs, today)[:max_new]
    ids = feed_ids([m for m in want if m.get("competition") in FD_COMPS], fetch) if want else {}
    changed = False
    for m in want:
        gid = ids.get(m["match_id"]) if m.get("competition") in FD_COMPS else m.get("match_id")
        key = pair_key(m["home"], m["away"])
        if not gid:
            log(f"  - {key}: no feed game id")
            continue
        try:
            hid, _aid, games = parse_feed(fetch(f"games/h2h/?appTypeId=5&langId=27&gameId={int(gid)}"))
        except Exception as e:                          # noqa: BLE001
            log(f"  ! {key}: feed unreachable ({e})")
            continue
        cur = pairs.get(key) or {"a": sorted([m["home"], m["away"]])[0], "b": sorted([m["home"], m["away"]])[1]}
        got = to_sides(games, hid, a_is_home=(cur["a"] == m["home"]))
        merged, n = merge(cur.get("games") or [], got)
        pairs[key] = {"fetched": today.isoformat(), "a": cur["a"], "b": cur["b"], "games": merged}
        changed = True
        log(f"  {key}: feed {len(got)}, added {n}, held {len(merged)}")
    return pairs, changed


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--max", type=int, default=MAX_NEW)
    a = ap.parse_args()
    try:
        import match_brief as MB
        from site_lib.loaders import load as load_data
        matches = load_data("matches.json")
        pairs = load()
        today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).date()
        if a.dry:
            for m in wanted(matches, pairs, today)[:a.max]:
                print(f"  would ask: {m.get('kickoff')} {m.get('competition')} {pair_key(m['home'], m['away'])}")
            return 0
        pairs, changed = run(matches, pairs, today, MB._s365, a.max)
        if changed:
            with open(OUT, "w", encoding="utf-8", newline="\n") as f:
                json.dump({"_why": WHY, "pairs": pairs}, f, ensure_ascii=False, indent=1)
                f.write("\n")
            print(f"  wrote data/h2h_feed.json ({len(pairs)} pairs)")
        else:
            print("  nothing to ask")
    except Exception as e:                              # noqa: BLE001 - never fails the publish run
        print(f"h2h_feed: skipped ({e!r})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
