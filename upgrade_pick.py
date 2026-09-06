"""Pick short archive articles for the daily AI upgrade run.

Usage:
    python upgrade_pick.py                 # human-readable list of the next 5
    python upgrade_pick.py --count 5 --json > /tmp/upgrade_queue.json
    python upgrade_pick.py --stats         # how much of the archive is still thin

Selection (AdSense "low value content" remediation, 2026-09-06): articles whose
body has fewer than MAX_WORDS whitespace tokens, not already upgraded
(`upgraded_ts` absent), older than MIN_AGE_DAYS (fresh ones are written at the
new 500-700 standard anyway), newest first (they carry the most traffic and are
what a reviewer sampling the home/news pages sees first). Match previews/reports
(`kind` set) are excluded — they are 650-900 words by construction.
"""
import argparse
import datetime
import json
import os
import re
import sys

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
                    "pub_date": a.get("pub_date"), "words": w})
    # items are newest-first in the file already; keep that order
    return out


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
        print(f"articles: {len(items)} | upgraded: {up} | still thin (<{MAX_WORDS} words, eligible): {len(cands)}")
        return
    pick = cands[:args.count]
    if args.json:
        json.dump(pick, sys.stdout, ensure_ascii=False, indent=1)
        return
    for p in pick:
        print(f"{p['article_id']:>5}  {p['pub_date']}  {p['words']:>3}w  {p['title']}")
    print(f"-- {len(pick)} of {len(cands)} eligible")


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    main()
