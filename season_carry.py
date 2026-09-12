"""Season carry-over Elo seeds (roadmap factor 1, 2026-09-12).

Every club used to start the season at Elo 1500, so after three rounds a
promoted side that kept two clean sheets stood above the champion. This
module gives each club a STARTING Elo derived from last season:

    seed = 1500 + (final_elo_last_season - 1500) * (1 - SHRINK)

i.e. two thirds of last season's edge is kept, one third is given back to the
mean (the usual football-Elo practice; the exact fraction is swept in
backtest.py). Clubs that were not in the league last season (promoted) start
at the mean carried Elo of the clubs that left it (relegated) - the seats they
took. Scope: the five big European leagues only (user decision) - the
Egyptian, Saudi, Turkish and cup competitions keep the flat 1500 start.

Data: football-data.org, `?season=<prev>` for PL / PD / BL1 / SA / FL1, stored
as data/season_prev/<CODE>-<season>.json so the seeds can be recomputed
offline with a different shrink (backtest.py does exactly that). The FD_TOKEN
only exists on the GitHub runner, so `--fetch` runs there (season-carry.yml);
`--seeds` runs anywhere the raw files are committed.

    python season_carry.py --fetch           # runner: pull last season's results
    python season_carry.py --seeds           # write data/elo_seeds.json
    python season_carry.py --show            # print the seeds per league

The same seeds feed both models: analysis.team_stats(seeds=...) here and
ELO_SEEDS in the Oracle copy (oracle-yalla/26_elo_seeds.sql), so the two keep
agreeing club by club.
"""
import datetime
import json
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
PREV_DIR = os.path.join(DATA, "season_prev")
SEEDS_FILE = os.path.join(DATA, "elo_seeds.json")

# the five leagues, football-data code -> the competition name used everywhere
# else in this project (matches.json, competitions.comp_id in Oracle)
LEAGUES = {"PL": "Premier League", "PD": "Primera Division", "BL1": "Bundesliga",
           "SA": "Serie A", "FL1": "Ligue 1"}
SEASON_PREV = 2025          # football-data's season key = the year it starts (2025 = 2025/26)
SHRINK = 1.0 / 3.0          # share of last season's edge given back to the mean


