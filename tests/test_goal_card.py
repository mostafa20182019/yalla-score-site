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
ck("2a the card is the Facebook portrait size", im.size == (1080, 1350))
ck("2b the file is a JPEG", open(tmp, "rb").read(3) == b"\xff\xd8\xff")
# the big word sits in the upper band: lots of white there, none mid-left
band = im.crop((200, 160, 880, 330)); white = sum(1 for p in band.getdata() if min(p) > 230)
ck("2c «جووووول» is drawn large in the upper band", white > 8000, str(white))
# the orange minute chip exists to the right of centre at the scorer row
chip = im.crop((540, 840, 760, 900)); orange = sum(1 for p in chip.getdata() if p[0] > 200 and p[1] < 140 and p[2] < 60)
ck("2d the minute chip is orange", orange > 1500, str(orange))
# the score strip's two white discs
for x in (150, 930):
    px = im.getpixel((x, 1040 - 63))                  # inside the white disc, above the crest
    ck(f"2e a white crest disc at x={x}", min(px) > 200, str(px))
b = GC.render_bytes(ev)
ck("2f render_bytes gives a JPEG", b[:3] == b"\xff\xd8\xff" and len(b) > 40_000, str(len(b)))
im2 = GC.render({**ev, "minute": "", "tag": "", "player": "هدف عكسي؟"})
ck("3 no minute -> no chip, still renders", im2.size == (1080, 1350))

print()
print("ALL OK" if not fails else f"{len(fails)} FAILED: " + ", ".join(fails))
sys.exit(1 if fails else 0)
