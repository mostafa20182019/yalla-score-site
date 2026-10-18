r"""A match piece never ships without a picture (2026-10-18).

    python tests/test_match_card_fallback.py   (from the repo root)

The Brentford x Liverpool report (article 840) went live with the ph-pitch.svg
placeholder, and the Facebook link preview of its match page showed the site
banner: /m/<id> put the 95px home crest in og:image, which the shell swaps for
the banner. Now the match page settles the piece's image first - its own
photo when it has one, else OUR matchup card, drawn at build time when the
writer's run did not commit it - and that image is the og:image too.
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


import site_lib.articles as A                            # noqa: E402
import matchup_card as MC                                # noqa: E402
from site_lib.config import SITE_BASE                    # noqa: E402

M = {"match_id": "T560611", "home": "Brentford FC", "away": "Liverpool FC", "competition": "Premier League",
     "kickoff": "2026-10-17", "koff_time": "17:00", "home_score": 1, "away_score": 2, "status": "FINISHED"}
tmp = tempfile.mkdtemp(prefix="mcf-")

# 1 a placeholder image -> the card is drawn and becomes the image
art = {"article_id": "840", "kind": "report", "match_id": "T560611", "image_url": "/media/ph-pitch.svg"}
url = A.ensure_match_image(M, art, "FINISHED", media_dir=tmp)
fname = MC.card_name(dict(M, status="FINISHED"))
ck("1 a placeholder gives way to the matchup card (result card for a finished match)",
   url == f"{SITE_BASE}/media/{fname}" and fname.endswith("-result.jpg"), str(url))
ck("2 the card file was drawn into media/", os.path.exists(os.path.join(tmp, fname)) and os.path.getsize(os.path.join(tmp, fname)) > 10000)
ck("3 the article dict now carries the card + our credit",
   art["image_url"] == url and art["image_credit"] == "الصورة: تصميم يلا سكور")

# 2 no image at all, upcoming match -> the preview card
art2 = {"article_id": "841", "kind": "preview", "match_id": "T560611"}
url2 = A.ensure_match_image(M, art2, "UPCOMING", media_dir=tmp)
ck("4 a piece with no image on an upcoming match gets the preview card", url2 and url2.endswith("-preview.jpg"), str(url2))

# 3 a real photo is left alone (and made absolute for og:image)
art3 = {"image_url": "/media/liverpool-anfield.jpg", "image_credit": "الصورة: x"}
url3 = A.ensure_match_image(M, art3, "FINISHED", media_dir=tmp)
ck("5 a real photo is kept, made absolute, credit untouched",
   url3 == SITE_BASE + "/media/liverpool-anfield.jpg" and art3["image_url"] == "/media/liverpool-anfield.jpg" and art3["image_credit"] == "الصورة: x")

# 4 an existing card is not redrawn
mt = os.path.getmtime(os.path.join(tmp, fname))
A.ensure_match_image(M, {"image_url": ""}, "FINISHED", media_dir=tmp)
ck("6 an existing card is reused, not redrawn", os.path.getmtime(os.path.join(tmp, fname)) == mt)

# 5 a draw that fails returns None and leaves the article as it was
_orig = MC.for_match
def _boom(*a, **k):
    raise RuntimeError("no crests")
MC.for_match = _boom
try:
    art5 = {"image_url": "/media/ph-ball.svg"}
    r5 = A.ensure_match_image(dict(M, match_id="T999"), art5, "FINISHED", media_dir=tmp)
    ck("7 a failed draw returns None and leaves the piece untouched (the crest path still follows)",
       r5 is None and art5["image_url"] == "/media/ph-ball.svg")
finally:
    MC.for_match = _orig

# 6 the match page wires it before the head (source check, the build's own style)
src = io.open("site_pages/matches.py", encoding="utf-8").read()
ck("8 match_pages settles the article image BEFORE head() and uses it as og:image",
   0 < src.find("_art = pick_match_article(") < src.find("img = ensure_match_image(m, _art, st)") < src.find("page_head = head(title, desc, SITE_BASE + murl, image=img"))

print("\n" + (f"{len(fails)} FAILED: " + "; ".join(fails) if fails else "ALL OK"))
sys.exit(1 if fails else 0)
