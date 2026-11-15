"""results_archive.py (2026-09-24) - python's heir to Oracle's MATCH_RESULTS.

    python tests/test_results_archive.py   (from the repo root)

The archive carries two things the site used to take from the Oracle copy:
the WHOLE season pool (the opening rounds the feed forgets) and FROZEN results
(scorers kept after the rolling window drops them). It must freeze on exactly
Oracle's gate, never overwrite a frozen match, drop a match the feed says was
not played (the postponed Levante - Athletic that one Oracle export listed as
a frozen 0-0), be idempotent, and hand the build the shapes it reads.
"""
import os
import sys

sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8")
import results_archive as RA  # noqa: E402

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


def row(mid, hs, as_, status="FINISHED", home="الأهلي", away="الزمالك", comp="Egyptian Premier League",
        kickoff="2026-09-20"):
    return {"match_id": mid, "competition": comp, "kickoff": kickoff, "koff_time": "20:00",
            "home": home, "away": away, "home_score": hs, "away_score": as_, "status": status}


G2 = [{"side": "h", "player": "زيزو", "minute": "10"}, {"side": "a", "player": "ناصر", "minute": "70"}]

# 0) never frozen before the final whistle (2026-11-15: Gabon - Niger froze at
#    0-0 twenty minutes in, Zambia - Togo at 1-0 thirty-five minutes in)
_m = row(9, 0, 0, kickoff="2026-09-29")
_m["koff_time"] = "22:00"                                    # 19:00 UTC (Cairo +3 then)
ck("0a a match is not settled 20 minutes after kick-off", not RA.settled(_m, "2026-09-29T19:20:56Z"))
ck("0b it is settled SETTLE_MIN after kick-off", RA.settled(_m, "2026-09-29T21:15:00Z"))
ck("0c no kick-off = never settled", not RA.settled({"kickoff": None}, "2030-01-01T00:00:00Z"))
_a = {}
RA.update(_a, [_m], lambda m: None, now="2026-09-29T19:20:56Z")
ck("0d a 0-0 the feed calls FINISHED mid-match is KEPT, not frozen", "9" in _a and not _a["9"]["frozen"])
RA.update(_a, [dict(_m, home_score=2)], lambda m: None, now="2026-09-29T21:30:00Z")
ck("0e so the final score replaces it", _a["9"]["home_score"] == 2)
_b = {"9": dict(_m, match_id="9", frozen=True, frozen_at="2026-09-29T19:20:56Z", goals=None),
      "8": dict(_m, match_id="8", frozen=True, frozen_at="2026-09-29T23:00:00Z", goals=None)}
ck("0f an entry frozen before the whistle is unfrozen, a proper one is not",
   RA.unfreeze_early(_b) == ["9"] and not _b["9"]["frozen"] and _b["8"]["frozen"]
   and RA.unfreeze_early(_b) == [])
RA.update(_b, [dict(_m, home_score=2)], lambda m: None, now="2026-11-15T18:00:00Z")
ck("0g and the next run takes the feed's real score", _b["9"]["home_score"] == 2 and _b["9"]["frozen"] is False)

# 1) the completeness gate - Oracle's rule, exactly
ck("1a 0-0 is complete with no scorers (freezes at once)", RA.complete(None, 0, 0))
ck("1b 1-1 with two scorers is complete", RA.complete(G2, 1, 1))
ck("1c 2-1 with two scorers is NOT", not RA.complete(G2, 2, 1))
ck("1d no goals list for a scoring match is NOT", not RA.complete(None, 1, 0))
ck("1e an unknown score is never complete", not RA.complete([], None, 0))

# 2) update: add, freeze, keep the incomplete, count honestly
arch = {}
goals = {"1": G2, "2": G2[:1], "3": None}
res = RA.update(arch, [row(1, 1, 1), row(2, 2, 0), row(3, 0, 0), row(4, None, None, "LIVE")],
                lambda m: goals.get(str(m["match_id"])), now="T0")
ck("2a three finished rows added, the live one ignored", res == (3, 2, 0, 0) and set(arch) == {"1", "2", "3"}, res)
ck("2b 1-1 with both scorers and the 0-0 are frozen", arch["1"]["frozen"] and arch["3"]["frozen"])
ck("2c 2-0 with one scorer is kept, not frozen", not arch["2"]["frozen"] and arch["2"]["home_score"] == 2)

