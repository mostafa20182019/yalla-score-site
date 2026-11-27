# -*- coding: utf-8 -*-
r"""The day's slots for the round reels - one reel at a time, hours apart.

    python reel_slots.py --pending     # 1 when a slot is due now, else 0 (publish.yml asks this)
    python reel_slots.py --run         # post the ONE reel that is due (fb-post.yml daycard=events)
    python reel_slots.py --show        # what is due, in words

WHY (social review 2026-11-20; user: «اعمل 9»): the results card, the results
reel, the scorers reel, the movers reel and the day's events all went out
within minutes at 00:16 Cairo - 29 posts landed in hour 0 since 1 November -
and a reel posted on top of another buries the first. The results card and
reel stay at night. The rest wait for the next day:

    11:00  today's fixtures as a reel       (day_reel.py --today; since
                                             2026-11-26 - until then it went
                                             out at 09:03, one minute after the
                                             morning card with the same first
                                             line, and the poster in that minute)
    14:00  the scorers / assists reel       (scorers_reel.py)
    17:00  the title race, when it is on    (race_reel.py, FB_RACE)
    20:00  the table's movers               (movers_reel.py - a reel, or a card
                                             when fewer than four clubs moved)

Hours are Cairo. A slot is DUE from its hour until midnight, while its own
module says it has something unposted; one reel a run, the earliest slot
first, and never within GAP_H hours of the last reel of this family (the
morning reel, the results reel, another slot) - so a day whose slots were
all missed catches up one at a time, not in a burst. Each module still
claims its own ref in the store: a reel is posted once whoever asks.

No clock of its own: publish.yml runs every refresh and dispatches the
`events` run when `--pending` says 1, as it already does for the data news.
"""
import argparse
import datetime
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SLOTS = (("today", 11), ("scorers", 14), ("race", 17), ("movers", 20))
GAP_H = 3
FAMILY = ("scorers:", "race:", "movers:", "today:", "day:", "h2h:")   # the reels a slot keeps its distance from


def cairo_now():
    from zoneinfo import ZoneInfo
    return datetime.datetime.now(ZoneInfo("Africa/Cairo"))


def has_work(name, day):
    """Does this slot's module hold something unposted? Never raises: a slot
    that cannot be read is simply not due this time."""
    try:
        if name == "today":
            return today_reel_waits()
        if name == "scorers":
            import scorers_reel as SR
            return bool(SR.due(posted=SR._posted))
        if name == "movers":
            import movers_reel as MV
            return bool(MV.pending(day))
        if name == "race":
            import race_reel as RR
            return RR.armed() and bool(RR.pending(day))
    except Exception as e:                                   # noqa: BLE001
        print(f"reel slots: {name} cannot be read ({str(e)[:100]})", file=sys.stderr)
    return False


def today_reel_waits():
    """The morning reel of today's fixtures is still to post: no record of it
    in the store (a claim counts - another run holds it) and the day has
    enough matches for one (day_reel's own rule)."""
    import day_reel as DR
    import fb_post as P
    import fb_reel as R
    import match_brief as MB
    import store
    date = P.todaycard_date()
    if store.get_post(R.KIND, f"today:{date}"):
        return False
    return len(DR.today_matches(MB.load_all()["matches"], date)) >= P.TODAY_MIN


# ---------------------------------------------------------------- before a kick-off
# The match-day poster and the head-to-head reel are about ONE match, and
# they went out with the morning card: card 09:02, reel 09:03, poster 09:03 -
# three posts in a minute, nine hours before a 18:00 kick-off (social review
# 2026-11-26). They are due in the hours before THEIR match instead, asked
# by the same run as the slots. The poster is a card: it does not wait for
# the reels' gap. The reel does.
KICK_AHEAD_H = 6.0           # from this long before the kick-off, until it


def before_kick(kick, now, ahead=KICK_AHEAD_H):
    """True in the `ahead` hours before `kick` (both Cairo datetimes)."""
    return kick is not None and 0 < (kick - now).total_seconds() <= ahead * 3600


def _kick(m):
    try:
        import story_events as SE
        return SE._kick_dt(m) if m.get("koff_time") else None
    except Exception:                                        # noqa: BLE001
        return None


