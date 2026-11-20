# -*- coding: utf-8 -*-
r"""The goals video plays on the match page - when its owner allows it (2026-11-20).

    python tests/test_match_video.py      (from the repo root)

A rights holder can switch embedding off per video (beIN SPORTS does). So
highlights.py asks YouTube's own oEmbed for each video and stores the answer,
and the page plays a video in place only for a stored True. Unknown is never
treated as yes, and VideoObject data needs the video's real upload date.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

import highlights as HL                 # noqa: E402
import site_lib.media as MD             # noqa: E402

fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


print("1. learning what may be embedded")
store = {f"v{i}": {"vid": f"v{i}", "kickoff": f"2026-11-{10 + i:02d}"} for i in range(6)}
store["old"] = {"vid": "old", "kickoff": "2026-10-01", "embed": False}
asked = []
answers = {"v5": True, "v4": False, "v3": None, "v2": True}


def ask(vid):
    asked.append(vid)
    return answers.get(vid)


n = HL.check_embeds(store, limit=4, ask=ask)
ck("the newest unknown videos are asked first, `limit` a run, a known one never again",
   asked == ["v5", "v4", "v3", "v2"], str(asked))
ck("yes and no are stored; «could not be learnt» stores nothing and is asked again next run",
   n == 3 and store["v5"]["embed"] is True and store["v4"]["embed"] is False and "embed" not in store["v3"]
   and "embed" not in store["v1"])
ck("the run asks at most EMBED_CHECKS videos", 10 <= HL.EMBED_CHECKS <= 60)
src = open("highlights.py", encoding="utf-8").read()
ck("the answer is YouTube's own (oEmbed: 200 yes, 401/403 no, anything else unknown) - never the channel's name",
   "youtube.com/oembed" in src and "e.code in (401, 403)" in src and "return True if r.status == 200 else None" in src)
ck("run() learns it before saving, and a failure there never loses the run",
   src.index("n_e = check_embeds(store)") < src.index("    save(store, meta)\n    note ="))

print("2. what the page may play")
MD._HL_IDX = {"1": ("https://www.youtube.com/watch?v=a", "ON Sport"), "2": ("u", "beIN SPORTS"), "3": ("u", "x")}
MD._HL_ROW.clear()
MD._HL_ROW.update({"1": {"vid": "a", "embed": True, "channel": "ON Sport"},
                   "2": {"vid": "b", "embed": False, "channel": "beIN SPORTS"},
                   "3": {"vid": "c", "channel": "x"}})
ck("a stored yes plays", (MD.highlight_video(1) or {}).get("vid") == "a")
ck("a stored no does not, and neither does a video nobody asked about",
   MD.highlight_video("2") is None and MD.highlight_video("3") is None and MD.highlight_video("9") is None)
MD._HL_IDX = None
MD._HL_ROW.clear()

print("3. the page")
mp = open(os.path.join("site_pages", "matches.py"), encoding="utf-8").read()
tpl = open(os.path.join("site_src", "templates", "match.html"), encoding="utf-8").read()
ck("the facade (a thumbnail until tapped), on a finished match only, with the player script only when there is a video",
   "video_facade(" in mp and 'if (st == "FINISHED" and hs is not None) else None' in mp
   and "VIDEO_JS if _video else" in mp and "{{ video }}" in tpl and "{{ video_js }}" in tpl)
ck("VideoObject only with the video's real upload date", 'if _hv.get("published"):' in mp
   and '"uploadDate": _hv["published"]' in mp and '"found"' not in mp.split("VideoObject")[1][:600])

print("\nALL OK" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
