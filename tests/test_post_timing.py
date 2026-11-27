# -*- coding: utf-8 -*-
"""When a pre-match post goes out, what counts as pending, and the hours of
the weekly head-to-head card (2026-11-27).

    python tests/test_post_timing.py     (from the repo root)
"""
import datetime, io, os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import story_events as SE
import fb_post as fp

fails = 0
def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    fails += not cond

from zoneinfo import ZoneInfo
C = ZoneInfo("Africa/Cairo")
at = lambda h, m=0: datetime.datetime(2026, 11, 28, h, m, tzinfo=C)       # noqa: E731
KICK = at(18, 0)

print("1. a pre-match post: three to eight hours before the kick-off")
ck("the window shipped", SE.AHEAD_H == (3.0, 8.0) and SE.MORNING_H == 9)
ck("on the real clock: not a day before, not in the last three hours",
   not SE.ahead_ok(KICK, at(9, 59), None, 24) and SE.ahead_ok(KICK, at(10, 0), None, 24)
   and SE.ahead_ok(KICK, at(15, 0), None, 24) and not SE.ahead_ok(KICK, at(15, 1), None, 24))
ck("a datetime handed to detect() is the real clock too", SE.ahead_ok(KICK, at(12, 0), at(12, 0), 24))
ck("never before nine in the morning (a 13:00 kick-off posts from 09:00, not 05:00)",
   not SE.ahead_ok(at(13, 0), at(8, 59), None, 24) and SE.ahead_ok(at(13, 0), at(9, 0), None, 24))
day = datetime.date(2026, 11, 28)
midnight = SE._now(day)
ck("a DATE (the tests, --date) still means the plain window, as before",
   SE.ahead_ok(KICK, midnight, day, 24) and not SE.ahead_ok(KICK + datetime.timedelta(days=1), midnight, day, 24))
src = io.open("story_events.py", encoding="utf-8").read()
ck("both pre-match detectors ask it: the facts and the club's form",
   src.count("ahead_ok(kd, now, today, hours)") == 1 and "next_fixture(tp, up, now, hours, today)" in src
   and "not ahead_ok(k, now, today, hours)" in src)

print("2. pending = what the events run would really post")
ev = lambda kind, ref="x-timing-test": {"kind": kind, "ref": ref}      # noqa: E731
for var in ("FB_FORM", "FB_FACTS", "FB_SOCIAL"):
    os.environ.pop(var, None)
ck("a kind whose switch is off is not pending: form, facts, social",
   not fp.would_post(ev("club-form")) and not fp.would_post(ev("match-facts")) and not fp.would_post(ev("night-number")))
ck("a kind with no switch of its own is", fp.would_post(ev("cup-round-done")))
os.environ["FB_FORM"] = "on"
ck("FB_FORM on: the form card is pending", fp.form_on() and fp.would_post(ev("club-form")))
os.environ.pop("FB_FORM", None)
fsrc = io.open("fb_post.py", encoding="utf-8").read()
ck("a kind whose posts for the day are all out is not pending either",
   "FORM_DAILY_MAX:" in fsrc.split("def would_post")[1].split("def event_text")[0]
   and "FACTS_DAILY_MAX:" in fsrc.split("def would_post")[1].split("def event_text")[0])
ck("the workflow's question is that one rule", "n = sum(1 for ev in evs if would_post(ev))" in fsrc)

print("3. the weekly head-to-head card")
ck("only between 12:00 and 22:00 Cairo (it went out at 03:05 and 01:05 with a night article)",
   fp.H2H_HOURS == (12, 22) and "H2H_HOURS[0] <= _now().astimezone(CAIRO).hour < H2H_HOURS[1]" in fsrc)
print("\nALL OK" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
