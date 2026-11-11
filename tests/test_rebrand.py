# -*- coding: utf-8 -*-
"""The rebrand of 2026-11-04: «يلا سكور» / yallascore.site -> «الجون» / elgoon.com.

Run from the site root:  python tests/test_rebrand.py

What must hold: the site's own constants name the new site; the Worker's
canonical is the new host and the old one is still an allowed admin origin
(the admin pages keep working from either); links inside articles to the old
host still count as ours; the D1 task rewrites exactly the rendered fields,
leaves everything else alone and is idempotent; the old name survives as a
brand alias in the home schema (the Facebook page still says it).
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

fails = []


def ok(n, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + n + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(n)


from site_lib.config import SITE_BASE, SITE_NAME          # noqa: E402
import article_put as AP                                   # noqa: E402
import d1_admin as D                                       # noqa: E402
from site_pages.home import BRAND_ALIASES                  # noqa: E402

ok("1 the site is elgoon.com / «الجون»", SITE_BASE == "https://elgoon.com" and SITE_NAME == "الجون")
w = io.open("worker.js", encoding="utf-8").read()
ok("2a the Worker's canonical host is elgoon.com", 'const canonical = "elgoon.com";' in w)
ok("2b the old host is still an allowed admin origin (admin pages keep working during the move)",
   '"https://elgoon.com", "https://yallascore.site"' in w)
ok("2c no stray old-host cache key in the Worker", "https://yallascore.site/" not in w)
ok("3 links to the old host inside articles still count as ours",
   {"elgoon.com", "yallascore.site"} <= AP.OUR_HOSTS)
ok("4 the old name stays a brand alias in the home schema", "يلا سكور" in BRAND_ALIASES and "الجون" in BRAND_ALIASES)

rec = {"article_id": "1", "title": "توقع يلا سكور للقمة", "summary": "s",
       "body": '<p>اقرأ على <a href="https://yallascore.site/m/5">يلا سكور</a></p>',
       "fb_post": "التفاصيل: https://yallascore.site/a/1", "image_url": "https://yallascore.site/media/x.jpg",
       "image_credit": "الصورة: تصميم يلا سكور", "author": "يلا سكور", "sources": [{"name": "يلا سكور", "url": "https://yallascore.site/"}]}
upd = D.rebrand_fields(rec)
ok("5a the rendered fields are rewritten: title, body, fb_post, image_url, image_credit - and the sources",
   upd and set(upd) == {"title", "body", "fb_post", "image_url", "image_credit", "sources"})
ok("5b the domain and the name both change, links keep their paths",
   upd["body"] == '<p>اقرأ على <a href="https://elgoon.com/m/5">الجون</a></p>'
   and upd["image_url"] == "https://elgoon.com/media/x.jpg" and upd["title"] == "توقع الجون للقمة")
ok("5c author is not touched; a source named after us is renamed and its url moved, the whole list returned",
   "author" not in upd and upd["sources"] == [{"name": "الجون", "url": "https://elgoon.com/"}])
_f = D.rebrand_fields({"article_id": "3", "title": "x", "faq": [{"q": "ماذا توقع يلا سكور؟", "a": "رجّح نموذج يلا سكور الفوز"}, {"q": "كم انتهت؟", "a": "2-0"}]})
ok("5f FAQ questions and answers are rewritten too (69 articles said the old name there, 2026-11-05)",
   _f == {"faq": [{"q": "ماذا توقع الجون؟", "a": "رجّح نموذج الجون الفوز"}, {"q": "كم انتهت؟", "a": "2-0"}]}, _f)
ok("5d idempotent: an article already rebranded yields nothing", D.rebrand_fields({**rec, **upd}) is None)
ok("5e an article without the old strings yields nothing", D.rebrand_fields({"article_id": "2", "title": "خبر", "body": "<p>x</p>"}) is None)
wf = io.open(".github/workflows/d1-admin.yml", encoding="utf-8").read()
ok("6 the D1 Admin workflow offers the task and commits its export",
   '"rebrand"' in wf and "env.TASK == 'rebrand'" in wf and '"--rebrand"' in io.open("d1_admin.py", encoding="utf-8").read())
import site_lib.shell as SH                                # noqa: E402
_c = SH._clean_urls('<a href="https://yallascore.site/m/5.html">x</a> <img src="https://yallascore.site/media/a.jpg"> '
                    '<a href="https://old-credit-e926.mustafa-abdelsalam95.workers.dev/a/1.html">y</a> https://example.com/old.html')
ok("8 a page never emits a link into a former host: rewritten to the site, extensionless, externals untouched",
   _c == '<a href="https://elgoon.com/m/5">x</a> <img src="https://elgoon.com/media/a.jpg"> '
         '<a href="https://elgoon.com/a/1">y</a> https://example.com/old.html', _c)
man = io.open("root-extras/manifest.webmanifest", encoding="utf-8").read()
ok("7 the web manifest and the service worker name the new site",
   '"name": "الجون"' in man and "الجون" in io.open("root-extras/sw.js", encoding="utf-8").read())

# 2026-11-11: the Inzaghi story showed the OLD «يلا سكور» rocket badge - the
# two article placeholders had never been redrawn. They are the «الجون» cover
# now (tools/make_brand.py --ph), kept under the same names, on a short cache
for _ph in ("ph-pitch.svg", "ph-ball.svg"):
    _s = io.open(os.path.join("media", _ph), encoding="utf-8").read()
    ok(f"8 media/{_ph} is the «الجون» cover (an embedded picture), not the old rocket badge",
       "الجون" in _s and "data:image/png;base64," in _s and "Yalla" not in _s
       and "rocket" not in _s and len(_s) < 40_000, len(_s))
_hd = io.open("root-extras/_headers", encoding="utf-8").read().replace("\r\n", "\n")
_css = io.open("site_src/style.css", encoding="utf-8").read()
_rule = 'img[src*="/media/ph-"]{object-fit:contain;object-position:50% 50%;background:#1f94d3}'
ok("8b the placeholder is shown whole on its blue, by the LAST rule (a wide desktop hero sliced the logo)",
   _rule in _css and _css.rstrip().endswith(_rule))
ok("9 the placeholders are cached for an hour, so a redraw reaches returning readers",
   all(f"/media/{p}\n  ! Cache-Control\n  Cache-Control: public, max-age=3600" in _hd
       for p in ("ph-pitch.svg", "ph-ball.svg")))

print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL REBRAND TESTS PASSED")
sys.exit(1 if fails else 0)
