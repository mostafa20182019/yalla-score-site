# -*- coding: utf-8 -*-
"""Post new articles to the Yalla Score Telegram channel.

    python tg_post.py --auto        # what publish.yml runs, after Deploy
    python tg_post.py --dry         # show what would be sent, send nothing

WHY (2026-09-20): Search Console says 7 of our pages are indexed and 732 are
«Discovered – currently not indexed», so search sends nobody, and Facebook is
the only channel we have — one we do not own and whose reach we do not set. A
Telegram channel is an owned channel, it is where Egyptian football readers
already are, and it costs nothing.

It deliberately reuses Facebook's machinery rather than inventing a second one:

  * CLAIM-THEN-POST through store.py with kind="tg". The INSERT is the lock, so
    two overlapping publish runs cannot both post the same article — the bug
    that double-posted article 422 to Facebook on 2026-09-07. A claim with no
    post id is released on any failure and expires after store.CLAIM_TTL_SEC.
  * NEVER POST BEFORE THE PAGE IS LIVE. Facebook cached a 404 preview twice
    (articles 358 and 364) because the post went out before Cloudflare had the
    page on every edge. Telegram builds its preview the same way, so the URL is
    checked first and the post is DEFERRED to the next run if it is not live
    yet — a deferred post costs 15 minutes, a broken preview is forever.
  * THE SAME CONDENSED TEXT as Facebook (`fb_post` on the article), so the two
    channels read alike and there is one thing to edit, not two.

Fails closed and quiet: with no TG_BOT_TOKEN / TG_CHAT_ID it prints what it
would have posted and exits 0, exactly like fb_post.py without its token.

Setup (the user does this once, the tokens are secrets I never see):
  1. Telegram → @BotFather → /newbot → copy the token.
  2. Create the channel, add the bot as an ADMIN with "Post messages".
  3. Channel id: @yallascore for a public channel, or the numeric -100… id.
  4. GitHub → Settings → Secrets → Actions: TG_BOT_TOKEN and TG_CHAT_ID.
"""
import argparse
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import fb_post as FB          # noqa: E402  - article loading, link, liveness, age
import store                  # noqa: E402

KIND = "tg"                   # its own dedup namespace next to article/card
API = "https://api.telegram.org/bot{token}/{method}"
CAPTION_MAX = 1024            # Telegram's limit for a photo caption
TEXT_MAX = 4096
MAX_PER_RUN = 3
MAX_AGE_H = 12                # a channel tolerates a slightly older piece than a feed


def token():
    return (os.environ.get("TG_BOT_TOKEN") or "").strip()


def chat():
    return (os.environ.get("TG_CHAT_ID") or "").strip()


def clean(text):
    """Article summaries carry HTML; Telegram's parser accepts a small subset."""
    return html.escape(re.sub(r"<[^>]+>", " ", text or "")).strip()


def strip_tail(body):
    """`fb_post` is a finished Facebook post: prose, then a bare URL, then a
    «التفاصيل … 👇» line, then hashtags. Telegram gets the prose and the tags;
    the URL comes back once, as a proper anchor, in the canonical form (the
    stored text still carries some /a/<id>.html links from before the
    extensionless move)."""
    keep, tags = [], ""
    for line in (body or "").splitlines():
        t = line.strip()
        if not t:
            keep.append("")
            continue
        if t.startswith("#"):                       # the writer's hashtag line
            tags = t
            continue
        if re.fullmatch(r"https?://\S+", t):        # the bare link
            continue
        if t.endswith("\U0001F447") or "على الموقع" in t and len(t) < 60:
            continue                                 # «التفاصيل الكاملة … 👇»
        keep.append(t)
    return "\n".join(keep).strip(), tags


def strip_title(body, title):
    """The condensed `fb_post` text starts WITH the title (a Facebook post has
    no separate headline). Telegram bolds the title on its own line, so the
    first line has to go or every post says the same thing twice."""
    lines = (body or "").splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and _same(lines[0], title):
        lines.pop(0)
    return "\n".join(lines).strip()


