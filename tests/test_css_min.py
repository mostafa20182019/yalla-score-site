# -*- coding: utf-8 -*-
"""The served stylesheet is the source without its comments and layout
whitespace - and nothing else changed (2026-11-26).

    python tests/test_css_min.py     (from the repo root)
"""
import io, os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
from site_lib.text import css_min

fails = 0
def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    fails += not cond

src = io.open("site_src/style.css", encoding="utf-8").read()
out = css_min(src)
ck("1 no comment is served", "/*" not in out and "*/" not in out)
ck("2 at least a seventh smaller", len(out) < len(src) * 0.86, f"{len(src)} -> {len(out)}")
ck("3 the braces still pair", out.count("{") == out.count("}"))
bare = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
ck("4 every declaration survives: the same text once all whitespace is gone",
   re.sub(r"\s+", "", bare) == re.sub(r"\s+", "", out))
ck("5 a value keeps its inner spaces", css_min("a{width:calc(100% - 2px);margin:0 auto}") == "a{width:calc(100% - 2px);margin:0 auto}")
ck("6 a selector list and a descendant keep their meaning", css_min(".a,\n  .b > .c  .d {\n  color: red ;\n}") == ".a, .b > .c .d{color: red;}")
ck("7 the placeholder rule is still the last one served", out.endswith('img[src*="/media/ph-"]{object-fit:contain;object-position:50% 50%;background:#1f94d3}'))
print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
