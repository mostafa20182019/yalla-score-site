# -*- coding: utf-8 -*-
"""The cards and reels after the 2026-11-26 design review: the facts card's
font floor and shoot-out line, the results card's shoot-out note, two lines
of one colour on the race reel, the hook over a white half.

    python tests/test_cards_review.py     (from the repo root)
"""
import io, os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

fails = 0
def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    fails += not cond

# ---------------------------------------------------------------- the facts card
import facts_card as F
ck("1 the font floor and the sizes shipped", (F.MIN_SIZE, F.FEW, F.FEW_SIZE, F.MANY_SIZE) == (30, 2, 54, 40))
src = io.open("facts_card.py", encoding="utf-8").read()
ck("2 under the floor a sentence is left out, the font is not shrunk further",
   "facts = facts[:-1]" in src and "size <= 22" not in src and "if size > MIN_SIZE:" in src)
ck("3 no «×» for a match without a kick-off time", 'or "×"' not in src and "elif c.get(\"time\"):" in src)
LONG = "فاز الزمالك في آخر 5 مباريات له في الدوري المصري ولم تستقبل شباكه أي هدف في آخر 3 منها."
base = {"mode": "before", "home": "الزمالك", "away": "النادي الأفريقي", "comp": "دوري أبطال أفريقيا", "time": "18:00",
        "day": "السبت 28 نوفمبر", "home_badge": None, "away_badge": None}
for name, card in (("five long sentences with the meetings strip", dict(base, facts=[LONG] * 5, tally=[5, 2, 1, 2])),
                   ("one sentence, no kick-off time", dict(base, facts=[LONG], time="")),
                   ("no sentence at all", dict(base, facts=[]))):
    im = F.render({"card": card})
    ck(f"4 the card draws: {name}", im.size == (F.W, F.H))
after = dict(base, mode="after", home_score=1, away_score=1, facts=[LONG])
plain = F.render({"card": after})
pens = F.render({"card": dict(after, home_pens=4, away_pens=3)})
ck("5 a tie settled on penalties changes the line under the score (who went through)", plain.tobytes() != pens.tobytes())
ck("6 one number of the shoot-out alone, or a level one, changes nothing",
   F.render({"card": dict(after, home_pens=4)}).tobytes() == plain.tobytes()
   and F.render({"card": dict(after, home_pens=3, away_pens=3)}).tobytes() == plain.tobytes())
ck("7 the after-match event carries the shoot-out's score to the card",
   '"home_pens": m.get("home_pens"), "away_pens": m.get("away_pens"),' in io.open("story_events.py", encoding="utf-8").read())

# ---------------------------------------------------------------- the results card
import day_card as DC
M = {"status": "FINISHED", "home_score": 1, "away_score": 1, "home_pens": 4, "away_pens": 3}
ck("8 the note names who went through, the winner's kicks first", DC.pens_note(M, "الزمالك", "سيراميكا") == "الزمالك بالترجيح 4-3"
   and DC.pens_note(dict(M, home_pens=2, away_pens=4), "الزمالك", "سيراميكا") == "سيراميكا بالترجيح 4-2")
ck("9 no note without both numbers, for a level shoot-out, or before the final whistle",
   DC.pens_note(dict(M, away_pens=None), "أ", "ب") == "" and DC.pens_note(dict(M, home_pens=3), "أ", "ب") == ""
   and DC.pens_note(dict(M, status="LIVE"), "أ", "ب") == "" and DC.pens_note({"status": "FINISHED"}, "أ", "ب") == "")
dsrc = io.open("day_card.py", encoding="utf-8").read()
ck("10 both layouts of the card draw it under the score", dsrc.count("pens_note(m, h, a)") == 2)

# ---------------------------------------------------------------- the race reel
import race_reel as RR
import match_poster as MP
teams = ["Arsenal FC", "Manchester City FC", "Liverpool FC", "Chelsea FC"]
cols = RR.line_colours(teams)
ck("11 every line is a colour of its own club", all(c in MP.own_colours(__import__("matchup_card").kit_for(
    __import__("site_lib.names", fromlist=["ar_team"]).ar_team(t))) for t, c in zip(teams, cols)), str(cols))
tw = RR.twins(cols)
ck("12 the second red is marked a twin, the first is not", tw[0] is False and tw[2] is True and tw[3] is False, str(tw))
ck("13 colours far apart: no twin", RR.twins([(200, 16, 46), (3, 70, 148), (20, 140, 60)]) == [False, False, False])
rsrc = io.open("race_reel.py", encoding="utf-8").read()
ck("14 a twin gets its white core on the line AND on its legend chip", rsrc.count("if twin[k]:") == 2)

# ---------------------------------------------------------------- the new reel's hook
ssrc = io.open("reel_style.py", encoding="utf-8").read()
ck("15 a veil behind the hook only when a half is light", "if INK in (ink(self.hc), ink(self.ac)):" in ssrc
   and "if self.hook_veil is not None:" in ssrc and ssrc.index("img.alpha_composite(self.hook_veil)") < ssrc.index("for im, y in zip(self.hook"))
# ---------------------------------------------------------------- the Worker's full-time post
import fb_post as fp
G = {"id": 1, "c": 552, "h": "الزمالك", "a": "سيراميكا", "hs": 1, "as": 1, "ph": 4, "pa": 3}
ck("16 the full-time caption names who won the shoot-out, the winner's kicks first",
   fp.pens_line(G) == "🥅 فاز الزمالك بركلات الترجيح 4-3" and fp.whistle_caption("ft", G, []).splitlines()[1] == fp.pens_line(G)
   and fp.pens_line(dict(G, ph=2, pa=4)) == "🥅 فاز سيراميكا بركلات الترجيح 4-2")
ck("17 no line without both numbers, for a level shoot-out, or at half-time",
   fp.pens_line(dict(G, ph=None)) == "" and fp.pens_line(dict(G, pa=4)) == "" and "الترجيح" not in fp.whistle_caption("ht", G, []))
lj = io.open("liveposts.js", encoding="utf-8").read()
fsrc = io.open("fb_post.py", encoding="utf-8").read()
ck("18 the Worker sends the shoot-out's score with the full-time whistle, and the runner's card reads it",
   'kind === "ft" && g.ph != null && g.pa != null ? { ph: g.ph, pa: g.pa } : {}' in lj
   and '"hp": g.get("ph"), "ap": g.get("pa")' in fsrc)
ck("19 the Worker's own text says the same sentence (pensLine = pens_line)",
   "`🥅 فاز ${g.ph > g.pa ? g.h : g.a} بركلات الترجيح ${Math.max(g.ph, g.pa)}-${Math.min(g.ph, g.pa)}`" in lj
   and "...(pensLine(g) ? [pensLine(g)] : [])" in lj)
print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
