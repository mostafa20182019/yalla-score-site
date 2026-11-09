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
    body = req.data.decode("utf-8", "replace") if getattr(req, "data", None) else ""   # a photo post carries JPEG bytes
    calls.append((url, body))
    if url.startswith(fp.SITE + "/a/"):                       # our own site (page_is_live)
        link = url.split("?")[0]
        if SITE_404.get(link, 0) > 0:
            SITE_404[link] -= 1
            return FakeResp(f"<title>{fp.NOT_FOUND_MARK} — الجون</title>".encode())
        return FakeResp(b"<title>Real article</title>")
    if url.rstrip("/") == fp.GRAPH:                           # scrape
        link = urllib.parse.parse_qs(body)["id"][0]
        if FB_404.get(link, 0) > 0:
            FB_404[link] -= 1
            return FakeResp(json.dumps({"title": f"{fp.NOT_FOUND_MARK} — الجون"}).encode())
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
assert feed_links() == [f"https%3A%2F%2Felgoon.com%2Fa%2F{i}" for i in (358, 359, 360)], feed_links()
assert posted_ids() == ["358", "359", "360"] and all(state()[k]["og_ok"] for k in posted_ids())
assert live_checks_of(358) == 1 and scrapes_of(358) == 1
print("1 OK: backlog → oldest 3 posted, live-checked and scraped, og_ok recorded")

# 2) next run → the remaining 2
run(items)
assert feed_links() == [f"https%3A%2F%2Felgoon.com%2Fa%2F{i}" for i in (361, 362)]
print("2 OK: remaining two posted")

# 3) edge lag: SITE answers 404 twice, then the page → wait, then post
SITE_404[L(370)] = 2
run([A(370, 0.3)])
assert live_checks_of(370) == 3 and feed_links() == ["https%3A%2F%2Felgoon.com%2Fa%2F370"]
print("3 OK: site not live yet → waited 2 tries, then posted")

# 4) Facebook's crawler still sees the 404 twice, then the page → retried scrape, posted
FB_404[L(371)] = 2
run([A(371, 0.3)])
assert scrapes_of(371) == 3 and feed_links() == ["https%3A%2F%2Felgoon.com%2Fa%2F371"]
print("4 OK: FB saw 404 twice → re-scraped, then posted")

# 5) Facebook keeps seeing the 404 → DEFERRED: no post, not recorded (retried next run)
FB_404[L(372)] = 99
run([A(372, 0.3)])
assert feed_links() == [] and "372" not in posted_ids() and scrapes_of(372) == fp.SCRAPE_TRIES
FB_404[L(372)] = 0
run([A(372, 0.4)])
assert feed_links() == ["https%3A%2F%2Felgoon.com%2Fa%2F372"] and "372" in posted_ids()
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
assert feed_links() == ["https%3A%2F%2Felgoon.com%2Fa%2F390"]
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
assert feed_links() == ["https%3A%2F%2Felgoon.com%2Fa%2F501"], feed_links()
assert "501" in posted_ids()
print("12 OK: new article still posted next to a claimed one")

# 13) a deferral RELEASES the claim, so the next run may retry
reset_state()
SITE_404[L(502)] = 99                                # never live -> deferred
run([A(502, 1)])
assert feed_links() == [] and store.get_post("article", 502) is None,     "a deferred article must not keep its claim"
SITE_404[L(502)] = 0
run([A(502, 1)])
assert feed_links() == ["https%3A%2F%2Felgoon.com%2Fa%2F502"]
print("13 OK: deferral releases the claim and the retry succeeds")

# 14) an article that has failed MAX_POST_ATTEMPTS times stops eating a slot
reset_state()
for _ in range(fp.MAX_POST_ATTEMPTS):
    store.bump_failed("article", 503, "boom")
run([A(503, 1)])
assert feed_links() == [] and store.get_post("article", 503) is None
print("14 OK: an article past MAX_POST_ATTEMPTS is skipped")

# 15) PHOTO A/B (growth plan week 1): even id + readable image -> /me/photos with
#     the caption; odd id -> link post; even id with an SVG placeholder -> link post
reset_state()
photos = []
fp.post_photo = lambda token, img, caption: (photos.append((len(img), caption)), "PHOTO_1")[1]
fp.MEDIA = tempfile.mkdtemp()
with open(os.path.join(fp.MEDIA, "card.jpg"), "wb") as _f:
    _f.write(b"\xff\xd8" + b"x" * 5000)
