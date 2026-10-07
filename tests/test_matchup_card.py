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
ck("the card is 1600x680", Image.open(out).size == (1600, 680))
src = io.open("match_brief.py", encoding="utf-8").read()
ck("the brief draws a card only for an important match", "if featured_sides(m) == 2:" in src and '"credit": "الصورة: تصميم يلا سكور"' in src)
pr = io.open(".github/prompts/match-article.md", encoding="utf-8").read()
ck("the prompt makes the writer use brief.image and commit its file", "`brief.image` first" in pr and "git add` `image.file`" in pr)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
