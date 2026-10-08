#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The photo-vs-link A/B read-out helper (growth plan week 1 -> week 4).

Lists every article posted to Facebook since the A/B started, with its
variant (EVEN id = photo, ODD = link - fb_post.variant) and the post URL, so
the reach of each post can be read in Meta Business Suite -> Insights ->
Content and the two columns compared. Reading insights here automatically
would need the page token to carry `read_insights`; today's token does not.

    python fb_ab_list.py                 # since 2026-10-08
    python fb_ab_list.py --since 2026-10-15
"""
import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fb_post as fp                                  # noqa: E402

AB_START = "2026-10-08"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=AB_START)
    args = ap.parse_args()
    since = datetime.datetime.fromisoformat(args.since).replace(tzinfo=datetime.timezone.utc).timestamp()
    with open(os.path.join(HERE, "data", "fb_posted.json"), encoding="utf-8") as f:
        posted = (json.load(f).get("articles") or {})
    titles = {str(a.get("article_id")): a.get("title") for a in fp.load_articles()}
    rows = []
    for aid, rec in posted.items():
        if not rec.get("post_id") or float(rec.get("ts") or 0) < since:
            continue
        rows.append((float(rec["ts"]), aid, fp.variant({"article_id": aid}), rec["post_id"], titles.get(aid) or rec.get("title") or ""))
    rows.sort()
    by = {"photo": 0, "link": 0}
    print(f"{'date':16} {'id':5} {'variant':7} post")
    for ts, aid, var, pid, title in rows:
        by[var] += 1
        day = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
        print(f"{day:16} {aid:5} {var:7} https://www.facebook.com/{pid}  {title[:60]}")
    print(f"\n{len(rows)} posts since {args.since}: photo {by['photo']}, link {by['link']}")
    print("read each post's reach in Meta Business Suite -> Insights -> Content, then compare the two averages")


if __name__ == "__main__":
    main()
