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

PREVIEW SAFETY (the two 404-preview incidents):
  * 2026-09-03, article 358: the post was made from daily-article.yml at commit
    time, 1-2 min BEFORE publish.yml deployed the page -> Facebook cached the
    404 page as the link preview. Fix: post from publish.yml after Deploy.
  * 2026-09-04, article 364: posted seconds AFTER a successful Deploy and still
    got the 404 preview - Cloudflare's asset deploy is eventually consistent
    across edges, so Facebook's (US) crawler fetched the previous version.
    Fix: (1) wait until the article URL itself serves the real page, (2) ask
    Facebook to scrape and CHECK the og:title it got back, retrying for up to
    ~a minute, (3) if it still looks like the 404 page, DEFER the post to the
    next run (state untouched) instead of publishing a broken preview,
    (4) a heal pass re-scrapes recently posted URLs whose preview was never
    confirmed good, so an existing post picks up the real preview.

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
import re
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
AUTO_MAX_AGE_H = 6       # --auto never posts an article older than this (10 articles/day: 12h re-posted a half-day backlog on 2026-09-03)
AUTO_MAX_PER_RUN = 3     # --auto posts at most this many per run (staggers a backlog)
NOT_FOUND_MARK = "الصفحة غير موجودة"   # <title> of dist/404.html
LIVE_TRIES, LIVE_WAIT = 6, 10          # wait up to ~60s for the URL to serve the page
SCRAPE_TRIES, SCRAPE_WAIT = 4, 10      # then up to ~40s for Facebook's crawler to see it
HEAL_WINDOW_H = 4                      # re-scrape posts younger than this whose preview isn't confirmed


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


def article_link(art):
    # extensionless = the canonical URL form (build_site._clean_urls)
    return f"{SITE}/a/{str(art.get('article_id', '')).strip()}"


def page_is_live(link):
    """True when OUR site serves the real article at `link` (200 + not the 404 title)."""
    try:
        req = urllib.request.Request(link + f"?cb={int(time.time())}",
                                     headers={"User-Agent": "yalla-score-fbpost/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read(20000).decode("utf-8", "replace")
        return r.status == 200 and NOT_FOUND_MARK not in body
    except Exception:
        return False


def wait_live(link):
    for i in range(LIVE_TRIES):
        if page_is_live(link):
            return True
        print(f"  {link} not live yet (try {i + 1}/{LIVE_TRIES}) - waiting {LIVE_WAIT}s")
        time.sleep(LIVE_WAIT)
    return False


def scrape(token, link):
    """Ask Facebook to (re)fetch the URL now. Returns the og dict ({} on error)."""
    data = urllib.parse.urlencode({"id": link, "scrape": "true", "access_token": token}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(GRAPH + "/", data=data), timeout=30) as r:
            og = json.load(r)
        print(f"  scraped {link}: title={og.get('title', '')!r}")
        return og if isinstance(og, dict) else {}
    except Exception as e:  # noqa: BLE001
        print(f"  scrape failed ({e})")
        return {}


def og_ok(og):
    title = (og.get("title") or "").strip()
    return bool(title) and NOT_FOUND_MARK not in title


def scrape_until_ok(token, link):
    """Scrape, and if Facebook still sees the 404 page retry a few times.
    Returns (ok, og)."""
    og = {}
    for i in range(SCRAPE_TRIES):
        og = scrape(token, link)
        if og_ok(og):
            return True, og
        if i < SCRAPE_TRIES - 1:
            print(f"  preview not ready (try {i + 1}/{SCRAPE_TRIES}) - waiting {SCRAPE_WAIT}s")
            time.sleep(SCRAPE_WAIT)
    return False, og


def already_on_page(token, limit=50):
    """Article ids that are ALREADY published on the page, read from Facebook
    itself. Returns a set, or None when the read fails.

    Why this exists (root cause of the duplicate posts, found 2026-09-07): the
    dedup state lives in data/fb_posted.json, which the workflow commits back
    in its LAST step with `git push || echo "push failed (race...)"`. A log scan
    of 30 recent publish runs found 5 of them (17%) losing that race — the
    article had gone out to Facebook but the repo never learned it, so the next
    run read the old state, saw the article as unposted, and posted it again.
    With AUTO_MAX_AGE_H=6 and a run every ~15 min, one article could go out
    many times. Two overlapping runs both loading the state before either
    writes cause the same thing.

    The page itself is the only source that cannot be lost to a git race, so it
    is now the authority: every post we make carries the article URL in its
    message, so the ids present in the recent feed are the ids already posted.
    """
    url = (f"{GRAPH}/me/feed?fields=message,created_time,attachments%7Btarget%7D"
           f"&limit={limit}&access_token={urllib.parse.quote(token)}")
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"User-Agent": "yalla-score-fbpost/1.0"}), timeout=30) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        print(f"  ! could not read the page feed: HTTP {e.code} {body}")
        return None
    except Exception as e:  # noqa: BLE001
        print(f"  ! could not read the page feed: {e}")
        return None
    ids = set()
    for post in data.get("data") or []:
        blob = post.get("message") or ""
        for att in ((post.get("attachments") or {}).get("data") or []):
            blob += " " + str(((att.get("target") or {}).get("url")) or "")
        ids.update(re.findall(r"/a/(\d+)", blob))
    print(f"  page feed: {len(data.get('data') or [])} recent posts, "
          f"{len(ids)} article id(s) already published")
    return ids


