# -*- coding: utf-8 -*-
"""growth_kpi.py: the weekly row is built from the store with no network,
every missing token leaves a null instead of failing, and the file keeps one
row per day."""
import datetime, sys, os, tempfile, time, json
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _k in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_D1_ID", "FB_PAGE_TOKEN", "TG_BOT_TOKEN", "TG_CHAT_ID"):
    os.environ.pop(_k, None)
os.environ["D1_SQLITE"] = os.path.join(tempfile.mkdtemp(), "state.sqlite")
import store
store.init_schema()
import growth_kpi as K
import fb_post as fp

fails = 0


def ck(name, cond, extra=""):
    global fails
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f"  [{extra}]" if extra and not cond else ""))
    fails += 0 if cond else 1


now = time.time()
store.record_post("article", "600", "P1")      # even -> photo
store.record_post("article", "601", "P2")      # odd  -> link
store.record_post("pred", "4804684", "P3")
store.record_post("h2h", "4804684", "P4")
store.record_post("goal", "901:2", "P5")
store.sql("UPDATE fb_posted SET posted_at = ? WHERE ref_id = '601'", [int(now) - 9 * 86400])   # outside the week
fp.load_articles = lambda: [{"article_id": 1, "pub_ts": "2026-01-01T00:00:00+00:00"},
                            {"article_id": 2, "pub_ts": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()}]
r = K.row(now)
ck("1 no tokens -> nulls, not failures", r["followers"] is None and r["telegram"] is None and r["fb_insights"] is None and r["ab_reach"] is None)
ck("2 push_subs reads the store (0 rows)", r["push_subs"] == 0, str(r["push_subs"]))
ck("3 posts of the last 7 days by kind, the A/B split", r["posts_7d"]["article_photo"] == 1 and r["posts_7d"]["article_link"] == 0
   and r["posts_7d"]["pred"] == 1 and r["posts_7d"]["h2h"] == 1 and r["posts_7d"]["goal"] == 1 and r["posts_7d"]["xi"] == 0, str(r["posts_7d"]))
ck("4 articles published in the last 7 days", r["articles_7d"] == 1, str(r["articles_7d"]))
K.OUT = os.path.join(tempfile.mkdtemp(), "growth_kpi.json")
K.append(r); n = K.append(dict(r, followers=1200))
rows = json.load(open(K.OUT, encoding="utf-8"))
ck("5 one row per day, the latest wins", n == 1 and rows[0]["followers"] == 1200)
ck("6 the summary line is a markdown row", K.summary(r).startswith("| ") and K.summary(r).count("|") == 12, K.summary(r))


# ---- Cloudflare Web Analytics (2026-10-18) ---------------------------------
ck("7 no analytics token / site tag -> nulls in the row, never a failure",
   r["site"]["visits_7d"] is None and "غير متاح" in K.site_summary(r))
reply = {"data": {"viewer": {"accounts": [{
    "byDay": [{"count": 40, "sum": {"visits": 30}, "dimensions": {"date": "2026-10-05"}},
              {"count": 100, "sum": {"visits": 70}, "dimensions": {"date": "2026-10-12"}},
              {"count": 120, "sum": {"visits": 90}, "dimensions": {"date": "2026-10-17"}}],
    "byRef": [{"count": 90, "sum": {"visits": 80}, "dimensions": {"refererHost": "m.facebook.com"}},
              {"count": 50, "sum": {"visits": 40}, "dimensions": {"refererHost": "www.google.com"}},
              {"count": 30, "sum": {"visits": 25}, "dimensions": {"refererHost": "yallascore.site"}},
              {"count": 5, "sum": {"visits": 5}, "dimensions": {"refererHost": ""}}]}]}}}
st = K.parse_rum(reply, "2026-10-11")
ck("8 the 7-day window sums the days on or after its first date, the rest is the previous week",
   st["visits_7d"] == 160 and st["pageviews_7d"] == 220 and st["visits_prev7"] == 30 and st["pageviews_prev7"] == 40, str(st))
