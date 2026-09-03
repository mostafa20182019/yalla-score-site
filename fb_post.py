# -*- coding: utf-8 -*-
"""Post new articles to the Yalla Score Facebook page via the Graph API.

Called by .github/workflows/publish.yml AFTER the site is deployed:

    python fb_post.py --auto

--auto posts every article in data/articles.json that (a) is not yet recorded
in data/fb_posted.json ("articles" key, shared with fb_cards.py and committed
back by the workflow) and (b) was published within the last AUTO_MAX_AGE_H
hours - oldest first, at most AUTO_MAX_PER_RUN per run - so the first run never
floods the page with old articles, and two articles written in one slot both
get posted (only the top one used to be considered).

WHY it lives in publish.yml and not daily-article.yml (moved 2026-09-03): the
article workflow used to post the moment the article was committed, but the
page only goes live ~1-2 min later when publish.yml deploys. Facebook scraped
the link in that gap, got the 404 page, and the post carried "الصفحة غير
موجودة" as its preview for good (article 358). Posting after Deploy - and
asking Facebook to scrape the URL first - guarantees a real preview.

Legacy form (kept for manual use):  python fb_post.py "<prev top article_id>"
posts the top article when its id differs from the argument, no state.

Silently skips when FB_PAGE_TOKEN is absent. Never fails the workflow.
FB_PAGE_TOKEN = long-lived PAGE token with pages_manage_posts, and the Meta
app MUST be published (Live): posts made while the app is in Development mode
are visible to the app's admins only (see FB_AUTOPOST_RUNBOOK.md).
"""
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = "https://yallascore.site"
GRAPH = "https://graph.facebook.com/v23.0"
GRAPH_FEED = f"{GRAPH}/me/feed"
STATE_FILE = os.path.join(HERE, "data", "fb_posted.json")
AUTO_MAX_AGE_H = 12      # --auto never posts an article older than this
AUTO_MAX_PER_RUN = 3     # --auto posts at most this many per run (staggers a backlog)


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        st = {}
    st.setdefault("articles", {})
    return st


def save_state(st):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def load_articles():
    with open(os.path.join(HERE, "data", "articles.json"), encoding="utf-8") as f:
        return json.load(f)["results"][0]["items"]


def article_age_hours(art):
    ts = (art.get("pub_ts") or "").strip()
    try:
        t = datetime.datetime.fromisoformat(ts)
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        return (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() / 3600
    except Exception:
        return None       # unknown age (old articles have no pub_ts)


def scrape(token, link):
    """Ask Facebook to (re)fetch the URL now, so the post gets a fresh preview
    instead of whatever its crawler cached earlier. Best effort."""
    data = urllib.parse.urlencode({"id": link, "scrape": "true", "access_token": token}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(GRAPH + "/", data=data), timeout=30) as r:
            og = json.load(r)
        print(f"scraped {link}: title={og.get('title', '')!r}")
        return og.get("title") or ""
    except Exception as e:  # noqa: BLE001
        print(f"scrape failed ({e}) - posting anyway")
        return ""


def post_article(token, art):
    aid = str(art.get("article_id", "")).strip()
    link = f"{SITE}/a/{aid}"   # extensionless = the canonical URL form (build_site._clean_urls)
    title = (art.get("title") or "").strip()
    summary = (art.get("summary") or "").strip()
    # the article task writes a crafted fb_post (same text the user copies
    # from /fb.html) - prefer it; fall back to the plain generated format
    message = (art.get("fb_post") or "").strip() or f"⚽ {title}\n\n{summary}\n\n\U0001f449 {link}"
    scrape(token, link)
    data = urllib.parse.urlencode({"message": message, "link": link, "access_token": token}).encode()
    with urllib.request.urlopen(urllib.request.Request(GRAPH_FEED, data=data), timeout=30) as r:
        resp = json.load(r)
    return resp.get("id")


def try_post(token, art, st=None):
    """Post one article, print the outcome, record it in st when given.
    Returns True on success. Never raises."""
    aid = str(art.get("article_id", "")).strip()
    try:
        pid = post_article(token, art)
        print(f"posted article {aid} to Facebook: post id {pid}")
        if st is not None:
            st["articles"][aid] = {"ts": time.time(), "post_id": pid, "title": art.get("title")}
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        print(f"Facebook post FAILED (article {aid}): HTTP {e.code} {body}")
    except Exception as e:  # noqa: BLE001 - never block the publish over a social post
        print(f"Facebook post FAILED (article {aid}): {e}")
    return False


def auto(token, items):
    st = load_state()
    todo = []
    for art in items:
        aid = str(art.get("article_id", "")).strip()
        if not aid or aid in st["articles"]:
            continue
        age = article_age_hours(art)
        if age is None or age > AUTO_MAX_AGE_H:
            continue          # undated / old: never auto-posted
        todo.append((age, art))
    if not todo:
        print("no new article to post")
        return 0
    todo.sort(key=lambda t: -t[0])            # oldest first, newest last
    todo = [art for _, art in todo][:AUTO_MAX_PER_RUN]
    if not token:
        print(f"FB_PAGE_TOKEN not set - {len(todo)} article(s) would be posted, skipping")
        return 0
    for art in todo:
        try_post(token, art, st)
    save_state(st)
    return 0


def main() -> int:
    token = os.environ.get("FB_PAGE_TOKEN", "").strip()
    items = load_articles()
    if not items:
        print("no articles - skipping")
        return 0
    if "--auto" in sys.argv[1:]:
        return auto(token, items)

    # legacy: post the top article when its id differs from the argument
    art = items[0]
    aid = str(art.get("article_id", "")).strip()
    prev_id = next((a for a in sys.argv[1:] if not a.startswith("--")), "").strip()
    if not aid or aid == prev_id:
        print(f"top article unchanged (id {aid or '?'}) - skipping")
        return 0
    if not token:
        print("FB_PAGE_TOKEN not set - skipping Facebook post")
        return 0
    try_post(token, art)
    return 0


if __name__ == "__main__":
    sys.exit(main())
