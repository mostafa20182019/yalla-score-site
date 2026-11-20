# -*- coding: utf-8 -*-
r"""Web push for «تابع فريقك» (push_team.py, 2026-11-19), against a local
SQLite store and a fake sender.

    python tests/test_push_team.py      (from the repo root)

What it guards: a dispatched game reaches the followers of the clubs that
play in it and nobody else (exact names, the club's own competitions - never
the Saudi or the Libyan «الأهلي»); a goal / kick-off / full-time is pushed only
after its Facebook card is on record, once per club; half-time is not pushed;
club news goes to the club's followers only when the bell did not already send
it to everyone, inside the quiet hours and caps; nothing here can fail the job
it rides in; the Worker keeps the club on the subscription row.
"""
import datetime
import io
import json
import os
import sys
import tempfile
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
for k in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_D1_ID", "VAPID_PRIVATE_KEY"):
    os.environ.pop(k, None)
os.environ["D1_SQLITE"] = os.path.join(tempfile.mkdtemp(), "pt.sqlite")

import store                     # noqa: E402
import push_send as P            # noqa: E402
import push_team as T            # noqa: E402

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


store.init_schema()
CAI = ZoneInfo("Africa/Cairo")


def cai(h, m=0):
    return datetime.datetime(2026, 11, 19, h, m, tzinfo=CAI)


def reset():
    for t in ("fb_posted", "fb_failed", "push_subs"):
        store.sql(f"DELETE FROM {t}", [])


def sub(ep, team):
    store.sql("INSERT INTO push_subs (endpoint, p256dh, auth, created_at, team) VALUES (?, ?, ?, 0, ?)",
              [ep, "p" * 87, "a" * 22, team])


def fake(results=None):
    calls = []

    def s(sb, data, key):
        calls.append((sb["endpoint"], json.loads(data)["title"]))
        return (results or {}).get(sb["endpoint"], ("ok", 201))
    return s, calls


def G(c, h, a, hs=1, as_=0, i=900):
    return {"id": i, "c": c, "h": h, "a": a, "hs": hs, "as": as_}


# ------------------------------------------------------------- 1. whose game
ck("1 an Egyptian league match between two club pages reaches both",
   T.slugs_for_game(G(552, "الأهلي", "بيراميدز")) == ["al-ahly", "pyramids"])
ck("2 the Saudi «الأهلي» (Saudi Pro League) is not the Egyptian club: its own page since 2026-11-20, never al-ahly",
   sorted(T.slugs_for_game(G(649, "الفتح", "الأهلي"))) == ["al-ahli-saudi", "al-fateh"])
ck("3 «الأهلي طرابلس» is not «الأهلي»: exact names", T.slugs_for_game(G(627, "الأهلي طرابلس", "الزمالك")) == ["zamalek"])
ck("4 a European club is matched by its Arabic name (the payload is the Arabic feed)",
   T.slugs_for_game(G(7, "ليفربول", "تشيلسي")) == ["liverpool", "chelsea"])
ck("5 the national team's page takes the qualifiers, not the under-17 side",
   T.slugs_for_game(G(588, "مالاوي", "مصر")) == ["egypt"] and T.slugs_for_game(G(5582, "مصر تحت 17", "اليونان تحت 17")) == [])
ck("6 a match of clubs with no page reaches nobody; a league page's club reaches its own followers",
   T.slugs_for_game(G(552, "فاركو", "حرس الحدود")) == [] and T.slugs_for_game(G(552, "سموحة", "زد")) == ["smouha", "zed"])

# ------------------------------------------------------------- 2. payloads
gp = json.loads(T.goal_payload(G(552, "الأهلي", "بيراميدز"), {"s": "h", "p": "إمام عاشور", "m": "34"}))
ck("7 goal: the score line as the title, the scorer and minute as the body, the match page as the link",
   gp["title"] == "⚽ هدف! الأهلي 1 - 0 بيراميدز" and "إمام عاشور" in gp["body"] and "34" in gp["body"]
   and gp["url"] == "https://elgoon.com/m/900" and gp["tag"] == "g-900", str(gp))
fp = json.loads(T.whistle_payload("ft", G(552, "الأهلي", "بيراميدز", 2, 1), [{"s": "h", "p": "تريزيجيه", "m": "88"}]))
kp = json.loads(T.whistle_payload("ko", G(552, "الأهلي", "بيراميدز", 0, 0), []))
ck("8 full time: the result and the scorers; kick-off: the two names and the competition; no hashtag, no link text",
   fp["title"].startswith("🏁 انتهت المباراة: الأهلي 2 - 1") and "تريزيجيه" in fp["body"] and "#" not in fp["body"]
   and "elgoon" not in fp["body"] and kp["title"] == "🔔 انطلقت المباراة: الأهلي × بيراميدز" and kp["body"] == "الدوري المصري",
   str((fp, kp)))
