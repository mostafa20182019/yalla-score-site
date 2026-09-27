# -*- coding: utf-8 -*-
"""Web push: one notification to every subscribed browser when a new article
is live.

    python push_send.py --auto       # what publish.yml runs, after Deploy
    python push_send.py --dry        # what would be sent now, and why / why not
    python push_send.py --keygen     # make the VAPID key pair (once)

WHY (2026-09-27, the user's ask «زى مواقع فى الجول ويلا كورة»): a reader who
taps the bell gets the news the moment it is published, from a channel we own
- like Telegram, but without the reader having to open an app.

THE RULES (agreed with the user the same day - also stated on /privacy):
  1. NEW ARTICLES ONLY. An upgraded archive piece (upgraded_ts) is not news, and
     «الجولة بالأرقام» (a source note "round:…") is a data piece, not a story.
  2. QUIET HOURS 01:00-08:00 Cairo: nothing is sent. Age is counted in SENDABLE
     hours only, so a story published at 03:00 is still "fresh" at 08:00 and
     goes out then - the same trick fb_post.open_hours() uses.
  3. AT MOST DAILY_CAP a day (Cairo day), AT LEAST MIN_GAP_MIN apart, ONE per
     run, and the last RESERVED slots of the day are kept for Egyptian football
     and the 11 curated clubs: any other story may only use the first
     DAILY_CAP - RESERVED. When several stories wait, the Egyptian/curated one
     goes first, then the newest.
  A reader who gets eleven buzzes a day switches the bell off - and Chrome
  quietly demotes a site whose notifications people block.

The same machinery as Telegram and Facebook, not a new one:
  * CLAIM-THEN-POST (store.py, kind="push"): two overlapping publish runs
    cannot both notify for one article - the INSERT is the lock.
  * NEVER BEFORE THE PAGE IS LIVE (fb_post.wait_live): a tap that opens our 404
    page is worse than a notification 15 minutes later.

Sending happens HERE, on the GitHub runner, not in the Worker: every
subscriber is one outbound HTTPS request, and a Worker on the free plan may
make only a few dozen per invocation. pywebpush encrypts the payload to each
browser's keys (RFC 8291) and signs a VAPID token (RFC 8292) with our private
key; a push service answering 404/410 means the browser unsubscribed, and that
endpoint is deleted on the spot.

Fails closed and quiet like tg_post.py: no VAPID_PRIVATE_KEY, no public key in
site_lib/config.py, or no D1 -> it prints why and exits 0. A private key that
does NOT belong to the public key the pages hand out exits 1 (every send would
be refused with 403, and that must be visible).

Setup (the user does this once - the private key is a secret I never see):
  1. python push_send.py --keygen
  2. GitHub → Settings → Secrets → Actions → VAPID_PRIVATE_KEY = the private key
  3. the PUBLIC key goes into VAPID_PUBLIC_KEY in site_lib/config.py (public)
"""
import argparse
import base64
import concurrent.futures
import datetime
import json
import os
import re
import sys
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import fb_post as FB                                     # noqa: E402 - articles, link, liveness
import store                                             # noqa: E402
from site_lib import config as C                         # noqa: E402
from site_lib.clubs import TEAM_PAGES                    # noqa: E402
from site_lib.names import _egy_article                  # noqa: E402

KIND = "push"
CAIRO = ZoneInfo("Africa/Cairo")
QUIET = (1, 8)            # Cairo hours [start, end): nothing is sent
DAILY_CAP = 5
RESERVED = 2              # the last 2 of the day: Egyptian / curated-club stories only
MIN_GAP_MIN = 60
MAX_AGE_H = 3             # in SENDABLE hours (quiet hours do not age a story)
TTL_SEC = 6 * 3600        # a phone that is off for longer never gets a stale buzz
TOPIC = "yalla-news"      # an undelivered older notification is replaced, not stacked
CONTACT = "mailto:" + C.CONTACT_EMAIL
WORKERS = 16
PAYLOAD_MAX = 3000        # bytes of JSON; the encrypted record is capped at 4096
MAX_ATTEMPTS = 3          # like fb_post: a piece that never goes out must not block forever


# ---------------------------------------------------------------- the clock
def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def is_quiet(t):
    h = t.astimezone(CAIRO).hour
    return QUIET[0] <= h < QUIET[1]


def sendable_hours(since, now):
    """Hours between `since` and `now` that were outside the quiet hours."""
    if since >= now:
        return 0.0
    total, t = 0.0, since
    while t < now:
        step = min(now, (t + datetime.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0))
        if step <= t:
            step = min(now, t + datetime.timedelta(hours=1))
        if not is_quiet(t):
            total += (step - t).total_seconds() / 3600
        t = step
    return total