run([A(600, 1, image_url=f"{fp.SITE}/media/card.jpg", fb_post="T600 text\nnumbers"),
     A(601, 1, image_url=f"{fp.SITE}/media/card.jpg"),
     A(602, 1, image_url=f"{fp.SITE}/media/ph-pitch.svg")])
assert len(photos) == 1 and photos[0][0] == 5002, photos
assert photos[0][1].endswith(f"\n{fp.SITE}/a/600"), "the link must live in the caption text"
# order-free: the three share one pub_ts to the millisecond on Windows and
# differ by microseconds on Linux, so the posting order is not the point here
assert sorted(feed_links()) == ["https%3A%2F%2Felgoon.com%2Fa%2F601", "https%3A%2F%2Felgoon.com%2Fa%2F602"], feed_links()
assert posted_ids() == ["600", "601", "602"] and state()["600"]["post_id"] == "PHOTO_1"
assert fp.variant({"article_id": "600"}) == "photo" and fp.variant({"article_id": "601"}) == "link"
fp.PHOTO_AB = False
assert fp.variant({"article_id": "600"}) == "link"
fp.PHOTO_AB = True
print("15 OK: photo A/B - even id with an image is a photo post (link in the caption), odd/SVG stay link posts")

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

# 18) --repost: refuses while the old post still exists, reposts an OLD article
# once the page deleted it, and records the new post id
reset_state()
store.record_post("article", "687", "OLD_POST", title="T687")
GONE = set()
_base = urllib.request.urlopen
def _with_gone(req, timeout=0):
    url = req if isinstance(req, str) else req.full_url
    if isinstance(req, str) and url.startswith(fp.GRAPH + "/"):
        pid = url[len(fp.GRAPH) + 1:].split("?")[0]
        if pid in GONE:
            raise urllib.error.HTTPError(url, 400, "gone", {}, io.BytesIO(b"{}"))
        return FakeResp(json.dumps({"id": pid}).encode())
    return _base(req, timeout)
urllib.request.urlopen = _with_gone
old = [A(687, 40)]
assert run(old, argv=("--repost", "687")) == 1 and feed_links() == []
assert state()["687"]["post_id"] == "OLD_POST"
GONE.add("OLD_POST")
assert run(old, argv=("--repost", "687")) == 0
assert feed_links() == ["https%3A%2F%2Felgoon.com%2Fa%2F687"] and scrapes_of(687) >= 1, feed_links()
assert state()["687"]["post_id"] not in (None, "OLD_POST") and state()["687"]["og_ok"]
assert run(old, argv=("--repost", "999")) == 1
urllib.request.urlopen = _base
print("18 OK: --repost refuses while the old post exists, then reposts a 40h-old article once")

# 19) --text: posts drafts/fb/<name>.txt as a plain post once, records it under
# kind "text" / <name>, a second run is a no-op, a missing file is an error
# (user, 2026-11-08: a one-off worded post that goes through the store like
# everything else)
reset_state()
tdir = os.path.join(tmp, "fb"); os.makedirs(tdir, exist_ok=True)
tpath = os.path.join(tdir, "mun-avl.txt")
with open(tpath, "w", encoding="utf-8") as fh:
    fh.write("🏁 يونايتد يخسر\nسطر ثانٍ\n#الجون\n")
assert run([], argv=("--text", tpath)) == 0
feeds = [b for u, b in calls if u == fp.GRAPH_FEED]
assert len(feeds) == 1, calls
assert urllib.parse.parse_qs(feeds[0])["message"][0] == "🏁 يونايتد يخسر\nسطر ثانٍ\n#الجون", feeds
rec = store.get_post("text", "mun-avl")
assert rec and rec["post_id"] and rec["title"] == "🏁 يونايتد يخسر", rec
assert run([], argv=("--text", tpath)) == 0 and [b for u, b in calls if u == fp.GRAPH_FEED] == []
assert run([], argv=("--text", os.path.join(tdir, "missing.txt"))) == 1
assert run([], argv=("--text", tpath, "--dry")) == 0 and [b for u, b in calls if u == fp.GRAPH_FEED] == []
print("19 OK: --text posts the file once, records kind text, refuses a missing file")

