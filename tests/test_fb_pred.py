# -*- coding: utf-8 -*-
"""fb_post.py --prediction: the engagement post before a big match (growth
plan 2026-10-08). Text from the model's block, numbers only, no betting
disclaimer, the card drawn; no network, no token."""
import sys, os, io, tempfile
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _k in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_D1_ID", "FB_PAGE_TOKEN"):
    os.environ.pop(_k, None)
os.environ["D1_SQLITE"] = os.path.join(tempfile.mkdtemp(), "state.sqlite")
import store
import fb_post as fp
store.init_schema()

fails = 0


def ck(name, cond, extra=""):
    global fails
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f"  [{extra}]" if extra and not cond else ""))
    fails += 0 if cond else 1


m = {"match_id": 4804684, "competition": "Egyptian Premier League", "home": "الزمالك", "away": "الأهلي",
     "kickoff": "2026-10-11", "koff_time": "20:00", "status": "UPCOMING", "round": 6}
pr = {"home_win": "41%", "draw": "31%", "away_win": "28%",
      "likely_scores": [{"score_home_away": "1-0", "prob": "16%"}], "over_2_5": "30%",
      "record": {"all": {"scored": 384, "hits": 190}},
      "disclaimer": "التوقعات احتمالات إحصائية ... وليست نصيحة للمراهنة."}
t = fp.prediction_text(m, pr, tv="أون سبورت")
print(t)
ck("1 title line names both clubs", t.startswith("توقع يلا سكور قبل المباراة: الزمالك × الأهلي"))
ck("2 the three probabilities are in the post", all(x in t for x in ("41%", "31%", "28%")))
ck("3 the likely score and over-2.5 are in the post", "1-0 (16%)" in t and "2.5 هدف 30%" in t)
ck("4 the record is stated", "190 من 384" in t)
ck("5 the channel is named", "على أون سبورت" in t)
ck("6 NEVER the betting disclaimer (user rule 2026-10-08)", "مراهنة" not in t)
ck("7 the match page link, not an article link", f"{fp.SITE}/m/4804684" in t and "/a/" not in t)
ck("8 hashtags: #يلا_سكور first, both clubs", "#يلا_سكور #الزمالك #الأهلي" in t)
ck("9 a question invites comments", "👇" in t and "توقعك" in t)

# the dry run against the real data: draws the card, posts nothing
import matchup_card as MC
out = os.path.join(tempfile.gettempdir(), "pred-test.jpg")
MC.for_match(m, out, top_label="توقع يلا سكور")
ck("10 the card is drawn for the match", os.path.exists(out) and os.path.getsize(out) > 20000)

ck("11 a finished match is refused", fp.prediction_post("", "0", dry=True) == 1)


# ---- the OFF switch (user, 2026-10-18: no prediction posts on Facebook for now)
import datetime as _dt
ck("15 FB_PREDICTIONS defaults to OFF", fp.FB_PREDICTIONS is False)
news = {"article_id": "901", "kind": None, "title": "الزمالك يجدد لفتوح", "fb_post": "خبر"}
prev = {"article_id": "902", "kind": "preview", "match_id": "1", "title": "توقع يلا سكور: الأهلي × الزمالك", "fb_post": "x"}
ana = {"article_id": "903", "kind": "analysis", "match_id": "2", "title": "ديربي القاهرة بالأرقام", "fb_post": "x"}
rep = {"article_id": "904", "kind": "report", "match_id": "3", "title": "تقرير: الأهلي يفوز 2-1", "fb_post": "🤖 نموذج يلا سكور أصاب"}
plain_prev = {"article_id": "905", "kind": "preview", "match_id": "4", "title": "قبل المباراة: ليدز × يونايتد", "fb_post": "الترتيب والغيابات"}
ck("16 a prediction-titled preview and an analysis are prediction posts",
   fp.is_prediction_post(prev) and fp.is_prediction_post(ana))
ck("17 news, a plain preview and a REPORT (even one judging our prediction) are not",
   not fp.is_prediction_post(news) and not fp.is_prediction_post(plain_prev) and not fp.is_prediction_post(rep))
_pd, _oh = fp.article_pub_dt, fp.open_hours
fp.article_pub_dt = lambda a: _dt.datetime.now(_dt.timezone.utc)
fp.open_hours = lambda p: 1.0
try:
    got = [a["article_id"] for a in fp.pending([news, prev, ana, rep, plain_prev])]
    ck("18 --auto/--pending leave ONLY the prediction posts out while the switch is off (the report stays)", got == ["901", "904", "905"], str(got))
    fp.FB_PREDICTIONS = True
    got = [a["article_id"] for a in fp.pending([news, prev, ana])]
    ck("19 ...and take them again with FB_PREDICTIONS=on", got == ["901", "902", "903"], str(got))
finally:
    fp.FB_PREDICTIONS = False
    fp.article_pub_dt, fp.open_hours = _pd, _oh
ck("20 --prediction refuses while the switch is off (dry runs still draw)", fp.prediction_post("tok", "4804684") == 1)

# ---- the kick-off caption (2026-10-18): no score, no scorers, the live link
kg = {"id": 985, "c": 7, "h": "ليفربول", "a": "فياريال", "hs": 0, "as": 0}
kc = fp.whistle_caption("ko", kg, [{"s": "h", "p": "x", "m": "1"}])
ck("21 the kick-off caption opens with the bell and the two names, no score", kc.startswith("🔔 انطلقت المباراة: ليفربول × فياريال") and "0 - 0" not in kc)
ck("22 ...carries the live link and the hashtags, and ignores any goal list", "https://yallascore.site/m/985" in kc and "#يلا_سكور" in kc and "x 1'" not in kc)

