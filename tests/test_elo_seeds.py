r"""Season carry-over Elo seeds (roadmap factor 1, 2026-09-12).

    python tests/test_elo_seeds.py    (from the repo root)
"""
import json, os, sys, tempfile
sys.path.insert(0, os.getcwd())
import analysis as A
import season_carry as SC

# 1) team_stats: a seeded club starts from its seed and exists before playing
by = {"Premier League": [{"home": "Arsenal FC", "away": "Hull City AFC", "home_score": 2, "away_score": 0,
                          "kickoff": "2026-08-15"}],
      "Egyptian Premier League": [{"home": "الأهلي", "away": "الزمالك", "home_score": 1, "away_score": 1,
                                   "kickoff": "2026-08-15"}]}
seeds = {"Premier League": {"Arsenal FC": 1622.0, "Hull City AFC": 1414.58, "Liverpool FC": 1540.0}}
flat = A.team_stats(by)
seeded = A.team_stats(by, seeds)
assert flat["Premier League"]["Arsenal FC"]["elo"] > 1500 > flat["Premier League"]["Hull City AFC"]["elo"]
ars, hull = seeded["Premier League"]["Arsenal FC"], seeded["Premier League"]["Hull City AFC"]
assert ars["elo"] > 1622.0 and hull["elo"] < 1414.58, (ars["elo"], hull["elo"])       # moved FROM the seed
assert seeded["Premier League"]["Liverpool FC"] == dict(seeded["Premier League"]["Liverpool FC"], elo=1540.0, played=0)
assert "Liverpool FC" not in flat["Premier League"]                                    # flat: unknown until it plays
assert seeded["Egyptian Premier League"]["الأهلي"]["elo"] == flat["Egyptian Premier League"]["الأهلي"]["elo"]  # unseeded league untouched
print("1 OK: seeded clubs start from the seed and exist from day one; unseeded leagues unchanged")

# 2) the same match moves Elo by the same amount from either start
d_flat = flat["Premier League"]["Arsenal FC"]["elo"] - 1500.0
d_seed = ars["elo"] - 1622.0
assert d_seed < d_flat, (d_seed, d_flat)     # a stronger favourite gains LESS for the same win
print("2 OK: a favourite by seed gains less for the same win")

# 3) seeds_from_raw: shrink, promoted, relegated
prev = {"Premier League": [
    {"home": "A", "away": "B", "home_score": 3, "away_score": 0, "date": "2025-08-01"},
    {"home": "B", "away": "C", "home_score": 0, "away_score": 2, "date": "2025-08-08"},
    {"home": "C", "away": "A", "home_score": 1, "away_score": 1, "date": "2025-08-15"}]}
now = {"Premier League": {"A", "C", "N"}}          # B relegated, N promoted
s, notes = SC.seeds_from_raw(shrink=1/3, prev=prev, clubs_now=now)
final = A.team_stats(prev)["Premier League"]
carried_B = 1500 + (final["B"]["elo"] - 1500) * (2/3)
assert abs(s["Premier League"]["A"] - (1500 + (final["A"]["elo"] - 1500) * (2/3))) < 0.01
assert "B" not in s["Premier League"] and abs(s["Premier League"]["N"] - carried_B) < 0.01
assert notes["Premier League"]["promoted"] == ["N"] and notes["Premier League"]["relegated"] == ["B"]
s0, _ = SC.seeds_from_raw(shrink=0.0, prev=prev, clubs_now=now)
assert abs(s0["Premier League"]["A"] - final["A"]["elo"]) < 0.01                       # full carry = final
print("3 OK: shrink toward 1500, promoted at the relegated mean, full carry = last season's final")

# 4) load_elo_seeds: missing file -> {} ; present -> the seeds object
assert A.load_elo_seeds(os.path.join(tempfile.gettempdir(), "no-such-elo-seeds.json")) == {}
fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
json.dump({"meta": {}, "seeds": {"Serie A": {"Juventus FC": 1580}}}, open(path, "w"))
assert A.load_elo_seeds(path) == {"Serie A": {"Juventus FC": 1580}}
os.remove(path)
print("4 OK: load_elo_seeds is absent-tolerant")
print("ALL ELO_SEEDS TESTS PASSED")
