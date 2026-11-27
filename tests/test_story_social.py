# -*- coding: utf-8 -*-
r"""The social review's post kinds (story_social.py, 2026-11-19).

    python tests/test_story_social.py      (from the repo root)

«رقم الليلة», «سيناريو الجولة», «ركن السودان», «سؤال الجون». What this guards:
every number in a post is counted from the rows handed in (nothing from
memory), each kind fires once and only at its hour, the names are exact
(«جنوب السودان» is not «السودان»), nothing in the wording looks like betting,
and all four stay PRINTED until the repo variable FB_SOCIAL is "on".
"""
import datetime
import io
import os
import sys
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

import story_events as SE        # noqa: E402
import story_social as SS        # noqa: E402

fails = 0
CAIRO = ZoneInfo("Africa/Cairo")


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


def at(y, mo, d, h, mi=0):
    return datetime.datetime(y, mo, d, h, mi, tzinfo=CAIRO)


def res(i, h, a, hs, as_, kick, comp="Serie A", t="21:45"):
    return {"match_id": i, "home": h, "away": a, "home_score": hs, "away_score": as_, "status": "FINISHED",
            "kickoff": kick, "koff_time": t, "competition": comp}


def stat(i, hx, hsh, ax, ash):
    return {"match_id": str(i), "status": "ok", "h": {"xg": hx, "shots": hsh}, "a": {"xg": ax, "shots": ash}}


# ---------------------------------------------------------------- «رقم الليلة»
D = "2026-10-31"
ms = [res(1, "AC Milan", "FC Internazionale Milano", 3, 1, D),      # won against the numbers
      res(2, "Parma", "Atalanta", 1, 0, D),                         # a wider gap -> this one
      res(3, "Juventus", "Torino", 2, 0, D),                        # won WITH the numbers
      res(4, "Lazio", "Roma", 1, 1, D),                             # a draw: no winner to explain
      res(5, "Celje", "Sturm", 3, 2, D, comp="Some Small League")]  # nobody's league
st = [stat(1, 0.9, 7, 2.3, 19), stat(2, 0.3, 6, 2.6, 20), stat(3, 2.0, 15, 0.5, 6), stat(4, 0.2, 3, 2.9, 22),
      stat(5, 0.2, 4, 3.5, 30)]
ev = SS.night_number(ms, [], st, datetime.date(2026, 10, 31))
ck("1 one post a day: the widest gap between the result and the numbers", len(ev) == 1 and ev[0]["ref"] == D
   and ev[0]["match"]["match_id"] == 2 and ev[0]["number"] == 6, str([e.get("match") for e in ev]))
t = ev[0]["text"] if ev else ""
ck("2 the wording: the number, both shot counts, the confirmed score, one question",
   "رقم الليلة: 6" in t and "6 مرات فقط." in t and "20 مرة." in t and t.count("سدد ") == 2 and "1-0" in t and t.count("؟") == 1, t)
ev1 = SS.night_number(ms[:1], [], st, datetime.date(2026, 10, 31))
ck("3 the away side's goals and shots are its own (ميلان 3-1 إنتر: 7 against 19)",
   ev1 and "3-1" in ev1[0]["text"] and ev1[0]["shots"] == {"winner": 7, "loser": 19}
   and ev1[0]["text"].index(" 7 مرات") < ev1[0]["text"].index(" 19 مرة"))
ck("4 a win with the numbers, a draw, a league nobody follows: no post",
   SS.night_number(ms[2:], [], st, datetime.date(2026, 10, 31)) == [])
ck("5 a gap under the bar is not a story", SS.night_number(ms[:1], [], [stat(1, 0.9, 7, 1.7, 19)], datetime.date(2026, 10, 31)) == []
   and SS.night_number(ms[:1], [], [stat(1, 0.9, 14, 2.3, 19)], datetime.date(2026, 10, 31)) == [])
