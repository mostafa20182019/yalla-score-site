# -*- coding: utf-8 -*-
"""One row per workflow in D1 `health_beats`, written at the END of every run.

    python heartbeat.py publish --ok
    python heartbeat.py publish --fail --detail "fetch, commit"
    python heartbeat.py article:daily --outcome "$OUTCOME"   # a GitHub step outcome

WHY (2026-09-24): GitHub reports a failed continue-on-error step as "success" -
in the run list, in the API, everywhere - so the only honest place to read a
step's result is inside the run itself (`steps.<id>.outcome`). This carries it
out to the Worker's watchdog (health.js), which pages the user on Telegram when
a workflow keeps failing or stops reporting at all.

`fails` counts CONSECUTIVE failures: +1 on a failure, back to 0 on a success.
One failed article slot is normal (the next slot retries, the user's rule);
three in a row is an expired token or an empty quota, and that is what pages.

Never fails the run: without the CF secrets, or with D1 down, it prints and
exits 0. The watchdog notices a missing heartbeat on its own (a stale `ts`).
"""
import argparse
import sys
import time

import store

DDL = ("CREATE TABLE IF NOT EXISTS health_beats (name TEXT PRIMARY KEY, "
       "ts INTEGER NOT NULL, ok INTEGER NOT NULL, fails INTEGER NOT NULL DEFAULT 0, detail TEXT)")

UPSERT = ("INSERT INTO health_beats (name, ts, ok, fails, detail) VALUES (?, ?, ?, ?, ?) "
          "ON CONFLICT(name) DO UPDATE SET ts = excluded.ts, ok = excluded.ok, "
          "detail = excluded.detail, "
          "fails = CASE WHEN excluded.ok = 1 THEN 0 ELSE health_beats.fails + 1 END")


def beat(name, ok, detail="", now_ms=None):
    """Record one run's verdict. Returns True when it was written."""
    if store.backend() == "json":
        print(f"heartbeat {name}: {'ok' if ok else 'FAIL'} (no D1 configured - not recorded)")
        return False
    ts = now_ms if now_ms is not None else int(time.time() * 1000)
    store.sql(DDL)
    store.sql(UPSERT, [name, ts, 1 if ok else 0, 0 if ok else 1, (detail or "")[:300]])
    print(f"heartbeat {name}: {'ok' if ok else 'FAIL'}" + (f" ({detail})" if detail else ""))
    return True


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--ok", action="store_true")
    g.add_argument("--fail", action="store_true")
    # a GitHub step outcome: success | failure | cancelled | skipped
    g.add_argument("--outcome")
    ap.add_argument("--detail", default="")
    a = ap.parse_args(argv)

    if a.outcome is not None:
        if a.outcome not in ("success", "failure"):
            # skipped = nothing was attempted (no match due, etc.); cancelled =
            # superseded. Neither says anything about health - leave the row.
            print(f"heartbeat {a.name}: outcome '{a.outcome}' - not recorded")
            return 0
        ok = a.outcome == "success"
    else:
        ok = a.ok
    try:
        beat(a.name, ok, a.detail)
    except Exception as e:                                   # noqa: BLE001
        print(f"::warning::heartbeat {a.name} not recorded: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