# 20-23) --events: news FROM THE DATA (story_events.py, user 2026-11-08). Each
# detector is fed fixture data; the post goes out once through the store under
# (kind, ref), a second run is a no-op, --dry posts nothing.
import story_events as SE
reset_state()
_D = lambda **kw: {"matches": [], "fixtures": [], "standings": [], "scorers": [], "archive": [],
                   "articles": [], "moments": [], **kw}
_M = lambda mid, h, a, st, hs=None, as_=None, kick="2026-11-07", t="17:00": {
    "match_id": mid, "home": h, "away": a, "status": st, "home_score": hs, "away_score": as_,
    "kickoff": kick, "koff_time": t, "competition": "Egypt Cup"}
R32 = [_M(i, f"H{i}", f"A{i}", "FINISHED", 1, 0) for i in range(1, 17)]
R16 = [_M(100 + i, "الأهلي" if i == 1 else f"H{i}", "الزمالك" if i == 1 else f"A{i}", "UPCOMING",
          kick="2026-12-01", t="20:00") for i in range(1, 9)]
CUP = [{"competition": "Egypt Cup", "current": 2, "rounds": [
    {"round": 1, "label": "تصفيات", "matches": [_M(900, "P1", "P2", "FINISHED", 2, 0, kick="2026-10-17")]},
    {"round": 2, "label": "دور الـ 32", "matches": R32},
    {"round": 3, "label": "دور الـ 16", "matches": R16}]}]
feeds = lambda: [urllib.parse.parse_qs(b)["message"][0] for u, b in calls if u == fp.GRAPH_FEED]

# 20) cup round: complete + next round's pairings -> one post; incomplete / started / no pairings -> none
SE.load_data = lambda: _D(fixtures=CUP)
assert run([], argv=("--events", "--dry")) == 0 and feeds() == []
# the switch: without the repo variable FB_EVENTS=on the run prints and posts nothing (he reads first)
os.environ.pop("FB_EVENTS", None)
assert run([], argv=("--events",)) == 0 and feeds() == [] and store.get_post(SE.KIND_CUP, "Egypt Cup:R32:2026-27") is None
os.environ["FB_EVENTS"] = "on"
assert run([], argv=("--events",)) == 0
msgs = feeds(); assert len(msgs) == 1, msgs
assert msgs[0].startswith("🏆 انتهى دور الـ32 من كأس مصر.\nهذه مواجهات دور الـ16:\n• الأهلي × الزمالك — الثلاثاء 1 ديسمبر 20:00"), msgs[0]
assert "#الجون #كأس_مصر" in msgs[0] and "fixtures/egypt-cup.html" in msgs[0]
rec = store.get_post(SE.KIND_CUP, "Egypt Cup:R32:2026-27"); assert rec and rec["post_id"], rec
assert run([], argv=("--events",)) == 0 and feeds() == [], "posted twice"
# a live match in the round, or the next round already started, or TBD pairings: nothing
live = [dict(m) for m in R32]; live[5]["status"] = "LIVE"; live[5]["home_score"] = None
assert SE.cup_round_done([], [{"competition": "Egypt Cup", "rounds": [dict(CUP[0]["rounds"][1], matches=live), CUP[0]["rounds"][2]]}]) == []
started = [dict(m) for m in R16]; started[0].update({"status": "FINISHED", "home_score": 1, "away_score": 1})
assert SE.cup_round_done([], [{"competition": "Egypt Cup", "rounds": [CUP[0]["rounds"][1], {"round": 3, "label": "دور الـ 16", "matches": started}]}]) == []
assert SE.cup_round_done([], [{"competition": "Egypt Cup", "rounds": [CUP[0]["rounds"][1], {"round": 3, "label": "دور الـ 16", "matches": [_M(500, "", "", "UPCOMING")]}]}]) == []
# matches.json is fresher than fixtures.json: a LIVE status there vetoes a FINISHED copy in fixtures
assert SE.cup_round_done([dict(R32[0], status="LIVE", home_score=None)], CUP) == []
print("20 OK: cup round done -> the next round's pairings posted once; live / started / TBD rounds post nothing")

