r"""xG on the site (2026-10-07): the league table and the match block.

    python tests/test_xg_display.py   (from the repo root)

Pure: hand-made stats rows and season pool. Pins the arithmetic (totals per
club, home/away the right way round, goals joined from the season pool), the
silence rules (a league under AN.XG_MIN_LEAGUE matches, a club under
AN.XG_MIN_MATCHES, a match without xG), and that build() hands the data to
both pages.
"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


import analysis as AN                                      # noqa: E402
from site_lib.predictions import xg_table_html              # noqa: E402
from site_lib.tables import match_stats_html                # noqa: E402

C = "Egyptian Premier League"
pool, stats = {C: []}, []
# A beats B 2-0 four times at home; A's chances 1.5 vs 0.5 each time
for i in range(4):
    mid = str(100 + i)
    pool[C].append({"match_id": int(mid), "competition": C, "home": "A", "away": "B",
                    "home_score": 2, "away_score": 0, "home_badge": None, "away_badge": None})
    stats.append({"match_id": mid, "status": "ok", "h": {"xg": 1.5}, "a": {"xg": 0.5}})
# C v D, 6 more to pass the league floor; plus one row without xG and one "none"
for i in range(6):
    mid = str(200 + i)
    pool[C].append({"match_id": int(mid), "competition": C, "home": "C", "away": "D",
                    "home_score": 0, "away_score": 1})
    stats.append({"match_id": mid, "status": "ok", "h": {"xg": 1.2}, "a": {"xg": 0.4}})
pool[C].append({"match_id": 300, "competition": C, "home": "A", "away": "E", "home_score": 1, "away_score": 1})
stats.append({"match_id": "300", "status": "none", "h": {}, "a": {}})
stats.append({"match_id": "999", "status": "ok", "h": {"xg": 9}, "a": {"xg": 9}})     # not in the pool

t = AN.xg_table(stats, pool)
c = t[C]
ck("only rows with xG AND a known finished match count", c["n"] == 10, c["n"])
a = next(x for x in c["clubs"] if x["team"] == "A")
b = next(x for x in c["clubs"] if x["team"] == "B")
ck("home club totals: xG for/against and goals", (a["n"], round(a["xgf"], 2), round(a["xga"], 2), a["gf"], a["ga"]) == (4, 6.0, 2.0, 8, 0), a)
ck("away club is the mirror", (round(b["xgf"], 2), round(b["xga"], 2), b["gf"], b["ga"]) == (2.0, 6.0, 0, 8), b)
ck("ordered by xG difference per match", c["clubs"][0]["team"] == "A" and c["clubs"][-1]["team"] == "B",
   [x["team"] for x in c["clubs"]])
ck("a club under the match floor is left out", "E" not in [x["team"] for x in c["clubs"]])

html = xg_table_html("الدوري المصري", c)
ck("table renders with every listed club", html.count("<tr><td>") == len(c["clubs"]), html.count("<tr><td>"))
ck("signs are kept left-to-right in RTL cells", '<span dir="ltr">+1.00</span>' in html)
ck("over-performers named: A scored 2.0 above its chances",
   "يسجّل أكثر من فرصه" in html and re.search(r"<bdi>A</bdi> \(<span dir=\"ltr\">\+2\.0</span> في 4\)", html), html[-400:])
ck("under-performers named: C scored 7.2 below", "يسجّل أقل من فرصه" in html and "−7.2" in html)
ck("the source is credited", "365scores" in html)
small = AN.xg_table(stats[:4], pool)[C]
ck("a league under the floor stays silent", small["n"] == 4 and xg_table_html("x", small) == "")
ck("no data -> nothing", xg_table_html("x", None) == "")

row = {"status": "ok", "h": {"xg": 2.35, "shots": 18, "sot": 7, "poss": 61}, "a": {"xg": 0.3, "shots": 4, "sot": 1, "poss": 39}}
mh = match_stats_html(row, "أتلتيكو مدريد", "ريال مدريد")
ck("match block: xG both sides, home first", re.search(r"<td class=\"good\">2\.35</td><th>الأهداف المتوقعة \(xG\)</th><td class=\"\">0\.30</td>", mh), mh[:400])
ck("match block: possession with %", "61%" in mh and "39%" in mh)
ck("match block: a stat missing on one side is skipped", "xG على المرمى" not in mh)
ck("match block: no xG row -> nothing", match_stats_html({"status": "none", "h": {}, "a": {}}, "a", "b") == ""
   and match_stats_html(None, "a", "b") == "")

src = io.open("build_site.py", encoding="utf-8").read()
ck("build() passes the stats to the match pages and the xG to the analysis pages",
   "md_idx, st_by_comp, urls, _mstats)" in src and "forms, matches, urls, _xg)" in src)
tpl = io.open("site_src/templates/analysis_league.html", encoding="utf-8").read()
ck("the league template prints the xG section", "{{ xg }}" in tpl)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
