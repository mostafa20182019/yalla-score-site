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

  site                    Cloudflare Web Analytics (visits, page views, referrers)
  fb_insights             the page's week: reach, post engagements, new follows
                          (Graph: me/insights - the token needs read_insights)
  ab_reach                the photo-vs-link A/B read-out: each article post's
                          reach since the A/B began, averaged per variant
                          (Graph: {post}/insights/post_impressions_unique)

A page token WITHOUT read_insights leaves fb_insights/ab_reach as
{"error": ...} and the step summary says so - re-issue the token with
pages_read_engagement + read_insights. GSC clicks/impressions stay manual.
Everything here fails soft - a missing token leaves its cell null and the
row still lands.

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
# the photo-vs-link A/B began on 2026-10-08 (fb_post.PHOTO_AB); computed, not typed -
# a hand-typed epoch was one day off on the first try
AB_START = datetime.datetime(2026, 10, 8, tzinfo=datetime.timezone.utc).timestamp()


def _get(url, timeout=30):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "yallascore-kpi"}), timeout=timeout) as r:
        return json.load(r)


def _post_json(url, body, headers, timeout=40):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"User-Agent": "yallascore-kpi", "Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


# Cloudflare Web Analytics (2026-10-18, user: «ابدأ بقياس الزوار تلقائيًا»):
# the dashboard's numbers come from the GraphQL Analytics API, dataset
# rumPageloadEventsAdaptiveGroups, filtered by the site's beacon tag. Two
# secrets/variables the user adds: CF_ANALYTICS_TOKEN (an API token with
# Account > Account Analytics > Read; the D1 token lacks it) and
# CF_RUM_SITE_TAG (the Web Analytics site tag = the beacon token shown under
# Analytics & Logs > Web Analytics > Manage site). Missing either = nulls.
CF_GRAPHQL = "https://api.cloudflare.com/client/v4/graphql"
RUM_QUERY = """
query ($account: String!, $site: String!, $since: Date!, $until: Date!) {
  viewer { accounts(filter: {accountTag: $account}) {
    byDay: rumPageloadEventsAdaptiveGroups(
      filter: {siteTag: $site, date_geq: $since, date_leq: $until}, limit: 100, orderBy: [date_ASC]) {
      count sum { visits } dimensions { date } }
    byRef: rumPageloadEventsAdaptiveGroups(
      filter: {siteTag: $site, date_geq: $since, date_leq: $until}, limit: 50, orderBy: [sum_visits_DESC]) {
      count sum { visits } dimensions { refererHost } }
  } }
}"""


def parse_rum(j, since7):
    """The GraphQL reply -> {visits_7d, pageviews_7d, visits_prev7, pageviews_prev7,
    by_day: {date: [visits, pageviews]}, top_referrers: [[host, visits], ...]}.
    `since7` = the first date of the current 7-day window; earlier days are
    the previous window (the query asks for 14 days)."""
    accs = (((j or {}).get("data") or {}).get("viewer") or {}).get("accounts") or []
    if not accs:
        err = (j or {}).get("errors")
        raise ValueError(f"no account data in the reply: {str(err)[:200]}")
    acc = accs[0]
    by_day, cur_v = {}, 0
    cur_p = prev_v = prev_p = 0
    for g in acc.get("byDay") or []:
        d = (g.get("dimensions") or {}).get("date")
        v, pv = int((g.get("sum") or {}).get("visits") or 0), int(g.get("count") or 0)
        by_day[d] = [v, pv]
        if d and d >= since7:
            cur_v += v; cur_p += pv
        else:
            prev_v += v; prev_p += pv
    refs = {}
    for g in acc.get("byRef") or []:
        h = (g.get("dimensions") or {}).get("refererHost") or "(direct)"
        if h.endswith("yallascore.site"):
            continue                                   # our own pages are not a source
        refs[h] = refs.get(h, 0) + int((g.get("sum") or {}).get("visits") or 0)
    # the referrer groups cover 14 days; the 7-day split is not available per host
    # without a second query, so the list is labelled 14d in the row
    top = sorted(refs.items(), key=lambda kv: -kv[1])[:6]
    return {"visits_7d": cur_v, "pageviews_7d": cur_p, "visits_prev7": prev_v, "pageviews_prev7": prev_p,
            "by_day": by_day, "top_referrers_14d": [[h, n] for h, n in top]}