ck("6 no stats row for the match -> nothing is guessed", SS.night_number(ms[:1], [], [], datetime.date(2026, 10, 31)) == [])
ck("7 the clock: not before 23:00 Cairo, still «tonight» until 03:00, then gone",
   SS.night_number(ms, [], st, at(2026, 10, 31, 22, 30)) == [] and len(SS.night_number(ms, [], st, at(2026, 10, 31, 23, 5))) == 1
   and (SS.night_number(ms, [], st, at(2026, 11, 1, 0, 30)) or [{}])[0].get("ref") == D
   and SS.night_number(ms, [], st, at(2026, 11, 1, 9, 0)) == [])

# ---------------------------------------------------------------- «سيناريو الجولة»
EPL = "Egyptian Premier League"


def fxm(i, h, a, kick, status="UPCOMING"):
    return {"match_id": i, "home": h, "away": a, "kickoff": kick, "koff_time": "20:00", "status": status,
            "home_score": None, "away_score": None, "competition": EPL}


table = [{"pos": i + 1, "team": n, "played": 8, "pts": p} for i, (n, p) in
         enumerate((("بيراميدز", 24), ("الأهلي", 20), ("الزمالك", 19), ("المصري", 15), ("سموحة", 12)))]
FX = [{"competition": EPL, "rounds": [
    {"round": 8, "matches": [dict(fxm(80, "الأهلي", "سموحة", "2026-11-01"), status="FINISHED", home_score=1, away_score=0)]},
    {"round": 9, "matches": [fxm(90, "الأهلي", "المصري", "2026-11-24"), fxm(91, "الزمالك", "بيراميدز", "2026-11-23")]},
    {"round": 10, "matches": [fxm(100, "سموحة", "الأهلي", "2026-11-30")]}]}]
STD = [{"competition": EPL, "table": table}]
ev = SS.round_scenario([], FX, STD, datetime.date(2026, 11, 22))
t = ev[0]["text"] if ev else ""
ck("8 the evening before the round's FIRST match: the top three and the calculator's door",
   len(ev) == 1 and ev[0]["ref"] == f"{EPL}:R9:2026-27" and "الجولة 9" in t and "بيراميدز أول الجدول بـ24 نقطة" in t
   and "الأهلي ثاني الجدول بـ20 نقطة" in t and "https://elgoon.com/calc/egypt" in t, t)
ck("9 any other day: nothing (two days before, the day itself, the next round's eve only when it is next)",
   SS.round_scenario([], FX, STD, datetime.date(2026, 11, 21)) == [] and SS.round_scenario([], FX, STD, datetime.date(2026, 11, 23)) == []
   and SS.round_scenario([], FX, STD, datetime.date(2026, 11, 29)) == [])
ck("10 the clock: from 19:00 Cairo", SS.round_scenario([], FX, STD, at(2026, 11, 22, 18, 0)) == []
   and len(SS.round_scenario([], FX, STD, at(2026, 11, 22, 19, 1))) == 1)
ck("11 nothing that looks like betting: no «توقّع», no «اكسب», no prize, no points to win",
   not any(w in t for w in ("توقع", "توقّع", "اكسب", "جائزة", "جوائز", "رهان", "اربح")))
ck("12 a season that has not started (zeroed) or a league without a calculator page: no post",
   SS.round_scenario([], FX, [{"competition": EPL, "zeroed": True, "table": table}], datetime.date(2026, 11, 22)) == []
   and SS.round_scenario([], [dict(FX[0], competition="No Such League")], STD, datetime.date(2026, 11, 22), comps=("No Such League",)) == [])

# ---------------------------------------------------------------- «ركن السودان»
CL = "CAF Champions League"
hil = [res(1, "الهلال السوداني", "حوريا", 2, 0, "2026-09-20", CL), res(2, "سيمبا", "الهلال السوداني", 0, 1, "2026-10-04", CL),
       res(3, "الهلال السوداني", "مولودية الجزائر", 1, 1, "2026-10-25", CL),
       res(4, "الهلال السوداني", "حوريا", 3, 0, "2025-11-20", CL),                       # last season: not counted
       res(5, "الهلال", "الاتحاد", 5, 0, "2026-10-01", "Saudi Pro League")]              # the Saudi club: never
