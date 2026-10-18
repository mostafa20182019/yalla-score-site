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
ck("1 no tokens -> nulls, not failures", r["followers"] is None and r["telegram"] is None)
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
print("\nALL GROWTH KPI TESTS PASSED" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
