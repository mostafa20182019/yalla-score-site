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
# the orange minute chip exists to the right of centre at the scorer row
chip = im.crop((540, 724, 760, 784)); orange = sum(1 for p in chip.getdata() if p[0] > 200 and p[1] < 140 and p[2] < 60)
ck("2d the minute chip is orange", orange > 1500, str(orange))
# the score strip's two white discs
for x in (172, 908):
    px = im.getpixel((x, 968 - 56))                   # inside the white disc, above the crest
    ck(f"2e a white crest disc at x={x}", min(px) > 200, str(px))
rule = im.crop((100, 824, 480, 829)); rw = sum(1 for p in rule.getdata() if min(p) > 200)
ck("2g the rule runs across the card with the ball in its middle", rw > 600 and min(im.getpixel((540, 826))) < 120, str(rw))   # a 2 px line over 380 px
b = GC.render_bytes(ev)
ck("2f render_bytes gives a JPEG", b[:3] == b"\xff\xd8\xff" and len(b) > 40_000, str(len(b)))
im2 = GC.render({**ev, "minute": "", "tag": "", "player": "هدف عكسي؟"})
ck("3 no minute -> no chip, still renders", im2.size == (1080, 1080))

# the half-time / full-time card (same style)
wev = {"kind": "ft", "home": "مانشستر سيتي", "away": "إبسويتش تاون", "hs": 3, "as": 2, "comp": 7, "home_badge": hb, "away_badge": ab,
       "goals": [{"s": "h", "p": "هالاند", "m": "12"}, {"s": "a", "p": "ديلاب", "m": "40", "t": "ج"}, {"s": "h", "p": "فودين", "m": "77"}, {"s": "h", "p": "هالاند", "m": "90+2"}, {"s": "a", "p": "هيرست", "m": "88"}]}
wim = GC.render_whistle(wev)
ck("4a the whistle card is square too", wim.size == (1080, 1080))
band2 = wim.crop((100, 140, 980, 280)); white2 = sum(1 for p in band2.getdata() if min(p) > 230)
ck("4b the headline «انتهت المباراة» is drawn large", white2 > 6000, str(white2))
ck("4c the rule sits under the crests with the ball in its middle", min(wim.getpixel((540, 712))) < 120 and min(wim.getpixel((200, 712))) > 200)
wb = GC.render_whistle_bytes({**wev, "kind": "ht", "goals": []})
ck("4d render_whistle_bytes gives a JPEG for a goalless half", wb[:3] == b"\xff\xd8\xff")
# 5 the kick-off card (2026-10-18): the whistle layout with «انطلقت المباراة», a «×» instead of a score
kim = GC.render_whistle({**wev, "kind": "ko", "hs": 0, "as": 0, "goals": []})
ck("5a the kick-off card renders at the whistle card's size", kim.size == (GC.W, GC.H))
ck("5b WHISTLE_TITLE knows the kick-off", GC.WHISTLE_TITLE.get("ko") == "انطلقت المباراة")
kb = GC.render_whistle_bytes({**wev, "kind": "ko", "hs": 0, "as": 0, "goals": []})
ck("5c render_whistle_bytes gives a JPEG for the kick-off", kb[:3] == b"\xff\xd8\xff")

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
ck("6f the whistle card renders a break-label goal (name only, no «استراحة'»)", _wl.size == (GC.W, GC.H))

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
_rc = FP.goal_post("tok", json.dumps({"g": _g21, "seq": 3, "ev": {"s": "a", "m": "31'"}}))
ck("7d --goal refuses a goal the live score no longer carries: nothing posted, the claim released",
   _rc == 0 and _calls == [("release", "4855321:3")], str(_calls))
_calls.clear()
GC._s365_game = lambda gid: {"homeCompetitor": {"score": 3}, "awayCompetitor": {"score": 0}}
_rc = FP.goal_post("tok", json.dumps({"g": {**_g21, "hs": 3, "as": 0}, "seq": 4, "ev": {"s": "h", "p": "مصطفى فتحي", "m": "45+3'"}}))
ck("7e and posts a goal that stands", _rc == 0 and _calls and _calls[0][0] == "photo", str(_calls))
GC._s365_game, _ST.get_post, _ST.claim, _ST.release, _ST.record_post, FP.post_photo, FP.post_text = _saved

print()
print("ALL OK" if not fails else f"{len(fails)} FAILED: " + ", ".join(fails))
sys.exit(1 if fails else 0)
