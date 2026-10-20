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
import io, json, os, sys, tempfile
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
from PIL import Image
import lineup_card as LC

# offline photos (2026-10-20): the feed's default silhouette for everyone
# except Donnarumma (14478), who gets a solid magenta square
def _png(colour):
    b = io.BytesIO(); Image.new("RGB", (120, 120), colour).save(b, "PNG"); return b.getvalue()
DEFAULT_PNG, DONNA_PNG = _png((90, 90, 90)), _png((255, 0, 255))
fetched = []
FAIL_IDS = set()                                        # athletes whose photo fetch blows up
def fake_fetch(url, timeout=10):
    fetched.append(url)
    if url.endswith("/Athletes/14478"):
        return DONNA_PNG
    if any(url.endswith(f"/Athletes/{a}") for a in FAIL_IDS):
        raise OSError("network down")
    return DEFAULT_PNG
LC.fetch_bytes = fake_fetch

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

# eleven on one side without positions (2026-10-20): the layout is derived
# from the announced formation, in the feed's order, and the side is flagged
nopos = json.loads(json.dumps(game))
nopos["awayCompetitor"]["lineups"]["hasFieldPositions"] = False
for m in nopos["awayCompetitor"]["lineups"]["members"]:
    m.pop("yardFormation", None)
dd = LC.parse(nopos)
ck("3a no field positions on one side -> derived from the formation, flagged", dd and dd["away"]["derived"] and not dd["home"]["derived"])
rows = {}
for p in dd["away"]["players"]:
    rows.setdefault(p["y"], []).append(p["x"])
ck("3a2 4-2-3-1 -> keeper + rows of 4, 2, 3, 1, evenly spread", sorted((y, len(xs)) for y, xs in rows.items()) == [(0.0, 1), (25.0, 4), (50.0, 2), (75.0, 3), (100.0, 1)]
   and sorted(rows[25.0]) == [12.5, 37.5, 62.5, 87.5], str(sorted(rows.items())))
ck("3a3 the feed's positions are untouched on the other side", dd["home"]["players"][1]["x"] == 0.0 and dd["home"]["players"][1]["y"] == 25.0)
nofor = json.loads(json.dumps(nopos))
nofor["awayCompetitor"]["lineups"]["formation"] = ""
dd2 = LC.parse(nofor)
grp = {}
for p in dd2["away"]["players"]:
    grp.setdefault(p["y"], set()).add(p["pos"])
ck("3a4 no formation either -> rows from the position groups (DF / MF / FW), one group per row",
   dd2 and all(len(v) == 1 for v in grp.values()) and len(grp) == 4, str(grp))
ck("3a5 a formation that does not add up to ten falls back to the groups", LC.formation_rows("4-3-3-1", 10) is None and LC.formation_rows("4-3-3", 10) == [4, 3, 3])
broken = json.loads(json.dumps(game))
broken["homeCompetitor"]["lineups"]["members"] = [m for m in broken["homeCompetitor"]["lineups"]["members"] if m.get("status") == 1][:-1]
ck("3b ten starters -> None", LC.parse(broken) is None)

# colours: our kit table first (City sky blue), the feed's for a club we lack
ck("4a Man City takes the kit table's sky blue", LC.kit_colour(data["home"]) == (108, 171, 221))
ck("4b Ipswich takes the feed's colour", LC.kit_colour(data["away"]) == (0, 85, 170))

# the render (the bottom keeper's photo fetch fails)
FAIL_IDS.add(bot[0][2]["athlete"])
tmp = os.path.join(tempfile.mkdtemp(), "xi.jpg")
LC.render(data, tmp)
with Image.open(tmp) as im:
    ck("5a the card is the Facebook portrait size", im.size == (1080, 1350), str(im.size))
    px = im.getpixel(((x0 + x1) // 2 + 160, int(my) + 14))     # just under the halfway line, off any disc
    ck("5b the pitch is green where no disc sits", px[1] > px[0] + 30 and px[1] > px[2] + 30, str(px))
b = LC.render_bytes(data)
ck("5c render_bytes gives a JPEG", b[:3] == b"\xff\xd8\xff" and len(b) > 50_000, str(len(b)))

# the photos (2026-10-20): the keeper's disc shows his photo, a player the feed
# has no photo of (the default silhouette) and a failed fetch keep the kit disc
with Image.open(tmp) as im:
    kx, ky, _ = top[0]
    ck("6a Donnarumma's disc is his photo", im.getpixel((int(kx), int(ky)))[0] > 200 and im.getpixel((int(kx), int(ky)))[1] < 60, str(im.getpixel((int(kx), int(ky)))))
    # sampled off-centre: the centre of a numbered disc is the number itself
    dx, dy, dp = top[1]
    px = im.getpixel((int(dx) + 20, int(dy) + 14))
    ck("6b a player on the default silhouette keeps the kit-coloured disc", px[2] > 180 and px[0] < 140, str(px) + " " + dp["name"])
    bx, by, bp = bot[0]
    px = im.getpixel((int(bx) + 20, int(by) + 14))
    ck("6c a failed photo fetch keeps the disc too (the bottom keeper)", bp["athlete"] in FAIL_IDS and px[2] > 120 and px[0] < 60, str(px))
ck("6d the default silhouette was fetched once, under athlete 0, and every starter once", sum(u.endswith("/Athletes/0") for u in fetched) == 1 and len(set(fetched)) == 23, str(len(set(fetched))))
ck("6e --no-photos / photos_on=False never fetches", (fetched.clear(), LC.render_bytes(data, photos_on=False), len(fetched))[2] == 0)
der = os.path.join(tempfile.mkdtemp(), "xi_derived.jpg")
LC.render(dd, der, photos_on=False)
ck("6f a derived card renders at the same size", Image.open(der).size == (1080, 1350))

# the two forwards never meet at halfway: the top side's name hangs towards
# the line, so its forward line stops short of the bottom side's
ty = max(y for _, y, _ in top); by_ = min(y for _, y, _ in bot)
ck("7 the halfway strip keeps the top forward's name clear of the bottom forward's disc", by_ - LC.R > ty + LC.R + 30, f"{ty} {by_}")

print()
print("ALL OK" if not fails else f"{len(fails)} FAILED: " + ", ".join(fails))
sys.exit(1 if fails else 0)
