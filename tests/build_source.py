"""The build's Python source as ONE string, for tests that grep the code.

Since the build_site split (slices 3, 6, 7, 8 - 2026-09-25/26) the build is
build_site.py (build() only) + site_lib/*.py (helpers) + site_pages/*.py
(the pages). A test that reads only build_site.py goes
blind to what moved: a positive check fails loudly (good), but a NEGATIVE
check ("the raw author is never printed", "the build issues no SQL") keeps
passing while the forbidden code sits in a module it no longer reads. Read
the whole build instead.
"""
import glob
import io
import os


def build_source():
    files = (["build_site.py"] + sorted(glob.glob(os.path.join("site_lib", "*.py")))
             + sorted(glob.glob(os.path.join("site_pages", "*.py"))))
    return "\n".join(io.open(f, encoding="utf-8").read() for f in files)
