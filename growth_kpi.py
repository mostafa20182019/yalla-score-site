#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The weekly growth numbers (growth plan week 5, 2026-10-08) - the automatic
half of the Monday read-out. Appends one row to data/growth_kpi.json:

  followers / fans        Facebook page (Graph: me?fields=followers_count,fan_count)
  posts_7d                what we posted in the last 7 days, by kind
                          (article photo/link - the A/B - pred, h2h, goal, xi, card)
  articles_7d             articles published in the last 7 days
  telegram                channel subscribers (Bot API getChatMemberCount)
  push_subs               web-push subscriptions in D1

The manual half (Cloudflare visitors, GSC clicks/impressions/indexed, post
reach per variant) stays in matches-guide/GROWTH_LOG.md: those need a
browser session we do not hold. Everything here fails soft - a missing token
leaves its cell null and the row still lands.

    python growth_kpi.py            # append the row (needs the tokens)
    python growth_kpi.py --dry      # print the row, write nothing
"""
import datetime
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import store                                          # noqa: E402

OUT = os.path.join(HERE, "data", "growth_kpi.json")
GRAPH = "https://graph.facebook.com/v23.0"
KINDS = ("article", "pred", "h2h", "goal", "xi", "card", "reel")
AB_START = 1791504000          # 2026-10-08T00:00Z - the photo-vs-link A/B began (fb_post.PHOTO_AB)


def _get(url, timeout=30):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "yallascore-kpi"}), timeout=timeout) as r:
        return json.load(r)


def facebook(token):
    if not token:
        return {"followers": None, "fans": None}
    try:
        j = _get(f"{GRAPH}/me?fields=followers_count,fan_count&access_token={urllib.parse.quote(token)}")
        return {"followers": j.get("followers_count"), "fans": j.get("fan_count")}
    except Exception as e:                            # noqa: BLE001
        print(f"facebook: {e}")
        return {"followers": None, "fans": None}


def telegram(bot, chat):
    if not bot or not chat:
        return None
    try:
        j = _get(f"https://api.telegram.org/bot{bot}/getChatMemberCount?chat_id={urllib.parse.quote(chat)}")
        return j.get("result") if j.get("ok") else None
    except Exception as e:                            # noqa: BLE001
        print(f"telegram: {e}")
        return None


def push_subs():
    try:
        rows = store.sql("SELECT COUNT(*) AS n FROM push_subs")
        return int(rows[0]["n"]) if rows else 0
    except Exception as e:                            # noqa: BLE001
        print(f"push_subs: {e}")
        return None


def posts_7d(now=None):
    import fb_post as fp
    since = (now or time.time()) - 7 * 86400
    out = {}
    for kind in KINDS:
        try:
            rows = store.posted_since(kind, since)
        except Exception:                             # noqa: BLE001
            rows = []
        if kind == "article":
            # the A/B split counts only posts made SINCE the A/B began: before
            # 2026-10-08 every article was a link post whatever its id's parity
            by = {"photo": 0, "link": 0}
            for r in rows:
                if r["posted_at"] >= AB_START:
                    by[fp.variant({"article_id": r["ref_id"]})] += 1
            out["article"] = len(rows)
            out["article_photo"], out["article_link"] = by["photo"], by["link"]
        else:
            out[kind] = len(rows)
    return out


def articles_7d(now=None):
    import fb_post as fp
    since = (now or time.time()) - 7 * 86400
    n = 0
    for a in fp.load_articles():
        ts = (a.get("pub_ts") or "").strip()
        try:
            t = datetime.datetime.fromisoformat(ts)
            if t.tzinfo is None:
                t = t.replace(tzinfo=datetime.timezone.utc)
            if t.timestamp() >= since:
                n += 1
        except ValueError:
            pass
    return n


def row(now=None):
    now = now or time.time()
    fb = facebook(os.environ.get("FB_PAGE_TOKEN", "").strip())
    return {
        "date": datetime.datetime.fromtimestamp(now, datetime.timezone.utc).strftime("%Y-%m-%d"),
        "followers": fb["followers"], "fans": fb["fans"],
        "telegram": telegram(os.environ.get("TG_BOT_TOKEN", "").strip(), os.environ.get("TG_CHAT_ID", "").strip()),
        "push_subs": push_subs(),
        "articles_7d": articles_7d(now),
        "posts_7d": posts_7d(now),
    }


def append(r):
    try:
        with open(OUT, encoding="utf-8") as f:
            rows = json.load(f)
    except (OSError, ValueError):
        rows = []
    rows = [x for x in rows if x.get("date") != r["date"]] + [r]      # one row per day, the latest wins
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return len(rows)


def summary(r):
    p = r["posts_7d"]
    return (f"| {r['date']} | {r['followers']} | {r['telegram']} | {r['push_subs']} | {r['articles_7d']} | "
            f"{p.get('article_photo')} / {p.get('article_link')} | {p.get('pred')} | {p.get('h2h')} | "
            f"{p.get('goal')} | {p.get('xi')} | {p.get('card')} |")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    r = row()
    print(json.dumps(r, ensure_ascii=False, indent=1))
    if "--dry" in sys.argv[1:]:
        return 0
    n = append(r)
    print(f"growth_kpi.json: {n} rows")
    s = os.environ.get("GITHUB_STEP_SUMMARY")
    if s:
        with open(s, "a", encoding="utf-8") as fh:
            fh.write("### Growth KPI\n\n| date | followers | telegram | push | articles 7d | posts photo/link | pred | h2h | goal | xi | cards |\n"
                     "|---|---|---|---|---|---|---|---|---|---|---|\n" + summary(r) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
