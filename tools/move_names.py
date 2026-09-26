# -*- coding: utf-8 -*-
"""Move top-level names out of build_site.py into site_lib modules, VERBATIM.

    python tools/move_names.py SPEC.json [--dry]

SPEC.json:
    {"package": "site_lib",                     # optional; "site_pages" for pages
     "modules": [{"name": "config", "doc": "...", "names": ["SITE_BASE", ...]}, ...],
     "no_reexport": ["TICKER_HTML"],            # optional
     "fixups": [["config", "old line", "new line"]]}   # optional, exact lines

Each moved function / assignment takes the comment block right above it.
A module's imports are computed from what its code reads: the stdlib and
module imports build_site already has, the site_lib names it already
imports, and names moved to an EARLIER module of the same spec. Anything
else - a name that stays in build_site - stops the tool: the new module
would have to import build_site back (a cycle), so that name must move
first (or together). build_site then re-imports every moved name under the
same name, so `import build_site as b; b.head(...)` keeps working.

Refused on purpose:
  * a name that is the target of a `global` statement: after the move the
    `global` would rebind a copy in build_site and the moved code would keep
    reading the old value. Rebind it through the module instead
    (`_shell.TICKER_HTML = ...`) before running the tool.
  * a name assigned in more than one top-level statement split across
    modules (all its statements move together, or none).

Written 2026-09-26 for slice 6 of the build_site split (the page shell);
the proof is still tools/repro_build.py + tools/prove_same.sh.
"""
import ast
import builtins
import io
import json
import os
import sys


