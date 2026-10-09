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
# the Yalla Score page (2026-10-09): every post id on record starts with it.
# --whoami refuses a token that is not THIS page's - a page token of another
# page the same user manages posts green runs to the wrong page.
PAGE_ID = "104238901487012"
GRAPH_FEED = f"{GRAPH}/me/feed"
GRAPH_PHOTOS = f"{GRAPH}/me/photos"
MEDIA = os.path.join(HERE, "media")
# Growth plan week 1 (2026-10-08): Facebook reaches further with a PHOTO post
# than with a link post, so an article now goes out as its own image (the
# matchup card or the article photo) with the text as the caption and the
# link inside the text. A/B for two weeks: EVEN article ids = photo, ODD = the
# old link post; the variant is a function of the id, so Insights can be
# read per variant without storing anything. Set False to go back to links.
PHOTO_AB = True
AUTO_MAX_AGE_H = 6       # --auto never posts an article older than this (10 articles/day: 12h re-posted a half-day backlog on 2026-09-03)
AUTO_MAX_PER_RUN = 3     # --auto posts at most this many per run (staggers a backlog)
# POSTING WINDOW - OFF (2026-09-12, second decision of the day). A window of
# Cairo hours [open, close) was added in the morning to post only 13:00-01:00
# ("fewer runs"); by the afternoon the user restated the rule the page should
# follow: an article that lands on the site lands on Facebook - and the two
# morning slots (09:00, 11:00) were waiting up to four hours. None = post at
# any hour. The machinery (window_open / open_hours) stays for the tests and
# for the day someone wants a window again: set e.g. (13, 1). Runs are not
# affected either way - publish.yml dispatches the poster only when
# `--pending` finds an article.
POST_WINDOW = None
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
    # extensionless = the canonical URL form (build_site._clean_urls).
    # A match preview/report lives inside its match page since 2026-09-16
    # (build_site.article_href) - posting /a/<id> would share a redirect, and
    # Facebook would cache the redirect target's card under the wrong url.
    if art.get("kind") in ("preview", "report") and art.get("match_id"):
        return f"{SITE}/m/{str(art['match_id']).strip()}"
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


def variant(art):
    """"photo" or "link" for this article - by id parity while the A/B runs."""
    if not PHOTO_AB:
        return "link"
    try:
        return "photo" if int(str(art.get("article_id", "")).strip()) % 2 == 0 else "link"
    except ValueError:
        return "link"


def image_bytes(art):
    """The article's image as bytes: media/<name> from the checkout first, else
    downloaded; None for our SVG placeholders (Facebook refuses SVG) or when
    nothing can be read - the caller then falls back to a link post."""
    url = (art.get("image_url") or "").strip()
    if not url or url.lower().endswith(".svg"):
        return None
    name = os.path.basename(urllib.parse.urlparse(url).path)
    local = os.path.join(MEDIA, name)
    try:
        if name and os.path.isfile(local):
            with open(local, "rb") as f:
                return f.read()
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "yallascore-fb"}),
                                    timeout=30) as r:
            data = r.read()
        return data if len(data) > 1000 else None
    except Exception as e:                              # noqa: BLE001
        print(f"  image unavailable ({e}) - link post instead")
        return None


def _multipart(fields, files):
    boundary = "----yallascore" + str(int(time.time() * 1000))
    out = []
    for k, v in fields.items():
        out += [f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n".encode("utf-8"),
                str(v).encode("utf-8"), b"\r\n"]
    for k, (fn, data, ctype) in files.items():
        out += [f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fn}\"\r\n"
                f"Content-Type: {ctype}\r\n\r\n".encode("utf-8"), data, b"\r\n"]
    out.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(out), f"multipart/form-data; boundary={boundary}"


def post_photo(token, img, caption):
    """Upload the image as a page photo with the post text as its caption.
    Returns the Graph post id, raises on failure."""
    body, ctype = _multipart({"caption": caption, "access_token": token},
                             {"source": ("article.jpg", img, "image/jpeg")})
    req = urllib.request.Request(GRAPH_PHOTOS, data=body,
                                 headers={"Content-Type": ctype, "Content-Length": str(len(body))})
    with urllib.request.urlopen(req, timeout=60) as r:
        resp = json.load(r)
    return resp.get("post_id") or resp.get("id")


