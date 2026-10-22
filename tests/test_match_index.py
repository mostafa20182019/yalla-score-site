# -*- coding: utf-8 -*-
"""Which match pages are indexable (2026-10-22, after the 4th AdSense
rejection named thin content with 386 match pages in the sitemap): a score
or a lineup sheet alone is a scoreboard every site repeats - only an
original article, a finished match WITH its reading, or an upcoming match
whose pre-match reading found four facts, is content.

    python tests/test_match_index.py     (from the repo root)
"""
import os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

src = open("site_pages/matches.py", encoding="utf-8").read()
rule = re.search(r"_rich = (.*)", src)
ck("1 the rule exists once", rule is not None and src.count("_rich = ") == 1)
line = rule.group(1) if rule else ""
ck("2 a finished match is content only with its reading", '(st == "FINISHED" and bool(post_read))' in line, line)
ck("3 an original article and a four-fact pre-match reading still count", "bool(_art)" in line and "_pre_weight >= 4" in line, line)
ck("4 a bare score or lineup sheet no longer counts", "bool(_goals)" not in line and "bool(_det)" not in line, line)
ck("5 the reading is computed before the rule and only for finished matches with details",
   src.index('if st == "FINISHED" and _det and hs is not None') < src.index("_rich = ") and src.index("post_read = _read") < src.index("_rich = "))
ck("6 noindex still follows the rule", "if not _rich:" in src and 'content="noindex"' in src)

print()
print("ALL OK" if not fails else f"{len(fails)} FAILED: " + ", ".join(fails))
sys.exit(1 if fails else 0)
