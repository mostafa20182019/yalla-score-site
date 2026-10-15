# -*- coding: utf-8 -*-
r"""Home analyses block: the featured clubs' pieces lead (user, 2026-10-15).

    python tests/test_home_featured_first.py     (from the repo root)

«خلي دايمًا توقعات وتقارير الفرق المميزة في الأول»: on 10-15 the block led with
Lech Poznan x Leverkusen (the newest preview) while the Zamalek and Pyramids
previews sat 1st and 2nd in the list. The rule: Egyptian curated sides first,
then the other curated clubs, then everyone else - newest within each tier;
the HOME_PIN lead and the held big-match analyses keep their precedence.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import site_lib.cards as C
from site_lib.names import curated_tier

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

def P(i, title, kind="preview"):
    return {"article_id": str(i), "title": title, "summary": "", "kind": kind, "match_id": str(1000 + i)}

# newest first, as the build hands them over
arts = [P(9, "توقع يلا سكور: ليخ بوزنان يواجه باير ليفركوزن في الدوري الأوروبي"),
        P(8, "توقع يلا سكور: الجيش الرواندي يواجه الزمالك في دوري أبطال أفريقيا"),
        P(7, "توقع يلا سكور: المريخ بنتو × بيراميدز في دوري أبطال أفريقيا"),
        P(6, "تقرير: أستون فيلا يسحق فنربخشة 6-0 في دوري أبطال أوروبا", "report"),
        P(5, "توقع يلا سكور: ليفربول يواجه برينتفورد في الدوري الإنجليزي"),
        P(4, "تقرير: بودو جليمت يصدم بوروسيا دورتموند 1-0", "report")]

ck("1a tiers: Egyptian curated 0, other curated 1, rest 2",
   [curated_tier(a) for a in arts] == [2, 0, 0, 2, 1, 2])
ck("1b the Saudi «الأهلي» is not the Egyptian club",
   curated_tier(P(3, "توقع يلا سكور: الفتح × الأهلي في دوري روشن السعودي")) == 1 or
   curated_tier(P(3, "توقع يلا سكور: الفتح × الأهلي السعودي في دوري روشن")) == 2)
ck("1c the national team counts as Egyptian", curated_tier(P(2, "توقع يلا سكور: منتخب مصر يواجه غانا في تصفيات كأس الأمم")) == 0)

lead, rest = C.home_insights(arts, pinned=False)
ids = [a["article_id"] for a in rest]
ck("2a the lead is the Zamalek match, not the newest preview", lead["article_id"] == "8", lead["title"])
ck("2b the second is the Pyramids match", ids[0] == "7", str(ids))
ck("2c then the other curated club (Liverpool), then the rest newest-first", ids == ["7", "5", "9", "6"], str(ids))

# the pin still wins the lead
pinned = [P(1, "تحليل: الديربي بالأرقام", "analysis")] + arts
lead, rest = C.home_insights(pinned, pinned=True)
ck("3a HOME_PIN keeps the lead", lead["article_id"] == "1")
ck("3b ...and the list below it is still featured-first", [a["article_id"] for a in rest][:2] == ["8", "7"])

# a held big-match analysis (unplayed) still comes before everything
lead, rest = C.home_insights(arts, pinned=False, held=["4"])
ck("4 a held analysis keeps its precedence over the tiers", lead["article_id"] == "4" and [a["article_id"] for a in rest][:2] == ["8", "7"])

# ------------------------------------------- stale pieces step back (same day)
import datetime
from zoneinfo import ZoneInfo
from site_lib.articles import stale_analyses
cairo = ZoneInfo("Africa/Cairo")
now = datetime.datetime(2026, 10, 15, 18, 0, tzinfo=cairo)
def MM(i, day, time, status="UPCOMING"):
    return {"match_id": str(1000 + i), "kickoff": day, "koff_time": time, "status": status,
            "home": "x", "away": "y", "competition": "c"}
ms = [MM(9, "2026-10-15", "19:45"),                       # tonight, not yet played  -> fresh preview
      MM(8, "2026-10-16", "19:00"),                       # tomorrow                 -> fresh preview
      MM(7, "2026-10-16", "16:30"),                       # tomorrow                 -> fresh preview
      MM(6, "2026-10-14", "22:00", "FINISHED"),           # last night's report (<24h after) -> fresh
      MM(5, "2026-10-17", "17:00"),                       # Saturday preview          -> fresh
      MM(4, "2026-10-13", "22:00", "FINISHED")]           # report two days old       -> stale
st = stale_analyses(arts, ms, now=now)
ck("5a a report is fresh for 24 h after the match, stale after", st == {"4"}, str(st))
st2 = stale_analyses(arts, [MM(9, "2026-10-15", "13:00", "FINISHED")] + ms[1:], now=now)
ck("5b a preview is stale the moment its match is over", "9" in st2)
st3 = stale_analyses(arts, [MM(9, "2026-10-15", "14:00")] + ms[1:], now=now)
ck("5c ...or 3 h past kick-off when the feed never said FINISHED", "9" in st3)
old = [dict(P(21, "تقرير: الزمالك يسحق إيه إس بورت 4-0", "report"), pub_ts="2026-09-26T23:10:00+03:00"),
       dict(P(22, "توقع يلا سكور: الزمالك يواجه إيه إس بورت"), pub_ts="2026-10-15T09:00:00+03:00"),
       {"article_id": "23", "title": "الجولة 5 من الدوري المصري بالأرقام", "summary": "", "pub_date": "2026-10-01",
        "sources": [{"name": "x", "url": "https://yallascore.site/", "note": "round:egypt:5"}]}]
st4 = stale_analyses(old, [], now=now)
ck("5d no match to read: the piece's own age decides (48 h) - old report + old round piece stale, this morning's preview fresh",
   st4 == {"21", "23"}, str(st4))

# the stale Pyramids/Ahly reports step behind every fresh piece, featured kept inside each group
arts2 = arts + [P(3, "تقرير: بيراميدز يكتسح سيراميكا كليوباترا 4-1", "report"),
                P(2, "تقرير: الأهلي يكسب قمة الزمالك 2-0", "report")]
lead, rest = C.home_insights(arts2, pinned=False, stale={"3", "2", "4"})
ids = [lead["article_id"]] + [a["article_id"] for a in rest]
ck("6a fresh featured lead, fresh pieces of every tier next, stale ones last",
   ids == ["8", "7", "5", "9", "6"], str(ids))
lead, rest = C.home_insights(arts2, pinned=False, stale={"8", "7", "5", "9", "6"})
ck("6b when only stale pieces remain, the featured ones still lead them",
   [lead["article_id"]] + [a["article_id"] for a in rest][:2] == ["3", "2", "4"], lead["article_id"])

print()
print("ALL OK" if not fails else f"{len(fails)} FAILED: " + ", ".join(fails))
sys.exit(1 if fails else 0)
