# -*- coding: utf-8 -*-
r"""The new-style result reel (reel_style.py, 2026-11-22).

    python tests/test_reel_style.py      (from the repo root)

The words are rules over the data, so they are tested as rules: the hook
says what the score says from the side the page follows, the verdict line
appears only when the numbers say it plainly, the table scene only for a
top or drop-zone side of a big league, and the reel never runs past 15 s.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

import reel_style as RS      # noqa: E402

fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


ar = lambda n: {"Liverpool FC": "ليفربول", "Manchester United FC": "مانشستر يونايتد",
                "Chelsea FC": "تشيلسي", "Leeds United FC": "ليدز يونايتد"}.get(n, n)   # noqa: E731

print("1. the hook: the score, from the side we follow, from frame 0")
G4 = [("10", "h", "سوبوسلاي", ""), ("13", "h", "فيرتز", ""), ("66", "h", "نجوموها", ""), ("82", "h", "مونيوز", "")]
ck("a 4-0 for the side we follow: «اكتسح … برباعية نظيفة!»",
   RS.hook("ليفربول", "مانشستر يونايتد", 4, 0, "h", G4) == ["ليفربول", "اكتسح مانشستر يونايتد", "برباعية نظيفة!"])
G14 = [("25", "h", "إميغا", ""), ("28", "a", "أوكافور", ""), ("53", "a", "كالفيرت لوين", ""),
       ("58", "a", "أوكافور", ""), ("90+1", "a", "آرونسون", "")]
ck("the side we follow beaten by three at home: «اتضرب برباعية / في بيته!» (the approved sample)",
   RS.hook("تشيلسي", "ليدز يونايتد", 1, 4, "h", G14) == ["تشيلسي", "اتضرب برباعية", "في بيته!"])
ck("...and away from home it names the winner instead",
   RS.hook("ليدز", "تشيلسي", 4, 1, "a", G14)[2] == "قدام ليدز!")
late = [("30", "h", "أ", ""), ("50", "a", "ب", ""), ("90+3", "h", "ج", "")]
ck("a one-goal win decided at 85' or later: «خطف الفوز / في الدقيقة 90+3!»",
   RS.hook("الأهلي", "الزمالك", 2, 1, "h", late) == ["الأهلي", "خطف الفوز", "في الدقيقة 90+3!"])
ck("an ordinary win: «كسب …» and the score", RS.hook("الأهلي", "سموحة", 2, 1, "h", late[:2] + [("60", "h", "ج", "")])
   == ["الأهلي", "كسب سموحة", "2 - 1"])
ck("a narrow loss: «خسر قدام …»", RS.hook("الأهلي", "بيراميدز", 0, 1, "h", [("70", "a", "د", "")])[1] == "خسر قدام بيراميدز")
ck("draws: «تعادل سلبي» for 0-0, «تعادل» otherwise",
   RS.hook("أ", "ب", 0, 0, "h", [])[0] == "تعادل سلبي" and RS.hook("أ", "ب", 2, 2, "h", [])[0] == "تعادل")

print("2. the verdict line only when the numbers say it")
ST = {"h": {"poss": 57, "big": 0, "sot": 3}, "a": {"poss": 43, "big": 7, "sot": 8}}
ck("the loser had the ball: «الكورة مع تشيلسي.. / والأهداف لليدز»",
   RS.punch("تشيلسي", "ليدز", 1, 4, ST) == ["الكورة مع تشيلسي..", "والأهداف لليدز"])
ST2 = {"h": {"poss": 62, "big": 9, "sot": 11}, "a": {"poss": 38, "big": 0, "sot": 3}}
ck("big chances 9 v 0: «9 فرص محققة لليفربول.. / ومانشستر يونايتد ولا فرصة!»",
   RS.punch("ليفربول", "مانشستر يونايتد", 4, 0, ST2) == ["9 فرص محققة لليفربول..", "ومانشستر يونايتد ولا فرصة!"])
ck("«للأهلي» for a name with the article", RS.li("الأهلي") == "للأهلي" and RS.li("ليدز") == "لليدز")
ck("nothing plain to say -> no verdict; a draw -> none; no stats -> none",
   RS.punch("أ", "ب", 2, 1, {"h": {"poss": 50, "big": 2, "sot": 4}, "a": {"poss": 50, "big": 1, "sot": 3}}) is None
   and RS.punch("أ", "ب", 1, 1, ST) is None and RS.punch("أ", "ب", 2, 0, {}) is None)

print("3. the question")
q, o = RS.question("ليفربول", "مانشستر يونايتد", 4, 0, "h", G4)
ck("a win with two scorers: «مين نجم الماتش؟» between the top two", q == ["مين نجم", "الماتش؟"] and o == ["سوبوسلاي", "فيرتز"])
q, o = RS.question("تشيلسي", "ليدز", 1, 4, "h", G14)
ck("a heavy defeat of ours: «مين المسؤول عن خسارة …؟ المدرب ولا اللاعيبة»",
   q == ["مين المسؤول", "عن خسارة تشيلسي؟"] and o == ["المدرب", "اللاعيبة"])
ck("an own goal never makes a player «نجم الماتش»",
   RS.question("أ", "ب", 2, 0, "h", [("10", "h", "س", "عكسي"), ("20", "h", "ص", "")])[1] == ["أيوه", "لأ"])
ck("a draw asks whether it was fair", RS.question("أ", "ب", 1, 1, "h", [])[0] == ["التعادل ده", "عادل؟"])

print("4. the table scene: top or the drop places of a big league only")
tab = [{"pos": i, "team": f"T{i}", "pts": 40 - i} for i in range(1, 21)]
tab[18]["team"] = "Manchester United FC"
STD = [{"competition": "Premier League", "table": tab}]
m = {"match_id": 1, "competition": "Premier League", "home": "Liverpool FC", "away": "Manchester United FC",
     "home_score": 4, "away_score": 0}
tb = RS.table_block(m, STD, ar)
ck("United 19th: the last seven rows, the zone from 18, United marked",
   tb and tb["title"] == "مانشستر يونايتد في منطقة الهبوط" and tb["drop_from"] == 18
   and [r[0] for r in tb["rows"]] == list(range(14, 21)) and [r[3] for r in tb["rows"]].count(True) == 1)
tab2 = [dict(r) for r in tab]; tab2[0]["team"] = "Liverpool FC"; tab2[18]["team"] = "T19"
tb2 = RS.table_block(m, [{"competition": "Premier League", "table": tab2}], ar)
ck("a leader: «… في الصدارة», rows 1-7, no zone", tb2 and tb2["title"] == "ليفربول في الصدارة" and tb2["drop_from"] is None)
ck("mid-table, a cup, or a league outside the big five: no table scene",
   RS.table_block({**m, "home": "T5", "away": "T6"}, STD, ar) is None
   and RS.table_block({**m, "competition": "UEFA Champions League"}, STD, ar) is None)

print("5. the plan and the clock")
cfg = RS.plan(m, G4, ST2, STD, None, ar, ((200, 16, 46), (255, 255, 255)), ("u1", "u2"))
ck("both sides ours (or neither): the winner's story", cfg["hook"][0] == "ليفربول")
ck("with a table the numbers scene keeps two rows (chances, shots on target)",
   [r[0] for r in cfg["stats"]] == ["فرص محققة", "تسديدات على المرمى"])
ck("Liverpool 4-0 United fits 15 s", RS.timeline(cfg)["total"] * RS.BEAT <= 15.0, RS.timeline(cfg))
G9 = [(str(10 * k), "h" if k % 2 else "a", f"لاعب {k}", "") for k in range(1, 10)]
m9 = {**m, "home_score": sum(1 for g in G9 if g[1] == "h"), "away_score": sum(1 for g in G9 if g[1] == "a")}
c9 = RS.plan(m9, G9, ST2, STD, "h", ar, ((200, 16, 46), (255, 255, 255)), ("u1", "u2"))
ck("the worst case (nine goals + numbers + verdict + table) still fits 15 s",
   RS.timeline(c9)["total"] <= RS.MAX_BEATS and RS.timeline(c9)["step"] == 0.5, RS.timeline(c9))
c0 = RS.plan({**m, "home_score": 0, "away_score": 0}, [], {}, [], "h", ar, ((200, 16, 46), (255, 255, 255)), ("", ""))
ck("a 0-0 with no stats and no table: hook, score, question - and still a reel", RS.timeline(c0)["stats"] is None
   and RS.timeline(c0)["table"] is None and RS.timeline(c0)["total"] >= 16)
ck("each match its own key and seed (consecutive reels do not repeat one tune)",
   RS.plan({**m, "match_id": 2}, G4, ST2, STD, None, ar, ((0, 0, 0), (9, 9, 9)), ("", ""))["key"] != cfg["key"]
   or RS.plan({**m, "match_id": 3}, G4, ST2, STD, None, ar, ((0, 0, 0), (9, 9, 9)), ("", ""))["key"] != cfg["key"])
ck("short names: the surname reads («محمد صلاح» -> «صلاح»; one word stays)",
   RS.short("محمد صلاح") == "صلاح" and RS.short("دومينيك كالفيرت لوين") == "كالفيرت لوين" and RS.short("نيمار") == "نيمار")

print("6. frames")
reel = RS.Reel(cfg)
f0 = reel.frame(0)
ck("frame 0 is the hook at full size (not a fade-in): white hook text on the club colours",
   f0.size == (RS.W, RS.H) and sum(1 for x in range(100, 980, 20) for y in range(480, 640, 20)
                                    if f0.getpixel((x, y))[:3] == (255, 255, 255)) > 10)
t = RS.timeline(cfg)
fq = reel.frame(int((t["q"] + 4) * RS.BEAT * RS.FPS))
ck("the last scene is the question on the dark ground", fq.getpixel((40, 300))[:3] == RS.INK)
ft = reel.frame(int((t["table"] + 4) * RS.BEAT * RS.FPS))
ck("the table scene draws a white row for our club", sum(1 for x in range(200, 900, 25)
                                                      if ft.getpixel((x, 430 + 5 * 118 + 59))[:3] == (255, 255, 255)) > 5)
row = RS.scorer_row("آرونسون", "90+1", RS.INK, 440)
ck("a stoppage-time minute is drawn on its own (never «1+90'» through the bidi)", row.width <= 440 and row.height > 30)

print("7. the wiring")
src = open("fb_reel.py", encoding="utf-8").read()
ck("fb_reel --auto makes the new style first, the still card only as its fallback",
   "def make_reel" in src and "RS.render(cfg, path, exe)" in src and "made, caption = make_reel(m, ctx, path)" in src)
import fb_reel as R                                         # noqa: E402
ck("a posted hand-made reel covers its match: no automatic second reel (Liverpool 4-0 United, 2026-11-22)",
   "560645" in R.file_reel_matches({"file:liverpool-united-2026-11-22", "560642"})
   and R.file_reel_matches({"560642", "file:no-such-draft"}) == set())
import store as _store                                      # noqa: E402
_orig = _store.posted_ids
_store.posted_ids = lambda kind: {"file:liverpool-united-2026-11-22"}
ck("...and _posted() hands that id to --plan / --auto", "560645" in R._posted())
_store.posted_ids = _orig
ck("a hand-made draft for today's match is found by its /m/<id> link (the h2h reel then stands aside)",
   R.drafts_linking(4804736) == ["ahly-pyramids-2026-11-23"] and R.drafts_linking(None) == []
   and R.drafts_linking(48047) == [])
ck("h2h_reel --auto skips a meeting a hand-made reel covers",
   "R.drafts_linking(nx.get(\"match_id\"))" in open("h2h_reel.py", encoding="utf-8").read())
FULL = ("⚔️ الأهلي × بيراميدز: آخر 14 مواجهة بينهما\n\nالأهلي فاز 7 · تعادل 3\n\nبتشجع مين؟ 👇\n\n"
        "https://elgoon.com/h2h/al-ahly-pyramids\n#الجون #الأهلي #بيراميدز\n")
ck("a reel's caption is its TITLE + the hashtags (user, 2026-11-23: «خلىه عنوان بس»)",
   R.reel_caption(FULL) == "⚔️ الأهلي × بيراميدز: آخر 14 مواجهة بينهما\n\n#الجون #الأهلي #بيراميدز\n")
ck("...but a licence credit line always stays (CC BY needs it)",
   "رخصة CC BY 4.0" in R.reel_caption("هدف صلاح\nتفاصيل\n📷 الصورة: X — رخصة CC BY 4.0 عبر ويكيميديا كومنز\n"))
ck("post_reel trims every reel at the one place they all go up",
   "description = reel_caption(description)" in open("fb_reel.py", encoding="utf-8").read())
ck("the result reel's title is its hook",
   "' '.join(cfg['hook'])" in open("fb_reel.py", encoding="utf-8").read())
ck("numpy is in requirements.txt (the music needs it on the runner)",
   "numpy" in open("requirements.txt", encoding="utf-8").read())

print()
print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
