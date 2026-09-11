# -*- coding: utf-8 -*-
"""Post new articles to the Yalla Score Facebook page via the Graph API.

Called by .github/workflows/publish.yml AFTER the site is deployed:

    python fb_post.py --auto

--auto posts every article in data/articles.json that (a) is not yet recorded in
the state store (store.py: D1 when configured, else the old json file) and
(b) was published within the last AUTO_MAX_AGE_H hours - oldest first, at most
AUTO_MAX_PER_RUN per run - so the first run never floods the page with old
articles, and two articles written in one slot both get posted.

CLAIM-THEN-POST (2026-09-09): the run INSERTs a claim keyed on the article id
BEFORE it posts, so a concurrent run loses on the primary key instead of
posting the same article twice - which is what happened to article 422 on
2026-09-07, when two overlapping publish runs both read a json state file that
neither had written yet. A claim with no post_id is released on any deferral
and expires after store.CLAIM_TTL_SEC, so a run that dies mid-post cannot
silence an article forever.

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
from zoneinfo import ZoneInfo
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import store  # noqa: E402 - needs HERE on sys.path first
SITE = "https://yallascore.site"
GRAPH = "https://graph.facebook.com/v23.0"
GRAPH_FEED = f"{GRAPH}/me/feed"
AUTO_MAX_AGE_H = 6       # --auto never posts an article older than this (10 articles/day: 12h re-posted a half-day backlog on 2026-09-03)
AUTO_MAX_PER_RUN = 3     # --auto posts at most this many per run (staggers a backlog)
# POSTING WINDOW (2026-09-12, user: fewer runs). Cairo hours [open, close):
# the page posts from 13:00 until 01:00 the next day. Outside it `--pending`
# answers 0, so publish.yml never dispatches the poster - roughly halving its
# runs - and AUTO_MAX_AGE_H is measured in OPEN hours (see open_hours), so a
# report written at 02:00 is still fresh at 13:00 instead of being dropped.
# None = no window (the tests set that; the runner never does).
POST_WINDOW = (13, 1)
CAIRO = ZoneInfo("Africa/Cairo")
NOT_FOUND_MARK = "الصفحة غير موجودة"   # <title> of dist/404.html
LIVE_TRIES, LIVE_WAIT = 6, 10          # wait up to ~60s for the URL to serve the page
SCRAPE_TRIES, SCRAPE_WAIT = 4, 10      # then up to ~40s for Facebook's crawler to see it
HEAL_WINDOW_H = 4                      # re-scrape posts younger than this whose preview isn't confirmed


MAX_POST_ATTEMPTS = 3    # a permanently failing article must not eat a slot forever


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


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def window_open(now=None):
    """Is the Facebook posting window open at `now` (Cairo clock)?"""
    if not POST_WINDOW:
        return True
    h = (now or _now()).astimezone(CAIRO).hour
    o, c = POST_WINDOW
    return (o <= h or h < c) if o > c else (o <= h < c)


def open_hours(since, now=None):
    """Hours between `since` and `now` during which the window was open.
    Walks the span hour by hour (it is at most a day or two long), so the
    freshness rule sees a night-time article as 0 h old when the page reopens."""
    now = now or _now()
    if not POST_WINDOW:
        return (now - since).total_seconds() / 3600
    if since >= now:
        return 0.0
    total, t = 0.0, since
    while t < now:
        step = min(now, (t + datetime.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0))
        if step <= t:
            step = min(now, t + datetime.timedelta(hours=1))
        if window_open(t):
            total += (step - t).total_seconds() / 3600
        t = step
    return total


def article_pub_dt(art):
    ts = (art.get("pub_ts") or "").strip()
    try:
        t = datetime.datetime.fromisoformat(ts)
        return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return None


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


def try_post(token, art, og_verified=None):
    """Post one article and record it. Returns True on success. Never raises.
    The caller must already hold the claim (see auto())."""
    aid = str(art.get("article_id", "")).strip()
    try:
        pid = post_article(token, art)
        print(f"posted article {aid} to Facebook: post id {pid}")
        store.record_post("article", aid, pid, title=art.get("title"),
                          og_ok=bool(og_verified))
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        print(f"Facebook post FAILED (article {aid}): HTTP {e.code} {body}")
        store.bump_failed("article", aid, f"HTTP {e.code} {body[:200]}")
    except Exception as e:  # noqa: BLE001 - never block the publish over a social post
        print(f"Facebook post FAILED (article {aid}): {e}")
        store.bump_failed("article", aid, str(e)[:200])
    return False


def heal_previews(token):
    """Re-scrape recently posted URLs whose preview was never confirmed good.
    Facebook refreshes the existing post's preview from the new scrape."""
    for rec in store.unconfirmed("article", HEAL_WINDOW_H):
        aid = rec["ref_id"]
        if "seeded" in str(rec.get("post_id") or ""):
            continue
        link = f"{SITE}/a/{aid}"
        print(f"heal: re-scraping {link}")
        if og_ok(scrape(token, link)):
            store.set_og_ok("article", aid)
            print(f"  preview for article {aid} is good now")


