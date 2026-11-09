# -*- coding: utf-8 -*-
r"""The club FORM card and reel (form_card.py / form_reel.py, 2026-11-09).

    python tests/test_form_card.py      (from the repo root)

What it guards: the three marks (W / D / L) as drawn discs, the photo only
from team-photos/<slug>/ and never a person (else crest-only), the club's
own colour from the kit table, a 1080x1350 card with 8 and with 10 rows, the
club's goals drawn RIGHT of the dash, and the reel's frames (1080x1920, the
rows inside the Reels safe band, 12-16 s). No ffmpeg: frames only.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

import fb_reel as R           # noqa: E402
import form_card as FC        # noqa: E402
import form_reel as FR        # noqa: E402
import story_events as SE     # noqa: E402

fails = 0


def check(cond, msg):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails += 1


def row(i, gf, ga, home=True):
    return {"match_id": i, "date": f"2026-10-{i:02d}", "competition": "Primera Division", "comp_label": "الدوري الإسباني",
            "opponent": f"خصم {i}", "opponent_badge": None, "club_badge": None, "home": home, "gf": gf, "ga": ga,
            "mark": "W" if gf > ga else "D" if gf == ga else "L"}


def event(rows):
    s = SE.form_summary(rows)
    nxt = {"match_id": 564749, "home": "FC Barcelona", "away": "Villarreal CF", "home_badge": None, "away_badge": None,
           "kickoff": "2026-11-22", "koff_time": "15:00", "competition": "Primera Division", "club_home": True}
    return SE.event(SE.KIND_FORM, "form:barcelona:564749", "برشلونة يدخل مواجهة فياريال", ["x"], None, None, [],
                    club={"slug": "barcelona", "name": "برشلونة", "badge": None}, rows=rows,
                    record={k: v for k, v in s.items() if k != "run"}, run=list(s["run"]), next=nxt)


# 1) the marks: a draw is its own mark, and each disc is its own colour
rows = [row(1, 8, 1), row(2, 1, 1, False), row(3, 0, 1), row(4, 2, 0), row(5, 3, 3), row(6, 1, 0), row(7, 0, 4, False), row(8, 2, 1)]
check([r["mark"] for r in rows] == ["W", "D", "L", "W", "D", "W", "L", "W"], "W / D / L marks from the scores")
from PIL import Image
for mk, col in (("W", FC.GREEN), ("D", FC.GREY), ("L", FC.RED)):
    im = Image.new("RGB", (80, 80), (0, 0, 0))
    FC.draw_mark(im, 40, 40, 30, mk)
    on_glyph = (46, 40) if mk == "W" else (40, 40)            # the tick's long stroke passes right of the centre
    check(im.getpixel((40, 14)) == col and im.getpixel(on_glyph) == FC.WHITE, f"mark {mk}: disc {col}, white glyph")

# 2) the photo: only a non-person file in team-photos/<slug>/; a person, another folder or no record -> None (crest-only)
ph = FC.club_photo("barcelona")
check(ph is not None and ph["path"].replace("\\", "/").split("/team-photos/")[1].startswith("barcelona/") and os.path.exists(ph["path"]) and ph["credit"],
      f"barcelona: a credited photo from its own folder ({ph and ph['file']})")
fake = [{"slug": "barcelona", "is_person": True, "source": "team-photos/barcelona/raphinha-barcelona-2025.jpg", "file": "x.jpg", "credit": "c", "width": 1600},
        {"slug": "barcelona", "is_person": False, "source": "media/other.jpg", "file": "y.jpg", "credit": "c", "width": 1600}]
check(FC.club_photo("barcelona", fake) is None, "a player's photo or a file outside team-photos/<slug>/ is never used")
check(FC.club_photo("no-such-club") is None, "a club without a folder -> crest-only")
real = {"slug": "barcelona", "is_person": False, "source": "team-photos/barcelona/camp-nou-matchday.jpg", "file": "camp-nou-matchday.jpg", "credit": "صورة: جماهير — X", "width": 1280}
design = {"slug": "barcelona", "is_person": False, "source": "team-photos/barcelona/identity-card.jpg", "file": "identity-card.jpg", "credit": "الصورة: تصميم الجون", "width": 1600}
check(FC.club_photo("barcelona", [design, real])["file"] == "camp-nou-matchday.jpg", "a photograph beats one of our own designs")

# 3) the club's colour from the kit table: Barcelona blue, Zamalek red (its white is skipped), Real's gold accent, a club without a kit -> brand blue
check(FC.club_colour("برشلونة") == (0, 77, 152) and FC.club_colour("الزمالك") == (200, 16, 46), "kit colours, never white")
check(FC.club_colour("ريال مدريد") == (212, 175, 55) and FC.club_colour("نادي مجهول") == (31, 148, 211), "the accent for a white kit; brand blue without a kit")

# 4) the card: 1080x1350 with the photo and crest-only, 8 and 10 rows; the club's goals RIGHT of the dash
ev = event(rows)
im_photo = FC.render(ev, photo=ph)
im_plain = FC.render(ev, use_photo=False)
check(im_photo.size == (1080, 1350) and im_plain.size == (1080, 1350), "card 1080x1350 with and without a photo")
check(im_photo.getpixel((540, 120)) != im_plain.getpixel((540, 120)), "the photo strip changes the header, the crest-only card has none")
rows10 = rows + [row(9, 1, 2), row(10, 2, 2)]
check(FC.render(event(rows10), use_photo=False).size == (1080, 1350), "10 rows still fit the card")
# the first (newest) row is 8-1 for the club: more white ink right of the pill's centre than left
g = im_plain.convert("L")
# the first row is drawn newest first = rows[-1] = 2-1; make a card whose newest row is 8-1 instead
im81 = FC.render(event(rows[1:] + [row(9, 8, 1)]), use_photo=False).convert("L")
cy = 400 + FC.H and 400 + 46
px = FC.W // 2 - 40
def ink(im, x0, x1):
    return sum(1 for x in range(int(x0), int(x1)) for y in range(cy - 16, cy + 16) if im.getpixel((x, y)) < 120)
check(ink(im81, px + 8, px + 50) > ink(im81, px - 50, px - 8), "the club's 8 sits right of the dash, the opponent's 1 left")
out = os.path.join(os.getcwd(), "media", "form", "test-form.png")
os.makedirs(os.path.dirname(out), exist_ok=True)
FC.render(ev, out, use_photo=False)
check(os.path.exists(out) and len(FC.render_bytes(ev, use_photo=False)) > 20000, "render() writes the file, render_bytes() a JPEG for the post")
os.remove(out)

# 5) the reel: intro + rows + fixture + outro, 12-16 s, every frame 1080x1920, the rows inside the safe band and clear of the button column
scenes = FR.build(ev)
secs = sum(s[1] for s in scenes)
check(len(scenes) == 4 and 12 <= secs <= 16, f"4 scenes, {secs:.1f} s")
for draw, dur, _ in scenes:
    fr = draw(dur - 0.05)
    check(fr.size == (R.W, R.H), f"frame {fr.size}")
rh = FR.row_h(len(rows))
check(FR.ROW_TOP + (len(rows) - 1) * rh + rh // 2 <= R.SAFE_BOTTOM, "8 rows end inside the Reels safe band")
check(FR.MARK_X + 26 <= R.W * 0.91, "the mark discs stay left of the like/comment column")
rh10 = FR.row_h(10)
check(FR.ROW_TOP + 9 * rh10 + rh10 // 2 <= R.SAFE_BOTTOM, "10 rows end inside the safe band too")
streak = dict(ev, kind=SE.KIND_STREAK, next=None)
check(len(FR.build(streak)) == 3, "a streak event (no fixture) has no fixture scene")
check(FR.caption(ev).rstrip("\n") == ev["text"], "the reel's caption is the event text")

print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
