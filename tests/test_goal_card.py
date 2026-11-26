# -*- coding: utf-8 -*-
r"""The goal graphic (2026-10-17): «جووووول» + the scoring club's crest + scorer/minute + the score strip.

    python tests/test_goal_card.py     (from the repo root)

Offline: badges come from the saved City x Ipswich detail; the crests may or
may not download here (no network at the office), so the checks are about
geometry, text placement and the file, never about a fetched image.
"""
import json, os, sys, tempfile
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
from PIL import Image
import goal_card as GC

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

game = json.load(open("tests/fixtures/game_4742043_lineups.json", encoding="utf-8"))["game"]
hb, ab = GC.badges_for(game)
ck("1a badge URLs come from the competitor ids", hb.endswith("/Competitors/110") and ab.endswith("/Competitors/9"), f"{hb} {ab}")
ck("1b a game with no competitors gives no badges", GC.badges_for({}) == (None, None))

ev = {"side": "h", "player": "إيرلينغ هالاند", "minute": "66", "tag": "ج", "home": "مانشستر سيتي", "away": "إبسويتش تاون",
      "hs": 1, "as": 1, "comp": 7, "home_badge": hb, "away_badge": ab}
tmp = os.path.join(tempfile.mkdtemp(), "goal.jpg")
im = GC.render(ev, tmp)
ck("2a the card is square, like the reference", im.size == (1080, 1080))
ck("2b the file is a JPEG", open(tmp, "rb").read(3) == b"\xff\xd8\xff")
# the big word sits in the upper band: lots of white there, none mid-left
band = im.crop((200, 130, 880, 300)); white = sum(1 for p in band.getdata() if min(p) > 230)
ck("2c «جووووول» is drawn large in the upper band", white > 8000, str(white))
# the orange minute chip sits LEFT of centre at the scorer row (after the name
# in reading order, 2026-11-05; it used to come before it)
chip = im.crop((320, 724, 540, 784)); orange = sum(1 for p in chip.getdata() if p[0] > 200 and p[1] < 140 and p[2] < 60)
ck("2d the minute chip is orange", orange > 1500, str(orange))
# the score strip's two white discs
for x in (172, 908):
    px = im.getpixel((x, 968 - 56))                   # inside the white disc, above the crest
    ck(f"2e a white crest disc at x={x}", min(px) > 200, str(px))
rule = im.crop((100, 824, 480, 829)); rw = sum(1 for p in rule.getdata() if min(p) > 200)
# 2026-11-07: the dart in the rule's middle went with the wordmark - one unbroken line
ck("2g the rule runs across the card, unbroken through the middle", rw > 600 and min(im.getpixel((540, 826))) > 200, str(rw))   # a 2 px line over 380 px
_top = im.crop((440, 30, 640, 95)).convert("RGB")
ck("2h the brand at the top is the «الجون» wordmark: its black ink and white rim",
   sum(1 for p in _top.getdata() if max(p) < 60) > 800 and sum(1 for p in _top.getdata() if min(p) > 235) > 800)
b = GC.render_bytes(ev)
ck("2f render_bytes gives a JPEG", b[:3] == b"\xff\xd8\xff" and len(b) > 40_000, str(len(b)))
im2 = GC.render({**ev, "minute": "", "tag": "", "player": "هدف عكسي؟"})
ck("3 no minute -> no chip, still renders", im2.size == (1080, 1080))

# the kick-off / half-time / full-time card - the MATCH POSTER's design since
# 2026-11-22 (user: «عايزك تعمل الكروت بالشكل ده»): 1080x1350, two halves in
# the clubs' own colours, the score in the dark pill on the seam
wev = {"kind": "ft", "home": "مانشستر سيتي", "away": "إبسويتش تاون", "hs": 3, "as": 2, "comp": 7, "home_badge": hb, "away_badge": ab,
       "date": "2026-11-21",
       "goals": [{"s": "h", "p": "هالاند", "m": "12"}, {"s": "a", "p": "ديلاب", "m": "40", "t": "ج"}, {"s": "h", "p": "فودين", "m": "77"}, {"s": "h", "p": "هالاند", "m": "90+2"}, {"s": "a", "p": "هيرست", "m": "88"}]}