# 21) league half: every club at n-1 (one may be at n) -> top 5, bottom 3, the top scorer; 8 played -> nothing
_T = lambda n, played: [{"pos": i, "team": f"Club {i}", "played": played, "pts": 3 * (n - i)} for i in range(1, n + 1)]
tbl = _T(20, 19); tbl[3]["played"] = 20
SC = [{"competition": "Egyptian Premier League", "scorers": [{"name": "محمود ممدوح", "team": "مودرن سبورت", "goals": 8}]}]
SE.load_data = lambda: _D(standings=[{"competition": "Egyptian Premier League", "season_label": "2026/27", "table": tbl}], scorers=SC)
assert run([], argv=("--events",)) == 0
msgs = feeds(); assert len(msgs) == 1, msgs
assert msgs[0].startswith("📊 انتهى الدور الأول من الدوري المصري.\nالخماسي الأول بعد 19 جولة:\n1. Club 1 — 57 نقطة"), msgs[0]
assert "المراكز الأخيرة:\n18. Club 18 — 6 نقطة\n19. Club 19 — 3 نقطة\n20. Club 20 — 0 نقطة" in msgs[0], msgs[0]
assert "⚽ الهداف: محمود ممدوح (مودرن سبورت) — 8 أهداف" in msgs[0] and "standings/egypt.html" in msgs[0] and "#الدوري_المصري" in msgs[0]
assert store.get_post(SE.KIND_HALF, "Egyptian Premier League:2026-27")["post_id"]
assert run([], argv=("--events",)) == 0 and feeds() == []
assert SE.league_half_done([{"competition": "Premier League", "table": _T(20, 8)}], []) == []
assert SE.league_half_done([{"competition": "Premier League", "table": _T(20, 22)}], []) == [], "the moment has passed - never late"
assert SE.league_half_done([{"competition": "Premier League", "table": _T(20, 19), "zeroed": True}], []) == []
print("21 OK: league first half -> top 5 / bottom 3 / top scorer posted once; 8 played, long past or zeroed -> nothing")

# 22) on this day: a derby of an earlier year on today's date beats a big score; a dated moment is the fallback; a plain match is no hit
derby = {"match_id": "4804684", "competition": "Egyptian Premier League", "kickoff": "2026-10-11", "home": "الزمالك", "away": "الأهلي",
         "home_score": 0, "away_score": 2, "goals": [{"side": "a", "player": "محمد هاني", "minute": "39"}, {"side": "a", "player": "منصف بقرار", "minute": "80"}]}
big = {"match_id": "1", "competition": "Premier League", "kickoff": "2025-10-11", "home": "Hull City AFC", "away": "Manchester United FC", "home_score": 4, "away_score": 3}
plain = {"match_id": "2", "competition": "Premier League", "kickoff": "2024-10-11", "home": "Hull City AFC", "away": "Everton FC", "home_score": 1, "away_score": 0}
mo = {"id": "salah-congo-2017", "title": "ليلة برج العرب", "date": "2017-10-11", "otd_lines": ["مصر 2 - 1 الكونغو."], "hashtags": ["#منتخب_مصر"]}
SE.load_data = lambda: _D(archive=[plain, big, derby], moments=[mo])
assert run([], argv=("--events", "2027-10-11")) == 0
msgs = feeds(); assert len(msgs) == 1, msgs
assert msgs[0] == ("📅 في مثل هذا اليوم قبل عام، 11 أكتوبر 2026:\nالزمالك 0 - 2 الأهلي في الدوري المصري.\nالمباراة هي قمة الكرة المصرية.\n"
                   "أهداف الأهلي: محمد هاني 39'، منصف بقرار 80'.\nتفاصيل المباراة: https://elgoon.com/m/4804684\n#الجون #الدوري_المصري"), msgs[0]
assert store.get_post(SE.KIND_OTD, "2027-10-11")["post_id"]
assert run([], argv=("--events", "2027-10-11")) == 0 and feeds() == []
ev = SE.on_this_day([plain, big], [mo], datetime.date(2027, 10, 11))
assert len(ev) == 1 and "هال سيتي 4 - 3 مانشستر يونايتد" in ev[0]["text"] and "7 أهداف" in ev[0]["text"], ev
ev = SE.on_this_day([plain], [mo], datetime.date(2027, 10, 11))
assert len(ev) == 1 and ev[0]["moment"] == "salah-congo-2017" and "قبل 10 أعوام" in ev[0]["text"] and "#منتخب_مصر" in ev[0]["text"], ev
assert SE.on_this_day([plain], [], datetime.date(2027, 10, 11)) == []
assert SE.on_this_day([derby], [], datetime.date(2026, 10, 11)) == [], "the same year is not «on this day»"
# the same match as a moment reel script: scenes from the goals, 6-8 scenes, 14-17.5 s, no photo
import moment_reel as M
script = SE.moment_script(derby, mid="derby-test")
assert script and script["id"] == "derby-test" and script["date"] == "2026-10-11" and 14 <= M.validate(script) <= 17.5
assert [s["kind"] for s in script["scenes"]] == ["hook", "date", "teams", "goal", "climax", "finale", "cta"]
assert script["scenes"][4]["score"] == [0, 2] and script["scenes"][4]["crest"] == "away" and "#الجون" in script["caption"]
assert SE.moment_script(big) is None, "no scorer data -> no reel"
print("22 OK: on this day -> the derby wins, the dated moment is the fallback, posted once; the reel script validates")

