# -*- coding: utf-8 -*-
"""fb_post.py --auto plumbing test with a mocked Graph API + mocked site (no network)."""
import sys, os, json, io, tempfile, datetime, urllib.request, urllib.error
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# state lives in store.py now: point it at a throwaway sqlite file BEFORE
# fb_post imports it, so these tests exercise the real claim/record SQL
tmp = tempfile.mkdtemp()
for _k in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_D1_ID"):
    os.environ.pop(_k, None)
os.environ["D1_SQLITE"] = os.path.join(tmp, "state.sqlite")
import store
import fb_post as fp
import time as _time
_time.sleep = lambda s: None          # no real waiting in tests
fp.time.sleep = lambda s: None
# the shipped default is NO window (user, 2026-09-12 afternoon: an article that
# lands on the site lands on Facebook, whatever the hour); test 16 switches a
# window on for its own checks and back off again
assert fp.POST_WINDOW is None, f"shipped default must be None, got {fp.POST_WINDOW}"
assert store.backend() == "sqlite", store.backend()
store.init_schema()

calls = []
SITE_404 = {}      # link -> number of times the SITE should still answer with the 404 page
FB_404 = {}        # link -> number of times FACEBOOK's scrape should still return the 404 title

class FakeResp(io.BytesIO):
    status = 200
    def __enter__(self): return self
    def __exit__(self, *a): return False

def fake_urlopen(req, timeout=0):
    url = req.full_url
    body = req.data.decode() if getattr(req, "data", None) else ""
    calls.append((url, body))
    if url.startswith(fp.SITE + "/a/"):                       # our own site (page_is_live)
        link = url.split("?")[0]
        if SITE_404.get(link, 0) > 0:
            SITE_404[link] -= 1
            return FakeResp(f"<title>{fp.NOT_FOUND_MARK} — يلا سكور</title>".encode())
        return FakeResp(b"<title>Real article</title>")
    if url.rstrip("/") == fp.GRAPH:                           # scrape
        link = urllib.parse.parse_qs(body)["id"][0]
        if FB_404.get(link, 0) > 0:
            FB_404[link] -= 1
            return FakeResp(json.dumps({"title": f"{fp.NOT_FOUND_MARK} — يلا سكور"}).encode())
        return FakeResp(json.dumps({"title": "scraped title"}).encode())
    return FakeResp(json.dumps({"id": f"POST_{len(calls)}"}).encode())
import urllib.parse
urllib.request.urlopen = fake_urlopen

def ts(hours_ago):
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours_ago)).isoformat()

def run(items, token="tok", argv=("--auto",)):
    fp.load_articles = lambda: items
    os.environ["FB_PAGE_TOKEN"] = token
    sys.argv = ["fb_post.py", *argv]
    calls.clear()
    return fp.main()

def state():
    """article_id -> row, straight from the store (posted rows only)."""
    return {a: store.get_post("article", a) for a in store.posted_ids("article")}
def posted_ids(): return sorted(store.posted_ids("article"))
def reset_state():
    store.sql("DELETE FROM fb_posted"); store.sql("DELETE FROM fb_failed")
def feed_links(): return [b.split("link=")[1].split("&")[0] for u, b in calls if u == fp.GRAPH_FEED]
def scrapes_of(aid): return sum(1 for u, b in calls if u.rstrip("/") == fp.GRAPH and f"a%2F{aid}" in b)
def live_checks_of(aid): return sum(1 for u, _ in calls if u.startswith(f"{fp.SITE}/a/{aid}"))

A = lambda i, h, **kw: {"article_id": i, "title": f"T{i}", "summary": "S", "pub_ts": ts(h), **kw}
L = lambda i: f"{fp.SITE}/a/{i}"

# 1) backlog of 5 fresh articles → oldest 3 posted in order, each live-checked + scraped first
items = [A(362, 0.5), A(361, 0.8), A(360, 1.7), A(359, 2.6), A(358, 4.1)]
run(items)
assert feed_links() == [f"https%3A%2F%2Fyallascore.site%2Fa%2F{i}" for i in (358, 359, 360)], feed_links()
assert posted_ids() == ["358", "359", "360"] and all(state()[k]["og_ok"] for k in posted_ids())
assert live_checks_of(358) == 1 and scrapes_of(358) == 1
print("1 OK: backlog → oldest 3 posted, live-checked and scraped, og_ok recorded")

# 2) next run → the remaining 2
run(items)
assert feed_links() == [f"https%3A%2F%2Fyallascore.site%2Fa%2F{i}" for i in (361, 362)]
print("2 OK: remaining two posted")

# 3) edge lag: SITE answers 404 twice, then the page → wait, then post
SITE_404[L(370)] = 2
run([A(370, 0.3)])
assert live_checks_of(370) == 3 and feed_links() == ["https%3A%2F%2Fyallascore.site%2Fa%2F370"]
print("3 OK: site not live yet → waited 2 tries, then posted")

# 4) Facebook's crawler still sees the 404 twice, then the page → retried scrape, posted
FB_404[L(371)] = 2
run([A(371, 0.3)])
assert scrapes_of(371) == 3 and feed_links() == ["https%3A%2F%2Fyallascore.site%2Fa%2F371"]
print("4 OK: FB saw 404 twice → re-scraped, then posted")

# 5) Facebook keeps seeing the 404 → DEFERRED: no post, not recorded (retried next run)
FB_404[L(372)] = 99
run([A(372, 0.3)])
assert feed_links() == [] and "372" not in posted_ids() and scrapes_of(372) == fp.SCRAPE_TRIES
FB_404[L(372)] = 0
run([A(372, 0.4)])
assert feed_links() == ["https%3A%2F%2Fyallascore.site%2Fa%2F372"] and "372" in posted_ids()
print("5 OK: persistent 404 preview → deferred, then posted on the next run")

