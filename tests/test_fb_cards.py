# -*- coding: utf-8 -*-
"""Sanity tests for fb_cards.py --post plumbing (no network)."""
import sys, os, json, tempfile
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from email.parser import BytesParser
from email import policy
# state lives in store.py now: sqlite backend on a throwaway file, set BEFORE
# fb_cards imports it, so the claim/record SQL is genuinely exercised
tmp = tempfile.mkdtemp()
for _k in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_D1_ID"):
    os.environ.pop(_k, None)
os.environ["D1_SQLITE"] = os.path.join(tmp, "state.sqlite")
import store
import fb_cards as fc
assert store.backend() == "sqlite", store.backend()
store.init_schema()
fc.fetch_live = lambda: {}
fc.score_verified = lambda m, live, now=None: (True, 'test: verification mocked')

# 1) multipart body parses back correctly (Arabic caption, binary file)
body, ctype = fc.multipart({"caption": "نص عربي ⚽", "access_token": "T"},
                           {"source": ("card.png", b"\x89PNG\r\n..", "image/png")})
msg = BytesParser(policy=policy.default).parsebytes(b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + body)
parts = {p.get_param("name", header="content-disposition"): p for p in msg.iter_parts()}
assert parts["caption"].get_payload(decode=True).decode("utf-8").strip() == "نص عربي ⚽"
assert parts["access_token"].get_payload(decode=True).decode("utf-8").strip() == "T"
assert parts["source"].get_filename() == "card.png"
assert parts["source"].get_content_type() == "image/png"
assert parts["source"].get_payload(decode=True) == b"\x89PNG\r\n.."
print("multipart round-trip OK")

# 2) post_cards with a fake token + mocked upload: posts once, dedups, records failures
os.environ["FB_PAGE_TOKEN"] = "fake"
matches = fc.b.load("matches.json")
ge_idx = fc.b.goal_events_index(fc.b.load("goal_events.json"))
picked = fc.finished_matches(matches, None)[:3]
assert len(picked) == 3, "need 3 finished curated matches in data"

calls = []
def fake_post(token, png, caption):
    calls.append((token, len(png), caption))
    if len(calls) == 2:
        raise RuntimeError("simulated graph error")
    return f"post_{len(calls)}"
fc.post_photo = fake_post

fc.post_cards(picked, ge_idx, os.path.join(tmp, "cards"))
assert len(calls) == 3
assert store.posted_ids("card") == {str(picked[0]["match_id"]), str(picked[2]["match_id"])}
assert store.failed_count("card", picked[1]["match_id"]) == 1
assert store.get_post("card", picked[1]["match_id"]) is None,     "a failed card must not keep its claim"
assert all(c[1] > 20000 for c in calls), "png bytes look too small"
assert fc.b.SITE_BASE in calls[0][2] and "#يلا_سكور" in calls[0][2]
print("first pass OK: 2 posted, 1 failed, captions carry link + hashtag")

# second pass: only the failed one is retried
calls.clear()
fc.post_cards(picked, ge_idx, os.path.join(tmp, "cards"))
assert len(calls) == 1
assert len(store.posted_ids("card")) == 3
assert store.failed_count("card", picked[1]["match_id"]) == 0
print("second pass OK: only the failed card retried, now all 3 posted")

# third pass: nothing to do
calls.clear()
fc.post_cards(picked, ge_idx, os.path.join(tmp, "cards"))
assert calls == []
print("third pass OK: nothing new")

# 3) no token: state untouched, nothing posted
os.environ["FB_PAGE_TOKEN"] = ""
fc.STATE_FILE = os.path.join(tmp, "fb_posted2.json")
fc.post_cards(picked, ge_idx, os.path.join(tmp, "cards"))
assert not os.path.exists(fc.STATE_FILE) and calls == []
print("no-token pass OK: inert, state file not created")
# 3) THE DUPLICATE FIX for cards: a match already claimed by another run must
#    not be rendered or posted by this one.
store.sql("DELETE FROM fb_posted"); store.sql("DELETE FROM fb_failed")
calls.clear()
os.environ["FB_PAGE_TOKEN"] = "fake"   # the no-token case above cleared it, and
                                       # without this the early return would make
                                       # this case pass for the wrong reason
assert store.claim("card", picked[0]["match_id"]) is True     # another run got there first
fc.post_cards([picked[0]], ge_idx, os.path.join(tmp, "cards"))
assert calls == [], f"posted a card another run had claimed! {calls}"
print("3 OK: a card claimed by another run is never posted twice")

# 4) score_verified's stability timer lives in the store, so it survives a run
#    that loses its git push - it used to reset and re-delay the card.
store.sql("DELETE FROM fb_seen")
import importlib
fc.score_verified = importlib.reload(fc).score_verified   # restore the real one
fc.fetch_live = lambda: {}                                # /live.json knows nothing
m = dict(picked[0], home_score=2, away_score=1)
ok, why = fc.score_verified(m, {})
assert ok is False and "first seen" in why, why
ok, why = fc.score_verified(m, {})
assert ok is False and "stable for 0 min" in why, why      # timer running, not reset
store.sql("UPDATE fb_seen SET first_at = ? WHERE match_id = ?",
          [int(__import__("time").time()) - (fc.STABLE_MIN + 1) * 60, str(m["match_id"])])
ok, why = fc.score_verified(m, {})
assert ok is True and "stable" in why, why
# a CHANGED score restarts the clock - a corrected result must not slip through
ok, why = fc.score_verified(dict(m, away_score=2), {})
assert ok is False and "first seen" in why, why
print("4 OK: the stability timer persists in the store and resets on a score change")

print("ALL FB_CARDS TESTS PASSED")