# 23) a coach leaves the NT (one of OUR articles is the trigger) -> his record from the NT's archived matches, once
art = {"article_id": "1095", "title": "حسام حسن يرحل عن تدريب منتخب مصر وعلي ماهر خلفًا له رسميًا", "pub_date": "2026-11-07"}
nt = [{"match_id": "a", "competition": "Africa Cup of Nations Qualification", "kickoff": "2026-09-25", "home": "مصر", "away": "أنجولا", "home_score": 0, "away_score": 0},
      {"match_id": "b", "competition": "Africa Cup of Nations Qualification", "kickoff": "2026-09-29", "home": "جنوب السودان", "away": "مصر", "home_score": 0, "away_score": 5},
      {"match_id": "c", "competition": "Africa Cup of Nations Qualification", "kickoff": "2026-11-13", "home": "مصر", "away": "مالاوي", "home_score": 2, "away_score": 0},
      {"match_id": "d", "competition": "Egyptian Premier League", "kickoff": "2026-09-27", "home": "المصري", "away": "الأهلي", "home_score": 1, "away_score": 0}]
SE.load_data = lambda: _D(articles=[art], archive=nt)
assert run([], argv=("--events", "2026-11-08")) == 0
msgs = feeds(); assert len(msgs) == 1, msgs
assert msgs[0] == ("📊 حسام حسن يرحل عن تدريب منتخب مصر.\nأرقامه في المباريات التي تغطيها بيانات الجون (منذ 25 سبتمبر 2026):\n"
                   "مباراتان: فوز 1، تعادل 1، خسارة 0.\nالأهداف: 5 له، 0 عليه.\nأكبر فوز: جنوب السودان 0 - 5 مصر (29 سبتمبر 2026).\n"
                   "الخبر كاملًا: https://elgoon.com/a/1095\n#الجون #منتخب_مصر"), msgs[0]
assert store.get_post(SE.KIND_COACH, "1095")["post_id"]
assert run([], argv=("--events", "2026-11-08")) == 0 and feeds() == []
assert SE.coach_left([art], nt, datetime.date(2026, 11, 12)) == [], "an article older than two days is not news"
assert SE.coach_left([dict(art, title="حسام حسن يعلن قائمة مصر")], nt) == []
assert SE.coach_left([art], [nt[3]], datetime.date(2026, 11, 8)) == [], "no NT match in the archive -> no numbers -> no post"
ev = SE.coach_left([dict(art, title="رسميًا.. إقالة علي ماهر من تدريب منتخب مصر")], nt, datetime.date(2026, 11, 8))
assert len(ev) == 1 and ev[0]["text"].startswith("📊 علي ماهر يرحل"), ev
print("23 OK: a coach leaving the NT -> his record from the archive, with the window it covers, posted once")

# 24) the event SHAPE (a permanent editorial line, 2026-11-08): every kind is
# registered once, every event carries the structured data an article could
# be written from, and the post text is render()ed from that data - so a
# detector added later gets the store, the switch, --dry and --pending for free
assert [k for k, _ in SE.DETECTORS] == [SE.KIND_CUP, SE.KIND_HALF, SE.KIND_COACH, SE.KIND_OTD, SE.KIND_FORM, SE.KIND_STREAK]
SE.load_data = lambda: _D(fixtures=CUP, archive=[plain, big, derby] + nt, articles=[art], moments=[mo],
                          standings=[{"competition": "Egyptian Premier League", "season_label": "2026/27", "table": tbl}], scorers=SC)
