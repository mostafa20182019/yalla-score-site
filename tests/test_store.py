"""Tests for store.py against a real local SQLite file.

D1 *is* SQLite, so running the same statements against sqlite3 exercises the
actual logic — the schema, the claim race, ON CONFLICT, RETURNING. The only
part these tests cannot reach is the HTTP transport in store.sql().

The case that matters is 4: two concurrent claims on the same article. That is
the bug that posted article 422 to Facebook twice on 2026-09-07.
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for k in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_D1_ID"):
    os.environ.pop(k, None)                       # force the sqlite backend
db = os.path.join(tempfile.mkdtemp(), "t.sqlite")
os.environ["D1_SQLITE"] = db
import store  # noqa: E402

assert store.backend() == "sqlite", store.backend()
n = store.init_schema()
print(f"0 OK: schema applied ({n} statements) on the sqlite backend")

# 1) a fresh claim succeeds and is NOT yet a post
assert store.claim("article", 500, title="T500") is True
assert store.posted_ids("article") == set(), "an open claim must not count as posted"
row = store.get_post("article", 500)
assert row["post_id"] is None and row["title"] == "T500"
print("1 OK: claim opens a row, not a post")

# 2) recording the post closes the claim
store.record_post("article", 500, "PID_500", title="T500", og_ok=True)
assert store.posted_ids("article") == {"500"}
assert store.get_post("article", 500)["og_ok"] == 1
print("2 OK: record_post publishes the claim")

# 3) a second claim on a POSTED row is refused -> no duplicate
assert store.claim("article", 500) is False
print("3 OK: claiming an already-posted article is refused")

# 4) THE DUPLICATE BUG: two runs racing on the same NEW article.
#    Exactly one may win, and the loser must not post.
wins = [store.claim("article", 501), store.claim("article", 501)]
assert wins.count(True) == 1 and wins.count(False) == 1, wins
print("4 OK: concurrent claims -> exactly one winner (the duplicate is impossible)")

# 5) a claim that never became a post can be released and retried
store.release("article", 501)
assert store.get_post("article", 501) is None
assert store.claim("article", 501) is True
print("5 OK: released claim can be retried")

# 6) an ABANDONED claim (run died) is reclaimable only after the TTL
store.sql("UPDATE fb_posted SET claimed_at = ? WHERE kind='article' AND ref_id='501'",
          [int(time.time()) - store.CLAIM_TTL_SEC - 60])
assert store.claim("article", 501) is True, "a stale claim must be reclaimable"
store.sql("UPDATE fb_posted SET claimed_at = ? WHERE kind='article' AND ref_id='501'",
          [int(time.time())])
assert store.claim("article", 501) is False, "a FRESH claim must never be stolen"
print("6 OK: stale claims expire, fresh claims are protected")

# 7) release must not delete a real post
store.record_post("article", 501, "PID_501")
store.release("article", 501)
assert store.get_post("article", 501)["post_id"] == "PID_501"
print("7 OK: release never removes a published post")

# 8) failure counters
assert store.failed_count("card", 900) == 0
store.bump_failed("card", 900, "boom")
store.bump_failed("card", 900, "boom again")
assert store.failed_count("card", 900) == 2
store.clear_failed("card", 900)
assert store.failed_count("card", 900) == 0
print("8 OK: failure attempts count up and clear")

# 9) score-stability tracking
assert store.seen_get(900) == (None, None)
store.seen_set(900, "1-0")
s, t = store.seen_get(900)
assert s == "1-0" and t
store.seen_set(900, "2-0")                        # score changed -> timer resets
assert store.seen_get(900)[0] == "2-0"
store.seen_clear(900)
assert store.seen_get(900) == (None, None)
print("9 OK: seen score set/update/clear")

# 10) kinds are independent: an article and a card may share an id
assert store.claim("card", 500) is True
assert store.posted_ids("card") == set() and store.posted_ids("article") == {"500", "501"}
store.record_post("card", 500, "PID_C500", score="1-0")
assert store.posted_ids("card") == {"500"}
print("10 OK: article and card ids never collide")

# 11) predictions freeze once, and a scored row is immutable
rec = {"comp": "EPL", "home": "A", "away": "B", "kickoff": "2026-09-20",
       "koff_time": "20:00", "ph": 0.5, "pd": 0.3, "pa": 0.2, "lh": 1.4,
       "la": 0.9, "score": "1-0", "conf": "low", "ts": "2026-09-09"}
assert store.pred_freeze(700, rec) is True
assert store.pred_all()["700"]["home"] == "A"
rec2 = dict(rec, ph=0.9, score="2-0")
assert store.pred_freeze(700, rec2) is True, "an unplayed match may be refreshed"
assert store.pred_all()["700"]["ph"] == 0.9
assert store.pred_score(700, 1, 0, "H", "H", True, 0.35, True) is True
assert store.pred_score(700, 3, 3, "D", "H", False, 0.9, False) is False, \
    "a scored prediction must never be re-scored"
got = store.pred_all()["700"]
assert got["hs"] == 1 and got["as"] == 0 and got["hit"] == 1
assert store.pred_freeze(700, dict(rec, ph=0.1)) is False, \
    "a scored prediction must never be re-frozen (that would inflate accuracy)"
assert store.pred_all()["700"]["ph"] == 0.9
print("11 OK: predictions freeze once, scored rows are final")

# 11b) which model made it survives the round trip, and a scored row's
#      source can no longer be changed (the freeze that would carry it is refused)
assert store.pred_all()["700"]["src"] == "python", "no src given -> python"
orc = dict(rec, src="oracle", src_ts="2026-09-12")
assert store.pred_freeze(701, orc) is True
got = store.pred_all()["701"]
assert got["src"] == "oracle" and got["src_ts"] == "2026-09-12", got
assert store.pred_freeze(701, dict(rec, src="python")) is True, "unplayed -> may switch model"
assert store.pred_all()["701"]["src"] == "python"
assert store.pred_freeze(700, orc) is False
assert store.pred_all()["700"]["src"] == "python", "a scored row keeps its source"
print("11b OK: prediction source recorded, switchable while unplayed, fixed once scored")

# 12) counts + export shape
c = store.counts()
assert c["articles"] == 2 and c["cards"] == 1 and c["predictions"] == 2, c   # 700 + 701 (11b)
import json
store.FB_JSON = os.path.join(os.path.dirname(db), "fb.json")
store.PRED_JSON = os.path.join(os.path.dirname(db), "pred.json")
assert store.export_json() is True
fb = json.load(open(store.FB_JSON, encoding="utf-8"))
assert set(fb) == {"posted", "failed", "articles", "seen"}, set(fb)
assert fb["articles"]["500"]["post_id"] == "PID_500"
assert fb["posted"]["500"]["s"] == "1-0"
pred = json.load(open(store.PRED_JSON, encoding="utf-8"))
assert pred["700"]["as"] == 0
print("12 OK: export writes the same json shape the old code produced")

# ---------------------------------------------------------------- json backend
# The fallback that makes this mergeable before the secrets exist: with nothing
# configured the pipeline must behave exactly as it does today.
import importlib, json as _json
os.environ.pop("D1_SQLITE", None)
jdir = tempfile.mkdtemp()
importlib.reload(store)
assert store.backend() == "json", store.backend()
store.FB_JSON = os.path.join(jdir, "fb_posted.json")
store.PRED_JSON = os.path.join(jdir, "predictions.json")

# 13) json claim is a CHECK, not a lock: it writes nothing, so a crashed run
#     cannot leave a phantom claim (today's behaviour, faithfully)
assert store.claim("article", 600) is True
assert not os.path.exists(store.FB_JSON), "json claim must not write a placeholder"
assert store.claim("article", 600) is True, "json mode is best-effort by design"
store.record_post("article", 600, "PID_600", title="T600")
assert store.claim("article", 600) is False, "a recorded post blocks the next claim"
assert store.posted_ids("article") == {"600"}
print("13 OK: json claim writes nothing and blocks only after a real post")

# 14) json mode keeps the four-key shape other tools read
store.bump_failed("card", 601, "x")
store.seen_set(601, "0-0")
st = _json.load(open(store.FB_JSON, encoding="utf-8"))
assert set(st) == {"posted", "failed", "articles", "seen"}, set(st)
assert st["failed"]["601"] == 1 and st["seen"]["601"]["s"] == "0-0"
print("14 OK: json file keeps its historical shape")

# 15) predictions in json mode: freeze, then a scored row is final
rec = {"comp": "EPL", "home": "A", "away": "B", "kickoff": "2026-09-20",
       "ph": 0.5, "pd": 0.3, "pa": 0.2, "score": "1-0", "conf": "low"}
assert store.pred_freeze(800, rec) is True
assert store.pred_score(800, 2, 1, "H", "H", True, 0.3, False) is True
assert store.pred_score(800, 0, 0, "D", "H", False, 0.9, False) is False
assert store.pred_freeze(800, dict(rec, ph=0.1)) is False
assert store.pred_all()["800"]["ph"] == 0.5
print("15 OK: json predictions freeze once, scored rows are final")

# 16) one json bucket per kind. Found 2026-09-20 while checking whether the
# first reel had published: posted_ids("reel") came back holding seven CARD
# ids, because _bucket() sent every kind that is not an article to "posted".
# On this backend a match that already had a card looked as though it already
# had a reel, so the reel would never be made. D1 has a kind column and never
# had the collision - but the fallback is what runs when the quota is gone.
assert store._bucket("card") != store._bucket("reel")
assert len({store._bucket(k) for k in ("article", "card", "reel", "tg")}) == 4
assert store._bucket("article") == "articles" and store._bucket("card") == "posted"
assert store._fb_bucket({"posted": {}}, "reel") == {}   # older file, newer kind
store.record_post("card", 901, "p1")
store.record_post("reel", 901, "v1")
assert store.posted_ids("card") == {"901"} and store.posted_ids("reel") == {"901"}
store.record_post("card", 902, "p2")
assert "902" not in store.posted_ids("reel"), "a card must not silence a reel"
print("16 OK: a card and a reel of the same match keep separate json state")

print("ALL STORE TESTS PASSED")