wim = GC.render_whistle(wev)
ck("4a the whistle card is the match poster's size", wim.size == (GC.WW, GC.WH) == (1080, 1350))
_red = wim.crop((440, 160, 640, 218)); _rp = sum(1 for p in _red.getdata() if p[0] > 190 and p[1] < 90 and p[2] < 110)
ck("4b the whistle sits on the poster's RED tag under the wordmark", _rp > 4000, str(_rp))
import match_poster as MP
_hf, _af = MP.fills("مانشستر سيتي", "إبسويتش تاون", "الدوري الإنجليزي", {})
_near = lambda p, c: sum(abs(x - y) for x, y in zip(p, c)) < 90
ck("4c the right half is the HOME club's own colour, the left the away's",
   _near(wim.getpixel((1060, 250)), _hf) and _near(wim.getpixel((20, 250)), _af),
   f"{wim.getpixel((1060, 250))} {_hf} | {wim.getpixel((20, 250))} {_af}")
_pill = wim.getpixel((540, 800 + 8))
ck("4c2 the score pill on the seam is the poster's dark ink", max(_pill) < 90 or min(_pill) > 230, str(_pill))
ck("4c3 the foot band is dark", max(wim.getpixel((540, 1340))) < 70, str(wim.getpixel((540, 1340))))
wb = GC.render_whistle_bytes({**wev, "kind": "ht", "goals": []})
ck("4d render_whistle_bytes gives a JPEG for a goalless half", wb[:3] == b"\xff\xd8\xff")
# the feed's own colours for a club our KITS table lacks (Leeds: white + yellow)
_fe = {"home": ("#1532C1", "#0A0A0A"), "away": ("#FDF9F9", "#F4F330")}
_li = GC.render_whistle({**wev, "home": "تشيلسي", "away": "ليدز يونايتد", "feed": _fe})
_lp = _li.getpixel((20, 250))
ck("4e a club outside our KITS table takes the feed's OWN colour (Leeds' yellow, not the grey slate)",
   _lp[0] > 200 and _lp[1] > 200 and _lp[2] < 120, str(_lp))
ck("4f colors_for reads the game detail's color / awayColor per side",
   GC.colors_for({"homeCompetitor": {"color": "#1532C1", "awayColor": "#0A0A0A"}, "awayCompetitor": {}})
   == {"home": ("#1532C1", "#0A0A0A")} and GC.colors_for({}) == {})
# 5 the kick-off card: «انطلقت المباراة» on the tag, 0 - 0 in the pill
kim = GC.render_whistle({**wev, "kind": "ko", "hs": 0, "as": 0, "goals": []})
ck("5a the kick-off card renders at the whistle card's size", kim.size == (GC.WW, GC.WH))
ck("5b WHISTLE_TITLE knows the kick-off", GC.WHISTLE_TITLE.get("ko") == "انطلقت المباراة")
kb = GC.render_whistle_bytes({**wev, "kind": "ko", "hs": 0, "as": 0, "goals": []})
ck("5c render_whistle_bytes gives a JPEG for the kick-off", kb[:3] == b"\xff\xd8\xff")
# 5d the second half (2026-11-22): «انطلق الشوط الثاني» on the tag, the half-time
# score in the pill and the first-half scorers, one post per match
sim = GC.render_whistle({**wev, "kind": "sh"})
ck("5d the second-half card renders at the whistle card's size with its own title",
   sim.size == (GC.WW, GC.WH) and GC.WHISTLE_TITLE.get("sh") == "انطلق الشوط الثاني")
import fb_post as _FPsh
_shc = _FPsh.whistle_caption("sh", {"id": 5, "c": 7, "h": "ليفربول", "a": "برينتفورد", "hs": 1, "as": 0},
                             [{"s": "h", "p": "صلاح", "m": "30"}])