evs = SE.detect(today=datetime.date(2026, 11, 8))
assert [e["kind"] for e in evs] == [SE.KIND_CUP, SE.KIND_HALF, SE.KIND_COACH], [e["kind"] for e in evs]
for e in evs + SE.detect(today=datetime.date(2027, 10, 11)):
    for k in ("kind", "ref", "title", "competition", "lines", "link", "link_label", "tags", "text"):
        assert k in e, (e["kind"], k)
    assert e["text"] == SE.render(e) and e["text"].split("\n")[-1].startswith("#الجون") and all(ln.strip() for ln in e["lines"]), e["text"]
cup, half, coach = evs
assert cup["pairs"][0] == {"match_id": 101, "home": "الأهلي", "away": "الزمالك", "kickoff": "2026-12-01", "koff_time": "20:00"} and cup["round_next"] == "دور الـ16"
assert half["table"]["top"][0]["team"] == "Club 1" and half["table"]["bottom"][-1]["pos"] == 20 and half["scorer"]["goals"] == 8 and half["rounds"] == 19
assert coach["record"] == {"p": 2, "w": 1, "d": 1, "l": 0, "gf": 5, "ga": 0} and coach["best"]["match_id"] == "b" and coach["article"]["article_id"] == "1095"
# --events --pending: the count publish.yml dispatches on (unposted events only)
reset_state()
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    run([], argv=("--events", "--pending"))
assert buf.getvalue().strip() == "3", buf.getvalue()
os.environ["FB_EVENTS"] = "on"
assert run([], argv=("--events", "2026-11-08")) == 0 and len(feeds()) == 3
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    run([], argv=("--events", "--pending"))
assert buf.getvalue().strip() == "0", buf.getvalue()
print("24 OK: one registry, one event shape with the structured data, text rendered from it; --events --pending counts the unposted")

# 25-27) club FORM before a match + STREAK milestones (user example 2026-11-09:
# a club's last results as marks with the next fixture). The event goes out as
# the form CARD (a photo post) with the text as its caption, once per ref.
import re as _re
import form_card as FCard
import form_reel as FReel
import fb_reel as FReelBase
# test 15 replaced fp.post_photo; this one records the card's size and caption (a real JPEG is > 20 kB)
_cards = []
fp.post_photo = lambda token, img, caption: (_cards.append((len(img), caption)), f"PHOTO_{len(_cards)}")[1]
def photos():
    out = [c for n, c in _cards if n > 20000]
    assert len(out) == len(_cards), [n for n, _ in _cards]
    _cards.clear()
    return out
_R = lambda mid, kick, h, a, hs, as_, comp="Primera Division": {
    "match_id": mid, "competition": comp, "kickoff": kick, "koff_time": "22:00", "home": h, "away": a,
    "home_score": hs, "away_score": as_, "home_badge": None, "away_badge": None}
BAR = "FC Barcelona"
# eight finished matches, oldest first: W W W L D W W W (the last three wins)
FORM8 = [_R(1, "2026-10-01", BAR, "Getafe CF", 3, 0), _R(2, "2026-10-05", "Sevilla FC", BAR, 1, 4),
         _R(3, "2026-10-13", "Galatasaray SK", BAR, 1, 4, "UEFA Champions League"), _R(4, "2026-10-25", BAR, "Real Madrid CF", 1, 2),
         _R(5, "2026-10-28", "Valencia CF", BAR, 2, 2), _R(6, "2026-10-31", BAR, "Deportivo Alavés", 6, 1),
         _R(7, "2026-11-03", BAR, "Aston Villa FC", 3, 0, "UEFA Champions League"), _R(8, "2026-11-08", "Club Atlético de Madrid", BAR, 1, 2)]
NEXT = {"match_id": 564749, "competition": "Primera Division", "kickoff": "2026-11-22", "koff_time": "15:00",
        "home": BAR, "away": "Villarreal CF", "status": "UPCOMING", "home_score": None, "away_score": None,
        "home_badge": None, "away_badge": None}
