r"""Matchup cards (matchup_card.py, 2026-10-08) - the image for important matches.

    python tests/test_matchup_card.py   (from the repo root)

Pins: every featured club has a kit (colours, never a crest); Saudi «الأهلي» is
Al-Ahli Jeddah's green, the Egyptian one red; a colour clash puts the away side
in its alternate kit; the card is 1600x680; the brief attaches a card only to
an important match (both clubs featured) and the prompt makes the writer use it.
"""
import io
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


import matchup_card as MC                                  # noqa: E402
from site_pages.predictions import HUB_FOCUS               # noqa: E402
from PIL import Image                                      # noqa: E402

missing = sorted({n for c, v in HUB_FOCUS.items() for n in v
                  if MC.kit_for(n, c) is MC.NEUTRAL})
ck("every featured club has a kit", not missing, missing)
ck("Saudi «الأهلي» is green (Al-Ahli Jeddah), the Egyptian one red",
   MC.kit_for("الأهلي", "Saudi Pro League")[1][0] == (11, 138, 62)
   and MC.kit_for("الأهلي", "Egyptian Premier League")[1][0] == (192, 12, 36))
hk, ak = MC.kits("ليفربول", "مانشستر يونايتد", "Premier League")
ck("red v red: the away side wears its alternate (white, trimmed red)",
   ak[1][0] == (255, 255, 255) and ak[3] == (218, 41, 28), ak)
hk, ak = MC.kits("الزمالك", "الأهلي", "Egyptian Premier League")
ck("no clash: both keep their first kit", ak[1][0] == (192, 12, 36))
ck("an unknown club gets the neutral disc, never an invented colour", MC.kit_for("نادٍ مجهول") is MC.NEUTRAL)
ck("Arabic date + 12-hour time", MC.when_ar("2026-10-11", "20:00") == "الأحد 11 أكتوبر · 8 مساءً"
   and MC.when_ar("2026-10-18", "18:30") == "الأحد 18 أكتوبر · 6:30 مساءً", MC.when_ar("2026-10-18", "18:30"))
ck("one file per match and kind", MC.card_name({"match_id": 9, "status": "FINISHED"}) == "matchup-9-result.jpg"
   and MC.card_name({"match_id": 9, "status": "UPCOMING"}) == "matchup-9-preview.jpg")
out = os.path.join(tempfile.mkdtemp(), "c.jpg")
MC.render("بوروسيا مونشنجلادباخ", "برشلونة", out, comp_label="دوري أبطال أوروبا", round_label="الجولة 2",
          when="الأربعاء 21 أكتوبر · 10 مساءً", score=(2, 1))
im = Image.open(out).convert("RGB")
ck("the card is 1600x680", im.size == (1600, 680))
# nothing white outside SAFE (the home 16:9 crop and the hero band cut there):
# only the gradient and the faint pitch lines may live in the margins
x0, y0, x1, y1 = MC.SAFE
px = im.load()
spill = [(x, y) for y in range(0, 680, 2) for x in range(0, 1600, 2)
         if not (x0 <= x <= x1 and y0 <= y <= y1) and min(px[x, y]) > 200]
ck("nothing drawn outside the safe band (the site crops there)", not spill, spill[:3])
css = io.open("site_src/style.css", encoding="utf-8").read()
ck("the article hero centres a matchup card", '.a-img[src*="/matchup-"]{object-position:50% 50%}' in css)
src = io.open("match_brief.py", encoding="utf-8").read()
ck("the brief draws a card for EVERY match piece, in the feed's colours",
   "if featured_sides(m) == 2:" not in src and '"credit": "الصورة: تصميم يلا سكور"' in src
   and 'feed=(brief.get("s365") or {}).get("colors")' in src and '"colors": {side:' in src)
# the feed's colours fill the gap the KITS table leaves - never an invented one
ck("a club missing from KITS wears the feed's colours",
   MC.kit_for("برينتفورد", "Premier League", ("#E30613", "#FFFFFF"))[1][0] == (227, 6, 19))
ck("KITS still wins over the feed", MC.kit_for("الأهلي", "Egyptian Premier League", ("#000000", "#FFFFFF"))[1][0] == (192, 12, 36))
ck("a light feed colour gets the second colour as its trim",
   MC.kit_for("س", None, ("#FFFFFF", "#000099"))[3] == (0, 0, 153))
ck("bad / missing feed colours -> the neutral disc", MC.kit_for("س", None, ("blue", None)) is MC.NEUTRAL
   and MC.kit_for("س", None, None) is MC.NEUTRAL)
rows = [{"home": "الأهلي", "away": "الزمالك", "kickoff": "2026-05-01", "status": "FINISHED"},
        {"home": "الزمالك", "away": "الأهلي", "kickoff": "2026-10-11", "status": "SCHEDULED"},
        {"home": "الأهلي", "away": "سموحة", "kickoff": "2026-10-20", "status": "SCHEDULED"}]
ck("--teams finds the NEXT meeting, in either order",
   MC.find_fixture("الأهلي", "الزمالك", rows, "2026-10-08")["kickoff"] == "2026-10-11")
ck("--teams falls back to the latest played meeting",
   MC.find_fixture("الأهلي", "الزمالك", rows, "2026-10-12")["kickoff"] == "2026-05-01")
ck("--teams: no fixture -> None (the card draws the names only)", MC.find_fixture("الأهلي", "بيراميدز", rows) is None)
dp = io.open(".github/prompts/daily-article.md", encoding="utf-8").read()
ck("the daily prompt sends matchup stories to the card", "MATCHUP STORIES USE OUR CARD" in dp
   and "matchup_card.py --teams" in dp)
pr = io.open(".github/prompts/match-article.md", encoding="utf-8").read()
ck("the prompt makes the writer use brief.image and commit its file", "`brief.image` first" in pr and "git add` `image.file`" in pr)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