ck("9 referrers: our own host dropped, the empty host is (direct), facebook first",
   st["top_referrers_14d"][0] == ["m.facebook.com", 80] and ["(direct)", 5] in st["top_referrers_14d"]
   and not any(h.endswith("yallascore.site") for h, _ in st["top_referrers_14d"]), str(st["top_referrers_14d"]))
_pj = K._post_json
K._post_json = lambda url, body, headers, timeout=40: reply
try:
    now = datetime.datetime(2026, 10, 18, 9, 0, tzinfo=datetime.timezone.utc).timestamp()
    cf = K.cloudflare_site("acc", "tok", "site", now)
    ck("10 cloudflare_site asks for 14 days ending yesterday and labels the 7-day window",
       cf["window"] == ["2026-10-11", "2026-10-17"] and cf["visits_7d"] == 160, str(cf.get("window")))
    rr = dict(r, site=cf)
    ck("11 the step summary carries visits, the trend and the referrers",
       "160" in K.site_summary(rr) and "+130" in K.site_summary(rr) and "m.facebook.com 80" in K.site_summary(rr), K.site_summary(rr))
    K._post_json = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("401"))
    ck("12 an API error gives nulls, not a failed KPI run", K.cloudflare_site("acc", "tok", "site", now)["visits_7d"] is None)
finally:
    K._post_json = _pj

# ---- Facebook insights + the A/B reach (2026-10-22), Graph mocked
import urllib.error
store.record_post("article", "700", "POST700")      # even -> photo
store.record_post("article", "701", "POST701")      # odd  -> link
store.record_post("article", "702", "POST702")      # even -> photo, the Graph refuses it (a reel)
_calls = []
def fake_get(url, timeout=30):
    _calls.append(url)
    if "/me/insights" in url:
        return {"data": [{"name": "page_impressions_unique", "period": "week", "values": [{"value": 900}, {"value": 1200}]},
                         {"name": "page_post_engagements", "period": "week", "values": [{"value": 80}, {"value": 95}]},
                         {"name": "page_daily_follows_unique", "period": "week", "values": [{"value": 10}, {"value": 14}]}]}
    if "/POST702/insights" in url:
        raise urllib.error.HTTPError(url, 400, "Bad Request", {}, io.BytesIO(b'{"error":{"message":"(#100) Unsupported get request"}}'))
    pid = url.split("/")[4]
    return {"data": [{"name": "post_impressions_unique", "values": [{"value": {"POST700": 300, "POST701": 120}[pid]}]}]}
import io
K._get = fake_get
ins = K.page_insights("tok")
ck("8 page insights: the newest week's reach, engagements and follows", ins == {"reach_7d": 1200, "engagements_7d": 95, "follows_7d": 14}, str(ins))
ab = K.ab_reach("tok", now)
ck("9 the A/B read-out averages reach per variant and skips a post the Graph refuses",
   ab["photo"] == {"n": 1, "avg": 300.0, "median": 300} and ab["link"] == {"n": 1, "avg": 120.0, "median": 120} and ab["since"] == "2026-10-08", str(ab))
ck("10 posted_since carries the post id", all(x.get("post_id") for x in store.posted_since("article", 0)))
def denied(url, timeout=30):
    raise urllib.error.HTTPError(url, 403, "Forbidden", {}, io.BytesIO(b'{"error":{"message":"(#10) This endpoint requires the read_insights permission","code":10}}'))
K._get = denied
ins2, ab2 = K.page_insights("tok"), K.ab_reach("tok", now)
ck("11 a token without read_insights -> {error} on both, never an exception", "read_insights" in ins2.get("error", "") and "read_insights" in ab2.get("error", ""), str(ins2))
ck("12 the summary tells the user to re-issue the token", "read_insights" in K.fb_summary({"fb_insights": ins2, "ab_reach": ab2}))
ck("13 ...and reports the numbers when it can", "1200" in K.fb_summary({"fb_insights": ins, "ab_reach": ab}) and "300.0" in K.fb_summary({"fb_insights": ins, "ab_reach": ab}))

print("\nALL GROWTH KPI TESTS PASSED" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
