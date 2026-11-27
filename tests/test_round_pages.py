# -*- coding: utf-8 -*-
"""/fixtures/<slug>/round-N - a league round as its own page (2026-11-27).

    python tests/test_round_pages.py     (from the repo root)
"""
import io, os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
from site_lib import rounds as RD

fails = 0
def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    fails += not cond

EGY = "Egyptian Premier League"
def m(i, rnd, day, st="UPCOMING", hs=None, as_=None, h="الأهلي", a="الزمالك", t="18:00"):
    return {"match_id": i, "round": rnd, "kickoff": day, "koff_time": t, "status": st, "home_score": hs, "away_score": as_,
            "home": h, "away": a, "competition": EGY}

R8 = [m(81, 8, "2026-10-28", "FINISHED", 1, 1), m(82, 8, "2026-10-31", "FINISHED", 2, 0, "بيراميدز", "سموحة")]
R9 = [m(91, 9, "2026-11-23", "FINISHED", 0, 2, "الأهلي", "بيراميدز"), m(92, 9, "2026-12-10", "UPCOMING", h="بيراميدز", a="بتروجت")]
R10 = [m(101, 10, "2026-12-08"), m(102, 10, "2026-12-10", h="المصري", a="الزمالك")]
R11 = [m(111, 11, "2026-12-14")]
R12 = [m(121, 12, "2026-12-22")]
FX = {"current": 9, "rounds": [{"round": 8, "matches": R8}, {"round": 9, "matches": R9}, {"round": 10, "matches": R10},
                               {"round": 11, "matches": R11}, {"round": 12, "matches": R12},
                               {"round": 99, "label": "نصف النهائي", "matches": [m(991, 99, "2027-05-01")]}]}

ck("1 one line names the leagues that get round pages: Egypt, then Saudi Arabia (2026-11-27)",
   RD.ROUND_COMPS == (EGY, "Saudi Pro League") and RD.round_url("Saudi Pro League", 12) == "/fixtures/saudi/round-12.html")
ck("2 the URL: /fixtures/<slug>/round-N", RD.round_url(EGY, 9) == "/fixtures/egypt/round-9.html")
ck("3 numbered rounds only - a cup's stage (a label) gets no page", [n for n, _ in RD.numbered(FX)] == [8, 9, 10, 11, 12])
ck("4 the three states", (RD.state(R8), RD.state(R9), RD.state(R10)) == ("done", "on", "coming"))
post = R8 + [m(83, 8, "2026-10-30", "POSTPONED")]
ck("5 a postponed match does not hold a round open", RD.state(post) == "done" and "مباراة واحدة مؤجلة" in RD.intro(EGY, 8, post))
# the round on show is the site's own rule (tables.round_on_show): the round of the NEAREST match to
# come - round 10 (8 December), not round 9 whose last match was moved to the 10th
ck("6 the window: the round on show, the one before, the one after", RD.window(FX) == [9, 10, 11], str(RD.window(FX)))
ck("7 a played round is indexable for good; a round to come only inside the window",
   RD.indexable(FX, 8, R8) and RD.indexable(FX, 10, R10) and not RD.indexable(FX, 12, R12))
ck("8 «the table after round n» only while no later round has begun", not RD.is_latest(FX, 8) and RD.is_latest(FX, 9))
t_c, t_o = RD.title(EGY, 10, R10, True), RD.title(EGY, 9, R9, True)
t_d, t_old = RD.title(EGY, 9, [R9[0]], True), RD.title(EGY, 8, R8, False)
ck("9 a round to come: «مواعيد مباريات الجولة N … والقنوات الناقلة»", t_c == "مواعيد مباريات الجولة 10 من الدوري المصري والقنوات الناقلة", t_c)
ck("10 a round under way: its results and what is left", t_o == "نتائج الجولة 9 من الدوري المصري والمباريات المتبقية", t_o)
ck("11 the latest finished round: «… وترتيب الدوري بعدها»; an older one never promises a table",
   t_d == "نتائج الجولة 9 من الدوري المصري وترتيب الدوري بعدها" and "ترتيب" not in t_old, f"{t_d} | {t_old}")
ck("12 every title fits the search result", all(len(t) <= RD.TITLE_MAX for t in (t_c, t_o, t_d, t_old)))
ck("13 the sentence of a round to come: its days and how many matches",
   RD.intro(EGY, 10, R10) == "تقام الجولة 10 من الدوري المصري من الثلاثاء 8 ديسمبر 2026 إلى الخميس 10 ديسمبر 2026: مباراتان.", RD.intro(EGY, 10, R10))
ck("14 a finished round: its goals, counted from the scores", "انتهت الجولة 8" in RD.intro(EGY, 8, R8) and "سُجل فيها 4 أهداف." in RD.intro(EGY, 8, R8), RD.intro(EGY, 8, R8))
ck("15 under way: played and left, in words", "لُعبت مباراة واحدة من الجولة 9" in RD.intro(EGY, 9, R9) and "وبقيت مباراة واحدة." in RD.intro(EGY, 9, R9), RD.intro(EGY, 9, R9))
q9 = RD.faq(EGY, 9, R9)
ck("16 the questions of a round under way: what is left, the results, the channel",
   [q for q, _ in q9] == ["متى المباريات المتبقية من الجولة 9 من الدوري المصري؟", "ما نتائج الجولة 9 من الدوري المصري؟",
                         "ما القناة الناقلة لمباريات الجولة 9 من الدوري المصري؟"], str([q for q, _ in q9]))
