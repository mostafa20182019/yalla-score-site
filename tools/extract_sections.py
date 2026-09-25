# -*- coding: utf-8 -*-
"""Mechanical "extract method" for build_site.build() (2026-09-25, slice 4).

    python tools/extract_sections.py            # dry run: the plan, section by section
    python tools/extract_sections.py --apply    # rewrite build_site.py

build() is one 1,976-line function made of ~30 sections, each introduced by a
`    # ---- <name> ----` comment. This turns a section into a module-level
function `_page_<slug>(inputs...)` that build() calls, computed from the AST:

  inputs   names the section READS that build() bound BEFORE the section
  outputs  names the section BINDS that build() reads AFTER it - returned as a
           dict and bound back (`x = _r.get("x")`), so a variable the section
           only sets on some paths behaves as before on every path that worked

A section is LEFT IN PLACE (and the dry run says why) when moving it could
change behaviour:
  * it declares `global`/`nonlocal`;
  * it contains a top-level return/yield;
  * it hands a function or lambda it defines to later code (the closure would
    capture the extracted function's variables instead of build()'s);
  * it reads a build() variable that is NOT bound before it (in build() that
    name is local, so the read would fail; moved, it could silently resolve to
    a module global of the same name).

The body is moved verbatim: sections sit at build()'s indentation, which is
exactly a module-level function body's. Proof after --apply is the usual:
tools/repro_build.py on old and new, tools/prove_same.sh.
"""
import ast
import io
import re
import sys

PATH = "build_site.py"
HEADER = re.compile(r"^    # ---- (.+?) ----")
# a section already turned into a call (slice 4) - a boundary, never re-extracted
CALLED = re.compile(r"^    # (.+?) -> (_page_\w+)\(\) \(moved out of build\(\), slice 4\)")


def slug(title):
    s = re.sub(r"\(.*?\)", "", title)
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return (s[:40] or "section").rstrip("_")


class Scope(ast.NodeVisitor):
    """Names bound / loaded at ONE function scope (nested defs/lambdas/
    comprehensions are separate scopes: their own bindings do not count, but
    their free loads DO - they read the enclosing scope)."""

    def __init__(self):
        self.stores, self.loads, self.flags = set(), set(), set()

    def visit_Name(self, n):
        (self.stores if isinstance(n.ctx, (ast.Store, ast.Del)) else self.loads).add(n.id)

    def visit_Global(self, n):
        self.flags.add("global")

    def visit_Nonlocal(self, n):
        self.flags.add("nonlocal")

    def visit_Return(self, n):
        self.flags.add("return")

    def visit_Yield(self, n):
        self.flags.add("yield")

    visit_YieldFrom = visit_Yield

    def _nested(self, n, bound, body):
        inner = Scope()
        for b in body:
            inner.visit(b)
        self.loads |= (inner.loads - inner.stores - bound)

    def visit_FunctionDef(self, n):
        self.stores.add(n.name)
        for d in n.args.defaults + n.args.kw_defaults:
            if d is not None:
                self.visit(d)
        for d in n.decorator_list:
            self.visit(d)
        args = {a.arg for a in n.args.args + n.args.kwonlyargs + n.args.posonlyargs}
        args |= {a.arg for a in (n.args.vararg, n.args.kwarg) if a}
        self._nested(n, args, n.body)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, n):
        args = {a.arg for a in n.args.args + n.args.kwonlyargs}
        self._nested(n, args, [n.body])

    def _comp(self, n, elts):
        inner = Scope()
        for g in n.generators:
            inner.visit(g)
        for e in elts:
            inner.visit(e)
        self.loads |= (inner.loads - inner.stores)
        # the first iterable is evaluated in the enclosing scope
        self.visit(n.generators[0].iter)

    def visit_ListComp(self, n):
        self._comp(n, [n.elt])

    visit_SetComp = visit_GeneratorExp = visit_ListComp

    def visit_DictComp(self, n):
        self._comp(n, [n.key, n.value])

    def visit_ExceptHandler(self, n):
        if n.name:
            self.stores.add(n.name)
        self.generic_visit(n)

    def visit_Import(self, n):
        for a in n.names:
            self.stores.add((a.asname or a.name).split(".")[0])

    visit_ImportFrom = visit_Import


