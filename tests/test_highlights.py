# -*- coding: utf-8 -*-
"""/goals - «أهداف المباريات» (2026-11-02): beIN SPORTS / ON Sport highlight
links tied to our finished matches.

Run from the site root:  python tests/test_highlights.py

Network-free. The matching rules are the lessons of the first real run, when
a loose rule tied three different Turkish highlights to one match through
«سبور», and old ON Sport uploads to the wrong «الأهلي».
"""
import os, re, sys
from datetime import datetime, timezone
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import highlights as H

fails = []
def ok(n, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + n + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(n)


def m(mid, home, away, hs, as_, day, comp):
    return {"match_id": mid, "ar_home": home, "ar_away": away, "home_score": hs,
            "away_score": as_, "kickoff": day, "competition": comp, "status": "FINISHED"}


TR, EPL, EGY, ES = "Turkish Super Lig", "Premier League", "Egyptian Premier League", "Primera Division"
pool = [
    m(1, "آمد سبور", "أيوب سبور", 5, 1, "2026-11-01", TR),
    m(2, "طرابزون سبور", "غازي عنتاب", 2, 0, "2026-11-01", TR),
    m(3, "تشيلسي", "مانشستر يونايتد", 2, 0, "2026-10-31", EPL),
    m(4, "مانشستر سيتي", "برايتون", 0, 1, "2026-10-31", EPL),
    m(5, "البنك الاهلي", "المصري", 1, 1, "2026-10-28", EGY),
    m(6, "الأهلي", "المصري", 2, 0, "2026-10-27", EGY),
    m(7, "راسينج سانتاندير", "ريال مدريد", 0, 3, "2026-11-01", ES),
    m(8, "توتنهام هوتسبر", "كريستال بالاس", 2, 0, "2026-10-31", EPL),
    m(9, "سيراميكا كليوباترا", "زد", 2, 1, "2026-10-31", EGY),
]
NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
EU, EG = H.EUROPE, H.EGYPT


def mf(title, scope=EU, pub="2026-11-01T20:00:00+00:00"):
    r = H.match_for(title, pub, scope, pool, NOW)
    return r and r["match_id"]


ok("1 «سبور» names no club: a Trabzon highlight is NOT Amed-Eyup",
   mf("ملخص مباراة طرابزون سبور وغازي عنتاب | الدوري التركي") == 2)
ok("2 and a Turkish highlight of a match we do not hold matches nothing",
   mf("ملخص مباراة ريزة سبور وقونيا سبور | الدوري التركي") is None)
ok("3 the conjunction glued to the second club is read («ومانشستر يونايتد»)",
   mf("ملخص مباراة تشيلسي ومانشستر يونايتد | الدوري الإنجليزي") == 3)
ok("4 غ and ج are one letter («راسينغ» on beIN, «راسينج» ours)",
   mf("ملخص مباراة  راسينغ سانتاندير وريال مدريد | الدوري الإسباني") == 7)
ok("5 a short name works through the club's LONGEST word («توتنهام»)",
   mf("ملخص مباراة توتنهام وكريستال بالاس | الدوري الإنجليزي الممتاز") == 8)
ok("6 «البنك الأهلي - المصري» is that match, not الأهلي - المصري",
   mf("أهداف مباراة | البنك الأهلي - المصري | 1/1 | الجولة 8", EG, "2026-10-28T22:00:00+00:00") == 5)
ok("7 a title that says only «الأهلي» never names «البنك الأهلي»",
   H.team_hits("البنك الاهلي", set(H.tokens("الأهلي - المصري")),
               {H.club_key(n) for x in pool for n in (x["ar_home"], x["ar_away"])}) == 0)
ok("8 the score a title states must be ours (an old «2/0» upload is not a 1-1)",
   mf("أهداف مباراة | البنك الأهلي - المصري | 2/0 | الجولة 7", EG, "2026-10-28T22:00:00+00:00") is None)
ok("9 swapped letters in a long name («كيلوباترا») still name the club",
   mf("أهداف مباراة | سيراميكا كيلوباترا - زد اف سي | 2-1 |", EG, "2026-10-31T22:00:00+00:00") == 9)
ok("10 the channel's scope: beIN never gets an Egyptian match, ON Sport never a European one",
   mf("ملخص مباراة البنك الأهلي والمصري", EU, "2026-10-28T22:00:00+00:00") is None
   and mf("ملخص مباراة تشيلسي ومانشستر يونايتد", EG) is None)
ok("11 a match played after the upload, or long before it, is not the one",
   mf("ملخص مباراة تشيلسي ومانشستر يونايتد", EU, "2026-10-30T20:00:00+00:00") is None
   and mf("ملخص مباراة تشيلسي ومانشستر يونايتد", EU, "2026-11-20T20:00:00+00:00") is None)
ok("12 only highlights: talk shows and other sports never match",
   H.is_highlight("ملخص مباراة ليفربول وآرسنال") and H.is_highlight("استمتع بـ أهداف مباراة | الأهلي")
   and not H.is_highlight("ON TARGET - كواليس استبعاد إمام عاشور")
   and not H.is_highlight("مباراة | ريال مدريد - سان بابلو بورجوس | الدوري الإسباني لكرة السلة"))
ok("13 a stated score reads «2/1», «1 - 2» and «3-3», as a sorted pair",
   H.title_score("| 2/1 |") == (1, 2) and H.title_score("| 1 - 2 |") == (1, 2)
   and H.title_score("| 3-3 |") == (3, 3) and H.title_score("الجولة 9") is None)

# the page
html = open("dist/goals.html", encoding="utf-8").read() if os.path.exists("dist/goals.html") else ""
if html:
    yt = re.findall(r'href="(https://www\.youtube\.com/watch\?v=[\w-]{11})" target="_blank" rel="noopener"', html)
    ok("14 every card opens the video on YouTube in a new tab (links, nothing embedded)",
       yt and "<iframe" not in html, len(yt))
    ok("15 the score is the RTL pill (home number on the home side)",
       'class="gl-sc sc-in"' in html)
    ids = re.findall(r'data-ch="(on|bein)"', html)
    ok("16 both channels are tagged for the الكل · مصر · أوروبا chips",
       set(ids) <= {"on", "bein"} and 'data-f="on"' in html and 'data-f="bein"' in html)
    lines = re.findall(r'<article class="gl-card"[^>]*>.*?</article>', html, re.S)
    mps = [re.search(r'href="(/m/\d+)', c) for c in lines]
    ok("17 no match appears twice for one channel (ON Sport's أهداف + ملخص of one game)",
       len({(re.search(r'data-ch="(\w+)"', c).group(1), x.group(1)) for c, x in zip(lines, mps) if x})
       == len([x for x in mps if x]))
    nav = open("dist/index.html", encoding="utf-8").read()
    ok("18 no header tab (user, same day: «نستغنى عن التاب»), the page stays in the footer",
       "nt-goals" not in nav and "أهداف المباريات" in nav)
    mx = open("dist/matches.html", encoding="utf-8").read()
    btns = re.findall(r'<a class="mhl" href="(https://www\.youtube\.com/watch\?v=[\w-]{11})" target="_blank" rel="noopener"', mx)
    ok("18b the day list carries a «الأهداف» button on matches that have a video, opening YouTube",
       btns and mx.count('class="mhl"') == len(btns), len(btns))
    import glob as _g
    ok("18c the match page's own row carries it too",
       any('class="mhl"' in open(f, encoding="utf-8").read() for f in _g.glob("dist/m/*.html")[:400]))

from site_lib.tables import match_row
_fin = {"status": "FINISHED", "home": "A", "away": "B", "home_score": 1, "away_score": 0, "match_id": 1}
ok("18d only a FINISHED row gets the button (never a live or upcoming one)",
   'class="mhl"' in match_row(_fin, highlight=("https://www.youtube.com/watch?v=x", "ON Sport"))
   and 'class="mhl"' not in match_row(dict(_fin, status="LIVE"), highlight=("u", "c"))
   and 'class="mhl"' not in match_row(_fin))
css = open("site_src/style.css", encoding="utf-8").read()
ok("18e the button sits above the row's stretched link (z-index 2 > .mstretch 1)",
   ".mlist>.mrow .mhl{grid-area:hl" in css and "z-index:2" in css[css.index(".mlist>.mrow .mhl{"):][:200])

src = open("fetch_data.py", encoding="utf-8").read()
ok("19 a failing highlights fetch never fails the data fetch", "highlights failed" in src)
ds = open("data_store.py", encoding="utf-8").read()
ok("20 the store carries the file and merges it by video id", '"highlights.json"' in ds
   and '"highlights.json": lambda e: str(e.get("vid"))' in ds)

print("\nALL HIGHLIGHTS TESTS PASSED" if not fails else f"\n{len(fails)} FAILED")
sys.exit(1 if fails else 0)