def _fd_get(url, token):
    import urllib.request
    req = urllib.request.Request(url, headers={"X-Auth-Token": token, "User-Agent": "yalla-score/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch(season=SEASON_PREV, token=None):
    """Runner side: one request per league, 7 s apart (10 req/min limit)."""
    token = token or os.environ.get("FD_TOKEN", "").strip()
    if not token:
        print("FD_TOKEN not set - cannot fetch", file=sys.stderr)
        return 1
    os.makedirs(PREV_DIR, exist_ok=True)
    for i, code in enumerate(LEAGUES):
        if i:
            time.sleep(7)
        url = f"https://api.football-data.org/v4/competitions/{code}/matches?season={season}"
        try:
            doc = _fd_get(url, token)
        except Exception as e:                       # noqa: BLE001
            print(f"{code}: fetch failed - {e}", file=sys.stderr)
            return 1
        ms = [m for m in doc.get("matches", []) if m.get("status") == "FINISHED"]
        slim = [{"date": (m.get("utcDate") or "")[:10],
                 "home": (m.get("homeTeam") or {}).get("name"),
                 "away": (m.get("awayTeam") or {}).get("name"),
                 "home_score": ((m.get("score") or {}).get("fullTime") or {}).get("home"),
                 "away_score": ((m.get("score") or {}).get("fullTime") or {}).get("away")}
                for m in ms]
        slim = [m for m in slim if m["home"] and m["away"]
                and m["home_score"] is not None and m["away_score"] is not None]
        out = {"competition": LEAGUES[code], "code": code, "season": season,
               "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
               "n": len(slim), "matches": sorted(slim, key=lambda m: m["date"])}
        path = os.path.join(PREV_DIR, f"{code}-{season}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print(f"{code} {LEAGUES[code]}: {len(slim)} finished matches -> {os.path.relpath(path, HERE)}")
    return 0


def load_prev(season=SEASON_PREV):
    """{competition: [matches]} from the committed raw files (missing = skipped)."""
    out = {}
    for code, comp in LEAGUES.items():
        path = os.path.join(PREV_DIR, f"{code}-{season}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                out[comp] = json.load(f).get("matches", [])
    return out


def current_clubs():
    """{competition: set(club)} for the season now running, from the files the
    build already reads (fixtures.json has every scheduled match)."""
    clubs = {}
    for name in ("fixtures.json", "matches.json"):
        path = os.path.join(DATA, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        items = d["results"][0]["items"] if isinstance(d, dict) and "results" in d else d
        for it in items:
            comp = it.get("competition")
            if comp not in LEAGUES.values():
                continue
            ms = [it] if it.get("home") else [m for rd in it.get("rounds", []) for m in rd.get("matches", [])]
            for m in ms:
                for side in ("home", "away"):
                    if m.get(side):
                        clubs.setdefault(comp, set()).add(m[side])
    return clubs


def seeds_from_raw(shrink=SHRINK, season=SEASON_PREV, prev=None, clubs_now=None):
    """The seeds, plus the notes that explain them. Pure: no files written."""
    sys.path.insert(0, HERE)
    import analysis as A
    prev = prev if prev is not None else load_prev(season)
    clubs_now = clubs_now if clubs_now is not None else current_clubs()
    seeds, notes = {}, {}
    for comp, ms in prev.items():
        if not ms:
            continue
        final = {t: r["elo"] for t, r in A.team_stats({comp: ms})[comp].items()}
        carried = {t: 1500.0 + (e - 1500.0) * (1.0 - shrink) for t, e in final.items()}
        now = clubs_now.get(comp) or set()
        relegated = sorted(t for t in carried if now and t not in now)
        promoted = sorted(t for t in now if t not in carried)
        if relegated:
            promo_seed = statistics.mean(carried[t] for t in relegated)
        else:                       # no overlap info: start newcomers at the league's floor
            promo_seed = min(carried.values())
        comp_seeds = {t: round(carried[t], 2) for t in carried if t in now} if now else \
                     {t: round(v, 2) for t, v in carried.items()}
        for t in promoted:
            comp_seeds[t] = round(promo_seed, 2)
        seeds[comp] = comp_seeds
        notes[comp] = {"n_prev": len(ms), "clubs_prev": len(final), "clubs_now": len(now),
                       "relegated": relegated, "promoted": promoted,
                       "promoted_seed": round(promo_seed, 2),
                       "final_top": sorted(((round(e, 1), t) for t, e in final.items()), reverse=True)[:3]}
    return seeds, notes


def write_seeds(shrink=SHRINK, season=SEASON_PREV):
    seeds, notes = seeds_from_raw(shrink, season)
    if not seeds:
        print("no season_prev files - nothing written", file=sys.stderr)
        return 1
    doc = {"meta": {"season_prev": season, "shrink": round(shrink, 4),
                    "method": "seed = 1500 + (final_prev - 1500) * (1 - shrink); promoted = mean carried Elo of the relegated",
                    "leagues": sorted(seeds),
                    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")},
           "seeds": seeds, "notes": notes}
    with open(SEEDS_FILE, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    n = sum(len(v) for v in seeds.values())
    print(f"wrote {os.path.relpath(SEEDS_FILE, HERE)}: {n} clubs in {len(seeds)} leagues, shrink {shrink:.3f}")
    for comp, nt in notes.items():
        print(f"  {comp}: prev {nt['n_prev']} matches, promoted {nt['promoted']} -> {nt['promoted_seed']}, "
              f"relegated {nt['relegated']}")
    return 0


def show():
    if not os.path.exists(SEEDS_FILE):
        print("no elo_seeds.json"); return 1
    with open(SEEDS_FILE, encoding="utf-8") as f:
        d = json.load(f)
    print(d["meta"])
    for comp, s in d["seeds"].items():
        print(f"\n{comp}")
        for t, e in sorted(s.items(), key=lambda kv: -kv[1]):
            print(f"  {e:8.2f}  {t}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                    # noqa: BLE001
        pass
    args = sys.argv[1:]
    rc = 0
    if "--fetch" in args:
        rc = fetch()
    if rc == 0 and "--seeds" in args:
        rc = write_seeds()
    if rc == 0 and "--show" in args:
        rc = show()
    if not args:
        print(__doc__)
    sys.exit(rc)
