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

    13:00  the scorers / assists reel       (scorers_reel.py)
    16:00  the title race, when it is on    (race_reel.py, FB_RACE)
    19:00  the table's movers               (movers_reel.py - a reel, or a card
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

SLOTS = (("scorers", 13), ("race", 16), ("movers", 19))
GAP_H = 3
FAMILY = ("scorers:", "race:", "movers:", "today:", "day:", "h2h:")   # the reels a slot keeps its distance from


def cairo_now():
    from zoneinfo import ZoneInfo
    return datetime.datetime.now(ZoneInfo("Africa/Cairo"))


def has_work(name, day):
    """Does this slot's module hold something unposted? Never raises: a slot
    that cannot be read is simply not due this time."""
    try:
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
    name = due(now)
    if not name:
        print("reel slots: nothing is due now")
        return 0
    print(f"reel slots: {name} ({now:%H:%M} Cairo)")
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
        print("due now:", due(now))
        return 0
    print(1 if due(now) else 0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
