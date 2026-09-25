"""site_src/templates + site_lib.render (2026-09-25, the templating step).

    python tests/test_templates.py

Pins the one rule that keeps templated pages byte-identical: the loader joins
a template's lines with NO separator, so a line broken in the middle of a
sentence silently deletes the space between two words on the live page. A
template line must therefore start with a tag or a Jinja block - never with
bare text. Also: every template compiles, autoescape is on, a missing
variable fails loudly (StrictUndefined), and values keep their own newlines.
"""
import glob
import os
import sys

sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8")
from jinja2 import UndefinedError  # noqa: E402
from site_lib import render as R  # noqa: E402

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


files = sorted(glob.glob(os.path.join(R.TEMPLATES, "*.html")))
ck("1 there are templates", len(files) >= 6, f"{len(files)} files")

bad = []
for f in files:
    in_comment = False
    for i, line in enumerate(open(f, encoding="utf-8").read().splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        if in_comment:
            in_comment = "#}" not in s
            continue
        if s.startswith("{#"):
            in_comment = "#}" not in s
            continue
        if not (s.startswith("<") or s.startswith("{")):
            bad.append(f"{os.path.basename(f)}:{i}")
ck("2 no template line starts with bare text (a broken sentence would lose a space)", not bad, bad[:5])

for f in files:
    R._env.get_template(os.path.basename(f))
ck("3 every template compiles", True, f"{len(files)}")

t = R._env.from_string("<p>{{ x }}</p>")
ck("4 autoescape is on", t.render(x="<b>") == "<p>&lt;b&gt;</p>")
ck("5 Markup passes through untouched", t.render(x=R.Markup("<b>")) == "<p><b></p>")
try:
    t.render()
    ck("6 a missing variable fails loudly", False)
except UndefinedError:
    ck("6 a missing variable fails loudly", True)

# the loader joins the SOURCE lines, not the output: a value keeps its newlines
tmp = os.path.join(R.TEMPLATES, "_test_join.html")
open(tmp, "w", encoding="utf-8").write("<div>\n  <p>a</p>\n</div>\n{{ v }}\n")
try:
    out = R.render("_test_join.html", v=R.Markup("line1\nline2"))
finally:
    os.remove(tmp)
ck("7 template lines are joined with no separator, values keep their newlines",
   out == "<div><p>a</p></div>line1\nline2", repr(out))

# a page may pass a variable called `name` (the club page does) or `template`
tmp2 = os.path.join(R.TEMPLATES, "_test_names.html")
open(tmp2, "w", encoding="utf-8").write("<p>{{ name }}|{{ template }}</p>")
try:
    out2 = R.render("_test_names.html", name="الأهلي", template="x")
finally:
    os.remove(tmp2)
ck("8 variables called `name` or `template` do not collide with render()'s own argument",
   out2 == "<p>الأهلي|x</p>", repr(out2))

print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL OK")
sys.exit(1 if fails else 0)
