r"""claude_trace.py — the headless runs became readable (2026-09-18).

    python tests/test_claude_trace.py      (from the repo root)

`claude -p` prints only its final message, so the run that ended with «I'll wait
for the scheduled wakeup before retrying the fetch» left nothing to debug: no
fetch, no error, no step. The workflows now pipe --output-format stream-json
through .github/scripts/claude_trace.py.

What must keep holding, because the workflows depend on it:
  * /tmp/claude.txt still receives ONLY the final report - the summary block in
    all three workflows does `tail -n 40 /tmp/claude.txt`;
  * a run that dies before the result event (session limit, crash, cancel) still
    exits non-zero, or "Flag a failed Claude step" would stop warning;
  * a plain non-JSON line (that is how the session-limit message arrives) is not
    swallowed - it has to reach the summary;
  * the trace itself lands in the job summary and in the log.
"""
import json, os, subprocess, sys, tempfile
sys.stdout.reconfigure(encoding="utf-8")

SCRIPT = os.path.join(".github", "scripts", "claude_trace.py")
fails = []

def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


def run(lines):
    """Feed lines to the script the way the shell pipe does; return its world."""
    d = tempfile.mkdtemp()
    res, jsonl, summ = (os.path.join(d, n) for n in ("claude.txt", "claude.jsonl", "summary.md"))
    open(summ, "w").close()
    p = subprocess.run([sys.executable, SCRIPT, "--jsonl", jsonl, "--result", res],
                       input="\n".join(lines) + "\n", capture_output=True, text=True,
                       encoding="utf-8", errors="replace",
                       env={**os.environ, "GITHUB_STEP_SUMMARY": summ,
                            "PYTHONIOENCODING": "utf-8"})
    rd = lambda f: open(f, encoding="utf-8").read()
    return p, rd(res), rd(jsonl), rd(summ)


def ev(o):
    return json.dumps(o, ensure_ascii=False)


ASSISTANT = ev({"type": "assistant", "message": {"content": [
    {"type": "text", "text": "سأبحث عن خبر"},
    {"type": "tool_use", "name": "WebFetch", "input": {"url": "https://news.google.com/rss/search?q=الأهلي"}}]}})
TOOL_ERR = ev({"type": "user", "message": {"content": [
    {"type": "tool_result", "is_error": True, "content": [{"type": "text", "text": "fetch failed: 429"}]}]}})
BASH = ev({"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Bash", "input": {"command": "python article_put.py --file /tmp/a.json"}}]}})

# ------------------------------------------------------- 1 a healthy full run
OK = [ev({"type": "system", "subtype": "init", "model": "claude-sonnet-5"}),
      ASSISTANT, TOOL_ERR, BASH,
      ev({"type": "result", "subtype": "success", "is_error": False,
          "result": "Published successfully.\nArticle 540."})]
p, res, jsonl, summ = run(OK)
ck("1 a successful run exits 0", p.returncode == 0, p.returncode)
ck("2 the result file holds ONLY the final report (workflows tail it)",
   res.strip() == "Published successfully.\nArticle 540.", repr(res[:60]))
ck("3 every tool call is traced live on stdout, with elapsed time",
   "→ WebFetch" in p.stdout and "→ Bash" in p.stdout and "s  " in p.stdout)
ck("4 a failed tool call is marked, not hidden", "✗ tool error" in p.stdout and "429" in p.stdout)
ck("5 the trace is appended to the job summary, collapsed",
   "<details>" in summ and "خطوات Claude" in summ and "WebFetch" in summ)
ck("6 the summary counts the tool calls and the errors",
   "2 استدعاء أداة" in summ and "1 خطأ" in summ, summ[:120])
ck("7 the raw events are kept for a deeper look", jsonl.count("\n") == len(OK))

# ------------------------- 1b the api retries, captured from a real run today
# Ten of these (401, backoff) burned 191 seconds with NOTHING on stdout in text
# mode - the likeliest half of "why did that run take 20 minutes".
RETRY = ev({"type": "system", "subtype": "api_retry", "attempt": 3, "max_retries": 10,
            "retry_delay_ms": 546.697709799183, "error_status": 401,
            "error": "authentication_failed"})
p1b, res1b, _, summ1b = run([RETRY, RETRY,
                             ev({"type": "result", "subtype": "success", "is_error": True,
                                 "result": "Failed to authenticate. API Error: 401"})])
ck("1b api retries are traced with their status and backoff",
   "↻ api retry 3/10" in p1b.stdout and "401" in p1b.stdout and "0.5s" in p1b.stdout)
ck("1c the retries are counted in the summary and the end line",
   "2 إعادة محاولة" in summ1b and "2 api retries" in p1b.stdout, summ1b[:100])
ck("1d is_error=true wins over subtype=success (a real shape, seen today)",
   p1b.returncode == 1 and "ERROR" in p1b.stdout, p1b.returncode)

# --------------------------------------------- 2 the run dies before the end
p2, res2, _, _ = run([ev({"type": "system", "subtype": "init"}), ASSISTANT])
ck("8 no result event (cancel/crash/limit) exits non-zero",
   p2.returncode == 1, p2.returncode)

# ------------------------------------- 3 the session-limit line is not JSON
LIMIT = "You've hit your session limit · resets 10pm (UTC)"
p3, res3, _, _ = run([LIMIT])
ck("9 a plain non-JSON line reaches the report the summary shows",
   LIMIT in res3, repr(res3))
ck("10 and it still counts as a failed run", p3.returncode == 1, p3.returncode)

# ------------------------------------------------- 4 an errored result event
p4, res4, _, _ = run([ev({"type": "result", "subtype": "error_during_execution",
                          "is_error": True, "result": "boom"})])
ck("11 an errored result event exits non-zero", p4.returncode == 1, p4.returncode)

# --------------------------------------------- 5 the workflows are wired to it
for wf in ("daily-article", "match-article", "upgrade-articles"):
    y = open(os.path.join(".github", "workflows", wf + ".yml"), encoding="utf-8").read()
    ck(f"12 {wf} pipes claude through the tracer",
       "--output-format stream-json --verbose" in y
       and "| python .github/scripts/claude_trace.py" in y
       and "tail -n" in y)

# ------------------------------------- 6 the one-shot rule is in every prompt
for pr in ("daily-article", "match-article", "upgrade-article"):
    t = open(os.path.join(".github", "prompts", pr + ".md"), encoding="utf-8").read()
    ck(f"13 {pr} tells Claude the run is one-shot",
       "ONE-SHOT run" in t and "NEVER end your turn saying you will wait" in t)

print()
print(f"{len(fails)} FAILED: {', '.join(fails)}" if fails else "ALL CLAUDE-TRACE TESTS PASSED")
sys.exit(1 if fails else 0)
