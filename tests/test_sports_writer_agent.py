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

# 2026-11-08 (user: «عايز graphic-designer agent يكون مسئول عن الصور الخاصة
# بالمقالات والاخبار»): the writer hands every image to graphic-designer.
ok("7 the writer may call graphic-designer - and only it", "Agent(graphic-designer)" in tools, sorted(tools))
GD = ".claude/agents/graphic-designer.md"
g = io.open(GD, encoding="utf-8").read() if os.path.isfile(GD) else ""
gf = re.match(r"---\r?\n(.*?)\r?\n---\r?\n", g, re.S)
ok("8 graphic-designer is in the repo (a CI run can only call agents it can find)",
   gf is not None and re.search(r"^name:\s*graphic-designer\s*$", gf.group(1), re.M) is not None)
ok("9 the designer owns article images and reads the rules file first",
   "Article and news images" in g and ".github/prompts/article-image.md" in g and "image_url:" in g)
IR = ".github/prompts/article-image.md"
r = io.open(IR, encoding="utf-8").read() if os.path.isfile(IR) else ""
ok("10 the rules file carries every image rule that used to live in the prompts",
   all(k in r for k in ("MATCHUP STORIES USE OUR CARD", "CREDIT SELF-TEST", "THE LIVING-STORY TEST",
                        "THE EDITOR'S TEAM FOLDERS COME FIRST", "NO REUSE FROM media/", "IMAGE VARIETY",
                        "HERO CROP CHECK", "WHERE A NEW PHOTO LIVES", "COMPOSE THE NEWS IMAGE", "news_image.py", "find_photo.py",
                        "UNIQUE media/ FILENAME", "THE FOLDER PATH IS NOT EXEMPT", "BEWARE NAME CLASHES")))
ok("11 ...and names the four lines the designer returns",
   all(k in r for k in ("`image_url:", "`image_credit:", "`files:", "`why:")))
ok("12 the writer's agent file hands images over instead of composing them",
   'subagent_type: "graphic-designer"' in a and "You never pick, search, download or compose an image" in a)
for n in ("daily-article", "match-article", "round-article"):
    pr = io.open(f".github/prompts/{n}.md", encoding="utf-8").read()
    ok(f"13 {n}.md hands the image to graphic-designer and no longer runs the photo tools itself",
       'subagent_type: \"graphic-designer\"' in pr or 'subagent_type: "graphic-designer"' in pr,
       "no hand-off")
    ok(f"14 {n}.md does not run hero_card.py / news_image.py / find_photo.py itself",
       "hero_card.py" not in pr and "news_image.py" not in pr and "find_photo.py" not in pr)
ok("15 the rules file makes news_image.py (style C) THE article image and never runs hero_card.py",
   "--debug" in r and "**`hero_card.py` is never run**" in r and "python hero_card.py" not in r)

print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL SPORTS-WRITER AGENT TESTS PASSED")
sys.exit(1 if fails else 0)