def cloudflare_site(account, token, site_tag, now=None):
    """Visitors from Cloudflare Web Analytics for the last 7 days (and the 7
    before, for the trend). Nulls, never a failure, when anything is missing."""
    empty = {"visits_7d": None, "pageviews_7d": None, "visits_prev7": None, "pageviews_prev7": None,
             "by_day": {}, "top_referrers_14d": []}
    if not (account and token and site_tag):
        return empty
    now = now or time.time()
    today = datetime.datetime.fromtimestamp(now, datetime.timezone.utc).date()
    until = today - datetime.timedelta(days=1)                 # yesterday: the last complete day
    since7 = until - datetime.timedelta(days=6)
    since14 = until - datetime.timedelta(days=13)
    try:
        j = _post_json(CF_GRAPHQL, {"query": RUM_QUERY, "variables": {
            "account": account, "site": site_tag, "since": since14.isoformat(), "until": until.isoformat()}},
            {"Authorization": f"Bearer {token}"})
        out = parse_rum(j, since7.isoformat())
        out["window"] = [since7.isoformat(), until.isoformat()]
        return out
    except Exception as e:                            # noqa: BLE001
        print(f"cloudflare analytics: {e}")
        return empty


def facebook(token):
    if not token:
        return {"followers": None, "fans": None}
    try:
        j = _get(f"{GRAPH}/me?fields=followers_count,fan_count&access_token={urllib.parse.quote(token)}")
        return {"followers": j.get("followers_count"), "fans": j.get("fan_count")}
    except Exception as e:                            # noqa: BLE001
        print(f"facebook: {e}")
        return {"followers": None, "fans": None}


PAGE_METRICS = ("page_impressions_unique", "page_post_engagements", "page_daily_follows_unique")


def _insight_error(e):
    """The Graph error as a short string (a missing read_insights reads
    '(#100) ... permission' or '(#10) ... requires ... read_insights')."""
    msg = str(e)
    try:
        body = e.read().decode("utf-8", "replace")                 # urllib HTTPError
        j = json.loads(body)
        msg = (j.get("error") or {}).get("message") or body[:200]
    except Exception:                                 # noqa: BLE001
        pass
    return msg[:300]


def page_insights(token):
    """{"reach_7d", "engagements_7d", "follows_7d"} for the last full week,
    or {"error": ...}. period=week gives one value per week-ending day; the
    newest is the week we report."""
    if not token:
        return None
    try:
        j = _get(f"{GRAPH}/me/insights?metric={','.join(PAGE_METRICS)}&period=week&access_token={urllib.parse.quote(token)}")
    except Exception as e:                            # noqa: BLE001
        return {"error": _insight_error(e)}
    out = {}
    for m in j.get("data") or []:
        vals = m.get("values") or []
        v = (vals[-1] or {}).get("value") if vals else None
        if isinstance(v, dict):
            v = sum(x for x in v.values() if isinstance(x, (int, float)))
        key = {"page_impressions_unique": "reach_7d", "page_post_engagements": "engagements_7d",
               "page_daily_follows_unique": "follows_7d"}.get(m.get("name"), m.get("name"))
        out[key] = v
    return out


def post_reach(token, post_id):
    """post_impressions_unique for one post, or None (a reel or a deleted
    post answers an error - that post just drops out of the average)."""
    j = _get(f"{GRAPH}/{post_id}/insights?metric=post_impressions_unique&access_token={urllib.parse.quote(token)}")
    for m in j.get("data") or []:
        vals = m.get("values") or []
        if vals and isinstance(vals[0].get("value"), (int, float)):
            return vals[0]["value"]
    return None