ck("9 one tag per game: a later event replaces the earlier one on the phone", gp["tag"] == fp["tag"] == kp["tag"])

# ------------------------------------------------------------- 3. match events
PUB, PRIV = P.keygen()
T.C.VAPID_PUBLIC_KEY = PUB
os.environ["VAPID_PRIVATE_KEY"] = PRIV
GOAL = json.dumps({"g": G(552, "الأهلي", "بيراميدز"), "seq": 1, "ev": {"s": "h", "p": "إمام عاشور", "m": "34"}})

reset()
sub("https://e/ahly1", "al-ahly")
sub("https://e/ahly2", "al-ahly")
sub("https://e/pyr", "pyramids")
sub("https://e/zam", "zamalek")
sub("https://e/none", None)
snd, calls = fake()
T.goal(GOAL, sender=snd)
ck("10 a goal whose Facebook card is not on record is NOT pushed (its guards are ours)", calls == [])
store.record_post("goal", "900:1", "fb_1", title="x")
T.goal(GOAL, sender=snd)
ck("11 once the card is posted: the followers of the two clubs, nobody else",
   sorted(e for e, _ in calls) == ["https://e/ahly1", "https://e/ahly2", "https://e/pyr"], str(calls))
n = len(calls)
T.goal(GOAL, sender=snd)
ck("12 a second dispatch of the same goal buzzes nobody again", len(calls) == n)
ck("13 it is recorded once per club", store.get_post(T.KIND, "goal:900:1:al-ahly")["post_id"] == "2/2"
   and store.get_post(T.KIND, "goal:900:1:pyramids")["post_id"] == "1/1")

snd, calls = fake()
for kind in ("ko", "ht", "ft"):
    store.record_post(kind, "900", "fb_w", title="x")
    T.whistle(json.dumps({"kind": kind, "g": G(552, "الأهلي", "بيراميدز", 2, 1), "goals": []}), sender=snd)
ck("14 kick-off and full time are pushed, half-time is not",
   len(calls) == 6 and not any("الشوط" in t for _, t in calls), str(calls))

reset()
sub("https://e/dead", "al-ahly")
sub("https://e/live", "al-ahly")
store.record_post("goal", "900:1", "fb_1", title="x")
snd, calls = fake({"https://e/dead": ("gone", 410)})
T.goal(GOAL, sender=snd)
ck("15 an endpoint the push service calls gone is deleted",
   [r["endpoint"] for r in store.sql("SELECT endpoint FROM push_subs", [])] == ["https://e/live"])

reset()
sub("https://e/a", "al-ahly")
store.record_post("goal", "900:1", "fb_1", title="x")
snd, calls = fake({"https://e/a": ("fail", 500)})
T.goal(GOAL, sender=snd)
_r = store.get_post(T.KIND, "goal:900:1:al-ahly")
ck("16 nobody reached: the claim is released, so the next dispatch can try again", not _r or not _r.get("post_id"))
ck("17 a broken payload and a wrong kind never raise and never exit non-zero",
   T.goal("{not json", sender=snd) == 0 and T.whistle(json.dumps({"kind": "xx", "g": {}}), sender=snd) == 0)
os.environ.pop("VAPID_PRIVATE_KEY")
snd, calls = fake()
ck("18 no private key: nothing is sent", T.goal(GOAL, sender=snd) == 0 and calls == [])
os.environ["VAPID_PRIVATE_KEY"] = PRIV


# ------------------------------------------------------------- 4. club news
def art(aid, title, pub, **kw):
    a = {"article_id": str(aid), "title": title, "summary": "ملخص", "pub_ts": pub.isoformat(),
         "image_url": "https://elgoon.com/media/x.jpg"}
    a.update(kw)
    return a


AHLY = "الأهلي يعلن تفاصيل إصابة لاعبه قبل القمة"
BARCA = "برشلونة يحسم صفقة جديدة في الشتاء"
OTHER = "إنتر ميامي يتعاقد مع مدافع جديد"
reset()
sub("https://e/ahly", "al-ahly")
sub("https://e/barca", "barcelona")
sub("https://e/none", None)
ARTS = [art(1, AHLY, cai(12)), art(2, BARCA, cai(12)), art(3, OTHER, cai(12))]
T.FB.load_articles = lambda: ARTS
snd, calls = fake()
T.news(now=cai(12, 10), sender=snd, live=lambda u: True)
ck("19 each club's story goes to that club's followers only; a story about no club page goes to nobody",
   sorted(calls) == [("https://e/ahly", AHLY), ("https://e/barca", BARCA)], str(calls))
