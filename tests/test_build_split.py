"""Invariants of the build_site split (2026-09-26).

    python tests/test_build_split.py

The slice-4 page functions pass unbound build() variables as the sentinel
_UNSET and delete them on entry (`if x is _UNSET: del x`). That only works if
there is ONE _UNSET: a second run of tools/extract_sections.py once inserted a
second definition, so 25 functions bound their defaults to the first object
and compared against the second - the delete never fired and an unset
variable carried the sentinel back into build(). Pinned here: one definition,
and every function's _UNSET default is that very object.
"""
import inspect
import os
import sys

sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8")
import build_site as B  # noqa: E402

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


src = open("build_site.py", encoding="utf-8").read().splitlines()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_source import build_source  # noqa: E402  the whole build
import glob  # noqa: E402
import importlib  # noqa: E402
every = build_source().splitlines()   # build_site + site_lib + site_pages
defs = [i + 1 for i, l in enumerate(every) if l.startswith("_UNSET = object()")]
ck("1 _UNSET is defined exactly once in the whole build", len(defs) == 1, f"lines {defs}")
ck("2 _bound is defined exactly once", sum(1 for l in every if l.startswith("def _bound(")) == 1)

stale = []
page_mods = [importlib.import_module("site_pages." + os.path.basename(f)[:-3])
             for f in sorted(glob.glob("site_pages/*.py")) if not f.endswith("__init__.py")]
checked = 0
for mod in [B] + page_mods:
    for name, fn in vars(mod).items():
        if not (inspect.isfunction(fn) and fn.__module__ == mod.__name__):
            continue
        checked += 1
        for p in inspect.signature(fn).parameters.values():
            d = p.default
            if type(d) is object and d is not B._UNSET:
                stale.append(f"{name}({p.name})")
ck("3 every sentinel default IS build_site._UNSET (the `is` check can fire)",
   not stale and checked >= 30, f"{checked} functions checked; stale {stale[:5]}")

# slice 6 (tools/move_names.py): moved names are re-imported, never copied.
# A `global X` in build_site after X moved would rebind a build_site copy the
# moved code never reads (head() would print an empty ticker) - build() sets
# them on the module instead.
ck("4 build_site has no `global` statement", not [l for l in src if l.strip().startswith("global ")])
import site_lib.shell as SH  # noqa: E402
ck("5 the build-time values are NOT re-exported (a stale copy cannot be read)",
   not any(hasattr(B, n) for n in ("TICKER_HTML", "KO_SCRIPT", "CSS_VER"))
   and all(hasattr(SH, n) for n in ("TICKER_HTML", "KO_SCRIPT", "CSS_VER")))
ck("6 re-exported names are the SAME objects (the registry the sitemap reads is shared)",
   B._LASTMOD is SH._LASTMOD and B.write is SH.write and B.head is SH.head)
import ast  # noqa: E402


def imports_of(path):
    """Every module a file imports (real import statements, not docstrings)."""
    out = set()
    for n in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            out.add(n.module)
    return out


cyc = [f for f in glob.glob("site_lib/*.py") + glob.glob("site_pages/*.py")
       if "build_site" in imports_of(f)]
ck("7 no site_lib / site_pages module imports build_site (no cycles)", not cyc, cyc)
import site_lib.config as CF  # noqa: E402
ck("8 config paths still point at the repo root, not site_lib/",
   CF.HERE == os.path.dirname(os.path.abspath(B.__file__))
   and os.path.isdir(CF.SITE_SRC) and CF.DIST == os.path.join(CF.HERE, "dist"))
# slice 8: the pages moved to site_pages/ - layers point one way only
ck("9 site_lib never imports site_pages (helpers do not depend on pages)",
   not [f for f in glob.glob("site_lib/*.py")
        if any(m.startswith("site_pages") for m in imports_of(f))])
ck("10 build_site.py is build() + imports (the pages live in site_pages/)",
   [l.split("(")[0] for l in src if l.startswith("def ")] == ["def build"])

print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL OK")
sys.exit(1 if fails else 0)
