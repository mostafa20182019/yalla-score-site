r"""Per-match team stats - xG first (match_stats.py, 2026-10-07).

    python tests/test_match_stats.py   (from the repo root)

Pure: 365scores is a fake, the file goes to a temp folder. Pins the rules
that would silently corrupt the data if they broke: sides come from the home
competitor id (not list order), stats are read by numeric id, European games
are matched by date + both names (or ONE name + the exact score, unique),
finished-but-fresh matches wait, old matches with nothing are settled once,
the budget is respected, nothing already stored is asked again.
"""
import datetime
import json
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


import data_store as DS                                    # noqa: E402
import match_stats as MS                                   # noqa: E402

MS.PAUSE = 0
NOW = datetime.datetime(2026, 10, 7, 18, 0, tzinfo=MS.CAIRO)


def stats_doc(home_id, away_id, xg_h="1.62", xg_a="0.48", with_xg=True):
    rows = [{"id": 10, "competitorId": away_id, "value": "47%"},     # away FIRST on purpose
            {"id": 10, "competitorId": home_id, "value": "53%"},
            {"id": 3, "competitorId": home_id, "value": "12"},
            {"id": 3, "competitorId": away_id, "value": "7"},
            {"id": 4, "competitorId": home_id, "value": "5"},
            {"id": 999, "competitorId": home_id, "value": "77"}]        # an id we do not read
    if with_xg:
        rows += [{"id": 76, "competitorId": away_id, "value": xg_a},
                 {"id": 76, "competitorId": home_id, "value": xg_h}]
    return {"games": [{"homeCompetitor": {"id": home_id}, "awayCompetitor": {"id": away_id}}],
            "statistics": rows}


st, has = MS.parse_stats(stats_doc(11, 22))
ck("xG read per side by the home competitor id, not list order",
   has and st["h"]["xg"] == 1.62 and st["a"]["xg"] == 0.48, st)
ck("possession and shots parsed as numbers", st["h"]["poss"] == 53 and st["a"]["poss"] == 47 and st["h"]["shots"] == 12)
ck("unknown stat ids are ignored", all(k in MS.STAT_IDS.values() for k in st["h"]))
ck("no xG -> has_xg False", MS.parse_stats(stats_doc(1, 2, with_xg=False))[1] is False)


def row(mid, comp, day, t="20:00", home="Al Ahly", away="Zamalek", hs=1, as_=0):
    return {"match_id": mid, "competition": comp, "kickoff": day, "koff_time": t,
            "home": home, "away": away, "home_score": hs, "away_score": as_}


pool = [
    row("4800001", "Egyptian Premier League", "2026-10-01"),                     # native, old
    row("4800002", "Egyptian Premier League", "2026-10-07", t="16:00"),          # finished 2h ago -> waits
    row("4800003", "CAF Champions League", "2026-10-01"),                        # not covered
    row("560001", "Premier League", "2026-10-04", home="Arsenal FC", away="Chelsea FC", hs=2, as_=1),
    row("560002", "UEFA Champions League", "2026-10-02", home="Arsenal FC", away="Sabah FK", hs=3, as_=0),
    row("560003", "Premier League", "2026-10-04", home="Unknown FC", away="Nobody FC", hs=0, as_=0),
    row("4800004", "Egyptian Premier League", "2026-09-30", hs=None, as_=None),  # no score: not finished
]
due = MS.due(pool, {}, NOW)
ids = [r["match_id"] for r in due]
ck("due: covered + finished + 3h old; CAF, fresh and score-less skipped",
   set(ids) == {"4800001", "560001", "560002", "560003"}, ids)
ck("due: newest first", ids[0] in ("560001", "560003"), ids)
ck("due: already stored is not due", "4800001" not in [r["match_id"] for r in MS.due(pool, {"4800001": {}}, NOW)])

AR = {"Arsenal FC": "أرسنال", "Chelsea FC": "تشيلسي", "Al Ahly": "الأهلي", "Zamalek": "الزمالك"}
ar = lambda n: AR.get(n, n)                                 # noqa: E731
calls = []


def fake_s365(path):
    calls.append(path)
    if path.startswith("games/allscores/"):
        return {"games": [
            {"id": 9001, "homeCompetitor": {"name": "أرسنال", "score": 2}, "awayCompetitor": {"name": "تشيلسي", "score": 1}},
            # no Arabic spelling for Sabah: ONE name + the exact score
            {"id": 9002, "homeCompetitor": {"name": "أرسنال", "score": 3}, "awayCompetitor": {"name": "صباح", "score": 0}},
        ]}
    gid = int(path.rsplit("=", 1)[1])
    if gid == 4800001:
        return stats_doc(1, 2, "2.10", "0.70")
    return stats_doc(5, 6)


eu_ids, n_calls, _looked = MS.euro_ids([r for r in due if r["competition"] not in MS.NATIVE], fake_s365, ar)
ck("Europe: both names on the day -> the game", eu_ids.get("560001") == 9001, eu_ids)
ck("Europe: one name + exact score, unique -> the game", eu_ids.get("560002") == 9002, eu_ids)
ck("Europe: no match -> no id", "560003" not in eu_ids)
ck("Europe: one date lookup per match day", n_calls == 2, n_calls)

tmp = os.path.join(tempfile.mkdtemp(), "match_stats.json")
calls.clear()
dbg = MS.collect(pool, fake_s365, ar, now=NOW, path=tmp)
rows = MS.load(tmp)
ck("collect: native and European games stored with xG",
   rows["4800001"]["status"] == "ok" and rows["4800001"]["h"]["xg"] == 2.1 and rows["560001"]["s365_id"] == 9001, dbg)
ck("collect: the unmappable OLD match is settled as unmapped (not asked forever)",
   rows["560003"]["status"] == "unmapped", rows.get("560003"))
ck("collect: the 2-hour-old match waits", "4800002" not in rows)
ck("collect: CAF is never asked", not any("4800003" in c for c in calls))
calls.clear()
dbg2 = MS.collect(pool, fake_s365, ar, now=NOW, path=tmp)
ck("collect: a second run asks nothing already settled", dbg2["fetched"] == 0 and not calls, (dbg2, calls))

def down_s365(path):
    if path.startswith("games/allscores/"):
        raise OSError("365scores timed out")
    return stats_doc(1, 2)


tmp3 = os.path.join(tempfile.mkdtemp(), "match_stats.json")
MS.collect([r for r in pool if r["competition"] != "Egyptian Premier League"], down_s365, ar, now=NOW, path=tmp3)
ck("collect: a FAILED date lookup settles nothing (retried next run)", MS.load(tmp3) == {}, MS.load(tmp3))

tmp2 = os.path.join(tempfile.mkdtemp(), "match_stats.json")
d3 = MS.collect(pool, fake_s365, ar, now=NOW, budget=1, path=tmp2)
ck("collect: the budget caps the stats calls", d3["fetched"] == 1 and len(MS.load(tmp2)) == 1, d3)

with open(tmp, encoding="utf-8") as f:
    doc = json.load(f)
ck("file: the data store's item reader sees every row", len(DS._items(doc)) == len(rows))
ck("store: match_stats.json is a store file, merged by match_id",
   "match_stats.json" in DS.STORE_FILES and DS.ACCUMULATING["match_stats.json"]({"match_id": 7}) == "7")

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
