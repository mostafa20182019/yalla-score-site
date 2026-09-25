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

print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL OK")
sys.exit(1 if fails else 0)
