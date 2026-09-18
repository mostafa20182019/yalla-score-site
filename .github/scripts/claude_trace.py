#!/usr/bin/env python3
"""Make a headless Claude run readable while it is still running.

`claude -p` in its default text mode prints ONE thing: the final message. A run
that hangs, gets cancelled, or ends with something like «I'll wait for the
scheduled wakeup before retrying the fetch» (2026-09-18) leaves no trace of what
it was actually doing, so there is nothing to debug afterwards.

Piping `--output-format stream-json --verbose` through this script gives:

  * a live one-line-per-tool-call trace on stdout, with elapsed time, so the
    GitHub log shows progress as it happens - a cancelled run still shows its
    last step;
  * the raw JSONL kept at --jsonl for a deeper look;
  * the final report written to --result (default /tmp/claude.txt) so the
    workflow's existing summary block keeps working unchanged;
  * a collapsed trace appended to the job summary;
  * the exit code preserved: 1 when the transcript says the run errored, so
    `continue-on-error` + the "Flag a failed Claude step" warning still fire.

Usage:  claude -p ... --output-format stream-json --verbose | claude_trace.py
"""
import argparse
import json
import os
import sys
import time

TOOL_ARG = {
    "Bash": ("command", 110),
    "WebFetch": ("url", 110),
    "WebSearch": ("query", 80),
    "Read": ("file_path", 80),
    "Write": ("file_path", 80),
    "Edit": ("file_path", 80),
    "Glob": ("pattern", 60),
    "Grep": ("pattern", 60),
    "Task": ("description", 80),
}


def one_line(v, n):
    s = " ".join(str(v).split())
    return s[:n] + ("…" if len(s) > n else "")


def tool_summary(name, inp):
    if not isinstance(inp, dict):
        return ""
    key, n = TOOL_ARG.get(name, (None, 90))
    if key and key in inp:
        return one_line(inp[key], n)
    for v in inp.values():                      # unknown tool: first scalar
        if isinstance(v, (str, int, float)):
            return one_line(v, n)
    return ""


def blocks(msg):
    c = (msg or {}).get("content")
    return c if isinstance(c, list) else []


def result_is_error(ev):
    return bool(ev.get("is_error")) or ev.get("subtype") not in (None, "success")


def main():
    # the trace carries Arabic and arrows; a cp1252 console (Windows, some
    # runners) would abort the whole run on the first print
    for s in (sys.stdout, sys.stdin):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", default="/tmp/claude.jsonl")
    ap.add_argument("--result", default="/tmp/claude.txt")
    ap.add_argument("--summary-lines", type=int, default=150)
    a = ap.parse_args()

    t0 = time.time()
    raw = open(a.jsonl, "w", encoding="utf-8")
    trace, final, plain, tools, errors, retries = [], None, [], 0, 0, 0

    def say(line):
        trace.append(line)
        print(line, flush=True)                 # live in the GitHub log

    for line in sys.stdin:
        raw.write(line)
        raw.flush()
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            plain.append(line)                  # e.g. «You've hit your session limit»
            print(line, flush=True)
            continue

        el = f"{time.time() - t0:6.0f}s"
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            say(f"{el}  ── start · model {ev.get('model', '?')}")
        elif t == "system" and ev.get("subtype") == "api_retry":
            # THE answer to "why did this run take 20 minutes": the CLI retries
            # a failing API call up to 10 times with backoff, silently in text
            # mode. A local check on 2026-09-18 burned 191 s on ten 401 retries.
            retries += 1
            say(f"{el}  ↻ api retry {ev.get('attempt', '?')}/{ev.get('max_retries', '?')}"
                f" · {ev.get('error_status', '?')} {ev.get('error', '')}"
                f" · waiting {round((ev.get('retry_delay_ms') or 0) / 1000, 1)}s")
        elif t == "assistant":
            for b in blocks(ev.get("message")):
                if b.get("type") == "tool_use":
                    tools += 1
                    say(f"{el}  → {b.get('name', '?'):<10} {tool_summary(b.get('name'), b.get('input'))}")
                elif b.get("type") == "text" and b.get("text", "").strip():
                    say(f"{el}  · {one_line(b['text'], 160)}")
        elif t == "user":
            for b in blocks(ev.get("message")):
                if b.get("type") == "tool_result" and b.get("is_error"):
                    errors += 1
                    c = b.get("content")
                    if isinstance(c, list):
                        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                    say(f"{el}  ✗ tool error: {one_line(c, 160)}")
        elif t == "result":
            final = ev
            say(f"{el}  ── end · {ev.get('subtype', '?')}"
                f"{' · ERROR' if result_is_error(ev) else ''}"
                f" · {tools} tool calls · {errors} tool errors · {retries} api retries")

    raw.close()

    text = (final or {}).get("result") or "\n".join(plain) or "(no output from claude)"
    with open(a.result, "w", encoding="utf-8") as f:
        f.write(text if text.endswith("\n") else text + "\n")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and trace:
        tail = trace[-a.summary_lines:]
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"\n<details><summary>🔍 خطوات Claude ({tools} استدعاء أداة"
                    f"{f'، {errors} خطأ' if errors else ''}"
                    f"{f'، {retries} إعادة محاولة' if retries else ''})</summary>\n\n```\n"
                    + "\n".join(tail) + "\n```\n</details>\n\n")

    # No result event at all = claude died before finishing (limit, crash,
    # cancellation). Let the exit code say so; the caller's pipefail keeps
    # claude's own code when it already failed.
    sys.exit(1 if final is None or result_is_error(final) else 0)


if __name__ == "__main__":
    main()