def poster_waits(now):
    """The day's poster is still to post and its match kicks off within
    KICK_AHEAD_H: FB_POSTER on, one of ours plays, no record for the day."""
    import match_brief as MB
    import match_poster as MP
    import store
    if not MP.armed():
        return False
    date = now.date().isoformat()
    m = MP.pick(MB.load_all()["matches"], date)
    if not m or store.get_post(MP.KIND, date):
        return False
    return before_kick(_kick(m), now)


def h2h_waits(now):
    """A pair of site_lib/h2h.PAIRS meets today, its reel has no record and
    the match kicks off within KICK_AHEAD_H (no hand-made reel covers it)."""
    import fb_reel as R
    import h2h_reel as HR
    import store
    today = now.date().isoformat()
    todo = [(p, nx) for p, nx in HR.meeting_today(HR.load_pool(), today) if not R.drafts_linking(nx.get("match_id"))]
    if not todo:
        return False
    pair, nx = todo[0]
    if store.get_post(R.KIND, f"h2h:{pair['slug']}:{today}"):
        return False
    return before_kick(_kick(nx), now)


def kickoff_due(now=None, recent=None):
    """'poster' / 'h2h' / None - what is due before a kick-off now. Never
    raises: a check that cannot be made is simply not due."""
    now = now or cairo_now()
    try:
        if poster_waits(now):
            return "poster"
    except Exception as e:                                   # noqa: BLE001
        print(f"reel slots: the poster cannot be read ({str(e)[:100]})", file=sys.stderr)
    try:
        if h2h_waits(now) and not recent_reel(now, recent):
            return "h2h"
    except Exception as e:                                   # noqa: BLE001
        print(f"reel slots: the head-to-head reel cannot be read ({str(e)[:100]})", file=sys.stderr)
    return None


def _script(name, *args):
    import os
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    return subprocess.call([sys.executable, os.path.join(here, name), *args], cwd=here)


def recent_reel(now, recent=None):
    """True when a reel of the family went out less than GAP_H hours ago."""
    if recent is not None:
        return recent
    try:
        import fb_reel as R
        import store
        rows = store.posted_since(R.KIND, time.time() - GAP_H * 3600)
        return any(str(r.get("ref_id") or "").startswith(FAMILY) for r in rows)
    except Exception as e:                                   # noqa: BLE001
        print(f"reel slots: the store cannot be read ({str(e)[:100]})", file=sys.stderr)
        return True            # unknown = wait: never two reels on a guess


def due(now=None, work=None, recent=None):
    """The ONE slot to run now, or None. `work(name, day)` and `recent` are
    for the tests; the real ones read the modules and the store."""
    now = now or cairo_now()
    work = work or has_work
    ready = [name for name, hour in SLOTS if now.hour >= hour and work(name, now.date())]
    if not ready or recent_reel(now, recent):
        return None
    return ready[0]


def run(now=None):
    now = now or cairo_now()
    kick = kickoff_due(now)                 # a match's own post first: it has a deadline
    if kick == "poster":
        print(f"reel slots: the match-day poster ({now:%H:%M} Cairo)")
        return _script("match_poster.py", "--auto", "--publish")
    if kick == "h2h":
        print(f"reel slots: the head-to-head reel ({now:%H:%M} Cairo)")
        return _script("h2h_reel.py", "--auto", "--publish")
    name = due(now)
    if not name:
        print("reel slots: nothing is due now")
        return 0
    print(f"reel slots: {name} ({now:%H:%M} Cairo)")
    if name == "today":
        import os
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        return subprocess.call([sys.executable, os.path.join(here, "day_reel.py"), "--today", "--publish"], cwd=here)
    if name == "scorers":
        import scorers_reel as SR
        return SR.auto()
    if name == "movers":
        import movers_reel as MV
        return MV.auto(today=now.date())
    import race_reel as RR
    return RR.auto(today=now.date())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pending", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    if args.run:
        return run()
    now = cairo_now()
    if args.show:
        for name, hour in SLOTS:
            print(f"{hour:02d}:00  {name}: {'has work' if has_work(name, now.date()) else 'nothing'}"
                  f"{'' if now.hour >= hour else ' (not its hour yet)'}")
        print("due now:", due(now), "| before a kick-off:", kickoff_due(now))
        return 0
    print(1 if (due(now) or kickoff_due(now)) else 0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
