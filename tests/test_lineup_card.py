# -*- coding: utf-8 -*-
r"""The line-up card (2026-10-17): the official XI drawn on a pitch.

    python tests/test_lineup_card.py     (from the repo root)

Offline: the fixture is the real game/ detail of Man City x Ipswich
(2026-10-17, 4742043) as 365scores served it. The rules under test: eleven
positioned starters per side or nothing, the keeper on his own goal line
and the striker nearest the halfway line, names from the members table with
the feed's stray tabs stripped, colours from our kit table first, and a
rendered card at the Facebook portrait size.
"""
import json, os, sys, tempfile
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
from PIL import Image
import lineup_card as LC

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

game = json.load(open("tests/fixtures/game_4742043_lineups.json", encoding="utf-8"))["game"]
data = LC.parse(game)
ck("1a both sides parse with eleven positioned starters", data and len(data["home"]["players"]) == 11 and len(data["away"]["players"]) == 11)
ck("1b names and formations come from the feed", data["home"]["name"] == "مانشستر سيتي" and data["home"]["formation"] == "4-2-3-1" and data["away"]["formation"] == "4-2-3-1")
gk = data["home"]["players"][0]
ck("1c the keeper is on his goal line, number 1, tab stripped", gk["y"] == 0 and gk["no"] == 1 and gk["name"] == "دوناروما", str(gk))
ck("1d the striker is the line nearest halfway", max(p["y"] for p in data["home"]["players"]) == 100)
ck("1e competition label and kick-off carried", data["comp"] == "الدوري الإنجليزي" and data["start"].startswith("2026-10-17"))

# geometry: home in the top half (keeper at the top), away in the bottom half
x0, y0, x1, y1 = LC.PITCH
my = (y0 + y1) / 2
top = LC._place(data["home"], True)
bot = LC._place(data["away"], False)
ck("2a every home disc sits in the top half, every away disc in the bottom half",
   all(y < my for _, y, _ in top) and all(y > my for _, y, _ in bot))
ck("2b the two keepers are the farthest from halfway", min(y for _, y, _ in top) == top[0][1] and max(y for _, y, _ in bot) == bot[0][1])
ck("2c discs stay inside the pitch", all(x0 < x < x1 and y0 < y < y1 for x, y, _ in top + bot))

# eleven on one side without positions = nothing (the caller falls back to text)
broken = json.loads(json.dumps(game))
broken["awayCompetitor"]["lineups"]["hasFieldPositions"] = False
ck("3a no field positions on one side -> None", LC.parse(broken) is None)
broken = json.loads(json.dumps(game))
broken["homeCompetitor"]["lineups"]["members"] = [m for m in broken["homeCompetitor"]["lineups"]["members"] if m.get("status") == 1][:-1]
ck("3b ten starters -> None", LC.parse(broken) is None)

# colours: our kit table first (City sky blue), the feed's for a club we lack
ck("4a Man City takes the kit table's sky blue", LC.kit_colour(data["home"]) == (108, 171, 221))
ck("4b Ipswich takes the feed's colour", LC.kit_colour(data["away"]) == (0, 85, 170))

# the render
tmp = os.path.join(tempfile.mkdtemp(), "xi.jpg")
LC.render(data, tmp)
with Image.open(tmp) as im:
    ck("5a the card is the Facebook portrait size", im.size == (1080, 1350), str(im.size))
    px = im.getpixel(((x0 + x1) // 2, int(my) + 40))
    ck("5b the pitch is green where no disc sits", px[1] > px[0] + 30 and px[1] > px[2] + 30, str(px))
b = LC.render_bytes(data)
ck("5c render_bytes gives a JPEG", b[:3] == b"\xff\xd8\xff" and len(b) > 50_000, str(len(b)))

print()
print("ALL OK" if not fails else f"{len(fails)} FAILED: " + ", ".join(fails))
sys.exit(1 if fails else 0)