up = [{"match_id": 50, "home": "حوريا", "away": "الهلال السوداني", "kickoff": "2026-11-29", "koff_time": "21:00",
       "status": "UPCOMING", "competition": CL},
      {"match_id": 51, "home": "جنوب السودان", "away": "أنجولا", "kickoff": "2026-11-25", "koff_time": "15:00",
       "status": "UPCOMING", "competition": "Africa Cup of Nations Qualification"},
      {"match_id": 52, "home": "السودان", "away": "النيجر", "kickoff": "2026-12-02", "koff_time": "18:00",
       "status": "UPCOMING", "competition": "Africa Cup of Nations Qualification"}]
FRI = datetime.date(2026, 11, 20)
ev = SS.sudan_corner(up, [], hil, FRI)
t = ev[0]["text"] if ev else ""
ck("13 Friday: الهلال السوداني's record this season in the Champions League, counted from the rows",
   len(ev) == 1 and ev[0]["ref"] == "2026-W47" and "لعب الهلال السوداني 3 مباريات" in t and "فوز 2، تعادل 1، خسارة 0" in t
   and "سجل 4 واستقبل 1" in t, t)
ck("14 its next match with the day and the Cairo hour from the fixture", "حوريا × الهلال السوداني" in t and "29 نوفمبر" in t and "21:00" in t)
ck("15 منتخب السودان's next match - «جنوب السودان» is another team", "منتخب السودان: السودان × النيجر" in t and "جنوب" not in t)
ck("16 once a week: Friday from 20:00 Cairo, never another day",
   SS.sudan_corner(up, [], hil, datetime.date(2026, 11, 19)) == [] and SS.sudan_corner(up, [], hil, at(2026, 11, 20, 19, 0)) == []
   and len(SS.sudan_corner(up, [], hil, at(2026, 11, 20, 20, 5))) == 1)
ck("17 nothing played this season and nothing ahead: no post", SS.sudan_corner([], [], hil[3:], FRI) == [])
z = SS.sudan_corner([], [], [hil[0], hil[1]], FRI)
ck("18 a clean record says so in words, not «استقبل 0»", z and "ولم تستقبل شباكه أي هدف" in z[0]["text"] and "لعب الهلال السوداني مباراتين" in z[0]["text"])

# ---------------------------------------------------------------- «سؤال الجون»
PL = "Premier League"
teams = ["Arsenal FC", "Chelsea FC", "Liverpool FC", "Everton FC"]
lg = []
i = 0
for rnd in range(6):
    for h, a in ((teams[0], teams[1]), (teams[2], teams[3])) if rnd % 2 == 0 else ((teams[1], teams[2]), (teams[3], teams[0])):
        i += 1
        lg.append(res(i, h, a, (i * 3) % 4, i % 3, f"2026-10-{rnd + 1:02d}", PL))
day = datetime.date(2026, 11, 19)
q = SS.question_of(lg, day, comps=(PL,))
ck("19 the riddle is the DATE's: the same team every time it is worked out", q and q == SS.question_of(list(reversed(lg)), day, comps=(PL,))
   and len(q[2]) == 5)
rows = SS._league_rows(lg, PL)[q[1]][-5:] if q else []
ck("20 the five results are that team's own last five, oldest first, its goals first", q and q[2] == rows)
few = SS.question_of(lg[:4], day, comps=(PL,))
ck("21 a league whose teams have fewer than five results gives no riddle", few is None)
_S = SS
_orig_q = _S.question_of
_S.question_of = lambda pool, d, comps=(PL,), n=5: _orig_q(pool, d, comps=(PL,), n=n)
_q_ev = _S.goon_question(lg, [], day)
ck("22 the post: the league as the only hint, five results, the answer NOT in it", len(_q_ev) == 1 and _q_ev[0]["ref"] == "2026-11-19"
   and SE.ar_team(q[1]) not in _q_ev[0]["text"] and q[1] not in _q_ev[0]["text"] and _q_ev[0]["answer"] == q[1]
   and "الدوري الإنجليزي" in _q_ev[0]["text"] and _q_ev[0]["link"] is None, _q_ev[0]["text"] if _q_ev else "")
