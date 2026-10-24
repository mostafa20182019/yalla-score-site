r"""The Facebook reel (2026-09-20).

    python tests/test_fb_reel.py      (from the repo root)

Built because Reels is the one surface on a page this size with organic reach
left and the site's bottleneck is distribution, not content (7 pages indexed,
732 «Discovered – not indexed»).

The tests are the lessons this one taught, in the order it taught them:
the RTL wrap that read bottom-to-top, the white-on-white card, a 4-0 with no
nameable scorers, the duplicate match list — and the two rules that were
already the site's: never publish a score 365scores has not confirmed, and
never publish to the page without the user's switch.
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

import fb_reel as R                                     # noqa: E402
import fb_cards as C                                    # noqa: E402
from PIL import ImageDraw                               # noqa: E402

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


src = io.open("fb_reel.py", encoding="utf-8").read()
MID = "560586"                                          # برايتون 3-0 أرسنال

# ------------------------------------------------------------- the Arabic
d = ImageDraw.Draw(R.background())
f = C.font("Bold", 38)
SENT = "برايتون في المركز الثالث برصيد 10 نقاط، بفارق نقطتين خلف أرسنال (الثاني)"
lines = R.wrap(d, SENT, f, R.W - 240, lines=3)
ck("1 a long sentence wraps to more than one line", len(lines) > 1, f"{len(lines)} lines")
ck("2 it reads TOP to bottom: the first line starts the sentence",
   C.ar("برايتون") in lines[0] and C.ar("برايتون") not in lines[-1])
ck("3 every line comes out SHAPED, not logical", all(l != l[::-1] for l in lines) and
   all(C.text_w(d, l, f) <= R.W - 240 for l in lines))
ck("4 no word is lost between the lines",
   sum(len(l.split()) for l in lines) == len(SENT.split()))

# the closing scene: white text on a white card drew four empty bars
ck("5 the table cards are drawn with dark text, not white-on-white",
   "C.draw_center(d, W / 2, y + slide, chunk, f, C.INK)" in src
   and "(255, 255, 255, 30)" not in src)

# ------------------------------------------------------------- the picking
cands = R.candidates(hours=400, limit=8)
ids = [str(m["match_id"]) for m, _ in cands]
ck("6 matches.json and matches_archive.json overlap - no match appears twice",
   len(ids) == len(set(ids)), f"{len(ids)} rows")
ck("7 a scoreline we cannot name is not worth a reel",
   all(ctx["scorers"] for m, ctx in cands
       if (m.get("home_score") or 0) + (m.get("away_score") or 0)))
ck("8 only curated clubs, only finished matches", cands and all(
    m.get("status") == "FINISHED" for m, _ in cands))
ck("9 newest first", ids == [i for i, _ in sorted(
    [(str(m["match_id"]), (m.get("kickoff"), m.get("koff_time") or "")) for m, _ in cands],
    key=lambda t: t[1], reverse=True)])

# ------------------------------------------------------------- the frames
ctx = R.context(MID)
fs = R.frames(ctx)
ck("10 a reel is long enough for Reels to accept it (>3s) and short enough to watch",
   3.0 < len(fs) / R.FPS < 90.0, f"{len(fs) / R.FPS:.1f}s")
ck("11 it is 9:16 at a size Reels accepts", (R.W, R.H) == (1080, 1920))
ck("12 a scene with no data is skipped, not drawn empty",
   len(R.frames(dict(ctx, scorers=[], rating=None))) < len(fs))
ck("13 every frame is a full RGB canvas", all(
    im.size == (R.W, R.H) and im.mode == "RGB" for im in fs[::40]))

# ------------------------------------------------------------- the video
ck("14 the MP4 carries a silent audio track (Reels refuses a file without one)",
   "anullsrc" in src and "-c:a" in src and "aac" in src)
ck("15 H.264 / yuv420p / faststart, the combination that plays everywhere",
   "libx264" in src and "yuv420p" in src and "+faststart" in src)
ck("16 the cv2 fallback says it is NOT uploadable instead of pretending",
   src.index("preview only, NOT uploadable") > 0
   and "return False" in src[src.index("def _encode_preview"):])

# ------------------------------------------------------------- publishing
ck("17 it uses the Reels upload, not the feed endpoint fb_post.py posts to",
   "/video_reels" in src and "/me/feed" not in src)
ck("18 three phases, and the bytes go up with an OAuth header",
   all(x in src for x in ('"upload_phase": "start"', '"upload_phase": "finish"',
                          'f"OAuth {token}"')))
ck("19 the page id is read from the token (/me/video_reels does not exist)",
   "def page_id" in src and "me?fields=id" in src)

# the two rules that predate the reel
ck("20 the score is verified BEFORE the claim, like the cards",
   src.index("C.score_verified(m, live)") < src.index("store.claim(KIND, mid"))
ck("21 the claim is the lock, and a failure releases it",
   src.count("store.release(KIND, mid)") >= 3)
ck("22 its dedup namespace is its own", R.KIND == "reel")

# the switch
os.environ.pop("FB_REELS", None)
ck("23 OFF by default: publishing to the page is the user's switch", not R.enabled())
os.environ["FB_REELS"] = "1"
ck("24 and on when the variable says so", R.enabled())
os.environ.pop("FB_REELS", None)
ck("25 no switch, no token, no crash: it says what it would do and exits 0",
   R.auto(dry=True) == 0)
ck("26 --plan answers no while the switch is off", R.plan() == 0)

# the store going away — what actually happened on the first live attempt:
# D1's free-tier daily row-read limit refused every query and the step died
# with a traceback instead of deferring
import store                                             # noqa: E402
_real = store.posted_ids
store.posted_ids = lambda kind: (_ for _ in ()).throw(
    RuntimeError("D1 HTTP 400: exceeded the daily row read limit"))
ck("30 an unreadable store defers, it does not raise", R.auto() == 0)
ck("31 and --plan answers no rather than crashing the step", R.plan() == 0)
ck("32 an unreadable store is NOT an empty posted set (that would double-post)",
   R._posted() is None)
store.posted_ids = _real

# ------------------------------------------------------------- 2026-10-24, the user's two asks
# «أنا عايز أهداف كل فريق لوحده» — the goals scene is two club columns, one
# row per scorer with his minutes side by side, never one mixed list
cols = R.goal_columns([("h", "A", "12"), ("a", "B", "30"), ("h", "A", "45+2"),
                       ("h", "C", ""), ("x", "Z", "9")])
ck("33 each club gets its own column", set(cols) == {"h", "a"} and len(cols["h"]) == 2
   and cols["a"] == [("B", "30'")], cols)
ck("34 a scorer's minutes sit side by side on ONE row (hat-trick rule)",
   cols["h"][0] == ("A", "12' 45+2'"), cols["h"][0])
ck("35 a goal with no minute still names the scorer", cols["h"][1] == ("C", ""))
ck("36 an unknown side is dropped, not drawn", "Z" not in str(cols))
_scn = src[src.index("def scene_scorers"):src.index("def scene_rating")]
ck("37 the scene draws both crests and names and a «بدون أهداف» for a side that did not score",
   '"home_badge"' not in _scn and 'f"{key}_badge"' in _scn and "بدون أهداف" in _scn)
ck("38 and it no longer prints the club name on every row (that was the mixed list)",
   "C.ar(club)" not in _scn)
# «الجزء الأخير بيعدي بسرعة» — the closing scene finishes animating at ~1.5s,
# so it must hold well past that
_cta = dict(R.SCENES)["cta"]
ck("39 the closing scene holds at least 3 seconds after its last line lands", _cta >= 4.5, _cta)
ck("40 and the whole reel still fits a Reel (under 90s)", sum(s for _, s in R.SCENES) < 90)

wf = io.open(".github/workflows/publish.yml", encoding="utf-8").read()
step = wf[wf.index("Is there a reel to make?"):][:1400]
ck("27 the workflow runs it only after a real deploy, and never fails the publish",
   "steps.deploy.outcome == 'success'" in step and step.count("continue-on-error: true") == 2)
ck("28 ffmpeg is installed only on the runs that have a reel to make",
   "steps.reel.outputs.make == 'yes'" in step and "install -y -qq ffmpeg" in step)
ck("29 the workflow is gated on the variable too, not only on the code",
   "vars.FB_REELS == '1'" in step)

print()
print(f"{len(fails)} FAILED: {', '.join(fails)}" if fails else "ALL REEL TESTS PASSED")
sys.exit(1 if fails else 0)
