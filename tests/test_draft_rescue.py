# -*- coding: utf-8 -*-
"""A finished article must not die because the database said no.

Run from the site root:  python tests/test_draft_rescue.py

D1's free tier has a daily row-READ limit as well as a write one, and it has
run out twice (2026-09-16, 2026-09-19). The second time a run had already
found the story, written 545 words, cleared `--check` with three sources and
three FAQ entries and vetted an image — and the INSERT raised «exceeded D1's
free tier daily row read limit». The article was discarded and the next slot
started researching from scratch; checked afterwards, nothing partial had
landed either, so it was simply gone.

So a draft the DATABASE refused is parked under drafts/ and published by the
next run. The distinction this file mostly guards is which failures earn that
rescue: an infrastructure failure does, a bad draft and a duplicate do NOT —
parking those would put a stuck file in front of every future run.
"""
import os, re, sys, io, json, glob, shutil, datetime
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import store
import article_put as AP

fails = []
def ok(n, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + n + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(n)

# park somewhere disposable, never the repo's own drafts/
import tempfile
AP.PENDING_DIR = os.path.join(tempfile.gettempdir(), "test_drafts")
shutil.rmtree(AP.PENDING_DIR, ignore_errors=True)


def draft(title="الأهلي يحسم صفقة جديدة في الميركاتو الشتوي المقبل رسميًا", **kw):
    now = datetime.datetime.now().astimezone()
    d = {"title": title,
         "summary": "ملخص الخبر في جملة واحدة تشرح ما حدث بالضبط اليوم.",
         "body": "<p>" + ("كلمة " * 520) + "</p>",
         "author": "مصطفى عبدالسلام",
         "pub_date": now.date().isoformat(),
         "pub_ts": now.isoformat(timespec="seconds"),
         "image_url": "https://yallascore.site/media/ph-pitch.svg",
         "image_credit": "",
         "sources": [{"name": "في الجول", "url": "https://filgoal.com/a"},
                     {"name": "مصراوي", "url": "https://masrawy.com/b"}],
         "faq": [{"q": "متى؟", "a": "اليوم."}, {"q": "كم؟", "a": "واحد."}]}
    d.update(kw)
    return d


print("== the draft this is all about is a VALID one ==")
bad, words = AP.validate(draft())
ok("1 the fixture passes the same check the run has to pass", not bad, bad)

print()
print("== which failures earn a rescue ==")
_add = store.article_add


def fail_with(exc):
    def boom(*a, **k):
        raise exc
    store.article_add = boom


def run_new(d):
    """--new against a draft file, with the D1 guard satisfied."""
    p = os.path.join(tempfile.gettempdir(), "t_draft.json")
    io.open(p, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False))
    _be, store.backend = store.backend, lambda: "d1"
    _argv, sys.argv = sys.argv, ["article_put.py", "--new", p]
    try:
        return AP.main()
    finally:
        sys.argv, store.backend = _argv, _be


def parked():
    return sorted(os.path.basename(x) for x in
                  glob.glob(os.path.join(AP.PENDING_DIR, "*.json")))


fail_with(RuntimeError("D1 HTTP 400: exceeded D1's free tier daily row read limit"))
rc = run_new(draft())
ok("2 a DATABASE failure parks the draft", len(parked()) == 1, parked())
ok("3 and reports it with its own exit code, not a crash", rc == 2, rc)

shutil.rmtree(AP.PENDING_DIR, ignore_errors=True)
fail_with(store.DuplicateArticle("already covered"))
rc = run_new(draft())
ok("4 a DUPLICATE is not parked — the site already has it",
   parked() == [] and rc == 1, (parked(), rc))

shutil.rmtree(AP.PENDING_DIR, ignore_errors=True)
store.article_add = _add
# thin body: the check the AdSense "low value content" rejection put there
rc = run_new(draft(body="<p>خبر قصير جدًا.</p>"))
ok("5 an INVALID draft is not parked — a stuck file blocks every future run",
   parked() == [] and rc == 1, (parked(), rc))

print()
print("== parking ==")
shutil.rmtree(AP.PENDING_DIR, ignore_errors=True)
p1 = AP.save_pending(draft())
p2 = AP.save_pending(draft())
ok("6 the same draft parked twice is one file, not two", len(parked()) == 1, parked())
ok("7 a different story is its own file",
   AP.save_pending(draft(title="الزمالك يعلن رحيل لاعبه الأجنبي إلى دوري الإمارات"))
   and len(parked()) == 2, parked())
