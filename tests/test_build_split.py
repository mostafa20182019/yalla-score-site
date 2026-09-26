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
defs = [i + 1 for i, l in enumerate(src) if l.startswith("_UNSET = object()")]
ck("1 _UNSET is defined exactly once", len(defs) == 1, f"lines {defs}")
ck("2 _bound is defined exactly once", sum(1 for l in src if l.startswith("def _bound(")) == 1)

stale = []
for name, fn in vars(B).items():
    if inspect.isfunction(fn) and fn.__module__ == B.__name__:
        for p in inspect.signature(fn).parameters.values():
            d = p.default
            if type(d) is object and d is not B._UNSET:
                stale.append(f"{name}({p.name})")
ck("3 every sentinel default IS build_site._UNSET (the `is` check can fire)", not stale, stale[:5])

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
cyc = [f for f in os.listdir("site_lib") if f.endswith(".py")
       and "build_site" in "".join(l for l in open(os.path.join("site_lib", f), encoding="utf-8")
                                   if l.lstrip().startswith(("import ", "from ")))]
ck("7 no site_lib module imports build_site (no cycles)", not cyc, cyc)
import site_lib.config as CF  # noqa: E402
ck("8 config paths still point at the repo root, not site_lib/",
   CF.HERE == os.path.dirname(os.path.abspath(B.__file__))
   and os.path.isdir(CF.SITE_SRC) and CF.DIST == os.path.join(CF.HERE, "dist"))

print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL OK")
sys.exit(1 if fails else 0)
