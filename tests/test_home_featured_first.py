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

print()
print("ALL OK" if not fails else f"{len(fails)} FAILED: " + ", ".join(fails))
sys.exit(1 if fails else 0)
