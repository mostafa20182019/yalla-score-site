# -*- coding: utf-8 -*-
"""The plain-wording rule (user, 2026-10-24: «عايز صياغة الخبر بسيطة للمستخدمين»).

    python tests/test_plain_wording.py     (from the repo root)

Born from article 939's Facebook post: «هذا الكلاسيكو الخامس لمونويرا.. فاز
ريال مدريد في 3 من مواجهاته الأربع السابقة» — true, and read by the user as a
contradiction («هما أربعة ولا خمسة؟»). The rule lives in the three writing
prompts; this test keeps it there, with its example, in every one of them.
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


PROMPTS = (".github/prompts/daily-article.md",
           ".github/prompts/match-article.md",
           ".github/prompts/round-article.md")
for p in PROMPTS:
    s = io.open(p, encoding="utf-8").read()
    n = os.path.basename(p)
    ck(f"1 {n} carries the PLAIN WORDING rule", "## PLAIN WORDING" in s)
    ck(f"2 {n} shows the right wording AND the wrong one it replaces",
       "ومباراة الأحد ستكون الخامسة له" in s
       and "فاز الريال في 3 من مواجهاته الأربع السابقة" in s)
    ck(f"3 {n} applies it to fb_post, where the user reads first",
       "`fb_post` most of all" in s)
    ck(f"4 {n} keeps the rule above the structure section, where the writer reads it before writing",
       s.index("## PLAIN WORDING") < s.index("fb_post"))

print()
print(f"{len(fails)} FAILED: {', '.join(fails)}" if fails else "ALL PLAIN-WORDING TESTS PASSED")
sys.exit(1 if fails else 0)