# ---- the line-up caption (2026-10-20): with the card, no names in the text
xd = {"gid": "4804707", "comp": "الدوري المصري",
      "home": {"name": "بترول أسيوط", "formation": "4-3-3", "players": [{"name": "أمجد يوسف"}]},
      "away": {"name": "الزمالك", "formation": "", "players": [{"name": "عمر جابر"}]}}
xc = fp.xi_caption(xd, names=False)
ck("23 the card's caption is the title line, the competition, the link and the tags - no names",
   xc.splitlines()[0] == "📋 التشكيل الرسمي لمباراة بترول أسيوط × الزمالك" and "أمجد" not in xc and "عمر جابر" not in xc
   and "https://yallascore.site/m/4804707" in xc and "#بترول_أسيوط" in xc and "الدوري المصري" in xc, xc)
ck("24 the text-only fallback still lists the eleven", "أمجد يوسف" in fp.xi_caption(xd) and "(4-3-3)" in fp.xi_caption(xd))

# ---- --xi --redo (2026-10-20): the text post is deleted and the card posted
import json as _json
import lineup_card as LC
_game = _json.load(open("tests/fixtures/game_4742043_lineups.json", encoding="utf-8"))["game"]
calls = []
_s, _r, _pe, _dp, _pp = LC._s365_game, LC.render_bytes, fp.post_exists, fp.delete_post, fp.post_photo
LC._s365_game = lambda gid: _game
LC.render_bytes = lambda data, photos_on=True: b"\xff\xd8\xffcard"
fp.post_exists = lambda tok, pid: calls.append(("exists", pid)) or True
fp.delete_post = lambda tok, pid: calls.append(("delete", pid)) or True
fp.post_photo = lambda tok, img, cap: calls.append(("photo", cap.splitlines()[0])) or "777_new"
store.record_post("xi", "4742043", "777_old", title="xi 4742043")
ck("25 --xi on a posted game does nothing", fp.xi_post("tok", "4742043") == 0 and calls == [])
rc = fp.xi_post("tok", "4742043", redo=True)
ck("26 --redo deletes the old post, posts the card with the no-names caption, records the new id",
   rc == 0 and calls == [("exists", "777_old"), ("delete", "777_old"), ("photo", "📋 التشكيل الرسمي لمباراة مانشستر سيتي × إبسويتش تاون")]
   and store.get_post("xi", "4742043")["post_id"] == "777_new", str(calls))
calls.clear()
LC._s365_game = lambda gid: {}
ck("27 --redo refuses while the card cannot be drawn: the old post stays", fp.xi_post("tok", "4742043", redo=True) == 1 and calls == [])
LC._s365_game, LC.render_bytes, fp.post_exists, fp.delete_post, fp.post_photo = _s, _r, _pe, _dp, _pp

# ---- the nightly results card (2026-10-22)
import datetime as _d2
from zoneinfo import ZoneInfo as _Z
ck("28 the card's date: before 04:00 Cairo it is the previous day",
   fp.daycard_date(_d2.datetime(2026, 10, 23, 1, 16, tzinfo=_Z("Africa/Cairo"))) == "2026-10-22"
   and fp.daycard_date(_d2.datetime(2026, 10, 23, 12, 0, tzinfo=_Z("Africa/Cairo"))) == "2026-10-23")
_dm = [{"match_id": 1, "competition": "Premier League", "home": "Liverpool FC", "away": "Everton FC", "kickoff": "2026-10-22", "koff_time": "21:00", "status": "FINISHED", "home_score": 2, "away_score": 0},
       {"match_id": 2, "competition": "UEFA Europa League", "home": "AS Roma", "away": "Lille OSC", "kickoff": "2026-10-22", "koff_time": "19:45", "status": "FINISHED", "home_score": 1, "away_score": 1},
       {"match_id": 3, "competition": "Serie A", "home": "Juventus FC", "away": "AC Milan", "kickoff": "2026-10-22", "koff_time": "21:45", "status": "UPCOMING"},
       {"match_id": 4, "competition": "Egyptian Premier League", "home": "الزمالك", "away": "سموحة", "kickoff": "2026-10-22", "koff_time": "17:00", "status": "FINISHED", "home_score": 1, "away_score": 0},
       {"match_id": 5, "competition": "Bundesliga", "home": "FC Bayern München", "away": "VfB Stuttgart", "kickoff": "2026-10-21", "koff_time": "19:30", "status": "FINISHED", "home_score": 3, "away_score": 1}]
got = fp.daycard_matches(_dm, "2026-10-22")
ck("29 the card takes the day's FINISHED matches of the nine leagues only, curated first (Zamalek, Liverpool), not the Europa League, not tomorrow",
   [m["match_id"] for m in got] == [4, 1], str([m["match_id"] for m in got]))
cap = fp.daycard_caption(got, "2026-10-22")
ck("30 the caption: the title line, one line per result with the league, the matches link, the tags",
   cap.splitlines()[0].startswith("📊 نتائج أبرز مباريات اليوم") and "الزمالك 1 - 0 سموحة · الدوري المصري" in cap and "ليفربول 2 - 0 إيفرتون" in cap
   and "https://yallascore.site/matches" in cap and "#يلا_سكور" in cap, cap)
wf2 = io.open(".github/workflows/fb-post.yml", encoding="utf-8").read()
ck("31 the workflow takes daycard=results", "daycard:" in wf2 and 'python fb_post.py --daycard "$DAYCARD"' in wf2)

print()
print("ALL FB PREDICTION TESTS PASSED" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
