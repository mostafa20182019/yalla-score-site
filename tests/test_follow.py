# -*- coding: utf-8 -*-
r"""«تابع فريقك» (2026-11-19).

    python tests/test_follow.py      (from the repo root)

What it guards: the club page's button and the home page's picker and block
are [hidden] in the HTML (a crawler and a browser without storage see the
page as it was); the picker lists every club page; the block is built from
the club page's own rows and links its page; the fragment files are kept out
of the index; the script ships in app.js, keeps the choice in the browser and
hands its rows to the live layer.
"""
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

from site_lib import follow as F            # noqa: E402
from site_lib.clubs import TEAM_PAGES       # noqa: E402
import site_lib.shell as SH                 # noqa: E402

fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


pick = F.my_pick_html()
ck("1 the picker is hidden in the HTML and lists every club page once",
   'id="myPick"' in pick and " hidden>" in pick.split(">")[0] + ">"
   and all(pick.count(f'data-slug="{tp["slug"]}"') == 1 for tp in TEAM_PAGES), pick[:120])
ck("2 ...with a way to dismiss it", "data-my-no" in pick)

blk = F.my_block_html("الأهلي", "al-ahly", "/assets/crests/x.png", '<p class="club-pos">المركز 2</p>',
                      '<div class="mrow" data-lv>UP</div>', '<div class="mrow" data-lv>LAST</div>',
                      [{"href": "/a/1.html", "title": "خبر <أول>"}, {"href": "/a/2.html", "title": "ثان"},
                       {"href": "/a/3.html", "title": "ثالث"}])
ck("3 the block: the club's name, its page, the next match before the last result, two news rows",
   "فريقك: الأهلي" in blk and 'href="/team/al-ahly.html"' in blk and blk.index("UP") < blk.index("LAST")
   and blk.count('class="my-n"') == 2 and "ثالث" not in blk)
ck("4 a news title is escaped", "خبر &lt;أول&gt;" in blk and "<أول>" not in blk)
ck("5 the block carries the «تغيير الفريق» control", "data-my-x" in blk)
empty = F.my_block_html("مصر", "egypt", "", "", "", "", [])
ck("6 a club with no rows and no news still gives a valid block, with no empty list",
   "فريقك: مصر" in empty and 'class="mlist"' not in empty and 'class="my-news"' not in empty and "<img" not in empty)
ck("7 the fragment is JSON with one key", json.loads(F.my_json(blk)) == {"html": blk})

js = SH.FOLLOW_JS
ck("8 the script ships in app.js", "elgoonTeam" in SH.app_js())
ck("9 the choice stays in the browser: localStorage only, no request but the club's own fragment",
   "localStorage" in js and js.count("fetch(") == 1 and "fetch('/my/'+slug+'.json'" in js
   and "XMLHttpRequest" not in js and "sendBeacon" not in js and "cookie" not in js)
ck("10 a slug is checked before it is used in a URL", "/^[a-z0-9-]{2,40}$/" in js and "if(ok(cur)" in js and "if(ok(s))" in js)
ck("11 the block's rows join the live layer", "window.__lvAdd(box)" in js)
ck("12 a browser without storage shows nothing", js.index("catch(e){ return; }") < js.index("getElementById('followBtn')"))

club = io.open("site_src/templates/club.html", encoding="utf-8").read()
home = io.open("site_src/templates/home.html", encoding="utf-8").read()
ck("13 the club page's button and note are hidden in the HTML",
   'id="followBtn"' in club and 'data-slug="{{ slug }}"' in club
   and club.split('id="followBtn"')[1].split(">")[0].rstrip().endswith("hidden")
   and club.split('id="followNote"')[1].split(">")[0].rstrip().endswith("hidden"))
ck("14 the home block is hidden in the HTML and sits UNDER the ad strip (firm rule: the ad slot never moves)",
   '<div id="myTeam" class="my-team" hidden></div>' in home and home.index("home-topad") < home.index('id="myTeam"')
   < home.index("{{ match_centre }}"))
hd = io.open("root-extras/_headers", encoding="utf-8").read()
ck("15 the fragments are kept out of the index", "/my/*\n  X-Robots-Tag: noindex" in hd.replace("\r\n", "\n"))
css = io.open("site_src/style.css", encoding="utf-8").read()
ck("16 [hidden] wins over the picker's display:flex", ".my-pick[hidden],.my-team[hidden]{display:none}" in css)

# the built files, when a build is at hand
dist = os.path.join(os.getcwd(), "dist")
if os.path.exists(os.path.join(dist, "my")):
    miss = [tp["slug"] for tp in TEAM_PAGES if not os.path.exists(os.path.join(dist, "my", tp["slug"] + ".json"))]
    ck("17 every club page has its fragment", not miss, str(miss))
    d = json.load(io.open(os.path.join(dist, "my", TEAM_PAGES[0]["slug"] + ".json"), encoding="utf-8"))
    ck("18 ...with clean URLs (no .html) like every page", ".html" not in d["html"] and "فريقك:" in d["html"])
    sm = io.open(os.path.join(dist, "sitemap.xml"), encoding="utf-8").read()
    ck("19 no fragment in the sitemap", "/my/" not in sm)

print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
