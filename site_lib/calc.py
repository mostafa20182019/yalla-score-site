# -*- coding: utf-8 -*-
"""«حاسبة الترتيب» (2026-11-19, step 2 of the user's «محتوى يخلى المستخدم
يرجعلك تانى»): /calc/<slug> - the reader picks the result of each coming
match and the league table re-sorts in front of them.

What a search engine's own results box does not answer: «لو الأهلي كسب
والزمالك اتعادل، الترتيب يبقى إيه؟». Everything is arithmetic on data the
site already holds - the saved table and the season's fixtures - and the
arithmetic happens in the reader's browser (snippets/calc_js.html). Nothing
is predicted and nothing is generated.

calc_data() is the one place that decides whether a league gets the page and
what the script receives; the standings page asks the same function before it
links here, so a link can never point at a page the build did not write.
"""
from site_lib.crests import local_crest
from site_lib.dates import day_month
from site_lib.names import ar_team

MIN_TEAMS = 4
# a page for two postponed matches is a stub (the Moroccan feed, 2026-11-19)
MIN_MATCHES = 5
# a match the reader can still decide: not played, and not being played now
# (a live match is the live layer's business - its score is not ours to guess)
_CLOSED = ("FINISHED", "LIVE", "IN_PLAY", "PAUSED", "CANCELLED")


def calc_data(st, fx):
    """{"teams": [...], "rounds": [...]} for one league, or None.

    st = the league's standings entry ({"table": [...]}), fx = its fixtures
    entry ({"rounds": [{"round": n, "matches": [...]}]}). A league gets the
    page only with a real table and at least one match still to play between
    two teams OF that table (a cup round, a play-off against another division
    or a renamed club would move points to a row that does not exist)."""
    table = (st or {}).get("table") or []
    if len(table) < MIN_TEAMS or not (fx or {}).get("rounds"):
        return None
    idx = {r.get("team"): i for i, r in enumerate(table)}
    teams = [{"n": ar_team(r.get("team") or ""),
              "c": local_crest(r["crest"]) if r.get("crest") else "",
              "p": int(r.get("played") or 0), "w": int(r.get("won") or 0),
              "d": int(r.get("draw") or 0), "l": int(r.get("lost") or 0),
              "gf": int(r.get("gf") or 0), "ga": int(r.get("ga") or 0),
              "pts": int(r.get("pts") or 0)} for r in table]
    rounds = []
    for rd in fx["rounds"]:
        if rd.get("label") or not isinstance(rd.get("round"), int):
            continue                      # a named stage is a cup round, not a league round
        ms = []
        for m in rd.get("matches") or []:
            if (m.get("status") or "").upper() in _CLOSED or m.get("home_score") is not None:
                continue
            h, a = idx.get(m.get("home")), idx.get(m.get("away"))
            if h is None or a is None or h == a:
                continue
            postponed = (m.get("status") or "").upper() == "POSTPONED"
            when = "مؤجلة" if postponed else (
                day_month(m.get("kickoff"), weekday=True) + (f" · {m['koff_time']}" if m.get("koff_time") else "")
                if m.get("kickoff") else "")
            ms.append([str(m.get("match_id") or f'{rd["round"]}-{h}-{a}'), h, a, when])
        if ms:
            rounds.append({"r": rd["round"], "m": ms})
    if sum(len(r["m"]) for r in rounds) < MIN_MATCHES:
        return None
    rounds.sort(key=lambda x: x["r"])
    return {"teams": teams, "rounds": rounds}


def calc_counts(data):
    return len(data["rounds"]), sum(len(r["m"]) for r in data["rounds"])