# 6) site never comes up → deferred too
SITE_404[L(373)] = 99
run([A(373, 0.3)])
assert feed_links() == [] and "373" not in posted_ids() and live_checks_of(373) == fp.LIVE_TRIES
SITE_404[L(373)] = 0
print("6 OK: page never live → deferred")

# 7) heal pass: a recent record without og_ok (e.g. article 364 posted by the old code) is re-scraped
store.record_post("article", 364, "111_222", title="old")          # og_ok False
store.record_post("article", 300, "111_333", title="too old")
store.sql("UPDATE fb_posted SET posted_at = ? WHERE ref_id = '300'",
          [int(fp.time.time()) - 30 * 3600])                        # outside the heal window
run([A(362, 0.5)])       # nothing new to post; heal pass runs
assert scrapes_of(364) == 1 and scrapes_of(300) == 0
assert state()["364"]["og_ok"] == 1 and state()["300"]["og_ok"] == 0
print("7 OK: heal pass re-scraped the recent unconfirmed post only, marked og_ok")

# 8) old (30h) / undated never auto-posted; no token → inert
run([A(200, 30), {"article_id": 201, "title": "undated"}])
assert feed_links() == []
before = posted_ids(); run([A(380, 1)], token="")
assert calls == [] and posted_ids() == before
print("8 OK: old/undated skipped; no token → inert")

# 9) legacy positional mode: scrape check then post top only, no state
run([A(390, 1), A(389, 2)], argv=("0",))
assert feed_links() == ["https%3A%2F%2Fyallascore.site%2Fa%2F390"]
assert "390" in posted_ids(), "legacy mode now records too, so --auto cannot repost it"
print("9 OK: legacy mode posts the top article and records it")

# 10) shared state: fb_cards keys survive
store.record_post("card", 1, "PID_CARD1", score="1-0")
run([A(400, 1)])
assert store.posted_ids("card") == {"1"}, "posting an article must not touch cards"
assert "400" in posted_ids()
print("10 OK: cards and articles share the table without colliding")
# 11) THE DUPLICATE BUG (article 422, 2026-09-07), now structurally impossible:
#     a claim already held by another run means this run must NOT post.
reset_state()
assert store.claim("article", 500) is True          # pretend another run got there first
run([A(500, 1)])
assert feed_links() == [], f"posted while another run held the claim! {feed_links()}"
print("11 OK: an article claimed by another run is never posted twice")

# 12) a genuinely new article still goes out while the claimed one is skipped
run([A(501, 1)])
assert feed_links() == ["https%3A%2F%2Fyallascore.site%2Fa%2F501"], feed_links()
assert "501" in posted_ids()
print("12 OK: new article still posted next to a claimed one")

# 13) a deferral RELEASES the claim, so the next run may retry
reset_state()
SITE_404[L(502)] = 99                                # never live -> deferred
run([A(502, 1)])
assert feed_links() == [] and store.get_post("article", 502) is None,     "a deferred article must not keep its claim"
SITE_404[L(502)] = 0
run([A(502, 1)])
assert feed_links() == ["https%3A%2F%2Fyallascore.site%2Fa%2F502"]
print("13 OK: deferral releases the claim and the retry succeeds")

# 14) an article that has failed MAX_POST_ATTEMPTS times stops eating a slot
reset_state()
for _ in range(fp.MAX_POST_ATTEMPTS):
    store.bump_failed("article", 503, "boom")
run([A(503, 1)])
assert feed_links() == [] and store.get_post("article", 503) is None
print("14 OK: an article past MAX_POST_ATTEMPTS is skipped")

print("ALL FB_POST TESTS PASSED")


# 16) the posting window (13:00-01:00 Cairo): closed hours neither dispatch nor age
fp.POST_WINDOW = (13, 1)
_c = lambda h, m=0, d=12: datetime.datetime(2026, 9, d, h, m, tzinfo=fp.CAIRO)
assert fp.window_open(_c(13)) and fp.window_open(_c(23, 59)) and fp.window_open(_c(0, 30))
assert not fp.window_open(_c(1)) and not fp.window_open(_c(12, 59)) and not fp.window_open(_c(7))
# a report written at 02:00 is 0 open-hours old at 13:00, 2 at 15:00
assert fp.open_hours(_c(2), _c(13)) == 0.0
assert abs(fp.open_hours(_c(2), _c(15)) - 2.0) < 1e-9
# an article at 23:00 has 2 open hours before the window closes, then waits
assert abs(fp.open_hours(_c(23, 0, 11), _c(13, 0, 12)) - 2.0) < 1e-9
assert abs(fp.open_hours(_c(23, 0, 11), _c(17, 0, 12)) - 6.0) < 1e-9
# --pending says 0 while closed, whatever is unposted
fp._now = lambda: _c(9).astimezone(datetime.timezone.utc)
import contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    sys.argv = ["fb_post.py", "--pending"]
    fp.load_articles = lambda: [A(900, 1)]
    fp.main()
assert buf.getvalue().strip() == "0", buf.getvalue()
fp._now = lambda: datetime.datetime.now(datetime.timezone.utc)
fp.POST_WINDOW = None
print("16 OK: window 13:00-01:00 - closed hours dispatch nothing and do not age an article")

# 17) with the shipped default (no window) the same 09:00 article IS pending
fp._now = lambda: _c(9).astimezone(datetime.timezone.utc)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    sys.argv = ["fb_post.py", "--pending"]
    fp.load_articles = lambda: [A(901, 1)]
    fp.main()
assert buf.getvalue().strip() == "1", buf.getvalue()
fp._now = lambda: datetime.datetime.now(datetime.timezone.utc)
print("17 OK: no window - a 09:00 article is pending at 09:00")