# 3) a frozen match is never touched again; an unfrozen one catches up
goals["1"] = [{"side": "h", "player": "WRONG", "minute": "1"}] * 3
goals["2"] = G2[:1] + [{"side": "h", "player": "تريزيجيه", "minute": "88"}]
res = RA.update(arch, [row(1, 2, 1), row(2, 2, 0)], lambda m: goals.get(str(m["match_id"])), now="T1")
ck("3a a later feed cannot rewrite a frozen score or scorers",
   arch["1"]["home_score"] == 1 and arch["1"]["goals"] == G2 and arch["1"]["frozen_at"] == "T0")
ck("3b the incomplete match freezes the moment its goals add up",
   arch["2"]["frozen"] and len(arch["2"]["goals"]) == 2 and arch["2"]["frozen_at"] == "T1", res)

# 4) idempotent: the same input twice changes nothing
before = {k: dict(v) for k, v in arch.items()}
res = RA.update(arch, [row(1, 1, 1), row(2, 2, 0), row(3, 0, 0)], lambda m: goals.get(str(m["match_id"])), now="T2")
ck("4 a second identical run adds, freezes and updates nothing", res == (0, 0, 0, 0) and arch == before, res)

# 5) the feed saying NOT PLAYED outranks the archive, frozen or not
res = RA.update(arch, [row(3, 0, 0, status="POSTPONED")], lambda m: None)
ck("5a a frozen 0-0 the feed now calls POSTPONED is removed", "3" not in arch and res[3] == 1, res)
res = RA.update(arch, [row(2, 2, 0, status="UPCOMING")], lambda m: None)
ck("5b so is a match moved into the future", "2" not in arch)
ck("5c a finished frozen match is untouched by all this", arch["1"]["frozen"] and arch["1"]["home_score"] == 1)

# 6) the shapes the build reads
arch = {}
RA.update(arch, [row(10, 1, 1, home="Liverpool FC", away="Arsenal FC", comp="Premier League")],
          lambda m: G2, now="T0")
sr = RA.season_rows(arch)
ck("6a season_rows: matches.json shape, status FINISHED, feed names kept",
   sr and sr[0]["status"] == "FINISHED" and sr[0]["home"] == "Liverpool FC"
   and sr[0]["competition"] == "Premier League" and sr[0]["home_score"] == 1)
fe = RA.frozen_entries(arch)
import build_site as B  # noqa: E402
ck("6b frozen_entries: {date, home, away, hs, as, goals} in the site's Arabic spellings",
   fe and fe[0]["date"] == "2026-09-20" and fe[0]["home"] == B.ar_team("Liverpool FC")
   and fe[0]["hs"] == 1 and fe[0]["goals"] == G2)
idx = B.goals_index([], [], fe)
got = B.match_goals(idx, row(10, 1, 1, home="Liverpool FC", away="Arsenal FC", comp="Premier League"))
ck("6c the build's goals index finds the frozen scorers for the feed row", got == G2)

# 7) save/load round trip, atomic, and the committed archive is sane
import tempfile  # noqa: E402
p = os.path.join(tempfile.mkdtemp(), "ra.json")
RA.save(arch, p)
ck("7a save -> load returns the same entries", RA.load(p) == arch and not os.path.exists(p + ".tmp"))
real = RA.load()
if real:
    ids = list(real)
    ck("7b the committed archive has no duplicate ids and every row is FINISHED-shaped",
       len(ids) == len(set(ids)) and all(r.get("home_score") is not None for r in real.values()),
       f"{len(real)} rows")
    frozen = [r for r in real.values() if r.get("frozen")]
    ck("7c every frozen row passes the gate it was frozen under",
       all(RA.complete(r.get("goals"), r["home_score"], r["away_score"]) for r in frozen),
       f"{len(frozen)} frozen")
    ck("7c2 no frozen row was frozen before its final whistle",
       not RA.unfreeze_early({k: dict(r) for k, r in real.items()}))
    ck("7d the opening weekend Oracle held survives the hand-over (>= 2026-08-13)",
       min(r["kickoff"] for r in real.values()) <= "2026-08-14")

print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL OK")
sys.exit(1 if fails else 0)
