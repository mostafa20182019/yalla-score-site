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
# the league pages (2026-11-20: every club of the Egyptian and Saudi leagues)
# have a page and a follow button on it, but are not in the picker - it
# would be fifty chips
ck("1 the picker is hidden in the HTML and lists every club page once - the league pages apart",
   'id="myPick"' in pick and " hidden>" in pick.split(">")[0] + ">"
   and all(pick.count(f'data-slug="{tp["slug"]}"') == (0 if tp.get("league_page") else 1) for tp in TEAM_PAGES)
   and pick.count("data-slug=") <= 20, pick[:120])
ck("2 ...with a way to dismiss it", "data-my-no" in pick)

blk = F.my_block_html("الأهلي", "al-ahly", "/assets/crests/x.png", "المركز 2 · 20 نقطة",
                      '<div class="mrow" data-lv>UP</div>',
                      [{"href": "/a/1.html", "title": "خبر <أول>"}, {"href": "/a/2.html", "title": "ثان"}])
# the block is SMALL (site review 2026-11-19: the first one was 433 px tall and
# pushed the day's matches off the first screen)
ck("3 the block: the club's name linked to its page, where it stands, ONE match row, ONE news line",
   'class="my-name" href="/team/al-ahly.html"' in blk and "<b>الأهلي</b>" in blk
   and '<span class="my-chip">المركز 2 · 20 نقطة</span>' in blk and blk.count('class="mrow"') == 1
   and blk.count('class="my-n"') == 1 and "ثان" not in blk)
ck("4 a news title is escaped", "خبر &lt;أول&gt;" in blk and "<أول>" not in blk)
ck("5 each block carries its own «إلغاء» control, named with its club for a screen reader",
   'data-my-x aria-label="إلغاء متابعة ' in blk and ">إلغاء</button>" in blk)
empty = F.my_block_html("مصر", "egypt", "", "", "", [])
ck("6 a club with no row, no chip and no news still gives a valid block, with nothing empty in it",
   "<b>مصر</b>" in empty and 'class="mlist"' not in empty and 'class="my-n"' not in empty
   and 'class="my-chip"' not in empty and "<img" not in empty)
ck("7 the fragment is JSON: the block, and when the club plays next", json.loads(F.my_json(blk)) == {"html": blk, "ko": ""})

js = SH.FOLLOW_JS
ck("8 the script ships in app.js", "elgoonTeam" in SH.app_js())
ck("9 the choice stays in the browser: localStorage only, no request but the club's own fragment",
   "localStorage" in js and js.count("fetch(") == 1 and "fetch('/my/'+slug+'.json'" in js
   and "XMLHttpRequest" not in js and "sendBeacon" not in js and "cookie" not in js)
ck("10 a slug is checked before it is used in a URL", "/^[a-z0-9-]{2,40}$/" in js and "if(ok(cur)" in js and "if(ok(s))" in js)
ck("11 the block's rows join the live layer", "window.__lvAdd(box)" in js)
ck("12 a browser without storage shows nothing - and loses the «فريقي» tab too (2026-11-20)",
   js.index("t0.hidden=true; return; }") < js.index("querySelectorAll('.follow-btn')"))

club = io.open("site_src/templates/club.html", encoding="utf-8").read()
home = io.open("site_src/templates/home.html", encoding="utf-8").read()
ck("13 the club page's button and note are hidden in the HTML",
   'id="followBtn"' in club and 'data-slug="{{ slug }}"' in club
   and club.split('id="followBtn"')[1].split(">")[0].rstrip().endswith("hidden")
   and club.split('id="followNote"')[1].split(">")[0].rstrip().endswith("hidden"))
# site review 2026-11-19
ck("13b the push button sits OUTSIDE the sentence (inline it cut the link beside it in two)",
   club.index('id="followNote"') < club.index("</p>", club.index('id="followNote"')) < club.index('class="push-btn follow-push"'))
ck("13c ONLY a 404 clears the reader's club; any other failed answer keeps it",
   "if(r.status===404) return 'gone';" in js and "rs.forEach(function(x){ if(x.d==='gone') drop(x.slug); });" in js
   and js.count("drop(") == 4)            # its definition, the follow button, the 404 branch, a block's own «إلغاء»
ck("13d the block's room is reserved before the first paint, and released when nothing is shown",
   "localStorage.getItem('elgoonTeam')" in F.MY_BOOT and "my-has" in F.MY_BOOT and "{{ my_boot }}" in home
   and home.index("{{ my_boot }}") < home.index('id="myTeam"') and "mode('')" in js)