def ab_reach(token, now=None):
    """The A/B read-out: every article post since the A/B began, its reach by
    variant -> {"photo": {"n", "avg", "median"}, "link": {...}, "since"}; or
    {"error": ...} when the token cannot read insights. Posts the Graph
    refuses individually are skipped, not fatal."""
    import fb_post as fp
    if not token:
        return None
    try:
        rows = store.posted_since("article", AB_START)
    except Exception:                                 # noqa: BLE001
        rows = []
    reach = {"photo": [], "link": []}
    first_err = None
    for r in rows:
        if r["posted_at"] < AB_START or not r.get("post_id") or str(r["post_id"]).startswith("seeded"):
            continue
        try:
            v = post_reach(token, r["post_id"])
        except Exception as e:                        # noqa: BLE001
            if first_err is None:
                first_err = _insight_error(e)
            continue
        if v is not None:
            reach[fp.variant({"article_id": r["ref_id"]})].append(v)
    if first_err and not (reach["photo"] or reach["link"]):
        return {"error": first_err}

    def agg(xs):
        if not xs:
            return {"n": 0, "avg": None, "median": None}
        xs = sorted(xs)
        return {"n": len(xs), "avg": round(sum(xs) / len(xs), 1), "median": xs[len(xs) // 2]}
    return {"photo": agg(reach["photo"]), "link": agg(reach["link"]),
            "since": datetime.datetime.fromtimestamp(AB_START, datetime.timezone.utc).strftime("%Y-%m-%d")}


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
    token = os.environ.get("FB_PAGE_TOKEN", "").strip()
    fb = facebook(token)
    return {
        "date": datetime.datetime.fromtimestamp(now, datetime.timezone.utc).strftime("%Y-%m-%d"),
        "followers": fb["followers"], "fans": fb["fans"],
        "fb_insights": page_insights(token),
        "ab_reach": ab_reach(token, now),
        "telegram": telegram(os.environ.get("TG_BOT_TOKEN", "").strip(), os.environ.get("TG_CHAT_ID", "").strip()),
        "push_subs": push_subs(),
        "articles_7d": articles_7d(now),
        "posts_7d": posts_7d(now),
        "site": cloudflare_site(os.environ.get("CF_ACCOUNT_ID", "").strip(), os.environ.get("CF_ANALYTICS_TOKEN", "").strip(),
                                os.environ.get("CF_RUM_SITE_TAG", "").strip(), now),
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


def site_summary(r):
    """The visitors block for the step summary: 7-day visits with the trend,
    page views, and the top referrers - the numbers the Monday review reads."""
    st = r.get("site") or {}
    if st.get("visits_7d") is None:
        return "زوار الموقع: غير متاح (أضف CF_ANALYTICS_TOKEN و CF_RUM_SITE_TAG)"
    prev = st.get("visits_prev7") or 0
    trend = f" ({'+' if st['visits_7d'] >= prev else ''}{st['visits_7d'] - prev} عن الأسبوع السابق)" if prev else ""
    refs = " · ".join(f"{h} {n}" for h, n in st.get("top_referrers_14d") or []) or "لا إحالات مسجّلة"
    w = st.get("window") or ["", ""]
    return (f"زوار الموقع {w[0]} → {w[1]}: **{st['visits_7d']}** زيارة{trend} · {st['pageviews_7d']} مشاهدة صفحة\n"
            f"مصادر الإحالة (14 يومًا): {refs}")


def fb_summary(r):
    """The page's week and the A/B read-out for the step summary."""
    ins, ab = r.get("fb_insights"), r.get("ab_reach")
    if ins is None:
        return "فيسبوك: لا رمز صفحة"
    if isinstance(ins, dict) and ins.get("error"):
        return ("فيسبوك: الرمز لا يقرأ الإحصاءات - أعد إصداره بصلاحيتي pages_read_engagement و read_insights "
                f"(الخطأ: {ins['error'][:120]})")
    lines = [f"فيسبوك هذا الأسبوع: وصول **{ins.get('reach_7d')}** · تفاعل {ins.get('engagements_7d')} · متابعون جدد {ins.get('follows_7d')}"]
    if isinstance(ab, dict) and not ab.get("error"):
        p, l = ab.get("photo") or {}, ab.get("link") or {}
        lines.append(f"A/B صورة مقابل رابط منذ {ab.get('since')}: صورة {p.get('n')} منشورًا بمتوسط وصول {p.get('avg')} (وسيط {p.get('median')}) · "
                     f"رابط {l.get('n')} منشورًا بمتوسط {l.get('avg')} (وسيط {l.get('median')})")
    elif isinstance(ab, dict):
        lines.append(f"A/B: تعذّرت قراءة وصول المنشورات ({ab['error'][:120]})")
    return "\n".join(lines)


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
                     "|---|---|---|---|---|---|---|---|---|---|---|\n" + summary(r) + "\n\n" + site_summary(r) + "\n\n" + fb_summary(r) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
