#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Save the head-to-head history of the pairs in site_lib/h2h.PAIRS.

    python h2h_history.py            # fetch every pair, merge, write
    python h2h_history.py --dry      # print what would change, write nothing

Feeds /h2h/<slug> (site_pages/h2h.py). The source is the 365scores
head-to-head feed of one game between the two clubs (PAIRS[...]["game"]):
played games only, official scores.

data/h2h_history.json is in git and ONLY GROWS: a game already saved is never
dropped or rewritten, even when the feed stops listing it (the feed keeps a
window of about 15 games). Run it by hand after adding a pair, or now and then
to pick up cup meetings outside our competitions; the build itself adds every
finished meeting it already holds, so the page does not wait for this script.
"""
import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.path.join(HERE, "data", "h2h_history.json")
WHY = ("Played meetings per pair from the 365scores head-to-head feed, saved by "
       "h2h_history.py for /h2h/<slug>. Keyed by the two Arabic names sorted and "
       "joined by '|'. Only grows: a saved game is never dropped. Notes the feed "
       "cannot know (awarded results, penalty shoot-outs) live in h2h_notes.json.")


def feed_games(game_id):
    """[{id, date, comp, home, away, hg, ag}] from the feed; raises offline."""
    import match_brief as MB
    j = MB._s365(f"games/h2h/?appTypeId=5&langId=27&gameId={int(game_id)}")
    out = []
    for x in (j.get("game") or {}).get("h2hGames") or []:
        sc = x.get("scores") or []
        if len(sc) < 2 or sc[0] is None or sc[1] is None or sc[0] < 0 or sc[1] < 0:
            continue                                   # not played yet
        out.append({"id": x.get("id"), "date": (x.get("startTime") or "")[:10],
                    "comp": x.get("competitionDisplayName") or "",
                    "home": (x.get("homeCompetitor") or {}).get("name") or "",
                    "away": (x.get("awayCompetitor") or {}).get("name") or "",
                    "hg": int(sc[0]), "ag": int(sc[1])})
    return out


def merge(old, new):
    """old + the games of `new` it does not hold (by id, then by date),
    newest first. Returns (games, how many were added)."""
    ids = {str(g.get("id")) for g in old}
    dates = {g.get("date") for g in old}
    add = [g for g in new if g.get("date") and str(g.get("id")) not in ids and g["date"] not in dates]
    games = sorted(old + add, key=lambda g: g.get("date") or "", reverse=True)
    return games, len(add)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    from site_lib.h2h import PAIRS, is_pair, pair_key
    try:
        with open(OUT, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        doc = {}
    pairs = doc.get("pairs") or {}
    changed = False
    for p in PAIRS:
        key = pair_key(p["a"], p["b"])
        try:
            got = [g for g in feed_games(p["game"]) if is_pair(p, g["home"], g["away"])]
        except Exception as e:                          # noqa: BLE001
            print(f"  ! {key}: feed unreachable ({e}) - kept as it is")
            continue
        cur = pairs.get(key) or {}
        games, n = merge(cur.get("games") or [], got)
        print(f"  {key}: feed {len(got)}, saved {len(cur.get('games') or [])}, added {n}")
        if n:
            pairs[key] = {"source": "365Scores", "fetched": datetime.date.today().isoformat(),
                          "games": games}
            changed = True
    if changed and not a.dry:
        with open(OUT, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"_why": WHY, "pairs": pairs}, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print("  wrote data/h2h_history.json")
    elif not changed:
        print("  nothing new")


if __name__ == "__main__":
    main()
