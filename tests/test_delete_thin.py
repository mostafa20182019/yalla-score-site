# -*- coding: utf-8 -*-
"""d1_admin --delete-thin picks ONLY the hidden August stubs: under the bar,
plain news, before 2026-09-01, no Facebook post (user decision 2026-10-09)."""
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import d1_admin as D

fails = 0
def ck(name, cond, extra=""):
    global fails
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f"  [{extra}]" if extra and not cond else ""))
    fails += 0 if cond else 1

short = "<p>" + " ".join(["كلمة"] * 150) + "</p>"
long_ = "<p>" + " ".join(["كلمة"] * 600) + "</p>"
A = lambda i, body, date="2026-08-10", kind=None: {"article_id": str(i), "title": f"t{i}", "body": body, "pub_date": date, "kind": kind}
arts = [A(1, short), A(2, long_), A(3, short, "2026-09-05"), A(4, short, kind="preview"),
        A(5, short, kind="analysis"), A(6, short), A(7, short, "2026-07-30")]
picks = D.thin_unlisted(arts, posted_ids={"6"})
ids = [p[0] for p in picks]
ck("1 only the hidden August stubs are picked", ids == ["1", "7"], str(ids))
ck("2 a listed (long) article is never picked", "2" not in ids)
ck("3 a September article is never picked (the bar moved; those were upgraded)", "3" not in ids)
ck("4 match pieces and analyses are never picked", "4" not in ids and "5" not in ids)
ck("5 an article with a live Facebook post is never picked", "6" not in ids)
ck("6 each pick carries its word count and title", picks[0][1] == 150 and picks[0][2] == "t1")
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".github", "workflows", "d1-admin.yml"), encoding="utf-8").read()
ck("7 the workflow offers the task and commits the export after a real run",
   '"delete-thin"' in src and "env.TASK == 'delete-thin' && env.ARGS != 'dry'" in src)
print("\nALL DELETE-THIN TESTS PASSED" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