def main(argv):
    spec = json.load(io.open(argv[0], encoding="utf-8"))
    dry = "--dry" in argv
    pkg = spec.get("package", "site_lib")   # site_pages for the page functions (slice 8)
    assert os.path.exists(os.path.join(pkg, "__init__.py")), f"{pkg}/__init__.py missing"
    src = io.open("build_site.py", encoding="utf-8").read()
    nl = "\r\n" if "\r\n" in src else "\n"
    lines = src.replace("\r\n", "\n").split("\n")
    tree = ast.parse("\n".join(lines))

    home = {}
    order = [m["name"] for m in spec["modules"]]
    for m in spec["modules"]:
        for n in m["names"]:
            assert n not in home, f"{n} listed twice"
            home[n] = m["name"]

    # top-level statements that bind each name
    stmts = {}
    for node in tree.body:
        bound = []
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            bound = [node.name]
        elif isinstance(node, ast.Assign):
            bound = [x.id for t in node.targets for x in ast.walk(t) if isinstance(x, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            bound = [node.target.id]
        for b in bound:
            stmts.setdefault(b, []).append(node)
    missing = set(home) - set(stmts)
    assert not missing, f"not defined at top level: {sorted(missing)}"

    # statements to move, with the module they go to
    move = {}
    for n, mod in home.items():
        for node in stmts[n]:
            names_here = ([node.name] if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else
                          [x.id for t in getattr(node, "targets", [getattr(node, "target", None)])
                           for x in ast.walk(t) if isinstance(x, ast.Name)])
            for other in names_here:
                assert home.get(other) == mod, \
                    f"{n} shares a statement (line {node.lineno}) with {other}, which does not move with it"
            move[id(node)] = (node, mod)

    globals_ = {g for x in ast.walk(tree) if isinstance(x, ast.Global) for g in x.names}
    bad = sorted(globals_ & set(home))
    assert not bad, f"`global` targets cannot move (rebind through the module first): {bad}"

    # what build_site already imports
    std, lib = {}, {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for a in node.names:
                std[a.asname or a.name] = f"import {a.name}" + (f" as {a.asname}" if a.asname else "")
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                lib[a.asname or a.name] = node.module

    def free_names(node):
        local = set()
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            for x in ast.walk(node):
                if isinstance(x, ast.arg):
                    local.add(x.arg)
                elif isinstance(x, ast.Name) and isinstance(x.ctx, (ast.Store, ast.Del)):
                    local.add(x.id)
                elif isinstance(x, (ast.FunctionDef, ast.ClassDef)) and x is not node:
                    local.add(x.name)
                elif isinstance(x, ast.ExceptHandler) and x.name:
                    local.add(x.name)
                elif isinstance(x, (ast.Import, ast.ImportFrom)):      # a function-local import
                    for a in x.names:
                        local.add((a.asname or a.name).split(".")[0])
                elif isinstance(x, ast.comprehension):
                    for y in ast.walk(x.target):
                        if isinstance(y, ast.Name):
                            local.add(y.id)
        else:
            for x in ast.walk(node):
                if isinstance(x, ast.comprehension):
                    for y in ast.walk(x.target):
                        if isinstance(y, ast.Name):
                            local.add(y.id)
                elif isinstance(x, ast.Lambda):
                    for a in x.args.args:
                        local.add(a.arg)
        return {x.id for x in ast.walk(node) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load)
                and x.id not in local and not hasattr(builtins, x.id)
                and x.id not in ("__file__", "__name__")}   # every module has its own

    # the lines of each moved statement, with its comment block
    spans = []
    for node, mod in move.values():
        start = node.decorator_list[0].lineno if getattr(node, "decorator_list", None) else node.lineno
        while start - 2 >= 0 and lines[start - 2].lstrip().startswith("#"):
            start -= 1
        spans.append((start, node.end_lineno, node, mod))
    spans.sort()
    for (a1, b1, _, _), (a2, b2, _, _) in zip(spans, spans[1:]):
        assert a2 > b1, f"overlapping statements at lines {a1}-{b1} / {a2}-{b2}"

    report, texts = [], {}
    for mod in order:
        need_std, need_lib = set(), {}
        for a, b, node, m in spans:
            if m != mod:
                continue
            for name in free_names(node):
                if name in home:
                    if home[name] == mod:
                        continue
                    assert order.index(home[name]) < order.index(mod), \
                        f"{mod}: line {node.lineno} needs {name} from the later module {home[name]} (cycle)"
                    need_lib.setdefault(f"{pkg}.{home[name]}", set()).add(name)
                elif name in std:
                    need_std.add(std[name])
                elif name in lib:
                    need_lib.setdefault(lib[name], set()).add(name)
                else:
                    raise SystemExit(f"{mod}: line {node.lineno} needs `{name}`, which stays in "
                                     "build_site - move it first or in the same step")
        doc = next(m["doc"] for m in spec["modules"] if m["name"] == mod)
        out = [f'"""{doc}\n\nMoved verbatim out of build_site.py (2026-09-26, tools/move_names.py):\n'
               "source and comments exactly as they were there. Edit here; build_site\n"
               'imports these back under the same names."""']
        out += sorted(need_std)
        for lm in sorted(need_lib):
            out.append(f"from {lm} import {', '.join(sorted(need_lib[lm]))}")
        out += ["", ""]
        n_lines = 0
        for a, b, node, m in spans:
            if m == mod:
                block = lines[a - 1:b]
                out += block + (["", ""] if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else [])
                n_lines += len(block)
        # only the separators between blocks are generated - the blocks
        # themselves are never touched (a string literal may hold blank lines)
        text = "\n".join(out).rstrip("\n") + "\n"
        for fm, old, new in spec.get("fixups", []):
            if fm == mod:
                assert text.count(old + "\n") == 1, f"fixup line not found exactly once in {mod}: {old}"
                text = text.replace(old + "\n", new + "\n")
        texts[mod] = text
        report.append(f"  {pkg}/{mod}.py: {sum(1 for s in spans if s[3] == mod)} statements, "
                      f"{n_lines} lines; imports {sorted(need_std)} "
                      f"{ {k: sorted(v) for k, v in need_lib.items()} }")

    print("\n".join(report))
    if dry:
        return 0
    for mod, text in texts.items():
        path = f"{pkg}/{mod}.py"
        assert not os.path.exists(path), f"{path} exists - this tool only creates new modules"
        io.open(path, "w", encoding="utf-8", newline="\n").write(text)

    for a, b, _, _ in sorted(spans, reverse=True):
        del lines[a - 1:b]
        # at most two blank lines where the statement was (a statement
        # boundary, so never inside a string literal)
        k = a - 1
        while (k < len(lines) and not lines[k].strip() and k >= 2
               and not lines[k - 1].strip() and not lines[k - 2].strip()):
            del lines[k]
    # re-import after the last `from site_lib.` / `from site_pages.` import block
    last = max(k for k, l in enumerate(lines) if l.startswith(("from site_lib.", "from site_pages.")))
    if "(" in lines[last]:                      # a parenthesised, multi-line import
        while not lines[last].split("#")[0].rstrip().endswith(")"):
            last += 1
    skip = set(spec.get("no_reexport", []))
    imp = [f"# {', '.join(order)}: moved to {pkg}/ by tools/move_names.py (2026-09-26) -",
           "# edit them there. Same names, same behaviour."]
    for mod in order:
        names = [n for m in spec["modules"] if m["name"] == mod for n in m["names"] if n not in skip]
        if not names:
            continue
        imp.append(f"from {pkg}.{mod} import (  # noqa: E402,F401")
        for i in range(0, len(names), 6):
            imp.append("    " + ", ".join(names[i:i + 6]) + ("," if i + 6 < len(names) else ")"))
    lines[last + 1:last + 1] = imp
    text = "\n".join(lines)
    io.open("build_site.py", "w", encoding="utf-8", newline="").write(text.replace("\n", nl))
    print(f"moved {len(spans)} statements into {len(order)} module(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
