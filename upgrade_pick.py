"""Pick short archive articles for the daily AI upgrade run.

Usage:
    python upgrade_pick.py                 # human-readable list of the next 5
    python upgrade_pick.py --count 5 --json > /tmp/upgrade_queue.json
    python upgrade_pick.py --stats         # how much of the archive is still thin

Selection (AdSense "low value content" remediation, 2026-09-06): articles whose
body has fewer than MAX_WORDS whitespace tokens, not already upgraded
(`upgraded_ts` absent), older than MIN_AGE_DAYS (fresh ones are written at the
new 500-700 standard anyway). Match previews/reports (`kind` set) are excluded
— they are 650-900 words by construction.

Order (2026-09-16): the articles the site still SHOWS come first — those at or
above build_site.ARTICLE_MIN_WORDS, which are indexed, in the sitemap and
reachable from the listings, so they are what a reviewer actually lands on.
Everything under that bar is already noindexed and out of every listing, so
upgrading it changes nothing a visitor sees today. It is still worth doing
second: each one that crosses the bar turns into a real indexed article, which
is the only lever we have on the article/match-page ratio in the sitemap.
Newest first inside each group.
"""
import argparse
import datetime
import json
import os
import re
import sys

# The bar the site itself uses to decide whether an article is listed at all.
# Imported rather than copied so the picker and the builder cannot drift apart.
from build_site import ARTICLE_MIN_WORDS as LISTED_MIN

HERE = os.path.dirname(os.path.abspath(__file__))
ARTICLES = os.path.join(HERE, "data", "articles.json")
MAX_WORDS = 450        # below the 500-700 standard with margin
MIN_AGE_DAYS = 2


def strip_tags(s):
    return re.sub(r"<[^>]+>", " ", s or "")


def words(a):
    return len(strip_tags(a.get("body") or "").split())


def load():
    d = json.load(open(ARTICLES, encoding="utf-8"))
    return d["results"][0]["items"] if isinstance(d, dict) else d


def candidates(items, today=None):
    today = today or datetime.date.today()
    cut = (today - datetime.timedelta(days=MIN_AGE_DAYS)).isoformat()
    out = []
    for a in items:
        if a.get("upgraded_ts") or a.get("kind"):
            continue
        if (a.get("pub_date") or "") > cut:
            continue
        w = words(a)
        if w >= MAX_WORDS:
            continue
        out.append({"article_id": str(a.get("article_id")), "title": a.get("title"),
                    "pub_date": a.get("pub_date"), "words": w,
                    "listed": w >= LISTED_MIN})
    # items are newest-first in the file already, so a stable partition keeps
    # that order inside each group: what the site still shows, then the rest
    return [c for c in out if c["listed"]] + [c for c in out if not c["listed"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()
    items = load()
    cands = candidates(items)
    if args.stats:
        up = sum(1 for a in items if a.get("upgraded_ts"))
        vis = sum(1 for c in cands if c["listed"])
        print(f"articles: {len(items)} | upgraded: {up} | "
              f"still thin (<{MAX_WORDS} words, eligible): {len(cands)} "
              f"= {vis} still listed (>={LISTED_MIN}w, indexed) "
              f"+ {len(cands) - vis} already unlisted")
        return
    pick = cands[:args.count]
    if args.json:
        json.dump(pick, sys.stdout, ensure_ascii=False, indent=1)
        return
    for p in pick:
        flag = "listed  " if p["listed"] else "unlisted"
        print(f"{p['article_id']:>5}  {p['pub_date']}  {p['words']:>3}w  {flag}  {p['title']}")
    print(f"-- {len(pick)} of {len(cands)} eligible")


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    main()
