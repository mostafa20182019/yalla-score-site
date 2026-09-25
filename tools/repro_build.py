# -*- coding: utf-8 -*-
"""A REPRODUCIBLE build, for proving that a refactor changed nothing.

    python tools/repro_build.py <repo_dir> <data_snapshot_dir> [--now 2026-09-25T12:00:00+03:00]

Runs build_site.build() inside <repo_dir> with:
  * the clock FROZEN at --now (datetime.datetime.now / date.today and the
    module-level REF_TODAY all see the same instant), so relative times
    («منذ ...»), lastmod dates and build-info are identical between two runs;
  * data/ replaced by a copy of <data_snapshot_dir> every time - the build
    writes data/predictions.json through the json fallback, so a second build
    on the same folder would otherwise start from different input;
  * PYTHONHASHSEED=0 and no Cloudflare secrets (json fallback, nothing
    remote is read or written).

Build the OLD code (a `git worktree add --detach`) and the NEW code with the
same snapshot and --now, then `diff -r old/dist new/dist`. Any difference is a
behaviour change and the refactor step is not done.

WHY (2026-09-25): build_site.py is being split into modules. A split is
supposed to be invisible; this is how "invisible" gets proven instead of
assumed.
"""
import os
import shutil
import subprocess
import sys


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    repo, snap = os.path.abspath(argv[0]), os.path.abspath(argv[1])
    now = argv[argv.index("--now") + 1] if "--now" in argv else "2026-09-25T12:00:00+03:00"
    if os.environ.get("REPRO_CHILD") != "1":
        env = {k: v for k, v in os.environ.items()
               if k not in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_D1_ID", "CLOUDFLARE_API_TOKEN")}
        env.update(PYTHONHASHSEED="0", REPRO_CHILD="1", PYTHONIOENCODING="utf-8")
        return subprocess.call([sys.executable, os.path.abspath(__file__)] + argv, env=env, cwd=repo)

    # fresh copy of the input, every run
    data = os.path.join(repo, "data")
    shutil.rmtree(data, ignore_errors=True)
    shutil.copytree(snap, data)

    # freeze the clock BEFORE anything imports datetime-dependent modules
    import datetime as _dt
    fixed = _dt.datetime.fromisoformat(now)

    class FrozenDatetime(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

        @classmethod
        def utcnow(cls):
            return fixed.astimezone(_dt.timezone.utc).replace(tzinfo=None)

        @classmethod
        def today(cls):
            return cls.now()

    class FrozenDate(_dt.date):
        @classmethod
        def today(cls):
            return fixed.date()

    _dt.datetime = FrozenDatetime
    _dt.date = FrozenDate

    sys.path.insert(0, repo)
    os.chdir(repo)
    import build_site
    build_site.build()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
