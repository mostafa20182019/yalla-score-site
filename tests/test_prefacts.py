# -*- coding: utf-8 -*-
"""«أرقام قبل المباراة» (site_lib/prefacts.py, h2h_feed.py, 2026-11-26).

The user, when the rewritten news was switched off: the site's news is what
its own data says before a match - the runs of the two sides, the last
meeting, the count of the last ten. Everything here is computed, so the
tests are about what must NEVER be said: a run counted over a season with a
hole in it, a run on a match the side does not play next, a count that
includes a result awarded by decision, a name read from the feed.

    python tests/test_prefacts.py
"""
import datetime
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import h2h_feed as HF                      # noqa: E402
from site_lib import prefacts as PF        # noqa: E402

fails = []


def ck(name, ok):
    print(("OK   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


def fm(h, a, hs, as_, day, comp="Premier League", mid=None):
    return {"match_id": mid or f"{h}{a}{day}", "competition": comp, "home": h, "away": a,
            "home_score": hs, "away_score": as_, "kickoff": day, "status": "FINISHED"}


# ---- 1. runs: A won its last 4 after a loss; B lost 3 in a row and has not scored in them
SEASON = [
    fm("A", "X", 0, 1, "2026-08-10"), fm("A", "Y", 2, 0, "2026-08-17"), fm("Z", "A", 0, 1, "2026-08-24"),
    fm("A", "W", 3, 0, "2026-08-31"), fm("V", "A", 0, 2, "2026-09-07"),
    fm("B", "X", 1, 1, "2026-08-10"), fm("Y", "B", 1, 0, "2026-08-17"), fm("B", "Z", 0, 2, "2026-08-24"),
    fm("W", "B", 3, 0, "2026-08-31"),
]
ra = PF.season_runs("A", SEASON, played=5)
ck("1 wins in a row, unbeaten, clean sheets counted from the end",
   ra["wins"] == 4 and ra["unbeaten"] == 4 and ra["clean"] == 4 and ra["losses"] == 0 and ra["p"] == 5)
rb = PF.season_runs("B", SEASON, played=4)
ck("2 losses in a row, winless over the whole season, no goal in three",
   rb["losses"] == 3 and rb["winless"] == 4 and rb["blank"] == 3)
# ---- the guard: the table says A played 6, we hold 5 -> no run at all
ck("3 a season with a hole in it gives NO run", PF.season_runs("A", SEASON, played=6) == {})
ck("4 a side with no finished match gives no run", PF.season_runs("Q", SEASON, played=0) == {})

la = [s for _w, s in PF.run_facts("أ", ra, "الدوري الإنجليزي", at_home=True)]
ck("5 «فاز في آخر 4 مباريات»: verb first, the competition named", la and la[0] == "فاز أ في آخر 4 مباريات له في الدوري الإنجليزي.")
ck("6 clean sheets said, and unbeaten NOT said twice (it is the same four)",
   any("لم يستقبل أ أي هدف في آخر 4 مباريات" in s for s in la) and not any("لم يخسر" in s for s in la))
lb = [s for _w, s in PF.run_facts("ب", rb, "الدوري الإنجليزي")]
ck("7 a run that covers the whole season is said as the season, never as «آخر»",
   "لم يفز ب بأي مباراة في الدوري الإنجليزي هذا الموسم (4 مباريات)." in lb)
ck("8 three losses and three blanks are said", any(s.startswith("خسر ب آخر 3 مباريات") for s in lb)
   and any("لم يسجل ب أي هدف في آخر 3 مباريات" in s for s in lb))
allw = PF.season_runs("C", [fm("C", "X", 1, 0, f"2026-08-{d:02d}") for d in (1, 8, 15, 22)], played=4)
ck("9 four wins of four = «كل مبارياته (4) ... هذا الموسم»",
   PF.run_facts("ج", allw, "الدوري")[0][1] == "فاز ج في كل مبارياته (4) في الدوري هذا الموسم.")
ck("10 nothing claims a first time or a record",
   not any(w in s for s in la + lb for w in ("لأول مرة", "تاريخ", "قياسي")))
ck("11 short runs are not facts", PF.run_facts("د", {"p": 6, "wins": 2, "losses": 0, "unbeaten": 4, "winless": 0,
                                                    "clean": 2, "blank": 0, "home_p": 3, "home_wins": 2,
                                                    "away_p": 3, "away_wins": 2}, "الدوري") == [])

# ---- 2. the meetings feed: sides by competitor id, never by name
FEED_J = {"game": {"homeCompetitor": {"id": 10, "name": "feed-A"}, "awayCompetitor": {"id": 20, "name": "feed-B"},
                   "h2hGames": [
    {"id": 1, "startTime": "2026-05-01T20:00", "competitionDisplayName": "الدوري", "scores": [2, 1], "statusText": "انتهت",
     "homeCompetitor": {"id": 20}, "awayCompetitor": {"id": 10}},
    {"id": 2, "startTime": "2025-12-01T20:00", "competitionDisplayName": "الدوري", "scores": [0, 0], "statusText": "انتهت",
     "homeCompetitor": {"id": 10}, "awayCompetitor": {"id": 20}},
    {"id": 3, "startTime": "2025-05-01T20:00", "competitionDisplayName": "الكأس", "scores": [3, 0], "statusText": "فوز تقني",
     "homeCompetitor": {"id": 10}, "awayCompetitor": {"id": 20}},
    {"id": 4, "startTime": "2027-01-01T20:00", "competitionDisplayName": "الدوري", "scores": [-1, -1],
     "homeCompetitor": {"id": 10}, "awayCompetitor": {"id": 20}},
    {"id": 5, "startTime": "2024-05-01T20:00", "competitionDisplayName": "الدوري", "scores": [1, 0], "statusText": "انتهت",
     "homeCompetitor": {"id": 10}, "awayCompetitor": {"id": 99}}]}}
hid, aid, games = HF.parse_feed(FEED_J)
ck("12 played meetings of THESE two only (not the coming game, not a third club)",
   (hid, aid) == (10, 20) and [g["id"] for g in games] == [1, 2, 3])
# our names: home «Zed FC» (sorts after «Alpha»), away «Alpha» -> a = Alpha, b = Zed FC
st = HF.to_sides(games, hid, a_is_home=False)
ck("13 `home` says which of a/b was at home that day", [g["home"] for g in st] == ["a", "b", "b"])
merged, n = HF.merge(st[:1], st)
ck("14 merge adds what is not held, newest first, and drops nothing", n == 2 and [g["id"] for g in merged] == [1, 2, 3]
   and HF.merge(merged, st[:1])[1] == 0 and len(HF.merge(merged, [])[0]) == 3)

UP = [{"match_id": 7, "competition": "Premier League", "home": "Zed FC", "away": "Alpha", "kickoff": "2026-11-28",
       "status": "UPCOMING"},
      {"match_id": 8, "competition": "Iraq Stars League", "home": "I1", "away": "I2", "kickoff": "2026-11-28", "status": "UPCOMING"},
      {"match_id": 9, "competition": "Premier League", "home": "Far", "away": "Away", "kickoff": "2026-12-20", "status": "UPCOMING"},
      {"match_id": 10, "competition": "Premier League", "home": "Done", "away": "Over", "kickoff": "2026-11-27", "status": "FINISHED"}]
T = datetime.date(2026, 11, 26)
ck("15 asked: a coming match of the next days in a followed competition - once",
   [m["match_id"] for m in HF.wanted(UP, {}, T)] == [7]
   and HF.wanted(UP, {"Alpha|Zed FC": {"fetched": "2026-11-20"}}, T) == []
   and [m["match_id"] for m in HF.wanted(UP, {"Alpha|Zed FC": {"fetched": "2026-10-01"}}, T)] == [7])


def fake(path):
    if "games/fixtures" in path:
        raise OSError("offline")
    return FEED_J


pairs, changed = HF.run([dict(UP[0], competition="Saudi Pro League")], {}, T, fake, log=lambda *_: None)
rec = pairs.get("Alpha|Zed FC") or {}
ck("16 a run saves the pair under our own names", changed and rec.get("a") == "Alpha" and rec.get("b") == "Zed FC"
   and len(rec["games"]) == 3 and rec["fetched"] == "2026-11-26")


def boom(path):
    raise OSError("offline")


p2, ch2 = HF.run([dict(UP[0], competition="Saudi Pro League")], {}, T, boom, log=lambda *_: None)
ck("17 an unreachable feed changes nothing and raises nothing", p2 == {} and ch2 is False)

# ---- 3. meetings in OUR names + the facts
ms = PF.meetings("Zed FC", "Alpha", pairs, before="2026-11-28")
ck("18 the feed's home side becomes our raw name (id 20 = the coming away side = Alpha)",
   [(g["home"], g["away"], g["hg"], g["ag"]) for g in ms] == [("Alpha", "Zed FC", 2, 1), ("Zed FC", "Alpha", 0, 0), ("Zed FC", "Alpha", 3, 0)])
ck("19 a result awarded by decision is listed and NOT counted", [g["counted"] for g in ms] == [True, True, False]
   and PF.tally(ms, "Zed FC", "Alpha") == (2, 0, 1, 1))
own = [fm("Zed FC", "Alpha", 4, 4, "2026-09-01"), fm("Alpha", "Zed FC", 2, 1, "2026-05-01"), fm("Zed FC", "Other", 1, 0, "2026-09-08")]
ms2 = PF.meetings("Zed FC", "Alpha", pairs, own, before="2026-11-28")
ck("20 the build's own meeting joins the list once (the feed's same day is not doubled)",
   [g["date"] for g in ms2] == ["2026-09-01", "2026-05-01", "2025-12-01", "2025-05-01"])
ck("21 `before` keeps the coming match's own day out", PF.meetings("Zed FC", "Alpha", pairs, own, before="2026-09-01")[0]["date"] == "2026-05-01")
mf = [s for _w, s in PF.meeting_facts("Zed FC", "Alpha", ms2)]
ck("22 the last meeting: winner or draw, score winner-first, competition, date",
   mf[0] == "انتهت آخر مواجهة بين الفريقين بالتعادل 4-4 في الدوري الإنجليزي (1 سبتمبر 2026).")
ck("23 the count of the last meetings, nominative («تعادلان», never «تعادلين»)",
   mf[1] == "آخر 3 مواجهات بين الفريقين: فوز واحد لAlpha، تعادلان.".replace("لAlpha", PF._lam("Alpha")))
ck("24 no «لم يفز على» from three meetings", not any("لم يفز" in s for s in mf))

# eight meetings, the home side never beaten in them: one direction only
LONG = {"H|V": {"a": "H", "b": "V", "games": [
    {"id": i, "date": f"202{5 - i // 3}-0{1 + i % 3}-10", "comp": "الدوري", "hg": 2 if i % 2 else 1, "ag": 1 if i % 2 else 1,
     "home": "a", "status": "انتهت"} for i in range(8)]}}
lf = [s for _w, s in PF.meeting_facts("H", "V", PF.meetings("H", "V", LONG))]
ck("25 «لم يفز V على H في آخر 8 مواجهات» - once, for the side that has not won",
   sum("لم يفز" in s for s in lf) == 1 and any(s.startswith("لم يفز V على H في آخر 8 مواجهات") for s in lf))
DR = {"H|V": {"a": "H", "b": "V", "games": [{"id": i, "date": f"2025-0{i + 1}-10", "comp": "", "hg": 1, "ag": 1, "home": "a",
                                           "status": "انتهت"} for i in range(4)]}}
df = [s for _w, s in PF.meeting_facts("H", "V", PF.meetings("H", "V", DR))]
ck("26 a row of draws is said as draws, not as two sides that cannot win",
   "انتهت آخر 4 مواجهات بين الفريقين بالتعادل." in df and not any("لم يفز" in s for s in df))

# ---- 4. a match: runs only on the side's NEXT match, the page section, the news list
STAND = [{"competition": "Premier League", "table": [
    {"team": "A", "pos": 1, "played": 5}, {"team": "B", "pos": 18, "played": 4},
    {"team": "X", "pos": 5, "played": 2}, {"team": "Y", "pos": 6, "played": 2}]}]
NEXT = {"match_id": 501, "competition": "Premier League", "home": "A", "away": "B", "kickoff": "2026-11-27",
        "koff_time": "21:00", "status": "UPCOMING", "home_badge": "", "away_badge": ""}
LATER = {"match_id": 502, "competition": "Premier League", "home": "B", "away": "A", "kickoff": "2026-12-05", "status": "UPCOMING"}
PF.setup([], {"Premier League": SEASON}, STAND, feed={}, matches=[NEXT, LATER])
f1, f2 = PF.for_match(NEXT), PF.for_match(LATER)
ck("27 the next match carries the runs of both sides", any("فاز A" in s for s in f1["runs"]) and any("B" in s for s in f1["runs"]))
ck("28 a later match carries NO run (the side plays again first)", f2["runs"] == [] and f2["lines"] == [])
html = PF.section_html(NEXT)
ck("29 the page section: heading, the sentences, no meetings list without meetings",
   html.startswith('<section class="minfo pf" data-t="أرقام قبل المباراة"') and "<h2>أرقام قبل مباراة A وB</h2><button" in html and html.count("<li>") == len(f1["lines"])
   and "h2h-list" not in html and "365Scores" not in html)
ck("30 no section when there is nothing to say", PF.section_html(LATER) == "")
PF.setup([], {"Premier League": SEASON}, [{"competition": "Premier League", "zeroed": True, "table": STAND[0]["table"]}],
         feed={}, matches=[NEXT])
ck("31 a zeroed (pre-season) table gives no run", PF.for_match(NEXT)["runs"] == [])
PF.setup([], {"Premier League": SEASON}, STAND, feed={"A|B": {"a": "A", "b": "B", "games": [
    {"id": 1, "date": "2026-03-01", "comp": "الدوري", "hg": 1, "ag": 2, "home": "b", "status": "انتهت"},
    {"id": 2, "date": "2025-10-01", "comp": "الدوري", "hg": 0, "ag": 0, "home": "a", "status": "بعد ركلات الترجيح"}]}},
    matches=[NEXT, LATER])
html = PF.section_html(NEXT)
ck("32 the meetings one by one, the score between the names as a pill, the winner marked, the note shown",
   'class="h2h-list"' in html and html.count('class="h2h-g"') == 2 and '<b class="h2h-sc"><span>1</span><i>-</i><span>2</span></b>' in html
   and '<b class="h2h-n w">A</b>' in html and "بعد ركلات الترجيح" in html and "365Scores" in html)
news = PF.day_news([NEXT, LATER], "2026-11-26")
ck("33 the day's news: the coming match with its strongest fact; a match days away is not news",
   [x["m"]["match_id"] for x in news] == [501] and news[0]["t"] == f1["lines"][0])
nh = PF.news_html([NEXT, LATER], "2026-11-26")
ck("34 the block links the match page and says «غدًا 21:00»", 'href="/m/501.html"' in nh and "غدًا 21:00" in nh
   and PF.news_html([LATER], "2026-11-26") == "")
ck("35 a competition outside the followed ones is never news",
   PF.day_news([dict(NEXT, competition="Iraq Stars League")], "2026-11-26") == [])

rf = PF.row_facts([NEXT, LATER, dict(NEXT, match_id=503, kickoff="2026-11-26")], "2026-11-26")
ck("35b the phone's row line: today's and tomorrow's matches by id, a later day never",
   set(rf) == {"501", "503"} and rf["501"] == f1["lines"][0])
many = [dict(NEXT, match_id=600 + i, kickoff="2026-11-26") for i in range(5)]
ck("35c three rows a day at most", len(PF.row_facts(many, "2026-11-26")) == PF.ROW_N == 3)
css = open(os.path.join(os.path.dirname(HERE), "site_src", "style.css"), encoding="utf-8").read()
shot = open(os.path.join(os.path.dirname(HERE), "site_src", "snippets", "shot_js.html"), encoding="utf-8").read()
ck("35d the line is hidden where the side column shows, one line on a phone, and not drawn in the image",
   ".mfact{display:none}" in css and "text-overflow:ellipsis" in css.split(".mrow>.mfact{")[1].split("}")[0]
   and "mfact" not in shot)

# ---- 4b. «أرقام بعد المباراة»: what the result changed, only while it is the news
import fb_post as fp                       # noqa: E402
import story_events as SE                  # noqa: E402

S2 = [fm("x0", "P", 1, 0, "2026-07-25"), fm("P", "x1", 1, 0, "2026-08-01"), fm("x2", "P", 0, 1, "2026-08-08"),
      fm("P", "x3", 2, 1, "2026-08-15"),
      fm("Q", "y1", 2, 1, "2026-07-20"), fm("y2", "Q", 1, 1, "2026-07-27"), fm("Q", "y3", 3, 1, "2026-08-03"),
      fm("y4", "Q", 2, 2, "2026-08-10"), fm("Q", "y5", 2, 1, "2026-08-17")]
FT = dict(fm("P", "Q", 2, 0, "2026-11-25", mid=900), koff_time="21:00", home_badge="", away_badge="")
T2 = [{"competition": "Premier League", "table": [
    {"team": "P", "pos": 2, "played": 5, "pts": 12}, {"team": "Q", "pos": 3, "played": 6, "pts": 11},
    {"team": "x1", "pos": 1, "played": 5, "pts": 13}]}]
F2 = {"P|Q": {"a": "P", "b": "Q", "games": [
    {"id": i, "date": f"202{5 - i // 2}-0{2 + i}-01", "comp": "الدوري", "hg": 1, "ag": 1 + i % 2, "home": "a", "status": "انتهت"}
    for i in range(4)]}}
PF.setup([], {"Premier League": S2 + [FT]}, T2, feed=F2, matches=[FT])
af = PF.for_after(FT)
ck("42 a run that grew is said as reached; a run that ended is said as ended",
   "وصل P إلى 4 انتصارات متتالية في الدوري الإنجليزي." in af["lines"]
   and "خسر Q بعد 5 مباريات دون خسارة في الدوري الإنجليزي." in af["lines"] and af["ready"] is True)
ck("43 a side beaten after meetings without a win", "فاز P على Q بعد 4 مواجهات دون فوز." in af["lines"])
ck("44 where the two stand now, from the official table", any(x.startswith("P في المركز الثاني برصيد 12 نقطة") for x in af["lines"]))
sec = PF.after_section_html(FT)
ck("45 the finished page's section", sec.startswith('<section class="minfo pf" data-t="أرقام بعد المباراة"') and "<h2>أرقام بعد مباراة P وQ</h2><button" in sec
   and 'data-mid="0 - 2"' in sec and 'data-shot="f"' in sec
   and sec.count("<li>") == len(af["lines"]))
# the table has not counted the match yet -> the runs wait, and it is not news / not a post
T_LAG = [{"competition": "Premier League", "table": [dict(r, played=r["played"] - 1) if r["team"] == "P" else r
                                                     for r in T2[0]["table"]]}]
PF.setup([], {"Premier League": S2 + [FT]}, T_LAG, feed={}, matches=[FT])
lag = PF.for_after(FT)
ck("46 a table that has not caught up: no run of that side, not ready, not news",
   lag["ready"] is False and not any("وصل P" in x for x in lag["lines"]) and PF.after_news([FT], "2026-11-25") == [])
# the side has played again since -> the old match says nothing about its runs
LATE = fm("P", "x9", 0, 0, "2026-11-29")
PF.setup([], {"Premier League": S2 + [FT, LATE]}, [{"competition": "Premier League", "table": [
    dict(r, played=6) if r["team"] == "P" else r for r in T2[0]["table"]]}], feed={}, matches=[FT])
ck("47 a later match of the side: the old page claims no run", not any("P إلى" in x or "وصل P" in x for x in PF.for_after(FT)["lines"]))
DRAW = dict(fm("H", "V", 1, 1, "2026-11-25"))
prev = [{"date": f"2026-0{i + 1}-10", "comp": "", "home": "H", "away": "V", "hg": 0, "ag": 0, "status": "", "counted": True}
        for i in range(2)]
ck("48 a third draw in a row is said - and not once the two have met again",
   PF.meeting_after(DRAW, prev) == [(6, "انتهت آخر 3 مواجهات بين الفريقين بالتعادل.")] and PF.meeting_after(DRAW, prev, later=True) == [])
PF.setup([], {"Premier League": S2 + [FT]}, T2, feed=F2, matches=[FT])
an = PF.after_news([FT], "2026-11-26")
ck("49 yesterday's result is news, with its strongest fact; the phone row carries it; an older one is not",
   [x["m"]["match_id"] for x in an] == [900] and an[0]["t"] == af["top"]
   and PF.row_facts([FT], "2026-11-26").get("900") == af["top"] and PF.after_news([FT], "2026-11-28") == [])
blk = PF.news_html([FT], "2026-11-26")
ck("50 the block: «أرقام بعد المباريات» with the score as a pill between the names",
   "أرقام بعد المباريات" in blk and '<b class="pf-sc"><span>2</span><i>-</i><span>0</span></b>' in blk)
ev2 = SE.match_facts_after([FT], [], T2, [dict(m) for m in S2] + [dict(FT)], datetime.date(2026, 11, 26), feed=F2)
ck("51 the Facebook post after a big match: once, the same sentences, the score in its first line",
   len(ev2) == 1 and ev2[0]["ref"] == "after:900" and ev2[0]["kind"] == SE.KIND_AFTER
   and ev2[0]["lines"][0] == "📊 أرقام بعد P 2 - 0 Q (الدوري الإنجليزي)"
   and all(l[2:] in af["lines"] for l in ev2[0]["lines"] if l.startswith("• ")))
ck("52 none when the streak card carries the same match, none three days later",
   SE.match_facts_after([FT], [], T2, S2 + [FT], datetime.date(2026, 11, 26), feed=F2, streak_ids={"900"}) == []
   and SE.match_facts_after([FT], [], T2, S2 + [FT], datetime.date(2026, 11, 28), feed=F2) == [])
ck("53 nothing after a match claims a first time or a record",
   not any(w in x for x in af["lines"] for w in ("لأول مرة", "تاريخ", "قياسي")))
# ---- 4c. the CARD (facts_card.py) and the page's «صورة» button
import facts_card as XC                    # noqa: E402

card = ev2[0]["card"]
ck("54 the event carries what the card draws: names, score, sentences",
   card["mode"] == "after" and (card["home"], card["away"]) == ("P", "Q") and (card["home_score"], card["away_score"]) == (2, 0)
   and card["facts"] == af["lines"])
im = XC.render(ev2[0])
ck("55 the card is drawn 1080x1350 and as JPEG bytes", im.size == (1080, 1350) and XC.render_bytes(ev2[0])[:2] == b"\xff\xd8")
ck("56 the count of the meetings is the strip of numbers - its sentence is not repeated in the list",
   XC.shown_facts({"facts": ["آخر 10 مواجهات بين الفريقين: 9 انتصارات لريال مدريد.", "x"], "tally": [10, 9, 1, 0]}) == ["x"]
   and XC.shown_facts({"facts": ["آخر 10 مواجهات بين الفريقين: 9.", "x"], "tally": None}) == ["آخر 10 مواجهات بين الفريقين: 9.", "x"]
   and len(XC.shown_facts({"facts": [str(i) for i in range(9)], "tally": None})) == XC.MAX_FACTS)
fsrc = open(os.path.join(os.path.dirname(HERE), "fb_post.py"), encoding="utf-8").read()
ck("57 the post is the card with the text as its caption, the text alone when the card fails",
   "XCard.render_bytes(ev), ev[\"text\"]" in fsrc and "card failed" in fsrc.split("import facts_card as XCard")[1][:400])
shot = open(os.path.join(os.path.dirname(HERE), "site_src", "snippets", "shot_js.html"), encoding="utf-8").read()
ck("58 the page's button draws the facts image from the section's own attributes",
   "k==='f'?jobFacts(btn)" in shot and "function drawFacts(" in shot and "data-'+k" in shot)
PF.setup([], {"Premier League": SEASON}, STAND, feed={}, matches=[NEXT, LATER])

# ---- 5. the Facebook kind: registered, behind its own switch, the same sentences

ck("36 the kind is registered once and has its own switch",
   [k for k, _ in SE.DETECTORS].count(SE.KIND_FACTS) == 1 and fp.FACTS_KINDS == (SE.KIND_FACTS, SE.KIND_AFTER)
   and SE.KIND_FACTS not in fp.SOCIAL_KINDS and SE.KIND_FACTS not in fp.FORM_KINDS)
os.environ.pop("FB_FACTS", None)
off = fp.facts_on()
os.environ["FB_FACTS"] = "on"
on = fp.facts_on()
os.environ.pop("FB_FACTS", None)
ck("37 FB_FACTS is off until the repo variable says on", off is False and on is True)
BIG = dict(NEXT, kickoff="2026-11-26", koff_time="21:00")
ARCH = [dict(m) for m in SEASON]
evs = SE.match_facts_before([BIG], [], STAND, ARCH, datetime.date(2026, 11, 26), feed={})
ck("38 a top-of-the-table match inside 24 h with three facts is one event, worded by prefacts",
   len(evs) == 1 and evs[0]["ref"] == "facts:501" and evs[0]["lines"][0] == "📊 أرقام قبل A × B (الدوري الإنجليزي)"
   and all(l[2:] in PF.for_match(BIG)["lines"] for l in evs[0]["lines"] if l.startswith("• "))
   and "⏰ اليوم 21:00 بتوقيت القاهرة" in evs[0]["lines"] and "https://elgoon.com/m/501" in evs[0]["text"])
ck("39 39 h away -> nothing; a mid-table pair -> nothing",
   SE.match_facts_before([dict(BIG, kickoff="2026-11-28")], [], STAND, ARCH, datetime.date(2026, 11, 26), feed={}) == []
   and SE.match_facts_before([dict(BIG, home="X", away="Y")], [], STAND, ARCH, datetime.date(2026, 11, 26), feed={}) == [])
src = open(os.path.join(os.path.dirname(HERE), "fb_post.py"), encoding="utf-8").read()
ck("40 a switched-off kind is neither posted nor counted as pending",
   "kind in FACTS_KINDS and not armed_facts" in src and 'ev["kind"] not in FACTS_KINDS or facts_on()' in src)
yml = open(os.path.join(os.path.dirname(HERE), ".github", "workflows", "publish.yml"), encoding="utf-8").read()
ck("41 the publish run keeps the meetings and the store carries the file",
   "python h2h_feed.py" in yml and "h2h_feed.json" in __import__("data_store").STORE_FILES)

print()
if fails:
    print(f"{len(fails)} FAILED: " + "; ".join(fails))
    sys.exit(1)
print("ALL OK")
