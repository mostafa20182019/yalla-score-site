# -*- coding: utf-8 -*-
r"""The round reels' slots: one reel at a time, hours apart (2026-11-20).

    python tests/test_reel_slots.py      (from the repo root)

The scorers reel, the title race and the table's movers used to ride the
00:16 results run, on top of the results reel. reel_slots.py gives each its
hour the next day (13:00 / 16:00 / 19:00 Cairo), one a run, never within
three hours of another reel of the family; and the movers go out as a card
when fewer than four clubs moved.
"""
import datetime
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

import reel_slots as RS            # noqa: E402

fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


def at(h, m=0):
    return datetime.datetime(2026, 11, 22, h, m)


ALL = lambda name, day: True                 # noqa: E731 - every slot has work
print("1. the hours")
ck("today's fixtures 11:00, scorers 14:00, race 17:00, movers 20:00 - three hours apart, as the gap asks",
   RS.SLOTS == (("today", 11), ("scorers", 14), ("race", 17), ("movers", 20)) and RS.GAP_H == 3)
ck("nothing before 11:00, whatever is waiting", RS.due(at(0, 16), ALL, False) is None and RS.due(at(10, 59), ALL, False) is None)
ck("11:00 is the morning reel's - two hours after the morning card, not one minute", RS.due(at(11, 0), ALL, False) == "today")
ONLY = lambda *names: (lambda name, day: name in names)      # noqa: E731
ck("14:00 is the scorers reel's", RS.due(at(13, 59), ONLY("scorers", "race", "movers"), False) is None
   and RS.due(at(14, 0), ONLY("scorers", "race", "movers"), False) == "scorers")
ck("17:00 the race, 20:00 the movers - each once its earlier slots are done",
   RS.due(at(17, 5), ONLY("race", "movers"), False) == "race" and RS.due(at(20, 5), ONLY("movers"), False) == "movers")
ck("a slot whose hour has not come waits, even alone", RS.due(at(16, 0), ONLY("race", "movers"), False) is None)
_wf = open(".github/workflows/fb-post.yml", encoding="utf-8").read()
ck("the morning run no longer posts the reel itself; the slot's run does, and only that reel",
   "day_reel.py --today --publish" not in _wf and '"day_reel.py"), "--today", "--publish"' in open("reel_slots.py", encoding="utf-8").read())
ck("a slot with nothing to post is skipped", RS.due(at(20, 0), ONLY("movers"), False) == "movers"
   and RS.due(at(20, 0), ONLY(), False) is None)

print("2. one at a time")
ck("never within three hours of another reel of the family", RS.due(at(19, 5), ALL, True) is None)
ck("a missed day catches up one slot a run, the earliest first", RS.due(at(21, 0), ALL, False) == "today"
   and RS.due(at(21, 0), ONLY("scorers", "race", "movers"), False) == "scorers")
ck("the family a slot keeps its distance from: the morning reel, the results reel, h2h and the slots",
   set(RS.FAMILY) == {"scorers:", "race:", "movers:", "today:", "day:", "h2h:"})
src = open("reel_slots.py", encoding="utf-8").read()
ck("a store that cannot be read means WAIT, never two reels on a guess",
   "return True            # unknown = wait" in src)
ck("a module that cannot be read is not due - it never raises", "except Exception" in src.split("def has_work")[1].split("def recent_reel")[0])

print("3. the movers: a card under four clubs")
import movers_reel as MV            # noqa: E402
ck("four moves is a reel, fewer a card", MV.REEL_MIN_MOVES == 4)
msrc = open("movers_reel.py", encoding="utf-8").read()
ck("the card is posted under the same ref as the reel would be - a round is posted once either way",
   'if len(ev["moves"]) < REEL_MIN_MOVES:' in msrc and "store.record_post(R.KIND, ref, pid" in msrc
   and msrc.index("store.claim(R.KIND, ref") < msrc.index('if len(ev["moves"]) < REEL_MIN_MOVES:'))
import social_card as SC            # noqa: E402
ev = {"competition": "Egyptian Premier League", "round": 12,
      "moves": [{"team": "الزمالك", "before": 5, "after": 2, "crest": None},
                {"team": "المصري", "before": 6, "after": 9, "crest": None}]}
b = SC.render_movers_bytes(ev)
ck("the card renders (JPEG, the family's size)", b[:2] == b"\xff\xd8" and SC.render_movers(ev).size == (SC.W, SC.H))

print("4. the workflows")
wf = open(os.path.join(".github", "workflows", "fb-post.yml"), encoding="utf-8").read()
pub = open(os.path.join(".github", "workflows", "publish.yml"), encoding="utf-8").read()
night = wf.split('elif [ -n "$DAYCARD" ]; then')[1].split("elif [ -n")[0]
ck("the night run keeps the results card and reel and carries NO round reel",
   "python fb_post.py --daycard" in night and "python day_reel.py --publish" in night
   and not any(x in night for x in ("python scorers_reel.py", "python movers_reel.py", "python race_reel.py")))
ck("the events run posts the slot that is due, and cannot fail on it",
   "python reel_slots.py --run | tee -a /tmp/fb.txt || true" in wf)
ck("publish.yml dispatches that run when a slot is due, not only for a data event",
   "python reel_slots.py --pending" in pub and 'if [ "$N" = "0" ] && [ "${S:-0}" != "1" ]; then exit 0; fi' in pub)

print("5. before a kick-off (2026-11-27)")
K = datetime.datetime(2026, 11, 22, 18, 0)
ck("the poster and the head-to-head reel are due in the six hours before their match, not after it",
   RS.KICK_AHEAD_H == 6.0 and RS.before_kick(K, at(12, 0)) and RS.before_kick(K, at(17, 59))
   and not RS.before_kick(K, at(11, 59)) and not RS.before_kick(K, at(18, 0)) and not RS.before_kick(None, at(12, 0)))
_rs = open("reel_slots.py", encoding="utf-8").read()
ck("the run posts a match's own post first; --pending counts it too",
   _rs.index("kick = kickoff_due(now)") < _rs.index("name = due(now)", _rs.index("def run(")) and "(due(now) or kickoff_due(now))" in _rs)
ck("the poster does not wait for the reels' gap; the reel does", "h2h_waits(now) and not recent_reel(now, recent)" in _rs
   and "if poster_waits(now):" in _rs)
ck("a check that cannot be made is not due - it never raises", RS.kickoff_due(at(12, 0), recent=False) in (None, "poster", "h2h"))
_pub = open(".github/workflows/publish.yml", encoding="utf-8").read()
ck("the question is asked with the switches the posting run reads", "FB_POSTER: ${{ vars.FB_POSTER }}" in _pub and "FB_FORM: ${{ vars.FB_FORM }}" in _pub)

print("\nALL OK" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
