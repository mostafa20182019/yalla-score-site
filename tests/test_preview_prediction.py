r"""Previews carry OUR prediction (2026-10-07) - and only our numbers.

    python tests/test_preview_prediction.py   (from the repo root)

match_brief.prediction_block() builds the «توقع يلا سكور» part of a preview
brief from the same code the match page uses (site_lib.model.model_core ->
AN.predict / AN.explain, formatted with the page's _pct), and article_put.py
refuses a preview whose percentages are not in that brief, or that drops the
disclaimer, or that was published without --match-brief at all.
Pure: the model and the store are monkeypatched, nothing is read or written.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


import analysis as AN                                      # noqa: E402
import article_put as AP                                   # noqa: E402
import match_brief as MB                                   # noqa: E402
import results_archive as RA                               # noqa: E402
import site_lib.model as PREP                             # noqa: E402
import store                                               # noqa: E402
from site_lib.text import _pct                             # noqa: E402

# ---- a tiny league the model can read: two clubs, a few results
COMP = "Saudi Pro League"
H, A = "Al-Fateh", "Al-Ahli"
stats = {H: {"elo": 1450.0, "played": 7, "gf": 4, "ga": 11},
         A: {"elo": 1530.0, "played": 7, "gf": 16, "ga": 10}}
params = {"mu": 1.4, "mu_home": 1.42, "mu_away": 1.33}
PREP.model_core = lambda fixtures, res: ({}, {COMP: stats}, {COMP: params}, [])
RA.load = lambda *a, **k: {}
log = {}
for i in range(12):                     # 12 scored, 7 right, in this league
    hit = i < 7
    log[str(i)] = {"comp": COMP, "hs": 1, "as": 0, "outcome": "H", "pick": "H" if hit else "A",
                   "hit": hit, "brier": 0.5, "score_hit": False, "ph": 0.65, "pd": 0.2, "pa": 0.15}
store.pred_all = lambda: log

m = {"match_id": 4789470, "competition": COMP, "home": H, "away": A,
     "kickoff": "2026-10-09", "koff_time": "18:00", "status": "UPCOMING"}
pr = MB.prediction_block({"fixtures": []}, m)
p = AN.predict(stats, params, H, A)
ck("a block is built", isinstance(pr, dict))
ck("the probabilities are the page's, formatted the page's way",
   (pr["home_win"], pr["draw"], pr["away_win"]) == (_pct(p["ph"]), _pct(p["pd"]), _pct(p["pa"])), pr["home_win"])
ck("the most likely scores are the page's", [s["score_home_away"] for s in pr["likely_scores"]]
   == [f"{i}-{j}" for i, j, _ in p["top"]])
ck("the favourite is the largest probability", pr["favourite_prob"] == _pct(max(p["ph"], p["pd"], p["pa"])))
ck("the why part is there (both clubs have played)", "why" in pr and "league_avg_goals" in pr["why"])
ck("the record counts this league once it has 10+ scored",
   pr.get("record", {}).get("this_league") == {"scored": 12, "hits": 7, "hit_rate": "58%"}, pr.get("record"))
ck("the disclaimer rides along", "ليست نصيحة للمراهنة" in pr["disclaimer"])
ck("no model data for the competition -> no block",
   MB.prediction_block({"fixtures": []}, dict(m, competition="CAF Champions League")) is None)

# ---- the percentage guard
brief = {"kind": "preview", "match": {"match_id": 4789470}, "prediction": pr}
good_body = (f"<p>يرجّح النموذج فوز الضيف بنسبة {pr['away_win']}، والتعادل {pr['draw']}.</p>"
             f"<p>{pr['disclaimer']}</p>" + "<p>" + "كلمة " * 320 + "</p>")
rec = {"title": "توقع يلا سكور: الفتح × الأهلي", "summary": "s", "body": good_body, "author": "x",
       "pub_date": "2026-10-08", "match_id": 4789470, "kind": "preview"}
ck("the brief's own percentages pass", MB.unknown_percents(rec, brief) == [])
bad = dict(rec, body=good_body + "<p>واحتمال فوز الأهلي 70%</p>")
ck("an invented percentage is caught", MB.unknown_percents(bad, brief) == ["70"], MB.unknown_percents(bad, brief))
ar = dict(rec, summary="فرص الأهلي ٧٠٪")
ck("Arabic-Indic digits and ٪ are caught too", MB.unknown_percents(ar, brief) == ["70"])
words = dict(rec, faq=[{"q": "من الأرجح؟", "a": "الأهلي بنسبة 70 في المئة"}])
ck("«في المئة» in the FAQ is caught", MB.unknown_percents(words, brief) == ["70"])

ok, _ = AP.validate(rec, brief=brief)
ck("a correct preview validates", ok == [], ok)
no_brief, _ = AP.validate(rec)
ck("a preview without --match-brief is refused", any("--match-brief" in x for x in no_brief), no_brief)
no_disc, _ = AP.validate(dict(rec, body=good_body.replace(pr["disclaimer"], "")), brief=brief)
ck("a preview that drops the disclaimer is refused", any("ليست نصيحة للمراهنة" in x for x in no_disc), no_disc)
wrong, _ = AP.validate(dict(rec, match_id=999), brief=brief)
ck("a brief for another match is refused", any("the brief is for match" in x for x in wrong), wrong)
inv, _ = AP.validate(bad, brief=brief)
ck("the invented 70% is refused at publish time", any("70%" in x for x in inv), inv)
rep, _ = AP.validate(dict(rec, kind="report", body=good_body))
ck("a report still publishes without a brief", not any("--match-brief" in x for x in rep), rep)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
