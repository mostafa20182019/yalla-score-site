"""The deploy gate's own wiring (2026-09-25).

    python tests/run_all.py --gate     # what publish.yml runs before the deploy
    python tests/test_deploy_gate.py

A gate that a later edit quietly disconnects protects nothing and still looks
green, so this pins the wiring: the gate runs after the build and before the
deploy, the deploy depends on it (with the documented escape hatch), nothing
that announces a deploy can run when the deploy did not, a red gate is
critical in the verdict, and the live-data exclusions are real files with a
reason each.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "tests"))
sys.stdout.reconfigure(encoding="utf-8")
import run_all  # noqa: E402

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


wf = open(".github/workflows/publish.yml", encoding="utf-8").read()
tests_wf = open(".github/workflows/tests.yml", encoding="utf-8").read()

i_build = wf.index("name: Build the static site")
i_save = wf.index("name: Save the working data")
i_gate = wf.index("name: Tests (the deploy gate)")
i_deploy = wf.index("name: Deploy to Cloudflare")
ck("1 order: build -> save the data -> gate -> deploy", i_build < i_save < i_gate < i_deploy)

gate_step = wf[i_gate:wf.index("\n\n", i_gate)]
ck("2 the gate runs the --gate suite, after a green build, and never stops the job itself",
   "python tests/run_all.py --gate" in gate_step and "steps.build.outcome == 'success'" in gate_step
   and "continue-on-error: true" in gate_step)

deploy_if = re.search(r"name: Deploy to Cloudflare\s+id: deploy\s+if: (.+)", wf).group(1)
ck("3 the deploy requires the gate, with the TESTS_GATE=off escape hatch",
   "steps.gate.outcome == 'success'" in deploy_if and "vars.TESTS_GATE == 'off'" in deploy_if
   and "steps.tip.outputs.fresh == 'true'" in deploy_if, deploy_if)

after = wf[wf.index("name: Tell IndexNow what changed"):wf.index("name: Commit shrunk photos")]
conds = re.findall(r"\n        if: (.+)", after)
announce = [c for c in conds if "steps.reel.outputs.make" not in c]
ck("4 every announcing step needs the deploy to have RUN, not just main unmoved",
   announce and all("steps.deploy.outcome == 'success'" in c for c in announce)
   and "steps.tip.outputs.fresh" not in after, f"{len(announce)} steps")

ck("5 a red gate is critical in the verdict and shows in the summary",
   '[ "$O_GATE" = "failure" ] && CRIT="$CRIT tests"' in wf and "tests (deploy gate)" in wf)

missing = [n for n in run_all.DATA_TESTS if not os.path.exists(os.path.join("tests", n))]
ck("6 every live-data exclusion is a real test file with a stated reason",
   not missing and all(v.strip() for v in run_all.DATA_TESTS.values()), missing)
ck("7 the gate keeps most of the suite (exclusions stay the exception)",
   len(run_all.DATA_TESTS) <= 12, f"{len(run_all.DATA_TESTS)} excluded")
ck("8 tests.yml still runs EVERYTHING (the live-data tests report there)",
   "python tests/run_all.py\n" in tests_wf and "--gate" not in tests_wf)

print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL OK")
sys.exit(1 if fails else 0)