ok("8 the path it reports uses forward slashes, so a git command can take it",
   p1.endswith(".json") and "\\" not in p1, p1)

print()
print("== publishing what was parked ==")
shutil.rmtree(AP.PENDING_DIR, ignore_errors=True)
AP.save_pending(draft())
AP.save_pending(draft(title="الزمالك يعلن رحيل لاعبه الأجنبي إلى دوري الإمارات"))
added = []
store.article_add = lambda rec, clubs=None: (added.append(rec["title"]), "999")[1]
store.article_export = lambda path=None: 500
rc = AP.retry_pending()
ok("9 it publishes a parked draft", len(added) == 1 and rc == 0, (added, rc))
ok("10 exactly ONE per run — the feed must not get three at the same minute",
   len(parked()) == 1, parked())
ok("11 and the published one is gone from the queue",
   not any(added[0] in json.load(io.open(os.path.join(AP.PENDING_DIR, f),
                                         encoding="utf-8"))["title"]
           for f in parked()))

print()
print("== the drafts that must NOT be published ==")
shutil.rmtree(AP.PENDING_DIR, ignore_errors=True)
old = (datetime.datetime.now().astimezone()
       - datetime.timedelta(hours=AP.PENDING_MAX_H + 2)).isoformat(timespec="seconds")
AP.save_pending(draft(pub_ts=old))
added.clear()
rc = AP.retry_pending()
ok("12 a draft older than the window is dropped, not published stale",
   not added and parked() == [], (added, parked()))

shutil.rmtree(AP.PENDING_DIR, ignore_errors=True)
AP.save_pending(draft())
fail_with(store.DuplicateArticle("covered since"))
rc = AP.retry_pending()
ok("13 one the site covered meanwhile is removed, not retried forever",
   parked() == [], parked())

shutil.rmtree(AP.PENDING_DIR, ignore_errors=True)
AP.save_pending(draft())
fail_with(RuntimeError("D1 HTTP 400: exceeded D1's free tier daily row read limit"))
rc = AP.retry_pending()
ok("14 with D1 still down the draft STAYS parked", len(parked()) == 1, parked())
ok("15 and the exit code says so", rc == 2, rc)
store.article_add = _add
shutil.rmtree(AP.PENDING_DIR, ignore_errors=True)
ok("16 nothing parked is not an error", AP.retry_pending() == 0)

print()
print("== the workflow has to carry it off the runner ==")
WF = io.open(".github/workflows/daily-article.yml", encoding="utf-8").read()
PROMPT = io.open(".github/prompts/daily-article.md", encoding="utf-8").read()
_pub = WF.find("Publish a parked draft")
_scan = WF.find("Shortlist today's stories")
_write = WF.find("Write today's article")
_keep = WF.find("Keep a draft D1 refused")
ok("17 a parked draft is published BEFORE the run looks for a new story",
   0 < _pub < _scan < _write, (_pub, _scan, _write))
ok("18 and a newly parked one is committed AFTER the write step",
   _write < _keep, (_write, _keep))
_keepstep = WF[_keep:WF.find("Report outcome")]
# the runner is thrown away at the end of the job: an uncommitted draft is
# exactly as lost as the article we were trying to save
ok("19 the parking step commits — and pushes", "git commit" in _keepstep
   and "git push" in _keepstep)
ok("20 with the image, which the article needs to render",
   "git add drafts media" in _keepstep)
ok("21 it runs even when the Claude step failed", "if: always()" in _keepstep)
ok("22 and it can never fail the run", "continue-on-error: true" in _keepstep)
ok("23 the publish step has the D1 secrets it needs",
   "CF_D1_ID" in WF[_pub:_scan])
ok("24 the prompt tells the run that a parked draft is a success, not a retry loop",
   "parked" in PROMPT and "do not hand-edit" in PROMPT.lower()
   or "لا" in PROMPT and "drafts/" in PROMPT, )

print()
print("FAILED: " + ", ".join(fails) if fails else "ALL DRAFT-RESCUE TESTS PASSED")
sys.exit(1 if fails else 0)