T.news(now=cai(12, 50), sender=snd, live=lambda u: True)
ck("20 the same story is never sent twice", len(calls) == 2)

reset()
sub("https://e/ahly", "al-ahly")
store.record_post(P.KIND, "1", "9/9", title=AHLY)        # the bell sent article 1 to everyone
snd, calls = fake()
T.news(now=cai(12, 10), sender=snd, live=lambda u: True)
ck("21 a story the bell already sent to everyone is not sent to the followers again",
   not any(t == AHLY for _, t in calls), str(calls))

reset()
sub("https://e/ahly", "al-ahly")
snd, calls = fake()
T.news(now=cai(3, 0), sender=snd, live=lambda u: True)
ck("22 club news keeps the quiet hours (01:00-08:00 Cairo)", calls == [])
T.news(now=cai(12, 10), sender=snd, live=lambda u: False)
ck("23 ...and waits for the page to be live", calls == [])
ARTS[:] = [art(10 + i, AHLY + f" {i}", cai(9 + i)) for i in range(8)]
_moved = set()
for i in range(8):
    T.news(now=cai(9 + i, 20), sender=snd, live=lambda u: True)
    # the store stamps the real clock; move what THIS run recorded to the run's own time
    for r in store.sql("SELECT ref_id FROM fb_posted WHERE kind = ?", [T.KIND]):
        if r["ref_id"] not in _moved:
            _moved.add(r["ref_id"])
            store.sql("UPDATE fb_posted SET posted_at = ?, claimed_at = ? WHERE kind = ? AND ref_id = ?",
                      [int(cai(9 + i, 20).timestamp()), int(cai(9 + i, 20).timestamp()), T.KIND, r["ref_id"]])
ck(f"24 at most {T.NEWS_CAP} club stories a day", len(calls) == T.NEWS_CAP, str(len(calls)))
ARTS[:] = [art(30, AHLY, cai(12), upgraded_ts="2026-11-19T12:00:00")]
reset()
sub("https://e/ahly", "al-ahly")
snd, calls = fake()
T.news(now=cai(12, 10), sender=snd, live=lambda u: True)
ck("25 an upgraded archive piece is not news for the followers either", calls == [])

# ------------------------------------------------------------- 5. the wiring
wf = io.open(".github/workflows/fb-post.yml", encoding="utf-8").read()
pub = io.open(".github/workflows/publish.yml", encoding="utf-8").read()
ck("26 fb-post.yml pushes right AFTER the goal and whistle cards, and cannot fail on it",
   wf.index('fb_post.py --goal "$GOAL"') < wf.index('push_team.py --goal "$GOAL" | tee -a /tmp/fb.txt || true')
   and wf.index('fb_post.py --whistle "$WHISTLE"') < wf.index('push_team.py --whistle "$WHISTLE" | tee -a /tmp/fb.txt || true')
   and wf.count("VAPID_PRIVATE_KEY: ${{ secrets.VAPID_PRIVATE_KEY }}") == 1)
ck("27 publish.yml sends club news after the bell's own run, and keeps the bell's exit code",
   pub.index("python push_send.py --auto; rc=$?") < pub.index("python push_team.py --news || true") < pub.index("exit $rc", pub.index("push_team.py --news")))
js = io.open("push.js", encoding="utf-8").read()
ck("28 the Worker keeps the club on the row; a body without the key leaves it alone",
   "ADD COLUMN team TEXT" in js and "team = CASE WHEN ? = 1 THEN excluded.team ELSE push_subs.team END" in js
   and "/^[a-z0-9-]{2,40}$/" in js)
pj = io.open("site_src/snippets/push_js.html", encoding="utf-8").read()
fj = io.open("site_src/snippets/follow_js.html", encoding="utf-8").read()
ck("29 the browser sends the followed club with the subscription and tells us when it changes",
   "withTeam(sub.toJSON())" in pj and "window.__pushTeam=function" in pj and "if(window.__pushTeam) window.__pushTeam();" in fj)
pv = io.open("site_src/templates/privacy.html", encoding="utf-8").read()
ck("30 /privacy says what is kept and states the same cap the code enforces",
   "تابع فريقك" in pv and T.NEWS_CAP == 4 and "أربعة إشعارات" in pv and "في أي ساعة" in pv)
sch = io.open("d1_schema.sql", encoding="utf-8").read()
ck("31 the schema file names the column", "team        TEXT" in sch)

print("ALL OK" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