def _same(a, b):
    """Same sentence give or take punctuation and spacing."""
    norm = lambda s: re.sub(r"[\s.:\-–—،؛]+", "", s or "")     # noqa: E731
    a, b = norm(a), norm(b)
    return bool(a) and bool(b) and (a == b or a.startswith(b[:40]) or b.startswith(a[:40]))



def message(art):
    """<b>title</b> + the condensed text + link + tags, within the caption limit."""
    title = clean(art.get("title"))
    body, tags = strip_tail(strip_title(clean(art.get("fb_post") or art.get("summary")), title))
    link = FB.article_link(art)
    head = f"<b>{title}</b>"
    tail = f'\n\n<a href="{html.escape(link)}">اقرأ التفاصيل على يلا سكور</a>'
    if tags:
        tail += f"\n{tags}"
    room = CAPTION_MAX - len(head) - len(tail) - 4
    if room > 80 and body:
        if len(body) > room:
            body = body[:room - 1].rsplit(" ", 1)[0] + "…"
        return f"{head}\n\n{body}{tail}"
    return head + tail


def photo_url(art):
    u = (art.get("image_url") or "").strip()
    return u if u.startswith("http") and not u.endswith(".svg") else ""


def call(method, params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(API.format(token=token(), method=method), data=data,
                                 headers={"User-Agent": "yalla-score-tg/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def send(art):
    """Returns the Telegram message id, or None. Photo when we have one."""
    text, img = message(art), photo_url(art)
    try:
        if img:
            out = call("sendPhoto", {"chat_id": chat(), "photo": img,
                                     "caption": text, "parse_mode": "HTML"})
        else:
            out = call("sendMessage", {"chat_id": chat(), "text": text,
                                       "parse_mode": "HTML",
                                       "disable_web_page_preview": "false"})
    except Exception as e:                                   # noqa: BLE001
        print(f"  telegram refused: {e}")
        return None
    if not out.get("ok"):
        print(f"  telegram said no: {str(out)[:200]}")
        return None
    return str((out.get("result") or {}).get("message_id") or "")


def pending(items):
    """Not yet on the channel, young enough, oldest first, capped."""
    posted = store.posted_ids(KIND)
    todo = []
    for art in items:
        aid = str(art.get("article_id", "")).strip()
        if not aid or aid in posted:
            continue
        age = FB.article_age_hours(art)
        if age is None or age > MAX_AGE_H:
            continue
        todo.append((age, art))
    todo.sort(key=lambda t: -t[0])
    return [a for _, a in todo][:MAX_PER_RUN]


def auto(dry=False):
    items = FB.load_articles()
    todo = pending(items)
    if not todo:
        print("telegram: nothing new to post")
        return 0
    if dry or not (token() and chat()):
        why = "dry run" if dry else "TG_BOT_TOKEN / TG_CHAT_ID not set"
        print(f"telegram: {len(todo)} article(s) would be posted ({why})")
        for art in todo:
            print("  ---")
            print("  " + message(art).replace("\n", "\n  ")[:400])
        return 0
    print(f"telegram: {len(todo)} to post (state backend: {store.backend()})")
    for art in todo:
        aid = str(art.get("article_id", "")).strip()
        link = FB.article_link(art)
        # the lock comes first: whoever wins the INSERT is the only one posting
        if not store.claim(KIND, aid, art.get("title")):
            print(f"  {aid}: another run holds it (or it is already posted)")
            continue
        if not FB.wait_live(link):
            # the page is not on every edge yet - defer rather than ship a
            # preview of the 404 page, and let the claim go so the next run
            # can try again
            print(f"  {aid}: page not live yet, deferring")
            store.release(KIND, aid)
            continue
        mid = send(art)
        if not mid:
            store.release(KIND, aid)
            continue
        store.record_post(KIND, aid, mid, title=art.get("title"))
        print(f"  {aid}: posted as message {mid} — {art.get('title', '')[:60]}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    if not (args.auto or args.dry):
        ap.print_help()
        return 0
    return auto(dry=args.dry)


if __name__ == "__main__":
    sys.exit(main())
