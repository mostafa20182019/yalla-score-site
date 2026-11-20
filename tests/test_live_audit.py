# -*- coding: utf-8 -*-
r"""The live layer's audit of 2026-11-20: the runner's lock and the page's
staleness rule. (The Worker's half - the forward-only store and the
fallback's lock - is in tests/test_live_posts.mjs, scenarios A-E.)

    python tests/test_live_audit.py      (from the repo root)
"""
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
for _k in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_D1_ID"):
    os.environ.pop(_k, None)
os.environ["D1_SQLITE"] = os.path.join(tempfile.mkdtemp(), "state.sqlite")

import store            # noqa: E402

store.init_schema()
fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


print("1. store.take: of the runner and the text fallback, exactly one publishes")
assert store.claim("goal", "9001:1", title="t")
rec = store.get_post("goal", "9001:1")
was = rec["claimed_at"]
ck("the first to take an open claim owns it", store.take("goal", "9001:1", was) is True)
ck("the second, holding the same reading, does not", store.take("goal", "9001:1", was) is False)
now = store.get_post("goal", "9001:1")["claimed_at"]
ck("taking MOVES the claim's time, so a reading made before it is stale", now > was, f"{was} -> {now}")
store.record_post("goal", "9001:1", "P1")
ck("a claim already published cannot be taken", store.take("goal", "9001:1", now) is False)
ck("a claim that does not exist cannot be taken", store.take("goal", "nope", 5) is False)

print("2. the runner locks the Worker's claim before it draws")
fp = open("fb_post.py", encoding="utf-8").read()
goal = fp.split("def goal_post(")[1].split("\ndef ")[0]
wh = fp.split("def whistle_post(")[1].split("\ndef ")[0]
ck("goal_post: store.take on the Worker's claim, before the card is rendered",
   'store.take("goal", ref, rec["claimed_at"])' in goal and goal.index("store.take(") < goal.index("GC.render_bytes("))
ck("whistle_post: the same, before its card is rendered",
   'store.take(kind, ref, rec["claimed_at"])' in wh and wh.index("store.take(") < wh.index("GC.render_whistle_bytes("))
lp = open("liveposts.js", encoding="utf-8").read()
fb = lp.split("export async function goalFallbacks")[1].split("\nexport ")[0]
ck("the Worker's fallback takes the same lock before it publishes, and reads claimed_at to do it",
   "SELECT ref_id, title, claimed_at FROM fb_posted" in lp and fb.index("await take(env, kind") < fb.index("await publish(env, row.title"))

print("3. the page never says «مباشر» on old data")
js = open(os.path.join("site_src", "snippets", "live_js.html"), encoding="utf-8").read()
ck("every live paint is stamped with ITS reply's time - the 20-second repaint cannot refresh it",
   "e.__lvT=g.live&&last?last.at:0;" in js)
ck("a row whose stamp is older than STALE loses the live label and the minute",
   "var STALE=150000;" in js and "now-x.e.__lvT>STALE)unlive(x.e)" in js
   and "e.classList.remove('mrow-live')" in js.split("function unlive(e){")[1].split("function sweep")[0]
   and "lv-min" in js.split("function unlive(e){")[1].split("function sweep")[0])
ck("the sweep runs after a paint, after a failed poll, on a failed reply and on the timer",
   js.count("sweep()") >= 5 and ".catch(function(){sweep();schedule(" in js
   and "if(d.ok===false){sweep();schedule(" in js and "if(hadLive)render();else sweep();" in js)
ck("a reply that says it failed does not replace the last good one",
   js.index("if(d.ok===false){sweep();") < js.index("last={gs:d.games||[],at:Date.now()-age};"))
ck("a reply too old to be true paints nothing (the tab woken after an hour)",
   "if(Date.now()-last.at>STALE){sweep();favRender([]);return false;}" in js)
ck("the minute is not advanced from an old reply", "if(Date.now()-at>STALE)return;" in js)
css = open(os.path.join("site_src", "style.css"), encoding="utf-8").read()
ck("the stale label has its own neutral pill", ".pill-stale{" in css)

print("\nALL OK" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