SE.load_data = lambda: _D(matches=[NEXT], archive=FORM8)
reset_state(); os.environ["FB_EVENTS"] = "on"; os.environ.pop("FB_REELS", None)
# 25) the fixture is within 24 h of the given day -> ONE photo post, the caption = headline + lines + link + tags; a second run is a no-op
assert run([], argv=("--events", "2026-11-22")) == 0
caps = photos(); assert len(caps) == 1 and feeds() == [], (caps, feeds())
assert caps[0] == ("📊 برشلونة يدخل مواجهة فياريال بـ3 انتصارات متتالية.\nآخر 8 مباريات: فوز 6، تعادل 1، خسارة 1.\nالأهداف: 25 له، 8 عليه.\n"
                   "الدوري الإسباني: برشلونة × فياريال، الأحد 22 نوفمبر الساعة 15:00 بتوقيت القاهرة.\n"
                   "تفاصيل المباراة: https://elgoon.com/m/564749\n#الجون #برشلونة #فياريال"), caps[0]
rec = store.get_post(SE.KIND_FORM, "form:barcelona:564749"); assert rec and rec["post_id"], rec
assert run([], argv=("--events", "2026-11-22")) == 0 and photos() == [] and feeds() == [], "posted twice"
# the day before: the fixture is 39 h away -> nothing; postponed -> nothing; too few results -> nothing
assert SE.club_form_before_match([NEXT], [], FORM8, datetime.date(2026, 11, 21)) == []
assert SE.club_form_before_match([dict(NEXT, status="POSTPONED")], [], FORM8, datetime.date(2026, 11, 22)) == []
assert SE.club_form_before_match([NEXT], [], FORM8[-4:], datetime.date(2026, 11, 22)) == []
# the fixture may come from fixtures.json alone; the rows are the LAST n (10 at most), newest last; the run counts every result held
ev = SE.club_form_before_match([], [{"competition": "Primera Division", "rounds": [{"round": 13, "matches": [NEXT]}]}], FORM8, datetime.date(2026, 11, 22))
assert len(ev) == 1 and [r["mark"] for r in ev[0]["rows"]] == ["W", "W", "W", "L", "D", "W", "W", "W"] and ev[0]["run"] == ["W", 3], ev[0]["rows"]
assert ev[0]["rows"][-1] == {"match_id": 8, "date": "2026-11-08", "competition": "Primera Division", "comp_label": "الدوري الإسباني",
                             "opponent": "أتلتيكو مدريد", "opponent_badge": None, "club_badge": None, "home": False, "gf": 2, "ga": 1, "mark": "W"}
assert ev[0]["next"]["match_id"] == 564749 and ev[0]["next"]["club_home"] is True and ev[0]["record"]["p"] == 8
ev10 = SE.club_form_before_match([NEXT], [], FORM8 + [_R(9, "2026-09-01", BAR, "X", 1, 0), _R(10, "2026-09-05", BAR, "Y", 1, 0), _R(11, "2026-09-09", BAR, "Z", 1, 0)],
                                 datetime.date(2026, 11, 22), n=12)
assert len(ev10[0]["rows"]) == SE.FORM_MAX == 10, len(ev10[0]["rows"])
# a 1-win window reads «بانتصار واحد», a winless run reads «بلا فوز في آخر N مباريات»
poor = [_R(i, f"2026-10-{10 + i:02d}", BAR, "X", 0, 1 if i < 8 else 0) for i in range(1, 9)]
ev = SE.club_form_before_match([NEXT], [], poor, datetime.date(2026, 11, 22))
assert ev[0]["title"] == "برشلونة يدخل مواجهة فياريال بلا فوز في آخر 8 مباريات", ev[0]["title"]
one = poor[:-1] + [_R(8, "2026-10-18", BAR, "X", 1, 0)]
ev = SE.club_form_before_match([NEXT], [], one, datetime.date(2026, 11, 22))
assert ev[0]["title"] == "برشلونة يدخل مواجهة فياريال بانتصار واحد في آخر 8 مباريات", ev[0]["title"]
print("25 OK: a fixture inside 24 h -> the form card posted once (headline names the real run); 39 h away / postponed / thin record -> nothing")

# 26) a streak milestone the last match completed, when no fixture is inside the window; ref = the last match
WINS5 = [_R(100 + i, f"2026-11-0{i}", BAR, f"Club {i}", 2, 0) for i in range(1, 6)]   # ids apart from FORM8 (the pool dedups by match_id)
SE.load_data = lambda: _D(matches=[], archive=FORM8[:3] + WINS5)        # W W W then five more wins = 8 in a row
reset_state()
assert run([], argv=("--events", "2026-11-06")) == 0
caps = photos(); assert len(caps) == 1 and feeds() == [], (caps, feeds())
assert caps[0].startswith("📊 برشلونة يحقق 8 انتصارات متتالية.\nآخر مباراة: برشلونة 2 - 0 Club 5 في الدوري الإسباني (5 نوفمبر 2026).\n"
                          "آخر 8 مباريات: فوز 8، تعادل 0، خسارة 0.\nالأهداف: 21 له، 2 عليه.\n"), caps[0]
