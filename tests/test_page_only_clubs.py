# -*- coding: utf-8 -*-
r"""Page-only club pages (2026-11-19): جلطة سراي, فنربخشة, بشكتاش, منتخب السودان.

    python tests/test_page_only_clubs.py      (from the repo root)

The user asked for these four pages to own a corner nobody holds in Arabic
(the Turkish league; Sudan). What this guards is the line between a PAGE and
a CURATED club: the four get a /team page, the «تابع فريقك» picker and their
chips - and none of what the curated twelve + the Egypt NT get (match
previews / reports, form posts, the ticker, a reserved push slot). And the
names: each one matched exactly, inside its own competitions.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

import site_lib.clubs as C                              # noqa: E402
from site_lib.names import _team_match, _team_news, curated_tier   # noqa: E402

fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


NEW = ("galatasaray", "fenerbahce", "besiktas", "sudan")
by = {tp["slug"]: tp for tp in C.TEAM_PAGES}
ck("1 the four pages exist and are marked page-only", all(by.get(s, {}).get("page_only") for s in NEW))
ck("2 the curated list is the old thirteen, unchanged and in the old order",
   [tp["slug"] for tp in C.CURATED_PAGES] == ["al-ahly", "zamalek", "pyramids", "egypt", "real-madrid", "barcelona",
                                              "man-united", "man-city", "arsenal", "liverpool", "chelsea",
                                              "al-hilal-sudan", "trabzonspor"], str([tp["slug"] for tp in C.CURATED_PAGES]))
ck("3 none of them is in the ticker", not any(t in ("جلطة سراي", "فنربخشة", "بشكتاش", "السودان") for t, _ in C.TICKER_TEAMS))


def m(comp, h, a):
    return {"competition": comp, "home": h, "away": a}


T, UCL, UEL, Q = "Turkish Super Lig", "UEFA Champions League", "UEFA Europa League", "Africa Cup of Nations Qualification"
ck("4 Galatasaray: the league under the feed's Arabic name, the Champions League under football-data's",
   _team_match(by["galatasaray"], m(T, "جلطة سراي", "آمد سبور")) and _team_match(by["galatasaray"], m(UCL, "Galatasaray SK", "Aston Villa FC")))
ck("5 Fenerbahçe and Beşiktaş in their league and their European competition",
   _team_match(by["fenerbahce"], m(T, "قونيا سبور", "فنربخشة")) and _team_match(by["fenerbahce"], m(UCL, "Fenerbahçe SK", "Liverpool FC"))
   and _team_match(by["besiktas"], m(T, "بشكتاش", "قاسم باشا")) and _team_match(by["besiktas"], m(UEL, "سيلتيك", "بشكتاش")))
ck("6 one club's match is not another's", not _team_match(by["besiktas"], m(T, "جلطة سراي", "فنربخشة"))
   and not _team_match(by["galatasaray"], m(T, "بشكتاش", "فنربخشة")))
ck("7 «السودان» is the national team in the qualifiers - never «جنوب السودان», never a club competition",
   _team_match(by["sudan"], m(Q, "السودان", "السنغال")) and not _team_match(by["sudan"], m(Q, "جنوب السودان", "أنجولا"))
   and not _team_match(by["sudan"], m("CAF Champions League", "الهلال السوداني", "حوريا")))

import match_brief as MB                                # noqa: E402
ck("8 no preview / report weight: a page-only club's match has no curated club",
   MB.curated_club(m(T, "جلطة سراي", "فنربخشة")) is None and MB.curated_clubs(m(T, "بشكتاش", "قاسم باشا")) == [])
# writer review 2026-11-19: السودان 2-4 السنغال passed with no preview and no
# report. The national team is the ONE page-only side whose matches get them.
ck("8b ...except منتخب السودان (match_pieces): its matches get a preview and a report, and nothing else curated",
   (MB.curated_club(m(Q, "السودان", "السنغال")) or {}).get("slug") == "sudan"
   and MB.curated_club(m(Q, "جنوب السودان", "أنجولا")) is None
   and by["sudan"].get("page_only") and by["sudan"] not in C.CURATED_PAGES
   and [tp["slug"] for tp in C.MATCH_PIECE_PAGES if tp.get("page_only")] == ["sudan"])
ck("9 ...while a curated club's match still has one, against a page-only side too",
   (MB.curated_club(m(T, "طرابزون سبور", "جلطة سراي")) or {}).get("slug") == "trabzonspor")
import story_events as SE                               # noqa: E402
ck("10 no club-form post for them", not ({tp["slug"] for tp in SE.form_clubs()} & set(NEW)))
import push_send as PS                                  # noqa: E402
ck("11 no reserved push slot: their story has the same priority as any other",
   PS.priority({"title": "بشكتاش يحسم صفقة جديدة", "summary": ""}) == 0
   and PS.priority({"title": "برشلونة يحسم صفقة جديدة", "summary": ""}) == 1)
ck("12 the home analyses block does not rank them as curated",
   curated_tier({"article_id": "t1", "title": "فنربخشة يفوز في الدوري التركي", "summary": ""}) == 2)
ck("13 their stories still reach their page, under every common spelling",
   _team_news(by["galatasaray"], {"article_id": "t2", "title": "غلطة سراي يتصدر", "summary": ""})
   and _team_news(by["galatasaray"], {"article_id": "t3", "title": "جالطة سراي يتصدر", "summary": ""})
   and _team_news(by["sudan"], {"article_id": "t4", "title": "منتخب السودان يخسر أمام السنغال", "summary": ""})
   and not _team_news(by["sudan"], {"article_id": "t5", "title": "منتخب جنوب السودان يخسر أمام أنجولا", "summary": ""})
   and not _team_news(by["sudan"], {"article_id": "t6", "title": "الهلال السوداني يفوز في دوري الأبطال", "summary": ""}))
import push_team as PT                                  # noqa: E402
ck("14 a follower still gets the live event when the Worker dispatches one",
   PT.slugs_for_game({"id": 1, "c": 78, "h": "جلطة سراي", "a": "بشكتاش"}) == ["galatasaray", "besiktas"]
   and PT.slugs_for_game({"id": 2, "c": 588, "h": "السودان", "a": "السنغال"}) == ["sudan"]
   and PT.slugs_for_game({"id": 3, "c": 588, "h": "جنوب السودان", "a": "أنجولا"}) == [])

dist = os.path.join(os.getcwd(), "dist")
if os.path.isdir(os.path.join(dist, "team")):
    import io
    sm = io.open(os.path.join(dist, "sitemap.xml"), encoding="utf-8").read()
    home = io.open(os.path.join(dist, "index.html"), encoding="utf-8").read()
    ck("15 the built pages: written, in the sitemap, in the «تابع فريقك» picker, with their fragment",
       all(os.path.exists(os.path.join(dist, "team", s + ".html")) and f"/team/{s}<" in sm
           and f'data-slug="{s}"' in home and os.path.exists(os.path.join(dist, "my", s + ".json")) for s in NEW))

print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