def cairo_midnight(now):
    c = now.astimezone(CAIRO)
    return c.replace(hour=0, minute=0, second=0, microsecond=0)


# ---------------------------------------------------------------- the rules
def excluded(art):
    """Why this article never gets a notification, or None."""
    if art.get("upgraded_ts"):
        return "upgraded archive piece"
    for s in art.get("sources") or []:
        if isinstance(s, dict) and str(s.get("note") or "").startswith("round:"):
            return "round-by-numbers data piece"
    if not (art.get("title") or "").strip():
        return "no title"
    return None


def priority(art):
    """2 = Egyptian football, 1 = one of the curated clubs, 0 = anything else.
    The same text tests the home page and the club pages use."""
    if _egy_article(art):
        return 2
    txt = (art.get("title") or "") + " " + (art.get("summary") or "")
    for tp in TEAM_PAGES:
        if any(t in txt for t in tp["news_tokens"]) and \
                not any(x in txt for x in tp.get("news_excl", [])):
            return 1
    return 0


def choose(items, now=None):
    """(article, why) - the one article to notify for on this run, or
    (None, reason). Reads the dedup store; writes nothing."""
    now = now or _now()
    if is_quiet(now):
        return None, "quiet hours (01:00-08:00 Cairo)"
    day0 = int(cairo_midnight(now).timestamp())
    recent = store.posted_since(KIND, min(day0, int(now.timestamp()) - MIN_GAP_MIN * 60))
    today = [r for r in recent if r["posted_at"] >= day0]
    if len(today) >= DAILY_CAP:
        return None, f"daily cap reached ({len(today)}/{DAILY_CAP})"
    if recent and now.timestamp() - recent[0]["posted_at"] < MIN_GAP_MIN * 60:
        mins = int((now.timestamp() - recent[0]["posted_at"]) // 60)
        return None, f"last notification {mins} min ago (gap {MIN_GAP_MIN})"
    done = store.posted_ids(KIND)
    best = None
    for art in items:
        aid = str(art.get("article_id", "")).strip()
        if not aid or aid in done or excluded(art):
            continue
        pub = FB.article_pub_dt(art)
        if pub is None or sendable_hours(pub, now) > MAX_AGE_H:
            continue
        pr = priority(art)
        if pr == 0 and len(today) >= DAILY_CAP - RESERVED:
            continue                      # the reserved slots are not for this story
        if store.failed_count(KIND, aid) >= MAX_ATTEMPTS:
            continue
        key = (pr, pub)
        if best is None or key > best[0]:
            best = (key, art)
    if best is None:
        return None, "no new article waiting"
    return best[1], f"priority {best[0][0]}, sent today {len(today)}/{DAILY_CAP}"


# ---------------------------------------------------------------- the payload
def _plain(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def _cut(text, n):
    return text if len(text) <= n else text[:n - 1].rsplit(" ", 1)[0] + "…"


def _image(art):
    u = (art.get("image_url") or "").strip()
    if not u.startswith("http") or u.lower().endswith(".svg"):
        return None
    try:                          # the 640px card copy when we have it - lighter on a phone
        from site_lib.shell import thumb_url
        u = thumb_url(u)
    except Exception:                                         # noqa: BLE001
        pass
    return u


def payload(art):
    """What sw.js shows: title, one line, where a tap goes. JSON, < PAYLOAD_MAX."""
    aid = str(art.get("article_id", "")).strip()
    d = {"title": _cut(_plain(art.get("title")), 100),
         "body": _cut(_plain(art.get("summary")), 150),
         "url": FB.article_link(art),
         "icon": "/assets/icon-192.png",
         "badge": "/assets/badge-96.png",
         "tag": f"a-{aid}"}
    img = _image(art)
    if img:
        d["image"] = img
    raw = json.dumps(d, ensure_ascii=False)
    while len(raw.encode("utf-8")) > PAYLOAD_MAX and d["body"]:
        d["body"] = _cut(d["body"], max(0, len(d["body"]) - 30))
        raw = json.dumps(d, ensure_ascii=False)
    return raw


# ---------------------------------------------------------------- keys
def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def keygen():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    k = ec.generate_private_key(ec.SECP256R1())
    priv = _b64(k.private_numbers().private_value.to_bytes(32, "big"))
    pub = _b64(k.public_key().public_bytes(serialization.Encoding.X962,
                                           serialization.PublicFormat.UncompressedPoint))
    return pub, priv


def public_of(private_b64):
    """The public key (base64url, uncompressed point) that belongs to a private one."""
    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid
    v = Vapid.from_string(private_key=private_b64)
    return _b64(v.public_key.public_bytes(serialization.Encoding.X962,
                                          serialization.PublicFormat.UncompressedPoint))


def private_key():
    return (os.environ.get("VAPID_PRIVATE_KEY") or "").strip()


# ---------------------------------------------------------------- subscribers
def load_subs():
    try:
        return store.sql("SELECT endpoint, p256dh, auth FROM push_subs", [])
    except Exception as e:                                    # noqa: BLE001
        if "no such table" in str(e):
            return []                     # nobody has tapped the bell yet
        raise


def drop_subs(endpoints):
    for ep in endpoints:
        try:
            store.sql("DELETE FROM push_subs WHERE endpoint = ?", [ep])
        except Exception as e:                                # noqa: BLE001
            print(f"  could not drop a dead endpoint: {e}")


def send_one(sub, data, key):
    """('ok'|'gone'|'fail', detail). pywebpush fills `aud` and `exp` INTO the
    claims dict it is given - one shared dict would carry the first push
    service's audience to every other one and get them all refused, so every
    call gets its own."""
    from pywebpush import WebPushException, webpush
    try:
        r = webpush(subscription_info={"endpoint": sub["endpoint"],
                                       "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                    data=data, vapid_private_key=key, vapid_claims={"sub": CONTACT},
                    ttl=TTL_SEC, headers={"Urgency": "normal", "Topic": TOPIC}, timeout=15)
        return "ok", r.status_code
    except WebPushException as e:
        code = getattr(e.response, "status_code", None)
        return ("gone" if code in (404, 410) else "fail"), code
    except Exception as e:                                    # noqa: BLE001
        return "fail", str(e)[:80]


def fan_out(subs, data, key, sender=None):
    """Send to everyone in parallel. Returns (ok, gone_endpoints, failures)."""
    sender = sender or send_one
    ok, gone, fails = 0, [], {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for sub, (res, detail) in zip(subs, ex.map(lambda s: sender(s, data, key), subs)):
            if res == "ok":
                ok += 1
            elif res == "gone":
                gone.append(sub["endpoint"])
            else:
                fails[str(detail)] = fails.get(str(detail), 0) + 1
    return ok, gone, fails


# ---------------------------------------------------------------- the run
def auto(dry=False, now=None, sender=None, live=None):
    key, site_key = private_key(), C.VAPID_PUBLIC_KEY
    if not site_key:
        print("push: VAPID_PUBLIC_KEY is empty in site_lib/config.py - the bell is dark, nothing to do")
        return 0
    if not dry and not key:
        print("push: VAPID_PRIVATE_KEY not set - push is off")
        return 0
    if key and public_of(key) != site_key:
        print("::error::push: VAPID_PRIVATE_KEY does not belong to VAPID_PUBLIC_KEY in "
              "site_lib/config.py - every push service would refuse it (403). Fix one of them.")
        return 1
    if store.backend() == "json":
        print("push: no D1 in this environment - the subscriptions live there, skipping")
        return 0
    art, why = choose(FB.load_articles(), now=now)
    if art is None:
        print(f"push: nothing to send - {why}")
        return 0
    aid = str(art.get("article_id")).strip()
    data = payload(art)
    subs = load_subs()
    print(f"push: article {aid} ({why}) -> {len(subs)} subscriber(s)")
    print("  " + data)
    if dry:
        return 0
    if not subs:
        print("push: no subscribers yet - nothing sent, nothing recorded")
        return 0
    if not store.claim(KIND, aid, art.get("title")):
        print(f"  {aid}: another run holds it (or it was already sent)")
        return 0
    link = FB.article_link(art)
    if not (live or FB.wait_live)(link):
        print(f"  {aid}: page not live yet - deferred to the next run")
        store.release(KIND, aid)
        return 0
    ok, gone, fails = fan_out(subs, data, key, sender)
    if gone:
        drop_subs(gone)
    print(f"  sent {ok}/{len(subs)}, dropped {len(gone)} dead endpoint(s)"
          + (f", failed {fails}" if fails else ""))
    if ok == 0 and fails:
        # nobody got it, so a retry cannot double-notify anyone
        store.release(KIND, aid)
        store.bump_failed(KIND, aid, json.dumps(fails)[:300])
        return 0
    store.record_post(KIND, aid, f"{ok}/{len(subs)}", title=art.get("title"))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--keygen", action="store_true")
    a = ap.parse_args()
    if a.keygen:
        pub, priv = keygen()
        print("PUBLIC key  (goes into VAPID_PUBLIC_KEY in site_lib/config.py - public):")
        print("  " + pub)
        print("PRIVATE key (goes into the GitHub secret VAPID_PRIVATE_KEY - never in the repo):")
        print("  " + priv)
        return 0
    if a.auto or a.dry:
        return auto(dry=a.dry)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
