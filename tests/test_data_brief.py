# -*- coding: utf-8 -*-
r"""Facts packs for the articles only we can write (data_brief.py, 2026-11-19).

    python tests/test_data_brief.py      (from the repo root)

Runs on the repo's own data files (the packs are made of them). What it
guards: every pack carries our data source with a key that changes with the
numbers, every number in it is in `allowed_numbers` (the guard article_put
uses), a fact is listed only when ONE side holds it, the pack's figures add
up to the table they came from, and a pack that cannot be computed says why
instead of guessing.
"""
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

import data_brief as DB        # noqa: E402
import round_brief as RB       # noqa: E402
import article_put as AP       # noqa: E402

fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


cat = DB.catalogue()
kinds = {k for k, _, key, _ in cat if key}
ck("1 the catalogue: every kind, each row either a key or the reason there is no pack",
   {k for k, *_ in cat} == set(DB.KINDS) and all((key and not why) or (not key and why) for _, _, key, why in cat))


def first(kind):
    return next((s for k, s, key, _ in cat if k == kind and key), None)


packs = {}
for kind in DB.KINDS:
    s = first(kind)
    if s:
        packs[kind] = DB.BUILD[kind](s)
ck("2 today's data gives at least one pack (the page of the tool is not empty)", bool(packs), str(kinds))

for kind, b in packs.items():
    src = b["data_source"]
    ck(f"3 {kind}: our own source, on our host, with a data: key that names the kind",
       src["name"] == RB.DATA_SOURCE_NAME and src["url"].startswith("https://elgoon.com/")
       and src["note"].startswith(f"data:{kind}:") and b["kind"] == f"data-{kind}", str(src))
    body = json.dumps({k: v for k, v in b.items() if k != "allowed_numbers"}, ensure_ascii=False)
    ck(f"4 {kind}: every number of the pack is allowed, and the pack has a note for the writer",
       RB.numbers_in(body) <= set(b["allowed_numbers"]) and b.get("note"))
    draft = {"title": "عنوان", "summary": "ملخص", "faq": [],
             "body": "<p>رقم ليس في الملخص: 987654.</p>", "sources": [src]}
    ck(f"5 {kind}: article_put's guard refuses a number the pack does not carry, and a draft without the source",
       any("987654" in p for p in AP.data_problems(draft, b))
       and any("facts pack's source" in p for p in AP.data_problems(dict(draft, sources=[], body="<p>نص</p>"), b)))

if "standing" in packs:
    b = packs["standing"]
    r = b["row"]
    ck("6 standing: the row adds up (won+draw+lost = played, 3 a win + 1 a draw = points) and the gaps are the table's",
       r["won"] + r["draw"] + r["lost"] == r["played"] and r["won"] * 3 + r["draw"] == r["pts"]
       and b["goal_difference"] == r["gf"] - r["ga"]
       and (b["above"] is None or b["points_behind_above"] == b["above"]["pts"] - r["pts"] >= 0)
       and (b["leader"] is None or b["points_behind_leader"] == b["leader"]["pts"] - r["pts"] >= 0), str(r))
    ck("7 ...the key carries the matches played: a new match is a new article, the same numbers never twice",
       b["data_source"]["note"].endswith(f":{r['played']}"))
if "number" in packs:
    b = packs["number"]
    ok = True
    for f in b["facts"]:
        row = b["rows"][f["team"]]
        ok &= all(n["value"] != f["value"] for n in f["next"]) and row["team"] == f["team"]
    ck("8 number: each fact is held by ONE side (the next ones differ), with that side's row beside it", ok and b["facts"])
    ck("9 ...and the key carries the round reached", b["data_source"]["note"].endswith(f":{b['max_played']}"))
if "h2h" in packs:
    b = packs["h2h"]
    ck("10 h2h: wins + draws = the meetings on record; newest first; the note forbids «في تاريخ المواجهات»",
       sum(b["wins"].values()) + b["draws"] == b["meetings_on_record"] >= DB.MIN_MEETINGS
       and [g["date"] for g in b["games"]] == sorted((g["date"] for g in b["games"]), reverse=True)
       and b["first_on_record"] <= b["last_on_record"] and "في تاريخ المواجهات" in b["note"])
if "minutes" in packs:
    b = packs["minutes"]
    ck("11 minutes: the quarter-hours add up to the goals, the halves to the quarter-hours, the count is stated",
       sum(b["scored_by_quarter_hour"].values()) == b["goals_for"] == b["scored_first_half"] + b["scored_second_half"]
       and sum(b["conceded_by_quarter_hour"].values()) == b["goals_against"] == b["conceded_first_half"] + b["conceded_second_half"]
       and DB.MIN_MINUTES_MATCHES <= b["matches_counted"] <= b["matches_played"])
    top = max(b["scored_by_quarter_hour"].values())
    ck("12 ...«the quarter-hour it scores most in» only when one quarter-hour stands alone",
       (b["most_scoring_quarter_hour"] is None) == (list(b["scored_by_quarter_hour"].values()).count(top) != 1 or top == 0))

ck("13 added time belongs to the quarter-hour before it; a minute that is not one gives no band",
   DB._band("45+2") == "31-45" and DB._band("90+6") == "76-90" and DB._band("1") == "1-15" and DB._band("") is None)
for bad in (("standing", "no-such-club"), ("number", "no-such-league"), ("h2h", "no-such-pair"), ("minutes", "no-such-club")):
    try:
        DB.BUILD[bad[0]](bad[1])
        ck(f"14 {bad[0]} {bad[1]}: refused", False)
    except DB.NoPack as e:
        ck(f"14 {bad[0]} {bad[1]}: refused with the reason", "see --list" in str(e))
ck("15 covered = an article whose sources carry the pack's key",
   DB.covered_keys([{"sources": [{"note": "data:number:turkey:11"}, {"note": "round:egypt:5"}, "x"]}, {"sources": None}])
   == {"data:number:turkey:11"})
ck("16 the Turkish league is second in the round pick, after the Egyptian",
   RB.LEAGUES[:2] == ["Egyptian Premier League", "Turkish Super Lig"] and len(RB.LEAGUES) == len(set(RB.LEAGUES)) == 9)        # + the Iraqi league, every two rounds (2026-11-20)
prompt = io.open(".github/prompts/daily-article.md", encoding="utf-8").read()
ck("17 the daily prompt knows the tool, its four kinds, the publish flag and the one-a-day limit",
   all(x in prompt for x in ("data_brief.py --list", "standing <club>", "number <league>", "h2h <pair>", "minutes <club>",
                             "--data-brief /tmp/brief.json", "At most ONE data article a day")))

print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