def scope_of(stmts):
    s = Scope()
    for st in stmts:
        s.visit(st)
    # A slice-4 call passes build() variables BY NAME: `_page_x(**_bound(
    # locals(), ('a', 'b')))`. Those strings are reads of a and b - without
    # this, a section feeding a later call looked output-free, and moving it
    # would have dropped every variable the call needs.
    for st in stmts:
        for x in ast.walk(st):
            if (isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id == "_bound"
                    and len(x.args) == 2 and isinstance(x.args[1], ast.Tuple)):
                s.loads |= {e.value for e in x.args[1].elts
                            if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return s


def plan(src):
    lines = src.split("\n")
    tree = ast.parse(src)
    build = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build")
    body = build.body
    heads = []
    for i, l in enumerate(lines):
        if build.lineno <= i + 1 <= build.end_lineno:
            if HEADER.match(l):
                heads.append((i + 1, HEADER.match(l).group(1)))
            elif CALLED.match(l):
                heads.append((i + 1, "CALL " + CALLED.match(l).group(2)))
    sections = []
    for k, (ln, title) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else build.end_lineno + 1
        stmts = [s for s in body if ln <= s.lineno < end]
        if stmts:
            sections.append({"title": title, "head": ln, "end": end, "stmts": stmts})
    build_locals = scope_of(body).stores
    out = []
    for sec in sections:
        first, last = sec["stmts"][0], sec["stmts"][-1]
        before = [s for s in body if s.end_lineno < sec["head"]]
        after = [s for s in body if s.lineno > last.end_lineno]
        sc = scope_of(sec["stmts"])
        bound_before = scope_of(before).stores
        read_after = scope_of(after).loads
        # names the section declares `global` are module names, not build() locals
        G = {n for st in sec["stmts"] for x in ast.walk(st) if isinstance(x, ast.Global) for n in x.names}
        inputs = sorted((sc.loads & build_locals & bound_before) - G)
        outputs = sorted((sc.stores & read_after) - G)
        inputs = sorted(set(inputs) | (set(outputs) & bound_before))
        why = []
        if sec["title"].startswith("CALL "):
            why.append("already a call")
        flags = set(sc.flags)
        if "global" in flags:
            # safe to move with it iff build() binds those names nowhere else
            # (in build() the declaration covers the WHOLE function)
            rest = [st for st in body if st not in sec["stmts"]]
            clash = G & scope_of(rest).stores
            if clash:
                why.append(f"global {sorted(clash)} is also bound elsewhere in build()")
            flags.discard("global")
        if flags:
            why.append("has " + "/".join(sorted(flags)))
        unbound = (sc.loads & build_locals) - bound_before - sc.stores
        if unbound:
            why.append(f"reads build() names not bound before it: {sorted(unbound)}")
        fn_out = set()
        for st in sec["stmts"]:
            if isinstance(st, ast.FunctionDef):
                fn_out.add(st.name)
            if isinstance(st, ast.Assign) and isinstance(st.value, ast.Lambda):
                fn_out |= {t.id for t in st.targets if isinstance(t, ast.Name)}
        # A closure handed to later code captures, once moved, the EXTRACTED
        # function's variables. That is only equivalent if build() never rebinds
        # any variable the closure reads after this section.
        stores_after = scope_of(after).stores
        for st in sec["stmts"]:
            if isinstance(st, ast.FunctionDef) and st.name in outputs:
                inner = scope_of(st.body)
                args = {a.arg for a in st.args.args + st.args.kwonlyargs + st.args.posonlyargs}
                args |= {a.arg for a in (st.args.vararg, st.args.kwarg) if a}
                risky = (inner.loads - inner.stores - args) & stores_after
                if risky:
                    why.append(f"closure {st.name} reads {sorted(risky)}, rebound later in build()")
        lam = {t for st in sec["stmts"] if isinstance(st, ast.Assign) and isinstance(st.value, ast.Lambda)
               for t in (x.id for x in st.targets if isinstance(x, ast.Name))}
        if lam & set(outputs):
            why.append(f"hands out a lambda: {sorted(lam & set(outputs))}")
        out.append(dict(sec, inputs=inputs, outputs=outputs, why=why,
                        body_from=sec["head"], body_to=last.end_lineno))
    return out, build


def apply(src, secs, build):
    """Inputs are passed ONLY IF BOUND at the call (`**_bound(locals(), ...)`)
    and default to _UNSET, which the function deletes on entry - so a name
    that was never bound (a loop variable from a loop that ran zero times)
    fails exactly where build() itself would have failed, and nowhere else.
    Outputs are written back only if the section bound them. That keeps
    "unbound stays unbound" and "prior value stays" exact. (The first version
    passed `_mid=_mid` and crashed on a loop that had not run - caught by the
    reproducible-build proof, not by the tests.)"""
    lines = src.split("\n")
    new_funcs, names = [], set()
    for s in sorted(secs, key=lambda s: -s["body_from"]):
        if s["why"]:
            continue
        name = "_page_" + slug(s["title"])
        while name in names:
            name += "_2"
        names.add(name)
        block = lines[s["body_from"] - 1:s["body_to"]]
        params = ", ".join(f"{i}=_UNSET" for i in s["inputs"])
        fn = [f"def {name}({params}):"]
        for i in s["inputs"]:
            fn.append(f"    if {i} is _UNSET:")
            fn.append(f"        del {i}")
        fn += block
        if s["outputs"]:
            fn += ["    _l = locals()",
                   f"    return {{k: _l[k] for k in {tuple(s['outputs'])!r} if k in _l}}"]
        new_funcs.insert(0, fn)
        pick = f"**_bound(locals(), {tuple(s['inputs'])!r})" if s["inputs"] else ""
        call = [f"    # {s['title']} -> {name}() (moved out of build(), slice 4)"]
        if s["outputs"]:
            call.append(f"    _r = {name}({pick})")
            for o in s["outputs"]:
                call.append(f"    if {o!r} in _r:")
                call.append(f"        {o} = _r[{o!r}]")
        else:
            call.append(f"    {name}({pick})")
        lines[s["body_from"] - 1:s["body_to"]] = call
    at = build.lineno - 1
    while at > 0 and lines[at - 1].lstrip().startswith("#"):
        at -= 1
    # _UNSET/_bound exist ONCE per module. A second run of this tool used to
    # insert them again: functions from the first run then bound defaults to
    # the first _UNSET but compared `is _UNSET` against the second, so the
    # delete never fired (caught 2026-09-26; tests/test_build_split.py).
    if any(l.startswith("_UNSET = object()") for l in lines):
        blob = []
    else:
        blob = ["# ---- slice 4: build()'s page sections as functions (tools/extract_sections.py) ----",
                "_UNSET = object()      # 'this build() variable was not bound at the call'",
                "",
                "",
                "def _bound(scope, names):",
                "    return {k: scope[k] for k in names if k in scope}",
                "",
                ""]
    for fn in new_funcs:
        blob += fn + ["", ""]
    lines[at:at] = blob
    return "\n".join(lines)


def main(argv):
    raw = io.open(PATH, encoding="utf-8").read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    src = raw.replace("\r\n", "\n")
    secs, build = plan(src)
    only = [a for a in argv if not a.startswith("--")]
    if only:
        for s in secs:
            if not any(w in s["title"] for w in only) and not s["why"]:
                s["why"] = ["not selected this run"]
    for s in secs:
        tag = "KEEP " if s["why"] else "MOVE "
        n = s["body_to"] - s["body_from"] + 1
        print(f"{tag} {n:4} lines  {s['title'][:55]:55}  in={len(s['inputs'])} out={len(s['outputs'])}"
              + (f"  <- {'; '.join(s['why'])}" if s["why"] else ""))
    if "--apply" in argv:
        new = apply(src, secs, build)
        compile(new, PATH, "exec")
        io.open(PATH, "w", encoding="utf-8", newline="").write(new.replace("\n", nl))
        moved = sum(s["body_to"] - s["body_from"] + 1 for s in secs if not s["why"])
        print(f"\napplied: {sum(1 for s in secs if not s['why'])} sections, {moved} lines moved out of build()")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