yq = _orig_q(lg, day - datetime.timedelta(days=1), comps=(PL,))
e = _q_ev[0]
ck("23 yesterday's answer opens the post ONLY when yesterday's question is on record",
   SS.with_prev(e, lambda k, r: False) == e["text"]
   and SS.with_prev(e, lambda k, r: (k, r) == (SS.KIND_QUESTION, "2026-11-18")).startswith(f"✅ إجابة سؤال أمس: {yq[1]}.\n\n")
   and e["prev_ref"] == "2026-11-18")
ck("24 the clock: from 14:00 Cairo", _S.goon_question(lg, [], at(2026, 11, 19, 13, 59)) == [] and len(_S.goon_question(lg, [], at(2026, 11, 19, 14, 0))) == 1)
_S.question_of = _orig_q

# ---------------------------------------------------------------- the switch
import fb_post as fp        # noqa: E402
src = open("fb_post.py", encoding="utf-8").read()
ck("25 the kinds are registered and are exactly fb_post's SOCIAL_KINDS",
   tuple(SS.SOCIAL_KINDS) == fp.SOCIAL_KINDS and len(SS.SOCIAL_KINDS) == 5
   and [k for k, _ in SE.DETECTORS][-5:] == list(SS.SOCIAL_KINDS) and SS.KIND_CLOCK not in SS.SOCIAL_KINDS
   and SS.KIND_MOVERS not in [k for k, _ in SE.DETECTORS])        # the movers are a reel (movers_reel.py)
os.environ.pop("FB_SOCIAL", None)
off = fp.social_on()
os.environ["FB_SOCIAL"] = "on"
on = fp.social_on()
os.environ.pop("FB_SOCIAL", None)
ck("26 FB_SOCIAL: off until the repo variable says on; printed not posted, and not counted as pending while off",
   not off and on and "(kind in SOCIAL_KINDS and not armed_social)" in src
   and '(ev["kind"] not in SOCIAL_KINDS or social_on())' in src)
wf = open(".github/workflows/fb-post.yml", encoding="utf-8").read() + open(".github/workflows/publish.yml", encoding="utf-8").read()
ck("27 both workflows hand the variable to the step", wf.count("FB_SOCIAL: ${{ vars.FB_SOCIAL }}") == 2)
for e in SE.detect(SE.load_data(), datetime.date(2026, 11, 20)):
    if e["kind"] in SS.SOCIAL_KINDS:
        ck(f"28 real data, {e['kind']}: plain lines, #الجون last, no line over 120 chars",
           e["text"].splitlines()[-1].startswith("#الجون") and all(len(x) <= 120 for x in e["text"].splitlines()), e["text"])

# ---------------------------------------------------------------- «الصاعد والهابط»
PLG = "Premier League"
tbl = [{"pos": i + 1, "team": t, "pts": p} for i, (t, p) in enumerate(
    (("Arsenal FC", 20), ("Liverpool FC", 17), ("Chelsea FC", 16), ("Everton FC", 13), ("Fulham FC", 12),
     ("Brentford FC", 10), ("Leeds United FC", 9), ("Burnley FC", 5)))]
RND = [res(1, "Arsenal FC", "Burnley FC", 2, 0, "2026-11-07", PLG), res(2, "Brentford FC", "Liverpool FC", 0, 1, "2026-11-08", PLG),
       res(3, "Everton FC", "Leeds United FC", 3, 0, "2026-11-08", PLG), res(4, "Chelsea FC", "Fulham FC", 0, 0, "2026-11-07", PLG)]
# before the round: Arsenal 17, Chelsea 15, Liverpool 14, Fulham 11, Everton 10, Brentford 10, Leeds 9, Burnley 5
mv = {t: (b, a) for t, b, a in SS.round_moves(tbl, RND)}
ck("29 the place before the round is rebuilt from the round's own points; the place after is the table's",
   mv.get(SE.ar_team("Liverpool FC")) == (3, 2) and mv.get(SE.ar_team("Chelsea FC")) == (2, 3)
   and mv.get(SE.ar_team("Fulham FC")) == (4, 5), str(mv))
