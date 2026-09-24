"""heartbeat.py + build_site.build_info (2026-09-24) - the two writers that
feed the Worker's watchdog (health.js; its own test is test_health.mjs).

    "C:\\Program Files\\Python312\\python.exe" tests/test_health_beats.py

heartbeat: `fails` must count CONSECUTIVE failures (the watchdog pages at 3),
reset on the first success, ignore skipped/cancelled runs, and never fail the
workflow that calls it. build_info: must flag a fetch source that raised and
find the newest article whatever time zone its pub_ts carries.
"""
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
for k in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_D1_ID"):
    os.environ.pop(k, None)
os.environ["D1_SQLITE"] = os.path.join(tempfile.mkdtemp(), "hb.sqlite")
import store       # noqa: E402
import heartbeat   # noqa: E402

assert store.backend() == "sqlite"


def row(name):
    r = store.sql("SELECT ts, ok, fails, detail FROM health_beats WHERE name = ?", [name])
    return r[0] if r else None


def run(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = heartbeat.main(list(argv))
    return rc, buf.getvalue()


# 1) consecutive failures count up, a success resets them
for n in (1, 2, 3):
    run("article:daily", "--outcome", "failure")
    assert row("article:daily")["fails"] == n, row("article:daily")
assert row("article:daily")["ok"] == 0
run("article:daily", "--outcome", "success")
r = row("article:daily")
assert r["fails"] == 0 and r["ok"] == 1, r
print("1 OK: fails counts 1,2,3 in a row and a success resets it to 0")

# 2) skipped / cancelled leave the row alone (no match due is not a failure)
before = row("article:daily")
rc, out = run("article:daily", "--outcome", "skipped")
assert rc == 0 and row("article:daily") == before and "not recorded" in out
run("article:daily", "--outcome", "cancelled")
assert row("article:daily") == before
print("2 OK: skipped and cancelled outcomes are not recorded")

# 3) publish: --ok / --fail with a detail, and one row per workflow
run("publish", "--fail", "--detail", "fetch commit")
run("publish", "--fail", "--detail", "fetch")
r = row("publish")
assert r["fails"] == 2 and r["detail"] == "fetch", r
run("publish", "--ok", "--detail", "soft: telegram")
assert row("publish")["fails"] == 0 and row("article:daily")["fails"] == 0
assert len(store.sql("SELECT name FROM health_beats")) == 2
print("3 OK: publish verdicts carry their detail; rows are per workflow")

# 4) it never fails the run: a broken store is a warning and exit code 0
real = store.sql
store.sql = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("D1 HTTP 429: limit"))
rc, out = run("publish", "--fail", "--detail", "deploy")
store.sql = real
assert rc == 0 and "::warning::" in out, out
os.environ.pop("D1_SQLITE")
rc, out = run("publish", "--ok")
assert rc == 0 and "no D1 configured" in out
os.environ["D1_SQLITE"] = os.path.join(tempfile.mkdtemp(), "hb2.sqlite")
print("4 OK: D1 down or not configured -> exit 0, never a red run")

# 5) build_info
import build_site as B  # noqa: E402

d = tempfile.mkdtemp()
with io.open(os.path.join(d, "fetch_debug.json"), "w", encoding="utf-8") as f:
    json.dump({"news": "skipped (FETCH_HEADLINES off)", "matches": "ok (43)",
               "goals": "FAIL: TimeoutError()", "standings": "FAIL: HTTPError(429)",
               "s365_charts": {"x": "FAIL: nested dicts are not sources"},
               "utc": "2026-09-24T18:35:29Z"}, f)
B.DATA = d
arts = [{"pub_ts": "2026-09-24T21:10:00+03:00"},     # 18:10Z
        {"pub_ts": "2026-09-24T18:20:00Z"},           # 18:20Z  <- newest
        {"pub_date": "2026-09-23"},                   # noon Cairo the day before
        {"title": "no time at all"}]
info = B.build_info(arts, {"1": {}, "2": {}})
assert info["fetch_failed"] == ["goals", "standings"], info["fetch_failed"]
assert info["fetch_at"] == 1790274929000, info["fetch_at"]
assert info["newest_article_at"] == 1790274000000, info["newest_article_at"]
assert info["articles"] == 4 and info["predictions"] == 2 and "predictions_oracle" not in info
assert abs(info["built_at"] / 1000 - __import__("time").time()) < 60
print("5 OK: build_info names the FAIL sources and finds the newest article across time zones")

B.DATA = tempfile.mkdtemp()                                  # no fetch_debug.json at all
info = B.build_info([], {})
assert info["fetch_at"] is None and info["fetch_failed"] == [] and info["newest_article_at"] is None
print("6 OK: a missing fetch_debug / empty site gives nulls, not a crash")

print("\nALL OK")