ck("14 the home block is hidden in the HTML and sits UNDER the ad strip (firm rule: the ad slot never moves)",
   '<div id="myTeam" class="my-team" hidden></div>' in home and home.index("home-topad") < home.index('id="myTeam"')
   < home.index("{{ match_centre }}"))
hd = io.open("root-extras/_headers", encoding="utf-8").read()
ck("15 the fragments are kept out of the index", "/my/*\n  X-Robots-Tag: noindex" in hd.replace("\r\n", "\n"))
css = io.open("site_src/style.css", encoding="utf-8").read()
ck("16 [hidden] wins over the picker's display:flex", ".my-pick[hidden],.my-team[hidden]{display:none}" in css)
ck("16b finger-sized targets: the follow button, the club chips, the ×, «تغيير», the push button",
   all(x in css for x in (".follow-btn{", ".mp-c{", ".mp-x{", ".my-x{", ".follow-push{"))
   and all("min-height:44px" in css.split(sel, 1)[1].split("}", 1)[0]
           for sel in (".follow-btn{", ".mp-c{", ".mp-x{", ".my-x{", ".follow-push{")))
ck("16c the clubs get their own full line in the picker", ".mp-list{flex-basis:100%" in css and ".my-pick{display:flex;flex-wrap:wrap" in css)

# the built files, when a build is at hand
dist = os.path.join(os.getcwd(), "dist")
if os.path.exists(os.path.join(dist, "my")):
    miss = [tp["slug"] for tp in TEAM_PAGES if not os.path.exists(os.path.join(dist, "my", tp["slug"] + ".json"))]
    ck("17 every club page has its fragment", not miss, str(miss))
    d = json.load(io.open(os.path.join(dist, "my", TEAM_PAGES[0]["slug"] + ".json"), encoding="utf-8"))
    ck("18 ...with clean URLs (no .html) like every page", ".html" not in d["html"] and 'class="my-lbl">فريقك<' in d["html"])
    sm = io.open(os.path.join(dist, "sitemap.xml"), encoding="utf-8").read()
    ck("19 no fragment in the sitemap", "/my/" not in sm)

# user 2026-11-20: the picker's x hid it for ever («مش راضى يظهرلى تانى»)
import site_lib.follow as _F        # noqa: E402
ck("20 the picker's x is remembered for the VISIT (sessionStorage), never written into localStorage",
   "sessionStorage.setItem(OFF,'1')" in js and "set('none')" not in js and "hide(); mode('my-off');" in js)
ck("21 an old 'none' left by the first version is cleared on sight, and is no choice",
   "if(LS.getItem(KEY)==='none') LS.removeItem(KEY)" in js and "if(ok(cur)) load(); else showPick();" in js)
ck("22 the pre-paint class agrees: hidden only while this visit's flag is set",
   "sessionStorage.getItem('elgoonPickOff')==='1'" in _F.MY_BOOT and "t==='none'?'my-off'" not in _F.MY_BOOT)

# up to four clubs (user, 2026-11-26)
ck("23 the same key holds up to four slugs joined by commas: valid ones only, no club twice, a browser with one club unchanged",
   "var MAX=4;" in js and "if(ok(s)&&out.indexOf(s)<0&&out.length<MAX) out.push(s);" in js
   and "LS.setItem(KEY,a.join(','))" in js and "(,[a-z0-9-]{2,40}){0,3}$/" in _F.MY_BOOT)
ck("24 a fifth club is refused and said so; nothing he follows is dropped for it",
   "if(a.length>=MAX) return false;" in js and "else if(!add(slug)){" in js and "setTimeout(paint,3000)" in js)
ck("25 one block per club, the one that plays soonest first; only the first is whole; each has its own «إلغاء»",
   "String(x.d.ko||'9').localeCompare(String(y.d.ko||'9'))" in js and "if(i) sec.classList.add('my-min');" in js
   and "x.addEventListener('click',function(){ drop(slug); load(); });" in js
   and ".my-min .my-calc,.my-min .my-n{display:none}" in io.open("site_src/style.css", encoding="utf-8").read()
   and ".my-min .my-h>:not(.my-x){display:none}" in io.open("site_src/style.css", encoding="utf-8").read()
   and json.loads(_F.my_json("<p>", "2026-11-28 18:00")) == {"html": "<p>", "ko": "2026-11-28 18:00"})
ck("26 the picker never offers a club he follows, and «أضف فريقًا آخر» goes when he has four",
   "c.hidden=a.indexOf(c.getAttribute('data-slug'))>=0;" in js and "if(list().length<MAX&&pick){" in js)

print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
