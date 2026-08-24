# -*- coding: utf-8 -*-
"""Post the newest article to the Yalla Score Facebook page via the Graph API.

Called by .github/workflows/daily-article.yml AFTER the article step:

    python fb_post.py "<top article_id BEFORE the run>"

Posts only when data/articles.json's top id differs from the argument
(= this run actually published a new article). Silently skips when the
FB_PAGE_TOKEN env var is absent, so the step is inert until the repo
secret exists. Never fails the workflow: a social-post error must not
block the article publish.

FB_PAGE_TOKEN must be a long-lived PAGE access token with
pages_manage_posts (see matches-guide/FB_AUTOPOST_RUNBOOK.md in the
apex-ai-lab repo for the exact Meta-for-Developers steps).
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

SITE = "https://yallascore.site"
GRAPH_FEED = "https://graph.facebook.com/v23.0/me/feed"


def main() -> int:
    token = os.environ.get("FB_PAGE_TOKEN", "").strip()
    if not token:
        print("FB_PAGE_TOKEN not set - skipping Facebook post")
        return 0

    prev_id = sys.argv[1].strip() if len(sys.argv) > 1 else ""

    with open("data/articles.json", encoding="utf-8") as f:
        items = json.load(f)["results"][0]["items"]
    if not items:
        print("no articles - skipping")
        return 0

    art = items[0]
    aid = str(art.get("article_id", "")).strip()
    if not aid or aid == prev_id:
        print(f"top article unchanged (id {aid or '?'}) - no new article this run, skipping")
        return 0

    link = f"{SITE}/a/{aid}.html"
    title = (art.get("title") or "").strip()
    summary = (art.get("summary") or "").strip()
    message = f"⚽ {title}\n\n{summary}\n\n\U0001f449 {link}"

    data = urllib.parse.urlencode(
        {"message": message, "link": link, "access_token": token}
    ).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(GRAPH_FEED, data=data), timeout=30) as r:
            resp = json.load(r)
        print(f"posted article {aid} to Facebook: post id {resp.get('id')}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        print(f"Facebook post FAILED (article {aid}): HTTP {e.code} {body}")
    except Exception as e:  # noqa: BLE001 - never block the publish over a social post
        print(f"Facebook post FAILED (article {aid}): {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