ck("17 the result is written home first with its score", q9[1][1] == "الأهلي 0 - 2 بيراميدز.", q9[1][1])
ck("18 a finished round asks no date and no channel", [q for q, _ in RD.faq(EGY, 8, R8)] == ["ما نتائج الجولة 8 من الدوري المصري؟"])
ck("19 nothing judged: no «أفضل», «مفاجأة», «تاريخ» in any sentence",
   not any(w in s for s in (RD.intro(EGY, 8, R8), RD.intro(EGY, 9, R9), RD.intro(EGY, 10, R10)) for w in ("أفضل", "مفاجأة", "تاريخ")))
src = io.open("site_pages/rounds.py", encoding="utf-8").read()
ck("20 the page: rows freshened from the day's pool and linked, the table only for the latest round, far rounds noindex",
   "pool.get(m.get(\"match_id\"), m)" in src and "if table and latest and st != \"coming\":" in src
   and "if not RD.indexable(fx, n, ms):" in src and "if n in win:" in src)
b = io.open("build_site.py", encoding="utf-8").read()
ck("21 built once, after the match pages and before the sitemap", b.count("round_pages(fx_by_comp, st_by_comp, forms, m_all, urls)") == 1
   and b.index("m_all = match_pages(") < b.index("round_pages(fx_by_comp"))
ck("22 the league's fixtures page links the window's rounds", "_RD.round_url(comp, _n)" in io.open("site_pages/leagues.py", encoding="utf-8").read())
msrc = io.open("site_pages/matches.py", encoding="utf-8").read()
mtpl = io.open("site_src/templates/match.html", encoding="utf-8").read()
ck("23 a match of a round that has a page links it from its breadcrumb (and from the breadcrumb data)",
   "(m.get(\"competition\"), m.get(\"round\")) in _round_pages" in msrc and "_RD.round_url(m[\"competition\"], m[\"round\"])" in msrc
   and '{% if round_href %} › <a href="{{ round_href }}">{{ round_label }}</a>{% endif %}' in mtpl
   and "[(round_label, SITE_BASE + round_href)] if round_href else []" in msrc)
from site_lib.tables import other_matches_panel as OMP, OTHER_MAX
_fx = {"rounds": [{"round": 1, "matches": [{"match_id": 1}]}]}
_pg = {1: {"match_id": 1, "competition": "C", "kickoff": "2026-11-25", "home": "A", "away": "B", "status": "FINISHED", "home_score": 1, "away_score": 0},
       2: {"match_id": 2, "competition": "C", "kickoff": "2026-11-21", "koff_time": "18:00", "home": "X", "away": "Y", "status": "FINISHED", "home_score": 2, "away_score": 2},
       3: {"match_id": 3, "competition": "D", "kickoff": "2026-11-21", "home": "P", "away": "Q", "status": "UPCOMING"}}
_h = OMP("C", _fx, _pg)
ck("24 a league's fixtures page lists the match pages its rounds do not (32 Under-17 World Cup pages had no link at all)",
   'href="/m/2.html"' in _h and "/m/1.html" not in _h and "/m/3.html" not in _h and "مباريات أخرى في" in _h)
ck("25 nothing extra when the rounds hold every page, or with no pages; capped", OMP("C", {"rounds": [{"round": 1, "matches": [{"match_id": 1}, {"match_id": 2}]}]}, _pg) == ""
   and OMP("C", _fx, None) == "" and OTHER_MAX == 120
   and "other_matches_panel(comp, fx, m_all)" in io.open("site_pages/leagues.py", encoding="utf-8").read())
# ---- a postponed match the feed listed again under a new id (the Saudi round 13)
from site_lib.tables import relisted
SA = "Saudi Pro League"
def sm(i, h, a, day, status="UPCOMING"):
    return {"match_id": i, "home": h, "away": a, "kickoff": day, "koff_time": "19:00", "status": status,
            "home_score": None, "away_score": None, "competition": SA}
G = {"current": 13, "rounds": [
    {"round": 13, "matches": [sm(1, "Al Fateh", "Al Riyadh", "2026-11-06", "POSTPONED"), sm(2, "Al Fateh", "Al Riyadh", "2026-11-26"),
                              sm(3, "Al Hazem", "Al Nassr", "2026-11-06", "POSTPONED")]},
    {"round": 14, "matches": [sm(4, "Al Riyadh", "Al Fateh", "2026-12-04")]}]}
ck("26 the old row of a match listed again is a ghost; a postponed match with no new date is not, nor the return leg",
   relisted(G) == {1}, str(relisted(G)))
ck("27 the round's page holds the match once, on its new date",
   [m["match_id"] for m in dict(RD.numbered(G))[13]] == [2, 3] and RD.intro(SA, 13, dict(RD.numbered(G))[13]).count("مؤجلة") == 1,
   RD.intro(SA, 13, dict(RD.numbered(G))[13]))
tsrc = io.open("site_lib/tables.py", encoding="utf-8").read()
ck("28 the league's fixtures page drops the ghost too", "if m.get(\"match_id\") in _ghost:" in tsrc)
print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
