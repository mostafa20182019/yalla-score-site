r"""The D1 READ budget (2026-09-20).

    python tests/test_d1_reads.py      (from the repo root)

The write side got its guard on 2026-09-15 (test_d1_writes.mjs). The read side
went unwatched and ran out three times — 09-16, 09-19 (it threw away a finished
545-word article) and 09-20, when it killed three steps of every evening publish
run and the first Facebook reel.

The spender was measurable all along: the warehouse refresh only WRITES what
changed, but to know what changed it READS everything. A warm refresh — nothing
changed at all — returns 26,050 rows:

    match_lineups  8,448      matches        2,274  (x3)
    match_subs     3,510      match_cards    1,490
    players        2,548      match_goals    1,107

and D1 counts rows SCANNED, not returned, so that is a floor. At ~96 publish
runs a day it is ~2.5M of the 5M free tier. Hourly: ~625k.

By default this checks the gate, which is what regresses. Pass --measure to
re-run the measurement against a local SQLite copy (about a minute).
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


wf = io.open(".github/workflows/publish.yml", encoding="utf-8").read()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_source import build_source  # noqa: E402  build_site.py + site_lib/*.py
bs = build_source()
wk = io.open("worker.js", encoding="utf-8").read()

# THE WAREHOUSE LEFT THE PIPELINE (2026-09-20). It was gated to hourly in the
# morning and removed the same evening, because nothing reads it and Oracle
# already holds every one of its tables.
# the step, not the word: the comment that explains the removal names the
# command, so matching on the command alone fails on its own explanation
ck("1 the warehouse no longer refreshes on the publish path",
   "Refresh the analytics warehouse" not in wf
   and "run: python d1_admin.py --warehouse" not in wf)
ck("2 …and the file says why, so nobody re-adds it by accident",
   "THE ANALYTICS WAREHOUSE LEFT THIS PIPELINE" in wf)

# the reason, asserted rather than remembered: if the site ever starts reading
# the warehouse, these two break and the decision gets revisited
ck("3 the build issues no SQL of its own — it builds from data/*.json",
   bs.count("store.sql(") == 0)
WAREHOUSE_ONLY = ["match_lineups", "match_cards", "match_subs", "top_players",
                  "team_strength", "competitions", "standings_meta"]
# in SQL, not anywhere: `competitions` is also a 365scores query parameter in
# this file, which a bare substring match reads as a table
import re                                                # noqa: E402
_sql_words = set(re.findall(r"(?:FROM|INTO|UPDATE|JOIN)\s+([a-z_]+)", wk))
ck("4 the Worker queries none of the warehouse-only tables",
   not (_sql_words & set(WAREHOUSE_ONLY)),
   ", ".join(sorted(_sql_words & set(WAREHOUSE_ONLY))) or "none")

# it must still be RUNNABLE by hand — this is a retirement, not a deletion
adm_wf = io.open(".github/workflows/d1-admin.yml", encoding="utf-8").read()
ck("5 d1-admin still offers it as a manual task", '"warehouse"' in adm_wf)

_adm = io.open("d1_admin.py", encoding="utf-8").read()
_wh = _adm.split('if "--warehouse" in args')[1].split('if "--articles-backfill"')[0]
ck("6 the cost line survives a refresh that dies (the one that ran out "
   "printed nothing)", "finally:" in _wh)
ck("6b there is an escape hatch for a warehouse edited elsewhere",
   "--warehouse-full" in _adm and "WAREHOUSE_FULL" in _wh)

if "--measure" in sys.argv:
    import collections
    import tempfile
    for k in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_D1_ID"):
        os.environ.pop(k, None)
    os.environ["D1_SQLITE"] = os.path.join(tempfile.mkdtemp(prefix="wh-"), "wh.db")
    import store
    seen = collections.Counter()
    _real = store.sql

    def counting(statement, params=None):
        rows = _real(statement, params)
        if statement.strip()[:6].upper() == "SELECT":
            seen["rows"] += len(rows)
        return rows

    store.sql = counting
    import warehouse
    store.init_schema()
    for _ in range(2):                       # cold, then the warm one that repeats
        seen.clear()
        warehouse.refresh(verbose=False)
        warehouse.refresh_details(verbose=False)
        warehouse.refresh_articles(verbose=False)
    warm = seen["rows"]
    print(f"\n  measured warm refresh: {warm:,} rows returned "
          f"→ ~{warm * 24 / 1e6:.2f}M/day hourly, ~{warm * 96 / 1e6:.2f}M/day per-run")
    # 26,050 before the signatures (2026-09-20), 246 after — on this local copy,
    # which holds no articles; on the real D1 add store.article_all() as the
    # SOURCE read (~2,600 rows), which no signature can avoid.
    ck("7 a warm refresh is still hashed, not read back",
       warm < 2_000, f"{warm:,}")

print()
print(f"{len(fails)} FAILED: {', '.join(fails)}" if fails else "ALL D1 READ TESTS PASSED")
sys.exit(1 if fails else 0)