def pending(items):
    """Articles not yet posted and young enough, oldest first, capped per run.
    Shared by --auto and --pending. This is a filter, not a lock - auto() still
    has to win the claim before it posts anything."""
    posted = store.posted_ids("article")
    todo = []
    for art in items:
        aid = str(art.get("article_id", "")).strip()
        if not aid or aid in posted:
            continue
        pub = article_pub_dt(art)
        age = open_hours(pub) if pub else None
        if age is None or age > AUTO_MAX_AGE_H:
            continue          # undated / old (in OPEN hours): never auto-posted
        if store.failed_count("article", aid) >= MAX_POST_ATTEMPTS:
            continue          # gave up on this one; don't burn a slot on it
        todo.append((age, art))
    todo.sort(key=lambda t: -t[0])            # oldest first, newest last
    return [art for _, art in todo][:AUTO_MAX_PER_RUN]


def auto(token, items):
    print(f"state backend: {store.backend()}")
    todo = pending(items)
    if not todo:
        print("no new article to post")
    elif not token:
        print(f"FB_PAGE_TOKEN not set - {len(todo)} article(s) would be posted, skipping")
        return 0
    for art in todo:
        aid = str(art.get("article_id", "")).strip()
        # CLAIM BEFORE POSTING. This one line is the duplicate fix: the claim is
        # an INSERT on PRIMARY KEY (kind, ref_id), so a concurrent run loses
        # here instead of posting the same article a second time - which is what
        # happened to article 422 on 2026-09-07. The claim is held through the
        # waits below, because that gap is exactly where the race used to live.
        if not store.claim("article", aid, title=art.get("title")):
            print(f"article {aid}: already posted, or claimed by another run - skipping")
            continue
        link = article_link(art)
        if not wait_live(link):
            store.release("article", aid)
            print(f"article {aid}: page not live yet - deferred to the next run")
            continue
        ok, og = scrape_until_ok(token, link)
        if not ok:
            store.release("article", aid)
            print(f"article {aid}: Facebook still sees the 404 page - deferred to the next run")
            continue
        if not try_post(token, art, og_verified=True):
            # try_post already counted the failure; drop the claim so a later
            # run may retry, up to MAX_POST_ATTEMPTS
            store.release("article", aid)
    if token:
        heal_previews(token)
    return 0


def main() -> int:
    token = os.environ.get("FB_PAGE_TOKEN", "").strip()
    items = load_articles()
    if not items:
        print("no articles - skipping")
        return 0
    if "--pending" in sys.argv[1:]:
        # how many articles WOULD be posted - lets publish.yml dispatch the
        # posting workflow only when there is something to do. The backend goes
        # to stderr so stdout stays a bare number the workflow can read, while
        # the log still says which store answered.
        print(f"store backend: {store.backend()}", file=sys.stderr)
        if not window_open():
            print(f"posting window {POST_WINDOW[0]:02d}:00-{POST_WINDOW[1]:02d}:00 Cairo is closed "
                  f"(now {_now().astimezone(CAIRO):%H:%M}) - nothing to dispatch", file=sys.stderr)
            print(0)
            return 0
        print(len(pending(items)))
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