ck("5e the second-half caption = liveposts.js's shMessage (score, scorer, live link)",
   _shc.startswith("▶️ انطلق الشوط الثاني: ليفربول 1 - 0 برينتفورد") and "ليفربول: صلاح 30'" in _shc
   and "المباراة لحظة بلحظة: https://elgoon.com/m/5" in _shc, _shc)
_wjs = open("liveposts.js", encoding="utf-8").read()
ck("5f the Worker posts it as kind 'sh' and resends the text if the card never comes",
   '["sh", shs, shMessage]' in _wjs and '"ko", "sh"]' in _wjs)

# 2026-10-24: Pyramids 3-0 El Merrikh Bentiu - a score-only goal first seen
# during the break carried the Worker's break label as its minute. The post
# read «الدقيقة استراحة» and the chip drew the word unshaped («ةحارتسا»).
ck("6a a minute is digits, or digits+digits", GC.minute_text("66") == "66" and GC.minute_text("45+2'") == "45+2")
ck("6b the break label is NOT a minute", GC.minute_text("استراحة") == "" and GC.minute_text("") == "" and GC.minute_text(None) == "")
_ht = dict(ev, player="", minute="استراحة")
_tmp2 = os.path.join(tempfile.mkdtemp(), "ht.jpg")
_im2 = GC.render(_ht, _tmp2)
# the chip is ORANGE; with no minute nothing orange is drawn on the scorer line
_orange = sum(1 for x in range(0, GC.W, 4) for y in range(718, 790, 4)
              if (lambda p: p[0] > 200 and 90 < p[1] < 170 and p[2] < 90)(_im2.getpixel((x, y))))
ck("6c no chip is drawn for a goal whose minute is the break label", _orange == 0, _orange)
import fb_post as FP
_cap = FP.goal_caption({"id": 1, "c": 624, "h": "بيراميدز", "a": "المريخ بنتو", "hs": 3, "as": 0},
                       {"s": "h", "m": "استراحة"})
ck("6d and the caption carries no «الدقيقة» line", "الدقيقة" not in _cap and "استراحة" not in _cap, _cap)
ck("6e a real minute still prints", "الدقيقة 63" in FP.goal_caption(
    {"id": 1, "c": 624, "h": "x", "a": "y", "hs": 1, "as": 0}, {"s": "h", "p": "زيزو", "m": "63"}))
_wl = GC.render_whistle({"kind": "ht", "home": "x", "away": "y", "hs": 1, "as": 0, "comp": 624,
                         "goals": [{"s": "h", "p": "زيزو", "m": "استراحة"}]}, os.path.join(tempfile.mkdtemp(), "w.jpg"))
ck("6f the whistle card renders a break-label goal (name only, no «استراحة'»)", _wl.size == (GC.WW, GC.WH))

# 2026-10-24 (same match): the list showed Pyramids 2-1 for ONE refresh, the
# Worker dispatched the phantom away goal, the match ended 4-0. The runner
# fetches the live detail for the crests anyway - it is also the check that
# the goal still stands.
_g21 = {"id": 4855321, "c": 624, "h": "بيراميدز", "a": "المريخ بنتو", "hs": 2, "as": 1}
ck("7a a side whose live score is below the claimed one has not scored it",
   FP.goal_stands({"awayCompetitor": {"score": 0}}, _g21, {"s": "a"}) is False)
ck("7b the same or a higher score means the goal stands",
   FP.goal_stands({"awayCompetitor": {"score": 1}}, _g21, {"s": "a"}) is True
   and FP.goal_stands({"homeCompetitor": {"score": 3}}, _g21, {"s": "h"}) is True)
ck("7c no usable detail (empty, or -1 before kick-off) decides nothing - the payload is trusted",
   FP.goal_stands({}, _g21, {"s": "a"}) is None and FP.goal_stands({"awayCompetitor": {"score": -1}}, _g21, {"s": "a"}) is None)