ck("30 two sides level on points before the round have no certain place: both are left out (Everton, Brentford on 10)",
   SE.ar_team("Everton FC") not in mv and SE.ar_team("Brentford FC") not in mv)
FXM = [{"competition": PLG, "rounds": [{"round": 10, "matches": RND},
                                       {"round": 11, "matches": [dict(res(9, "Arsenal FC", "Everton FC", None, None, "2026-11-21", PLG), status="UPCOMING")]}]}]
big2 = [{"pos": 1, "team": "Arsenal FC", "pts": 20}, {"pos": 2, "team": "Liverpool FC", "pts": 15},
        {"pos": 3, "team": "Chelsea FC", "pts": 14}, {"pos": 4, "team": "Everton FC", "pts": 13},
        {"pos": 5, "team": "Fulham FC", "pts": 9}, {"pos": 6, "team": "Brentford FC", "pts": 8},
        {"pos": 7, "team": "Leeds United FC", "pts": 6}, {"pos": 8, "team": "Burnley FC", "pts": 5}]
# before: Arsenal 17, Chelsea 13, Liverpool 12, Everton 10, Fulham 8, Brentford 8 (level), Leeds 6, Burnley 5 -> nobody moves 2
FX2 = [{"competition": PLG, "rounds": [{"round": 10, "matches": RND}]}]
ck("31 nobody moved two places: no post", SS.round_movers([], FX2, [{"competition": PLG, "table": big2}], datetime.date(2026, 11, 9)) == [])
JT = [{"pos": 1, "team": "Everton FC", "pts": 16}, {"pos": 2, "team": "Arsenal FC", "pts": 15},
      {"pos": 3, "team": "Chelsea FC", "pts": 14}, {"pos": 4, "team": "Liverpool FC", "pts": 12},
      {"pos": 5, "team": "Fulham FC", "pts": 9}, {"pos": 6, "team": "Brentford FC", "pts": 7},
      {"pos": 7, "team": "Leeds United FC", "pts": 6}, {"pos": 8, "team": "Burnley FC", "pts": 5}]
JR = [res(1, "Burnley FC", "Arsenal FC", 1, 0, "2026-11-07", PLG), res(2, "Brentford FC", "Liverpool FC", 1, 0, "2026-11-08", PLG),
      res(3, "Everton FC", "Leeds United FC", 3, 0, "2026-11-08", PLG), res(4, "Fulham FC", "Chelsea FC", 2, 0, "2026-11-07", PLG)]
# before: Arsenal 15, Chelsea 14, Everton 13, Liverpool 12, Fulham 6, Leeds 6 (level), Brentford 4, Burnley 2
# Everton 3 -> 1 (up two); Brentford 7 -> 6, Burnley 8 -> 8
JT = [dict(r, played=10) for r in JT]        # the table holds round 10 (a lagging table gives no event)
JFX = [{"competition": PLG, "rounds": [{"round": 10, "matches": JR}, FXM[0]["rounds"][1]]}]
ev = SS.round_movers([], JFX, [{"competition": PLG, "table": JT}], datetime.date(2026, 11, 9))
t = ev[0]["text"] if ev else ""
ck("32 the evening after the round: the side that climbed two places, with both places",
   len(ev) == 1 and ev[0]["ref"] == f"{PLG}:R10:2026-27" and f"تقدم {SE.ar_team('Everton FC')} مركزين: من المركز 3 إلى 1." in t
   and "standings/england" in t, t)
ck("33 only on the day after the round's last match, from 21:00 Cairo",
   SS.round_movers([], JFX, [{"competition": PLG, "table": JT}], datetime.date(2026, 11, 10)) == []
   and SS.round_movers([], JFX, [{"competition": PLG, "table": JT}], at(2026, 11, 9, 20, 0)) == []
   and len(SS.round_movers([], JFX, [{"competition": PLG, "table": JT}], at(2026, 11, 9, 21, 5))) == 1)
