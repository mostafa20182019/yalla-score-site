# -*- coding: utf-8 -*-
"""fetch_data._goal_rows: the scorer list a match page and a result card get
from a 365scores game detail (no network).

    python tests/test_goal_rows.py     (from the repo root)

Born 2026-10-24: El Merrikh 1-0 Horoya (CAF CL, decided on penalties) had ten
«هدف» events - one real goal at 70' and nine shoot-out kicks at 121'-125'
(stageId 11). The per-side count no longer matched the 1-0 scoreboard, the
reconciliation guard dropped the whole match, and the row showed no scorer.
The guard is right to refuse a list that does not add up; the shoot-out kicks
were never goals.
"""
import os
import sys
import importlib.util

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("fetch_data", os.path.join(ROOT, "fetch_data.py"))
fd = importlib.util.module_from_spec(spec); spec.loader.exec_module(fd)

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

H, A = 15877, 10476
def goal(cid, pid, gt, **kw):
    return {"eventType": {"name": "هدف", "subTypeName": kw.pop("sub", "هدف ميداني")},
            "competitorId": cid, "playerId": pid, "gameTime": gt, "addedTime": 0, **kw}

so = [goal(A if i % 2 else H, 100 + i, 121 + i // 2, sub="ركلة جزاء", stageId=11, statusId=11, hideFromLineup=True)
      for i in range(9)]
game = {"homeCompetitor": {"id": H, "name": "المريخ", "score": 1.0},
        "awayCompetitor": {"id": A, "name": "حوريا", "score": 0.0},
        "members": [{"id": 1, "name": "محمد عبد الرحمن"}] + [{"id": 100 + i, "name": f"لاعب {i}"} for i in range(9)],
        "events": [goal(H, 1, 70)] + so
                  + [{"eventType": {"name": "إضاعة الضّربات الجّزائيّة"}, "competitorId": H, "playerId": 105, "gameTime": 122, "stageId": 11, "statusId": 11}]}

rows, health = fd._goal_rows(game, H)
ck("1 the shoot-out kicks are not goals: one scorer, the 70' one",
   rows == [{"side": "h", "player": "محمد عبد الرحمن", "minute": "70", "tag": ""}], str(rows)[:200])
ck("2 and the list now adds up to the scoreboard", health == "ok", health)
ck("3 _is_shootout: stage 11, status 11, or past 120'",
   fd._is_shootout({"stageId": 11}) and fd._is_shootout({"statusId": 11}) and fd._is_shootout({"gameTime": 121})
   and not fd._is_shootout({"gameTime": 90, "stageId": 9}) and not fd._is_shootout({}))
# a real 120' extra-time goal is still a goal
et = dict(game, events=[goal(H, 1, 70), goal(A, 100, 118)], awayCompetitor={"id": A, "name": "حوريا", "score": 1.0})
rows, health = fd._goal_rows(et, H)
ck("4 an extra-time goal (118') stays", len(rows) == 2 and rows[1]["minute"] == "118" and health == "ok", str(rows))
# the guard itself is untouched: a list that does not add up is still refused
bad = dict(game, events=[goal(H, 1, 70)], awayCompetitor={"id": A, "name": "حوريا", "score": 1.0})
rows, health = fd._goal_rows(bad, H)
ck("5 a list short of the scoreboard is still refused (the guard stays)", not rows and health != "ok", health)

print()
print(f"{len(fails)} FAILED: {', '.join(fails)}" if fails else "ALL GOAL-ROWS TESTS PASSED")
sys.exit(1 if fails else 0)
