# -*- coding: utf-8 -*-
"""Both shapes of the 365scores player-chart response parse.

Run from the site root:  python tests/test_s365_charts_shape.py

Late October 2026 most leagues started answering
{"stats": {"athletesStats": {"tables": [...], "filters": ...}}} instead of the
bare list (Ligue 1 still sends the list). The parser iterated the dict, crashed
on its keys, and every league but Ligue 1 lost its scorers and assists - the
standings pages showed none. The user asked for the top 10 of each under the
table the same day (SCORERS_TOP 5 -> 10).
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import fetch_data as F

fails = []
def ok(n, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + n + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(n)


def chart(comp, cat, name, n):
    return {"id": cat, "name": name, "competitionId": comp,
            "rows": [{"entity": {"id": i, "name": f"p{i}", "competitorId": 9},
                      "stats": [{"typeId": 1, "value": str(20 - i)}]} for i in range(n)]}


tables = [chart(7, 1, "الأهداف", 15), chart(7, 3, "صناعة", 15), chart(7, 4, "صناعة أهداف متوقعة", 15)]
old = {"stats": {"athletesStats": tables}, "competitors": [{"id": 9, "name": "c"}]}
new = {"stats": {"athletesStats": {"tables": tables, "filters": []}}, "competitors": [{"id": 9, "name": "c"}]}

for label, j in (("list shape", old), ("tables shape", new)):
    g = F._s365_stat_rows(j, {7: "Premier League"}, 1, ("الأهداف",))
    a = F._s365_stat_rows(j, {7: "Premier League"}, 3, ("صناعة",))
    ok(f"{label}: goals parsed", len(g.get(7, [])) == F.SCORERS_TOP, len(g.get(7, [])))
    ok(f"{label}: assists parsed", len(a.get(7, [])) == F.SCORERS_TOP, len(a.get(7, [])))
    ok(f"{label}: chart names", len(F.s365_chart_names(j).get(7, [])) == 3)

ok("top 10 per chart", F.SCORERS_TOP == 10)
ok("empty / odd responses", F._athlete_tables({}) == [] and
   F._athlete_tables({"stats": {"athletesStats": {"filters": []}}}) == [])

print("\nALL S365-CHART-SHAPE TESTS PASSED" if not fails else f"\n{len(fails)} FAILED")
sys.exit(1 if fails else 0)
