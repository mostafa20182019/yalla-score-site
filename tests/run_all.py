# -*- coding: utf-8 -*-
"""Run every test in tests/ - the same way on a laptop and in CI.

    python tests/run_all.py              # everything
    python tests/run_all.py health live  # only files whose name contains a word

Each test is its own script (they print ok/FAIL lines and exit non-zero on a
failure), so this only discovers, runs them one by one from the repo root with
a timeout, and summarises. Sequential on purpose: several tests read dist/,
data/ and media/, and a parallel run would let one see another's half-written
file. Exit code 1 if anything failed.

WHY (2026-09-24): ~50 tests existed but lived in the other repo's mirror and
ran only when someone remembered. The first CI run of them found two real
bugs on day one (the reel never finding a match; shrunk photos never being
committed). Tests that nobody runs protect nothing.
"""
import glob
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "tests")
TIMEOUT = 300


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")        # a cp1252 console cannot print a test's arrows
    words = [w.lower() for w in argv]
    files = sorted(glob.glob(os.path.join(HERE, "test_*.py")) + glob.glob(os.path.join(HERE, "test_*.mjs")))
    if words:
        files = [f for f in files if any(w in os.path.basename(f).lower() for w in words)]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    # tests must never touch the real database: without these they use their
    # own temporary sqlite file or the json fallback
    for k in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_D1_ID"):
        env.pop(k, None)
    results = []
    t_all = time.time()
    for f in files:
        name = os.path.basename(f)
        cmd = [sys.executable, f] if f.endswith(".py") else ["node", f]
        t0 = time.time()
        try:
            p = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, timeout=TIMEOUT,
                               encoding="utf-8", errors="replace")
            ok, out = p.returncode == 0, (p.stdout or "") + (p.stderr or "")
        except subprocess.TimeoutExpired:
            ok, out = False, f"TIMEOUT after {TIMEOUT}s"
        dt = time.time() - t0
        results.append((name, ok, dt))
        print(f"{'PASS' if ok else 'FAIL'}  {dt:5.1f}s  {name}", flush=True)
        if not ok:
            tail = "\n".join(out.strip().splitlines()[-15:])
            print("      " + tail.replace("\n", "\n      "), flush=True)
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed in {time.time() - t_all:.0f}s")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"### Tests: {len(results) - len(failed)} passed, {len(failed)} failed\n")
            for name, ok, dt in results:
                if not ok:
                    fh.write(f"- ❌ `{name}`\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
