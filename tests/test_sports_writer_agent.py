# -*- coding: utf-8 -*-
"""The article runs write AS the sports-writer agent (2026-11-06, user:
«عايز ال agent ده هوه اللى يكتبها»): the persona and the house voice live in
.claude/agents/sports-writer.md, the three article workflows pass
`--agent sports-writer` to `claude -p`, and the task prompts keep the
procedure. If the agent file goes missing or a workflow drops the flag, the
run silently falls back to the bare model - this test is what notices.

    python tests/test_sports_writer_agent.py     (from the repo root)
"""
import io, os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
fails = []


def ok(n, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + n + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(n)


AGENT = ".claude/agents/sports-writer.md"
ok("1 the agent file exists", os.path.isfile(AGENT))
a = io.open(AGENT, encoding="utf-8").read() if os.path.isfile(AGENT) else ""
fm = re.match(r"---\r?\n(.*?)\r?\n---\r?\n", a, re.S)
front = fm.group(1) if fm else ""
ok("2 frontmatter names the agent sports-writer", re.search(r"^name:\s*sports-writer\s*$", front, re.M) is not None)
tools = re.search(r"^tools:\s*(.+)$", front, re.M)
tools = {t.strip() for t in tools.group(1).split(",")} if tools else set()
ok("3 the agent keeps the tools a run needs (shell, files, the web, looking at images)",
   {"Read", "Bash", "Write", "WebFetch"} <= tools, sorted(tools))
ok("4 the voice rules are in the agent: one fact per sentence, sources verbatim names, no hand edit of articles.json",
   "ONE fact per sentence" in a and "verbatim" in a and "data/articles.json" in a)
ok("5 the agent defers procedure to the task prompt (the gate, the publish steps stay in .github/prompts)",
   "the task wins" in a)

for n in ("daily-article", "match-article", "round-article"):
    w = io.open(f".github/workflows/{n}.yml", encoding="utf-8").read()
    pat = r'claude -p "\$\(cat \.github/prompts/' + n + r'\.md\)" \\\r?\n\s+--agent sports-writer \\'
    ok(f"6 {n}.yml runs claude -p as the agent", re.search(pat, w) is not None)

print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL SPORTS-WRITER AGENT TESTS PASSED")
sys.exit(1 if fails else 0)