def post_article(token, art):
    """Publish the feed post (preview already verified by the caller)."""
    link = article_link(art)
    title = (art.get("title") or "").strip()
    summary = (art.get("summary") or "").strip()
    # the article task writes a crafted fb_post (same text the user copies
    # from /fb.html) - prefer it; fall back to the plain generated format
    message = (art.get("fb_post") or "").strip() or f"⚽ {title}\n\n{summary}\n\n\U0001f449 {link}"
    data = urllib.parse.urlencode({"message": message, "link": link, "access_token": token}).encode()
    with urllib.request.urlopen(urllib.request.Request(GRAPH_FEED, data=data), timeout=30) as r:
        resp = json.load(r)
    return resp.get("id")


def try_post(token, art, st=None, og_verified=None):
    """Post one article, print the outcome, record it in st when given.
    Returns True on success. Never raises."""
    aid = str(art.get("article_id", "")).strip()
    try:
        pid = post_article(token, art)
        print(f"posted article {aid} to Facebook: post id {pid}")
        if st is not None:
            st["articles"][aid] = {"ts": time.time(), "post_id": pid, "title": art.get("title"),
                                   "og_ok": bool(og_verified)}
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        print(f"Facebook post FAILED (article {aid}): HTTP {e.code} {body}")
    except Exception as e:  # noqa: BLE001 - never block the publish over a social post
        print(f"Facebook post FAILED (article {aid}): {e}")
    return False


def heal_previews(token, st):
    """Re-scrape recently posted URLs whose preview was never confirmed good
    (older records have no og_ok at all). Facebook refreshes the existing
    post's preview from the new scrape."""
    now = time.time()
    for aid, rec in st["articles"].items():
        if rec.get("og_ok") or now - rec.get("ts", 0) > HEAL_WINDOW_H * 3600:
            continue
        if not str(rec.get("post_id") or "").strip() or "seeded" in str(rec.get("post_id")):
            continue
        link = f"{SITE}/a/{aid}"
        print(f"heal: re-scraping {link}")
        og = scrape(token, link)
        if og_ok(og):
            rec["og_ok"] = True
            print(f"  preview for article {aid} is good now")


def pending(items, st):
    """Articles the local state says are still unposted and young enough,
    oldest first, capped per run. Shared by --auto and --pending."""
    todo = []
    for art in items:
        aid = str(art.get("article_id", "")).strip()
        if not aid or aid in st["articles"]:
            continue
        age = article_age_hours(art)
        if age is None or age > AUTO_MAX_AGE_H:
            continue          # undated / old: never auto-posted
        todo.append((age, art))
    todo.sort(key=lambda t: -t[0])            # oldest first, newest last
    return [art for _, art in todo][:AUTO_MAX_PER_RUN]


def auto(token, items):
    st = load_state()
    todo = pending(items, st)
    if not todo:
        print("no new article to post")
    elif not token:
        print(f"FB_PAGE_TOKEN not set - {len(todo)} article(s) would be posted, skipping")
        return 0
    if todo and token:
        # second gate, and the authoritative one: ask the PAGE what is already
        # published. Catches every article whose state write was lost to a git
        # race, which is what was posting the same news more than once.
        on_page = already_on_page(token)
        if on_page is None:
            # Verified dead end 2026-09-07: the token's scope list DOES contain
            # pages_read_engagement and Graph still answers (#10) for both
            # /me/feed and /<page-id>/feed - the permission is Standard Access,
            # and reading a page's feed needs Advanced Access or the
            # "Page Public Content Access" feature, i.e. a full App Review.
            # Not worth it: duplicates are prevented by serialising the posting
            # workflow instead (concurrency group fb-post). Kept because it
            # starts working the day App Review is done.
            print("  page feed check unavailable (needs App Review) - relying on "
                  "the serialised queue + the state file")
        else:
            keep = []
            for art in todo:
                aid = str(art.get("article_id", "")).strip()
                if aid in on_page:
                    # repair the state so the next run does not ask again
                    st["articles"].setdefault(aid, {
                        "ts": time.time(), "post_id": "recovered-from-page",
                        "title": art.get("title"), "og_ok": True})
                    print(f"article {aid}: ALREADY on the page - skipping "
                          "(state had lost it; recovered)")
                else:
                    keep.append(art)
            todo = keep
            if not todo:
                save_state(st)
                print("nothing left to post after checking the page")
                return 0
    for art in todo:
        aid = str(art.get("article_id", "")).strip()
        link = article_link(art)
        if not wait_live(link):
            print(f"article {aid}: page not live yet - deferred to the next run")
            continue
        ok, og = scrape_until_ok(token, link)
        if not ok:
            print(f"article {aid}: Facebook still sees the 404 page - deferred to the next run")
            continue
        try_post(token, art, st, og_verified=True)
    if token:
        heal_previews(token, st)
    save_state(st)
    return 0


def main() -> int:
    token = os.environ.get("FB_PAGE_TOKEN", "").strip()
    items = load_articles()
    if not items:
        print("no articles - skipping")
        return 0
    if "--pending" in sys.argv[1:]:
        # how many articles WOULD be posted - lets publish.yml dispatch the
        # serialised posting workflow only when there is something to do
        print(len(pending(items, load_state())))
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
    ok, _ = scrape_until_ok(token, article_link(art))
    try_post(token, art, og_verified=ok)
    return 0


if __name__ == "__main__":
    sys.exit(main())
