# -*- coding: utf-8 -*-
"""The two-source gate on a news article — article_put.source_problems.

Run from the site root:  python tests/test_source_gate.py

/editorial promises the reader, in writing, that a news story is published only
after two independent sources agree. 37 articles published on 1-2 September
carry no sources at all, and an outside audit found the gap by reading the
policy page next to an article. These tests pin the gate that now keeps the
promise — and, just as important, pin what it must NOT block: a match piece
(built from our own data) and an official club announcement.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import article_put as AP

fails = []
def ok(n, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + n + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(n)

def news(sources):
    return {"title": "t", "summary": "s", "author": "a", "pub_date": "2026-09-16",
            "body": "<p>" + ("كلمة " * 400) + "</p>", "sources": sources}

two = [{"name": "في الجول", "url": "https://www.filgoal.com/x"},
       {"name": "الأهرام", "url": "https://gate.ahram.org.eg/y"}]

print("== counting independent sources ==")
ok("1 two outlets are two sources", len(AP.source_keys(news(two))) == 2)
ok("2 two links to the SAME outlet are one",
   len(AP.source_keys(news([{"name": "في الجول", "url": "https://www.filgoal.com/a"},
                            {"name": "في الجول", "url": "https://filgoal.com/b"}]))) == 1)
ok("3 www. does not make a second domain",
   AP.source_keys(news([{"name": "x", "url": "https://www.filgoal.com/a"}])) == {"filgoal.com"})
ok("4 citing ourselves counts for nothing",
   AP.source_keys(news([{"name": "يلا سكور", "url": "https://yallascore.site/m/1"}])) == set())
ok("5 a source with no url is counted by its name",
   AP.source_keys(news([{"name": "بيان النادي"}])) == {"بيان النادي".casefold()})

print()
print("== what the gate refuses ==")
ok("6 no sources at all is refused", AP.source_problems(news([])))
ok("7 one outlet is refused", AP.source_problems(news(two[:1])))
ok("8 two outlets pass", AP.source_problems(news(two)) == [])
ok("9 a nameless source is reported (the renderer would drop it)",
   any("no name" in x for x in AP.source_problems(news(two + [{"url": "https://z.com"}]))))

print()
print("== the official-announcement hatch ==")
official = [{"name": "النادي الأهلي — بيان رسمي",
             "url": "https://www.alahlyegypt.com/news", "official": True}]
ok("10 one OFFICIAL source is enough", AP.source_problems(news(official)) == [])
ok("11 but it still has to say who it is",
   AP.source_problems(news([{"name": "", "official": True}])) != [])

print()
print("== what the gate must never block ==")
prev = dict(news([]), kind="preview", match_id="4764281")
bad, _ = AP.validate(prev)
ok("12 a match preview with no sources is NOT news and passes",
   not any("independent source" in x for x in bad), bad)
bad, _ = AP.validate(news(two[:1]), updating=True)
ok("13 an update is not gated (the draft carries only changed fields)",
   not any("independent source" in x for x in bad), bad)
bad, _ = AP.validate(news([]))
ok("14 creating a news article with no sources IS refused",
   any("independent source" in x for x in bad), bad)

print()
print("FAILED: " + ", ".join(fails) if fails else "ALL SOURCE-GATE TESTS PASSED")
sys.exit(1 if fails else 0)