def post_article(token, art):
    """Publish the post (page already verified live by the caller): a PHOTO
    post for the A/B's photo variant when the image can be read, else the
    classic link post."""
    link = article_link(art)
    title = (art.get("title") or "").strip()
    summary = (art.get("summary") or "").strip()
    # the article task writes a crafted fb_post (same text the user copies
    # from /fb.html) - prefer it; fall back to the plain generated format
    message = (art.get("fb_post") or "").strip() or f"⚽ {title}\n\n{summary}\n\n\U0001f449 {link}"
    if variant(art) == "photo":
        img = image_bytes(art)
        if img:
            if link not in message:
                message += f"\n{link}"          # a photo post has no link card: the URL lives in the text
            print(f"  variant=photo ({len(img) // 1024} KB)")
            return post_photo(token, img, message)
    print("  variant=link")
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
    by_id = {str(a.get("article_id")): a for a in load_articles()}
    for rec in store.unconfirmed("article", HEAL_WINDOW_H):
        aid = rec["ref_id"]
        if "seeded" in str(rec.get("post_id") or ""):
            continue
        link = article_link(by_id.get(str(aid)) or {"article_id": aid})
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
        try:                                        # the weekly H2H card (growth plan week 4)
            h2h_post(token, "auto")
        except Exception as e:                      # noqa: BLE001 - never fail the article run over it
            print(f"h2h auto failed: {e}")
    return 0


def post_exists(token, post_id):
    """True / False from the Graph API; None when it could not tell."""
    url = f"{GRAPH}/{post_id}?" + urllib.parse.urlencode({"fields": "id", "access_token": token})
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return bool(json.load(r).get("id"))
    except urllib.error.HTTPError as e:
        return False if e.code in (400, 404) else None     # 400 = "does not exist" on Graph
    except Exception:  # noqa: BLE001
        return None


def repost(token, aid):
    """Post ONE article again, by hand (2026-10-08: the derby analysis's post
    kept Facebook's cached preview of the replaced photo, so the user deleted
    it). No age limit - the person asked for this article - but it refuses
    while the recorded post still exists on the page: a repost must never
    become a duplicate."""
    aid = str(aid).strip()
    art = next((a for a in load_articles() if str(a.get("article_id", "")).strip() == aid), None)
    if not art:
        print(f"repost: article {aid} not found"); return 1
    if not token:
        print("repost: FB_PAGE_TOKEN not set"); return 1
    rec = store.get_post("article", aid) or {}
    old = rec.get("post_id")
    if old and not str(old).startswith("seeded"):
        alive = post_exists(token, old)
        if alive is not False:
            print(f"repost: article {aid}'s post {old} "
                  f"{'is still on the page - delete it first' if alive else 'could not be checked'}"
                  " - nothing posted")
            return 1
        print(f"repost: old post {old} is gone from the page")
    if not store.reopen("article", aid):
        print(f"repost: article {aid} is claimed by another run - nothing posted"); return 1
    link = article_link(art)
    ok, _ = scrape_until_ok(token, link)        # a fresh scrape = the CURRENT og:image
    if not ok:
        store.release("article", aid)
        print(f"repost: Facebook still sees the 404 page for {link} - nothing posted"); return 1
    if try_post(token, art, og_verified=True):
        return 0
    store.release("article", aid)
    return 1


# ---------------------------------------------------------------- prediction post
# Growth plan 2026-10-08, week 0: an ENGAGEMENT post before a big match - our
# matchup card as the photo (photo posts reach further than link posts), the
# model's numbers only (user rule: never the betting disclaimer in a post),
# and a question that invites comments. Dispatched by hand from the Facebook
# Post workflow (`prediction` input) until the slots automate it.

def _tag(name):
    return "#" + "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in (name or "").replace(" ", "_")).strip("_")


def prediction_text(m, pr, tv=None):
    """The post text for match `m` (matches.json shape) and its prediction
    block (match_brief.prediction_block). Numbers only, no disclaimer."""
    import matchup_card as MC
    from site_lib.names import ar_team, comp_label
    h, a = ar_team(m.get("home")), ar_team(m.get("away"))
    when = MC.when_ar(m.get("kickoff"), m.get("koff_time"))
    comp = comp_label(m.get("competition"))
    top = (pr.get("likely_scores") or [{}])[0]
    lines = [f"توقع يلا سكور قبل المباراة: {h} × {a}",
             "⚽ " + " · ".join(x for x in (when, comp, f"على {tv}" if tv else "") if x),
             f"🤖 النموذج: {h} {pr['home_win']} · تعادل {pr['draw']} · {a} {pr['away_win']}"]
    extra = []
    if top.get("score_home_away"):
        extra.append(f"النتيجة الأرجح {top['score_home_away']} ({top['prob']})")
    if pr.get("over_2_5"):
        extra.append(f"أكثر من 2.5 هدف {pr['over_2_5']}")
    if extra:
        lines.append("🎯 " + " · ".join(extra))
    rec = (pr.get("record") or {}).get("all")
    if rec:
        lines.append(f"📊 سجل النموذج هذا الموسم: أصاب {rec['hits']} من {rec['scored']} توقعًا")
    lines += ["توقعك إيه؟ اكتبه في التعليقات 👇",
              f"التوقع الكامل بالأرقام: {SITE}/m/{m.get('match_id')}",
              " ".join(("#يلا_سكور", _tag(h), _tag(a)))]
    return "\n".join(lines)