import store as _ST
_calls = []
_saved = (GC._s365_game, _ST.get_post, _ST.claim, _ST.release, _ST.record_post, FP.post_photo, FP.post_text)
GC._s365_game = lambda gid: {"homeCompetitor": {"score": 2}, "awayCompetitor": {"score": 0}}
_ST.get_post = lambda kind, ref: None
_ST.claim = lambda kind, ref, title=None, score=None: True
_ST.release = lambda kind, ref: _calls.append(("release", ref))
_ST.record_post = lambda kind, ref, pid, title=None, score=None, og_ok=False: _calls.append(("record", ref))
FP.post_photo = lambda tok, img, cap: _calls.append(("photo", cap)) or "P1"
FP.post_text = lambda tok, cap: _calls.append(("text", cap)) or "P2"
_rc = FP.goal_post("tok", json.dumps({"g": _g21, "seq": 3, "ev": {"s": "a", "p": "لاعب المريخ", "m": "31'"}}))
ck("7d --goal refuses a goal the live score no longer carries: nothing posted, the claim released",
   _rc == 0 and _calls == [("release", "4855321:3")], str(_calls))
_calls.clear()
GC._s365_game = lambda gid: {"homeCompetitor": {"score": 3}, "awayCompetitor": {"score": 0}}
_rc = FP.goal_post("tok", json.dumps({"g": {**_g21, "hs": 3, "as": 0}, "seq": 4, "ev": {"s": "h", "p": "مصطفى فتحي", "m": "45+3'"}}))
ck("7e and posts a goal that stands", _rc == 0 and _calls and _calls[0][0] == "photo", str(_calls))
_calls.clear()
_rc = FP.goal_post("tok", json.dumps({"g": {**_g21, "hs": 3, "as": 0}, "seq": 5, "ev": {"s": "h", "m": "71'"}}))
ck("7f --goal refuses a goal with no scorer named (user, 2026-10-24): nothing posted",
   _rc == 0 and _calls == [], str(_calls))
GC._s365_game, _ST.get_post, _ST.claim, _ST.release, _ST.record_post, FP.post_photo, FP.post_text = _saved

# a tie settled on penalties says who won (design review 2026-11-26)
_cup = {"kind": "ft", "home": "الزمالك", "away": "سيراميكا كليوباترا", "hs": 1, "as": 1, "comp": 552, "date": "2026-11-27",
        "goals": [{"s": "h", "p": "زيزو", "m": "12"}, {"s": "a", "p": "أكرم", "m": "40"}]}
_plain = GC.render_whistle(_cup)
_pen = GC.render_whistle({**_cup, "hp": 4, "ap": 3})
_white = lambda im: sum(1 for px in im.crop((300, 946, 780, 1006)).getdata() if min(px) > 235)     # noqa: E731
ck("5a a shoot-out draws its white pill on the seam, under the score", _white(_pen) > _white(_plain) + 8000,
   f"{_white(_plain)} -> {_white(_pen)}")
ck("5b no shoot-out score, or only one side of it: the card is the same as before",
   GC.render_whistle({**_cup, "hp": None, "ap": None}).tobytes() == _plain.tobytes()
   and GC.render_whistle({**_cup, "hp": 4}).tobytes() == _plain.tobytes())
ck("5c a half-time or kick-off card never carries it",
   GC.render_whistle({**_cup, "kind": "ht", "hp": 4, "ap": 3}).tobytes() == GC.render_whistle({**_cup, "kind": "ht"}).tobytes())
_many = [{"s": "h", "p": f"لاعب {i}", "m": str(10 + i)} for i in range(6)]
ck("5d with the pill the scorers still end above the foot band (three rows, the rest counted)",
   max(GC.render_whistle({**_cup, "hs": 6, "goals": _many, "hp": 2, "ap": 4}).getpixel((540, 1340))) < 70)
_fc = open("fb_cards.py", encoding="utf-8").read()
ck("5e the publish path hands the shoot-out's score from the match row",
   '"hp": m.get("home_pens"), "ap": m.get("away_pens")' in _fc)

print()
print("ALL OK" if not fails else f"{len(fails)} FAILED: " + ", ".join(fails))
sys.exit(1 if fails else 0)
