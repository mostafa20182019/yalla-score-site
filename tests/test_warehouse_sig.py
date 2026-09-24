r"""One hash per table instead of every row (2026-09-20).

    python tests/test_warehouse_sig.py      (from the repo root)

A cache that quietly stops updating the warehouse would be far worse than the
reads it saves, so these tests are about CORRECTNESS first and cost second:

  * a changed row is still written;
  * a signature is stored only AFTER the write it describes lands, so a run
    that dies leaves the next one doing the full read;
  * WAREHOUSE_FULL=1 ignores every signature;
  * and only then: a warm refresh is cheap.
"""
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

for k in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_D1_ID", "WAREHOUSE_FULL"):
    os.environ.pop(k, None)
os.environ["D1_SQLITE"] = os.path.join(tempfile.mkdtemp(prefix="whsig-"), "wh.db")

import store                                              # noqa: E402
import warehouse as W                                     # noqa: E402

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


reads = {"n": 0, "tables": []}
_real = store.sql


def counting(statement, params=None):
    rows = _real(statement, params)
    if statement.strip()[:6].upper() == "SELECT":
        reads["n"] += len(rows)
        reads["tables"].append(statement.split("FROM")[-1].strip().split()[0])
    return rows


store.sql = counting
store.sql("CREATE TABLE IF NOT EXISTS t_demo (k TEXT PRIMARY KEY, v TEXT)")

COLS = ["k", "v"]
ROWS = [{"k": "a", "v": "1"}, {"k": "b", "v": "2"}, {"k": "c", "v": "3"}]


def cycle(rows):
    """One refresh of the toy table: diff, write, then store the signature."""
    reads["n"], reads["tables"] = 0, []
    to_write, same = W._changed_only("t_demo", ["k"], COLS, rows)
    store.upsert_many("t_demo", COLS, to_write, ["k"])
    W.commit_sigs()
    return to_write, same, reads["n"]


# ---------------------------------------------------------------- cold, warm
w, same, rd = cycle(ROWS)
ck("1 the first run writes every row and reads the table back",
   len(w) == 3 and same == 0 and "t_demo" in reads["tables"])

w, same, rd = cycle(ROWS)
ck("2 an unchanged run writes nothing", not w and same == 3)
ck("3 …and never touches the table: only the signature row was read",
   "t_demo" not in reads["tables"], str(set(reads["tables"])))

# ---------------------------------------------------------------- a real change
CHANGED = [{"k": "a", "v": "1"}, {"k": "b", "v": "CHANGED"}, {"k": "c", "v": "3"}]
w, same, rd = cycle(CHANGED)
ck("4 a changed row is still found and written", [r["k"] for r in w] == ["b"])
ck("5 …and the other two are recognised as unchanged", same == 2)
ck("6 the change really landed in the table",
   _real("SELECT v FROM t_demo WHERE k = 'b'")[0]["v"] == "CHANGED")

# a NEW row
w, _, _ = cycle(CHANGED + [{"k": "d", "v": "4"}])
ck("7 a new row is written", [r["k"] for r in w] == ["d"])

# order alone is not a change: an upsert is keyed, and treating a reorder as a
# change would read the whole table back for nothing
w, same, _ = cycle(list(reversed(CHANGED + [{"k": "d", "v": "4"}])))
ck("8 the same rows in a different order are not a change", not w and same == 4)

# ---------------------------------------------------------------- the crash
STATE = CHANGED + [{"k": "d", "v": "4"}]
CRASHED = [dict(r, v="post-crash") if r["k"] == "a" else r for r in STATE]
reads["n"], reads["tables"] = 0, []
W._changed_only("t_demo", ["k"], COLS, CRASHED)      # diff…
W._PENDING.clear()                                    # …and the run dies here
w, same, _ = cycle(CRASHED)
ck("9 a run that dies before commit_sigs leaves the next one doing the real read",
   [r["k"] for r in w] == ["a"], "the write was NOT lost")

cycle(CRASHED)                                        # settle

# ---------------------------------------------------------------- out-of-band
_real("UPDATE t_demo SET v = 'edited elsewhere' WHERE k = 'c'")
_real_commit = store._sqlite().commit()
w, same, _ = cycle(CRASHED)
ck("10 a signature CAN hide an edit made outside this script (the known limit)",
   not w)
os.environ["WAREHOUSE_FULL"] = "1"
W._SIGS = None
w, same, _ = cycle(CRASHED)
ck("11 …and WAREHOUSE_FULL=1 is the escape hatch that repairs it",
   [r["k"] for r in w] == ["c"])
os.environ.pop("WAREHOUSE_FULL", None)
W._SIGS = None

# ---------------------------------------------------------------- the point
src = open("warehouse.py", encoding="utf-8").read()
ck("12 the signature is written AFTER the upsert, never inside the diff",
   src.index("_PENDING[table] = (sig, len(rows))") > src.index("def _changed_only")
   and "commit_sigs()\n    return counts" in src)
ck("13 every signature is read in ONE query, not one per table",
   src.count('SELECT name, sig FROM warehouse_sig') == 1)
ck("14 refresh_details is gated as a whole, so _resolve_matches and the "
   "GROUP BY scans in _trim are skipped too",
   '_sig_matches("details_pool"' in src)

print()
print(f"{len(fails)} FAILED: {', '.join(fails)}" if fails else "ALL WAREHOUSE SIGNATURE TESTS PASSED")
sys.exit(1 if fails else 0)