def prediction_post(token, mid, dry=False):
    """Post the prediction card for one match. 0 = posted or dry-run, 1 = nothing to post."""
    import tempfile
    import match_brief as MB
    import matchup_card as MC
    import fb_cards
    from site_lib.competitions import COMP_TV
    d = MB.load_all()
    m = next((x for x in d["matches"] if str(x.get("match_id")) == str(mid)), None)
    if not m:
        print(f"prediction: match {mid} is not in matches.json")
        return 1
    if (m.get("status") or "").upper() == "FINISHED":
        print(f"prediction: match {mid} is already finished - nothing to predict")
        return 1
    pr = MB.prediction_block(d, m)
    if not pr:
        print(f"prediction: the model has nothing for {m.get('competition')}")
        return 1
    text = prediction_text(m, pr, tv=m.get("channel") or COMP_TV.get(m.get("competition")))
    out = os.path.join(tempfile.gettempdir(), f"pred-{mid}.jpg")
    venue, feed = "", None
    try:
        gid = MB.resolve_s365_game(m)
        hb = MB.h2h_block(gid) if gid else {}
        venue, feed = hb.get("venue") or "", hb.get("colors")
    except Exception:                                   # noqa: BLE001 - offline: names + our kits
        pass
    MC.for_match(m, out, venue=venue, top_label="توقع يلا سكور", feed=feed)
    print(text)
    print(f"[card: {out}]")
    if dry:
        return 0
    if not token:
        print("FB_PAGE_TOKEN not set - skipping")
        return 0
    if not store.claim("pred", mid, title=text.split("\n", 1)[0]):
        print(f"prediction {mid}: already posted, or claimed by another run - skipping")
        return 0
    try:
        with open(out, "rb") as f:
            pid = fb_cards.post_photo(token, f.read(), text)
        store.record_post("pred", mid, pid, title=text.split("\n", 1)[0])
        print(f"posted prediction {mid} to Facebook: post id {pid}")
    except Exception as e:                              # noqa: BLE001
        store.release("pred", mid)
        print(f"prediction post FAILED ({mid}): {e}")
        return 1
    return 0


# ---------------------------------------------------------------- the weekly H2H card
# Growth plan week 4 (2026-10-08): one head-to-head infographic a week for the
# biggest match coming up (h2h_card.py), posted as a photo. `auto` picks the
# match and keeps to one card per H2H_EVERY_DAYS; a match id posts that match
# (once - the fb_posted lock, kind "h2h").
H2H_EVERY_DAYS = 6
H2H_WINDOW_H = (20.0, 96.0)       # kick-off 20h..4 days away: close enough to matter, early enough to be read


def h2h_text(m, r, when=""):
    from site_lib.names import ar_team, comp_label
    h, a = ar_team(m.get("home")), ar_team(m.get("away"))
    lines = [f"📊 آخر {r['n']} مواجهات بين {h} و{a}" + (f" قبل لقاء {when}" if when else ""),
             f"🏆 {h} فاز {r['wins'][h]} · تعادل {r['draws']} · {a} فاز {r['wins'][a]}",
             f"⚽ الأهداف: {h} {r['goals'][h]} · {a} {r['goals'][a]}"
             + (f" (في {r['played']} مباريات لُعبت داخل الملعب)" if r.get("played") and r["played"] < r["n"] else "")]
    if r.get("finals"):
        lines.append(f"🏟️ {r['finals']}")
    for name in (h, a):
        if r["last"].get(name):
            import h2h_card as HC
            lines.append(f"🗓️ آخر فوز لـ{name}: {HC.ar_date(r['last'][name])}")
    lines += [f"{comp_label(m.get('competition'))} · التوقع والتحليل: {SITE}/m/{m.get('match_id')}",
              " ".join(("#يلا_سكور", _tag(h), _tag(a)))]
    return "\n".join(lines)


