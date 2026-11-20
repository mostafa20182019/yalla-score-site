# -*- coding: utf-8 -*-
r"""A page for every club of the Egyptian and the Saudi league (2026-11-20).

    python tests/test_league_pages.py      (from the repo root, after a build)

clubs.LEAGUE_PAGES adds thirty-five page-only entries. The danger is names:
«الأهلي», «الهلال», «الاتحاد» and «المصري» each mean something else on this
site. So: every entry is matched by the feed's exact name inside its own
league's competitions, a Saudi namesake's page says «السعودي», no bare news
token can catch another club's story, and slugs are unique and never those
of an existing page.
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

from site_lib import clubs as CL                # noqa: E402
from site_lib.config import load                # noqa: E402
from site_lib.names import _team_match, _team_news   # noqa: E402

fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


LP = CL.LEAGUE_PAGES
by = {tp["slug"]: tp for tp in CL.TEAM_PAGES}

print("1. what a league page is")
ck("every one is page_only + league_page, with one exact feed name and a scope",
   all(tp.get("page_only") and tp.get("league_page") and len(tp["match_tokens"]) == 1
       and isinstance(tp["match_tokens"][0][1], tuple) for tp in LP))
ck("slugs: ASCII, unique across every club page", len(by) == len(CL.TEAM_PAGES)
   and all(re.fullmatch(r"[a-z0-9-]{2,40}", tp["slug"]) for tp in LP))
ck("none of them is a curated side (no ticker, no live cards, no match pieces, no form posts)",
   not any(tp in CL.CURATED_PAGES or tp in CL.MATCH_PIECE_PAGES for tp in LP))

print("2. names that mean something else here")
M = lambda comp, h, a: {"competition": comp, "home": h, "away": a}      # noqa: E731
ck("«الأهلي» in the Saudi league is the Saudi club's page, in the Egyptian league the Egyptian one",
   _team_match(by["al-ahli-saudi"], M("Saudi Pro League", "الأهلي", "النصر"))
   and not _team_match(by["al-ahli-saudi"], M("Egyptian Premier League", "الأهلي", "سموحة"))
   and not _team_match(by["al-ahly"], M("Saudi Pro League", "الأهلي", "النصر")))
ck("«الهلال» in the Saudi league is not الهلال السوداني, and the other way round",
   _team_match(by["al-hilal-saudi"], M("Saudi Pro League", "الهلال", "الفتح"))
   and not _team_match(by["al-hilal-saudi"], M("CAF Champions League", "الهلال السوداني", "حوريا"))
   and not _team_match(by["al-hilal-sudan"], M("Saudi Pro League", "الهلال", "الفتح")))
ck("«الاتحاد» (Saudi) and «الاتحاد السكندري» never share a match",
   not _team_match(by["al-ittihad-saudi"], M("Egyptian Premier League", "الاتحاد السكندري", "زد"))
   and not _team_match(by["al-ittihad-alexandria"], M("Saudi Pro League", "الاتحاد", "نيوم")))
ck("«المصري» the club is not «مصر» the national team",
   _team_match(by["al-masry"], M("Egyptian Premier League", "المصري", "زد"))
   and not _team_match(by["al-masry"], M("Africa Cup of Nations Qualification", "مصر", "مالاوي"))
   and not _team_match(by["egypt"], M("Egyptian Premier League", "المصري", "زد")))
ck("a Saudi namesake's page says so in its name",
   all("السعودي" in by[s]["name"] for s in ("al-ahli-saudi", "al-hilal-saudi", "al-ittihad-saudi",
                                             "al-nassr", "al-shabab-saudi", "al-faisaly-saudi")))
A = lambda t: {"title": t, "summary": ""}      # noqa: E731
ck("news: «الدوري المصري» is not a story of المصري; a bare «الأهلي» / «الهلال» / «الاتحاد» is nobody's league page",
   not any(_team_news(tp, A("ترتيب الدوري المصري بعد الجولة 12")) for tp in LP)
   and not any(_team_news(tp, A("الأهلي يفوز على الزمالك")) for tp in LP)
   and not any(_team_news(tp, A("الهلال يتعادل مع الاتحاد")) for tp in LP))
ck("news: the club's own phrase does land on its page",
   _team_news(by["al-masry"], A("المصري البورسعيدي يعلن قائمته")) and _team_news(by["al-ahli-saudi"], A("الأهلي السعودي يضم لاعبًا"))
   and _team_news(by["smouha"], A("سموحة يفوز")))
ck("no league page's news token is a bare name another page answers to",
   not [(tp["slug"], t) for tp in LP for t in tp["news_tokens"]
        if t in ("الأهلي", "الهلال", "الاتحاد", "المصري", "النصر", "الشباب", "الفتح", "الخليج", "الرياض", "زد", "القناة", "الجونة")])

print("3. kept out of the short lists")
from site_lib.follow import my_pick_html       # noqa: E402
ck("the «اختر فريقك» picker does not list them", not any(f'data-slug="{tp["slug"]}"' in my_pick_html() for tp in LP))

print("4. the built site")
st = {s.get("competition"): s for s in load("standings.json") or []}
for comp, page in (("Egyptian Premier League", "egypt"), ("Saudi Pro League", "saudi")):
    path = os.path.join("dist", "standings", page + ".html")
    table = (st.get(comp) or {}).get("table") or []
    if not os.path.exists(path) or not table:
        continue
    html = open(path, encoding="utf-8").read()
    linked = set(re.findall(r'class="lt-tb" href="/team/([a-z0-9-]+)"', html))
    want = {tp["slug"] for tp in CL.TEAM_PAGES
            if any(_team_match(tp, {"competition": comp, "home": r.get("team") or "", "away": ""}) for r in table)}
    ck(f"/standings/{page}: every club of the table that has a page is linked ({len(want)} of {len(table)})",
       want <= linked and all(os.path.exists(os.path.join("dist", "team", s + ".html")) for s in linked),
       str(sorted(want - linked)))
    if page == "saudi":
        ck("/standings/saudi never links the Egyptian الأهلي or الهلال السوداني", not ({"al-ahly", "al-hilal-sudan"} & linked))
if os.path.exists(os.path.join("dist", "team", "al-ahly.html")):
    h = open(os.path.join("dist", "team", "al-ahly.html"), encoding="utf-8").read()
    ck("a curated club's page lists its own league's pages, not the Saudi ones",
       'href="/team/smouha' in h and 'href="/team/al-nassr' not in h)

print("\nALL OK" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
