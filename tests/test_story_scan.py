# -*- coding: utf-8 -*-
"""story_scan.py — the shortlist handed to the daily-article run.

Run from the site root:  python tests/test_story_scan.py

The thing this file mostly guards is DRIFT. The shortlist is only useful if
it covers the same ground the prompt would have covered itself, so the
queries here and the queries in .github/prompts/daily-article.md must stay
the same set — and nothing in the build would notice if they stopped.

The rest pins the two properties that make the step safe to add at all:

  * it is a BRIEFING, NOT A GATE. Measured 2026-09-19: 64 stories carry 2+
    outlets and 63 of them are not on the site, and the articles-per-day
    counts (8, 7, 2, 8, 4 over 09-14..09-18) predict nothing. A gate on
    either signal skips real articles or saves nothing. So the workflow must
    run the scan and then run Claude regardless.
  * every failure is silent. No file, no crash, exit 0 — the prompt falls
    back to searching for itself, which is what it did before this existed.
"""
import os, re, sys, io, json, tempfile
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import fetch_data as FD
import story_scan as S

fails = []
def ok(n, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + n + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(n)

PROMPT = io.open(".github/prompts/daily-article.md", encoding="utf-8").read()
WF = io.open(".github/workflows/daily-article.yml", encoding="utf-8").read()

print("== the shortlist covers the ground the prompt would have covered ==")
missing = [q for q in S.EGY_QUERIES + S.CLUB_QUERIES if q not in PROMPT]
ok("1 every query the scan runs is one the prompt names", not missing, missing)
# the other direction: the prompt lists its Egyptian queries in one bracket
_egy = re.search(r"Egyptian queries \(([^)]+)\)", PROMPT)
_named = [w.strip() for w in _egy.group(1).split("،")] if _egy else []
ok("2 and every Egyptian query the prompt names is one the scan runs",
   _named and all(q in S.EGY_QUERIES for q in _named),
   [q for q in _named if q not in S.EGY_QUERIES])
ok("3 the prompt tells the run to read the shortlist first",
   "/tmp/story_candidates.json" in PROMPT and "START FROM THE SHORTLIST" in PROMPT)

print()
print("== it clusters with the site's own logic, not a copy ==")
ok("4 the tokeniser is fetch_data's", S.FD._title_tokens is FD._title_tokens)
ok("5 and so is the near-duplicate test", S.FD._same_story is FD._same_story)

print()
print("== the shortlist itself ==")
ITEMS = [
    # one story, four outlets -> a candidate
    ("الأهلي يجدد عقد ياسر إبراهيم حتى 2029", "في الجول", 2.0, "http://g/1"),
    ("الأهلي يجدد عقد ياسر إبراهيم رسميا حتى 2029", "مصراوي", 3.0, "http://g/2"),
    ("رسميا الأهلي يجدد عقد ياسر إبراهيم 2029", "اليوم السابع", 4.0, "http://g/3"),
    ("تجديد عقد ياسر إبراهيم مع الأهلي حتى 2029", "الوطن", 5.0, "http://g/4"),
    # one story, two outlets -> below the shortlist bar
    ("الزمالك يتعاقد مع مدرب حراس جديد", "الوطن", 2.0, "http://g/5"),
    ("الزمالك يضم مدرب حراس جديد للجهاز", "مصراوي", 2.5, "http://g/6"),
    # blocked-in-Egypt outlets must not count as outlets at all
    ("خبر من مصدر محجوب عن الأهلي والزمالك معا", "الجزيرة", 1.0, "http://g/7"),
    # too old
    ("الأهلي يجدد عقد ياسر إبراهيم حتى 2029", "الأهرام", 99.0, "http://g/8"),
]
_real_rss, _real_cov = S.rss, S.covered_tokens
S.rss = lambda q: ITEMS if q == S.EGY_QUERIES[0] else []
S.covered_tokens = lambda: []
cands, lines = S.scan()
titles = " | ".join(c["title"] for c in cands)
ok("6 a story on 4 outlets makes the shortlist", "ياسر إبراهيم" in titles, titles)
ok("7 a story on 2 does not (the bar is 3, measured — 2 is noise)",
   "مدرب حراس" not in titles, titles)
ok("8 the outlet count is the number of DISTINCT outlets",
   cands and cands[0]["n_outlets"] == 4, cands[0] if cands else None)
ok("9 an outlet blocked inside Egypt is not a source",
   not any("محجوب" in c["title"] for c in cands), titles)
ok("10 a headline older than the window is dropped",
   cands and "الأهرام" not in cands[0]["outlets"], cands[0] if cands else None)
ok("11 the entry carries links to read", cands and len(cands[0]["links"]) >= 3,
   cands[0]["links"] if cands else None)

# the dedup against our own archive
S.covered_tokens = lambda: [FD._title_tokens("الأهلي يجدد عقد ياسر إبراهيم حتى 2029", None)]
cands2, _ = S.scan()
ok("12 a story we already published is not offered again",
   not any("ياسر إبراهيم" in c["title"] for c in cands2),
   [c["title"] for c in cands2])
S.rss, S.covered_tokens = _real_rss, _real_cov

print()
print("== every failure is silent ==")
S.rss = lambda q: (_ for _ in ()).throw(RuntimeError("network down"))
S.covered_tokens = lambda: (_ for _ in ()).throw(RuntimeError("no archive"))
_out = os.path.join(tempfile.gettempdir(), "test_story_scan_out.json")
if os.path.exists(_out):
    os.remove(_out)
_argv = sys.argv
sys.argv = ["story_scan.py", "--out", _out]
rc = S.main()
sys.argv = _argv
S.rss, S.covered_tokens = _real_rss, _real_cov
ok("13 a total failure still exits 0 — it must never fail the run", rc == 0, rc)
ok("14 and writes no shortlist, so the prompt falls back to searching",
   not os.path.exists(_out))
ok("15 the prompt states that fallback",
   "If the file is missing, empty, or nothing in it qualifies" in PROMPT)

print()
print("== the workflow wires it as a briefing, not a gate ==")
_scan_at = WF.find("story_scan.py")
_claude_at = WF.find("Write today's article")
ok("16 the scan runs before the Claude step",
   0 < _scan_at < _claude_at, (_scan_at, _claude_at))
_step = WF[WF.find("- name: Shortlist"):_claude_at]
ok("17 a failed scan cannot fail the run", "continue-on-error: true" in _step)
ok("18 and NOTHING gates the Claude step on its output",
   "story_scan" not in WF[_claude_at:] and "has_story" not in WF, )
# the 12 was set on an estimate of 5-7 minutes; the runs that published took
# 8.4, 9.8 and 10.6, leaving 1.4 minutes of headroom over a normal success
ok("19 the Claude step's cap is 15 minutes, not the too-tight 12",
   "timeout-minutes: 15" in WF and "timeout-minutes: 12" not in WF)
ok("20 and the job timeout still stands behind it", "timeout-minutes: 30" in WF)

print()
print("FAILED: " + ", ".join(fails) if fails else "ALL STORY-SCAN TESTS PASSED")
sys.exit(1 if fails else 0)
