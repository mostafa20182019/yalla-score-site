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

# THE DEPLOY GATE (2026-09-25). publish.yml runs `run_all.py --gate` after the
# build and deploys only if it passes. The gate is every test EXCEPT these:
# they read the LIVE data, pages or photos, so they can go red because the
# data moved rather than because the code broke (two did exactly that on
# 2026-09-24: /matches crossed its size budget, the sitemap crossed 500 URLs).
# A deploy gate that trips on data would freeze the site every 15 minutes for
# no code reason. They still run on every code push (tests.yml) and still say
# FAIL there - as a report, not a lock.
DATA_TESTS = {
    "test_fixtures_pages.py":   "size budget of the real /matches + sitemap",
    "test_indexnow.py":         "the real sitemap + what changed TODAY",
    "test_fb_reel.py":          "needs finished curated matches in today's data",
    "test_fb_cards.py":         "needs 3 finished curated matches in today's data",
    "test_scorers_guard.py":    "reads the real fixtures/standings/scorers",
    "test_shrink_media.py":     "the real photo library",
    "test_warehouse.py":        "the real articles + standings",
    "test_article_write.py":    "the real articles.json export",
    "test_results_archive.py":  "section 7 checks the real archive",
}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")        # a cp1252 console cannot print a test's arrows
    gate = "--gate" in argv
    words = [w.lower() for w in argv if w != "--gate"]
    files = sorted(glob.glob(os.path.join(HERE, "test_*.py")) + glob.glob(os.path.join(HERE, "test_*.mjs")))
    if words:
        files = [f for f in files if any(w in os.path.basename(f).lower() for w in words)]
    if gate:
        skipped = [f for f in files if os.path.basename(f) in DATA_TESTS]
        files = [f for f in files if os.path.basename(f) not in DATA_TESTS]
        print(f"deploy gate: {len(files)} code tests ({len(skipped)} live-data tests report in tests.yml only)")
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
            fh.write(f"### {'Deploy gate' if gate else 'Tests'}: {len(results) - len(failed)} passed, {len(failed)} failed\n")
            for name, ok, dt in results:
                if not ok:
                    tier = " (live data - report only)" if name in DATA_TESTS else ""
                    fh.write(f"- ❌ `{name}`{tier}\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
