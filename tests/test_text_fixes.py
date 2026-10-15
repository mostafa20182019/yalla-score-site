# -*- coding: utf-8 -*-
r"""Text fixes + the name guard (2026-10-15).

    python tests/test_text_fixes.py     (from the repo root)

Article 767 named شيكابالا (retired) where its sources said شيكو بانزا. Two
defences: `d1_admin --fix-text` corrects a published article from
data/text_fixes.json (idempotent, faq included), and article_put refuses a
guarded name that is not what the story is about.
"""
import json, os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import d1_admin as DA
import article_put as AP

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

fix = {"article_id": 1, "replace": [["شيكابالا", "شيكو بانزا"]]}
cur = {"title": "الزمالك يصعد", "summary": "عاشور أيد ركلة جزاء",
       "body": "<p>دفعة مروان عطية على شيكابالا ثم تماس داري مع شيكابالا</p>",
       "fb_post": "دفعة على شيكابالا", "faq": [{"q": "من؟", "a": "شيكابالا"}, {"q": "كم؟", "a": "13"}]}
upd = DA.apply_text_fix(cur, fix)
ck("1a body: every occurrence replaced", upd["body"].count("شيكو بانزا") == 2 and "شيكابالا" not in upd["body"])
ck("1b fb_post replaced too", upd["fb_post"] == "دفعة على شيكو بانزا")
ck("1c faq answers replaced, untouched pairs kept", upd["faq"][0]["a"] == "شيكو بانزا" and upd["faq"][1] == {"q": "كم؟", "a": "13"})
ck("1d fields with nothing to replace are not in the update", "title" not in upd and "summary" not in upd)
fixed = {**cur, **upd}
ck("1e idempotent: a second pass finds nothing", DA.apply_text_fix(fixed, fix) is None)
ck("1f fields subset honoured", set(DA.apply_text_fix(cur, {**fix, "fields": ["fb_post"]})) == {"fb_post"})

# ------------------------------------------------------------ the name guard
g = json.load(open("data/name_guard.json", encoding="utf-8"))
ck("2a the guard file lists شيكابالا", any(n["name"] == "شيكابالا" for n in g["names"]))
rec = {"title": "الزمالك يصعد ضد لجنة الحكام", "summary": "", "body": "<p>دفعة على شيكابالا</p>", "fb_post": ""}
probs = AP.name_guard_problems(rec)
ck("2b a guarded name in the body of a story about something else is refused", len(probs) == 1 and "شيكابالا" in probs[0], str(probs))
rec2 = {"title": "الزمالك يكرّم شيكابالا", "summary": "", "body": "<p>شيكابالا في الملعب</p>", "fb_post": ""}
ck("2c ...but a story ABOUT the man passes", AP.name_guard_problems(rec2) == [])
rec3 = {"title": "خبر", "summary": "", "body": "<p>شيكو بانزا سجل</p>", "fb_post": "", "faq": [{"q": "من؟", "a": "شيكابالا"}]}
ck("2d the faq is checked too", len(AP.name_guard_problems(rec3)) == 1)
ck("2e validate() carries the guard", any("شيكابالا" in p for p in AP.validate({**rec, "author": "x", "pub_date": "2026-10-15"})[0]))

# ------------------------------------------------------------ the committed fix
t = json.load(open("data/text_fixes.json", encoding="utf-8"))
f767 = next(f for f in t["fixes"] if f["article_id"] == 767)
ck("3a the 767 entry replaces the retired name with the sources' name", f767["replace"] == [["شيكابالا", "شيكو بانزا"]] and f767.get("why"))

print()
print("ALL OK" if not fails else f"{len(fails)} FAILED: " + ", ".join(fails))
sys.exit(1 if fails else 0)