assert caps[0].endswith("تفاصيل المباراة: https://elgoon.com/m/105\n#الجون #برشلونة #Club_5"), caps[0]
assert store.get_post(SE.KIND_STREAK, "streak:barcelona:105")["post_id"]
assert run([], argv=("--events", "2026-11-06")) == 0 and photos() == [], "posted twice"
# four wins in a row -> no milestone; a last match older than two days -> too late; a fixture inside 24 h -> the form post instead
assert SE.club_streak([], [], FORM8[:3] + [_R(99, "2026-10-20", BAR, "L", 0, 1)] + WINS5[:4], datetime.date(2026, 11, 5)) == []
assert SE.club_streak([], [], FORM8[:3] + WINS5, datetime.date(2026, 11, 9)) == [], "a streak is news the night it happens"
assert SE.club_streak([dict(NEXT, kickoff="2026-11-06", koff_time="20:00")], [], FORM8[:3] + WINS5, datetime.date(2026, 11, 6)) == []
# the first defeat after five wins; five without a win
loss = _R(109, "2026-11-07", "Club 9", BAR, 1, 0)
ev = SE.club_streak([], [], FORM8[:3] + WINS5 + [loss], datetime.date(2026, 11, 8))
assert len(ev) == 1 and ev[0]["milestone"] == {"kind": "first-loss", "n": 8} and ev[0]["title"] == "برشلونة يخسر لأول مرة بعد 8 انتصارات متتالية", ev
dry5 = [_R(200 + i, f"2026-11-0{i}", BAR, f"Club {i}", 1, 1 if i % 2 else 2) for i in range(1, 6)]
ev = SE.club_streak([], [], FORM8[:3] + dry5, datetime.date(2026, 11, 6))
assert len(ev) == 1 and ev[0]["milestone"] == {"kind": "winless", "n": 5} and ev[0]["title"] == "برشلونة بلا فوز في آخر 5 مباريات", ev
assert ev[0]["rows"][-1]["mark"] == "D" and SE.MARKS["D"] == "➖"
print("26 OK: 5 wins in a row / first defeat after them / 5 without a win -> posted once the night of the match; 4 wins, a stale run or a fixture inside 24 h -> nothing")

# 27) the reel rides behind FB_REELS (fb_reel.enabled) through the store under kind "reel" / the event's ref;
#     the card falls back to a text post when it cannot be drawn
SE.load_data = lambda: _D(matches=[NEXT], archive=FORM8)
reset_state(); os.environ.pop("FB_REELS", None)
assert run([], argv=("--events", "2026-11-22")) == 0 and len(photos()) == 1
assert store.get_post(FReelBase.KIND, "form:barcelona:564749") is None, "no reel while FB_REELS is off"
reset_state(); os.environ["FB_REELS"] = "1"
_rendered = []
FReel.render = lambda ev, out=None, sheet=None: (_rendered.append(ev["ref"]) or ("x.mp4", True, 14.4))
FReelBase.post_reel = lambda token, path, desc: "VID_1"
assert run([], argv=("--events", "2026-11-22")) == 0 and len(photos()) == 1
assert _rendered == ["form:barcelona:564749"] and store.get_post(FReelBase.KIND, "form:barcelona:564749")["post_id"] == "VID_1"
assert run([], argv=("--events", "2026-11-22")) == 0 and _rendered == ["form:barcelona:564749"], "reel rendered twice"
os.environ.pop("FB_REELS", None)
reset_state()
_ok = FCard.render_bytes
FCard.render_bytes = lambda ev, **kw: (_ for _ in ()).throw(RuntimeError("no font"))
assert run([], argv=("--events", "2026-11-22")) == 0 and photos() == [] and len(feeds()) == 1 and feeds()[0].startswith("📊 برشلونة يدخل")
FCard.render_bytes = _ok
assert run([], argv=("--events", "2026-11-22", "--dry")) == 0 and photos() == [] and feeds() == []
print("27 OK: the form reel only behind FB_REELS, once per ref under kind reel; a card that fails falls back to the text; --dry posts nothing")