def h2h_pick(d, now=None):
    """The biggest upcoming match: both sides featured, kick-off inside
    H2H_WINDOW_H, Egyptian league first, then the soonest. None when nothing fits."""
    import match_brief as MB
    now = now or _now()
    cands = []
    for m in d["matches"]:
        if (m.get("status") or "").upper() != "UPCOMING" or not m.get("match_id"):
            continue
        ko = MB._kick(m)
        if not ko:
            continue
        hrs = (ko - now).total_seconds() / 3600
        if not (H2H_WINDOW_H[0] <= hrs <= H2H_WINDOW_H[1]):
            continue
        if MB.featured_sides(m) < 2:
            continue
        cands.append((0 if m.get("competition") == "Egyptian Premier League" else 1, hrs, m))
    cands.sort(key=lambda x: (x[0], x[1]))
    return cands[0][2] if cands else None


def h2h_post(token, which, dry=False):
    """0 = posted / dry / nothing due, 1 = asked for a match that cannot be done."""
    import tempfile
    import match_brief as MB
    import matchup_card as MC
    import h2h_card as HC
    d = MB.load_all()
    if which == "auto":
        recent = store.posted_since("h2h", time.time() - H2H_EVERY_DAYS * 86400)
        if recent:
            print(f"h2h: a card went out {((time.time() - recent[0]['posted_at']) / 86400):.1f} days ago - not yet")
            return 0
        m = h2h_pick(d)
        if not m:
            print("h2h: no big match in the window")
            return 0
    else:
        m = next((x for x in d["matches"] if str(x.get("match_id")) == str(which)), None)
        if not m:
            print(f"h2h: match {which} is not in matches.json")
            return 1
    ref = str(m["match_id"])
    if store.get_post("h2h", ref):
        print(f"h2h: match {ref} already has its card")
        return 0
    out = os.path.join(tempfile.gettempdir(), f"h2h-{ref}.jpg")
    r = HC.for_match(m, out)
    if not r:
        print(f"h2h: too few meetings on record for {ref} (or the feed is unreachable)")
        return 0 if which == "auto" else 1
    text = h2h_text(m, r, MC.when_ar(m.get("kickoff"), m.get("koff_time")))
    print(text)
    print(f"[card: {out}]")
    if dry:
        return 0
    if not token:
        print("FB_PAGE_TOKEN not set - skipping")
        return 0
    if not store.claim("h2h", ref, title=text.split("\n", 1)[0]):
        print(f"h2h {ref}: claimed by another run - skipping")
        return 0
    try:
        with open(out, "rb") as f:
            pid = post_photo(token, f.read(), text)
        store.record_post("h2h", ref, pid, title=text.split("\n", 1)[0])
        print(f"posted h2h card {ref} to Facebook: post id {pid}")
    except Exception as e:                              # noqa: BLE001
        store.release("h2h", ref)
        print(f"h2h post FAILED ({ref}): {e}")
        return 1
    return 0


def whoami(token):
    """Print who the token is and refuse anything but the Yalla Score page.
    0 = the page token; 1 = no token, a user token, another page, or a dead
    token (HTTP 190). Run first in the workflow so a wrong secret fails the
    job loudly instead of posting to the wrong page for a day."""
    if not token:
        print("whoami: FB_PAGE_TOKEN not set")
        return 1
    try:
        url = f"{GRAPH}/me?fields=id,name&access_token={urllib.parse.quote(token)}"
        with urllib.request.urlopen(urllib.request.Request(url), timeout=30) as r:
            me = json.load(r)
    except urllib.error.HTTPError as e:
        print(f"whoami: Facebook refused the token: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:200]}")
        return 1
    except Exception as e:                                # noqa: BLE001
        print(f"whoami: could not reach Facebook ({e})")
        return 1
    who = f"{me.get('name')!r} (id {me.get('id')})"
    if str(me.get("id")) != PAGE_ID:
        print(f"whoami: the token belongs to {who}, NOT the Yalla Score page (id {PAGE_ID}) - "
              "paste the page's own access_token from me/accounts")
        return 1
    print(f"whoami: page token OK - {who}")
    return 0


def main() -> int:
    token = os.environ.get("FB_PAGE_TOKEN", "").strip()
    items = load_articles()
    if not items and not any(f in sys.argv[1:] for f in ("--prediction", "--h2h", "--whoami")):
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
    if "--whoami" in sys.argv[1:]:
        return whoami(token)
    if "--h2h" in sys.argv[1:]:
        i = sys.argv.index("--h2h")
        return h2h_post(token, sys.argv[i + 1] if i + 1 < len(sys.argv) else "auto",
                        dry="--dry" in sys.argv[1:])
    if "--prediction" in sys.argv[1:]:
        i = sys.argv.index("--prediction")
        return prediction_post(token, sys.argv[i + 1] if i + 1 < len(sys.argv) else "",
                               dry="--dry" in sys.argv[1:])
    if "--repost" in sys.argv[1:]:
        i = sys.argv.index("--repost")
        return repost(token, sys.argv[i + 1] if i + 1 < len(sys.argv) else "")

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