later = [{"competition": PLG, "rounds": [{"round": 10, "matches": JR},
                                         {"round": 11, "matches": [res(9, "Arsenal FC", "Everton FC", 1, 0, "2026-11-09", PLG)]}]}]
ck("34 a match of another round played since: the table is not this round's table, no post",
   SS.round_movers([], later, [{"competition": PLG, "table": JT}], datetime.date(2026, 11, 9)) == [])
ck("35 a side of the round missing from the table: nothing is rebuilt", SS.round_moves(JT[:7], JR) == [])

# ---------------------------------------------------------------- «محترفونا هذا الأسبوع»
TR = "Turkish Super Lig"
wk = [dict(res(1, "طرابزون سبور", "ألانيا سبور", 2, 0, "2026-11-14", TR),
           goals=[{"side": "h", "player": "محمد صلاح", "minute": "10"}, {"side": "h", "player": "محمد صلاح", "minute": "60"}]),
      dict(res(2, "قونيا سبور", "طرابزون سبور", 1, 1, "2026-11-10", TR),
           goals=[{"side": "h", "player": "محمد صلاح", "minute": "5"}, {"side": "a", "player": "لاعب آخر", "minute": "80"}]),
      dict(res(3, "طرابزون سبور", "بشكتاش", 0, 1, "2026-11-01", TR),
           goals=[{"side": "a", "player": "محمد صلاح", "minute": "9"}])]
PL1 = [{"name": "محمد صلاح", "team": "طرابزون سبور", "nation": "مصر"}]
MON = datetime.date(2026, 11, 16)
ev = SS.abroad_week(wk, [], MON, players=PL1)
t = ev[0]["text"] if ev else ""
ck("36 Monday: the listed player's goals of the last seven days, in his OWN club's matches only",
   len(ev) == 1 and ev[0]["ref"] == "2026-W47" and "محمد صلاح سجل هدفين لـطرابزون سبور في الفوز 2-0 على ألانيا سبور." in t
   and t.count("محمد صلاح سجل") == 1, t)
ck("37 a namesake on the other side and a goal credited to the opponent are not his (the 1-1 at قونيا سبور)", "قونيا" not in t)
ck("38 an empty list, a quiet week, another weekday: no post",
   SS.abroad_week(wk, [], MON, players=[]) == [] and SS.abroad_week(wk[2:], [], MON, players=PL1) == []
   and SS.abroad_week(wk, [], datetime.date(2026, 11, 17), players=PL1) == [])
ck("39 the list file is the user's: it ships empty, so nothing posts until he names the players",
   SS.load_abroad() == [] and os.path.exists(SS.ABROAD_FILE))

# ---------------------------------------------------------------- the two cards
import social_card as SC        # noqa: E402
import tempfile                 # noqa: E402
from PIL import Image           # noqa: E402

num = SS.night_number(ms, [], st, datetime.date(2026, 10, 31))[0]
out = os.path.join(tempfile.mkdtemp(), "n.jpg")
im = SC.render(num, out)
px = im.convert("RGB").getpixel((60, 67))
ck("40 «رقم الليلة» as a card: 1080x1350, the red tag, drawn from the event alone",
   im.size == (1080, 1350) and px[0] > 190 and px[1] < 80 and len(SC.render_bytes(num)) > 20000)
qim = SC.render(_q_ev[0])
ck("41 «سؤال الجون» as a card - and the card's source never reads the answer",
   qim.size == (1080, 1350) and 'ev["answer"]' not in io.open("social_card.py", encoding="utf-8").read()
   and "ev.get(\"answer\")" not in io.open("social_card.py", encoding="utf-8").read())
ck("42 both kinds post as a photo with the text as caption, the text alone when the card fails",
   tuple(SC.CARD_KINDS) == fp.SOCIAL_CARD_KINDS and "SCard.render_bytes(ev), event_text(ev)" in src
   and "card failed" in src)

print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
