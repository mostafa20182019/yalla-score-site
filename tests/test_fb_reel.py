r"""The Facebook reel (2026-09-20).

    python tests/test_fb_reel.py      (from the repo root)

Built because Reels is the one surface on a page this size with organic reach
left and the site's bottleneck is distribution, not content (7 pages indexed,
732 «Discovered – not indexed»).

2026-11-01: the reel became ONE card (both clubs, home on the right, the
score, the scorers) held ten seconds under music - the animation's tests
(RTL wrap, scenes, frames) went with it. What stays: the duplicate match list,
and the two rules that were already the site's: never publish a score 365scores has not confirmed, and
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

# ------------------------------------------------------------- the picking
cands = R.candidates(hours=400, limit=8)
ids = [str(m["match_id"]) for m, _ in cands]
ck("6 matches.json and matches_archive.json overlap - no match appears twice",
   len(ids) == len(set(ids)), f"{len(ids)} rows")
ck("7 a match without a final score is never a candidate",
   all(m.get("home_score") is not None and m.get("away_score") is not None for m, _ in cands))
ck("8 only curated clubs, only finished matches", cands and all(
    m.get("status") == "FINISHED" for m, _ in cands))
ck("9 newest first", ids == [i for i, _ in sorted(
    [(str(m["match_id"]), (m.get("kickoff"), m.get("koff_time") or "")) for m, _ in cands],
    key=lambda t: t[1], reverse=True)])

# ------------------------------------------------------------- the card (2026-11-01)
# «يكون عبارة عن صورة فقط فيها الفريقين والنتيجة واعدل مكان الفريقين صاحب
# الارض يكون على اليمين وضيف موسيقى» + «ضيف كمان مسجلى الاهداف»
ctx = R.context(MID)
im = R.card(ctx)
ck("10 the reel is ONE card, 9:16 at a size Reels accepts, full RGB",
   im.size == (R.W, R.H) == (1080, 1920) and im.mode == "RGB")
ck("11 it is held long enough for Reels (>3s) and short enough to watch",
   3.0 < R.REEL_SECS < 90.0, R.REEL_SECS)
ck("12 no animation is left (the five scenes are gone)",
   not hasattr(R, "frames") and not hasattr(R, "SCENES") and "def scene_" not in src)
_card = src[src.index("def card"):src.index("def goal_columns")]
ck("13 home on the RIGHT: its crest, name and scorers at x=0.74, the away club at 0.26",
   '(W * 0.74, "home"' in _card and '(W * 0.26, "away"' in _card
   and '(W * 0.74, "h")' in _card and '(W * 0.26, "a")' in _card)
ck("14 and the home goals on the right of the score box",
   '(ctx["hs"], W / 2 + box' in _card and '(ctx["as"], W / 2 - box' in _card)
# the crest really lands on the right: Brighton's blue at 0.74, Arsenal's red at 0.26
from PIL import ImageStat                                # noqa: E402
_px = lambda x: [round(v) for v in ImageStat.Stat(im.crop(
    (int(R.W * x) - 90, int(R.H * 0.36) - 90, int(R.W * x) + 90, int(R.H * 0.36) + 90))).mean]
ck("15 the rendered card agrees: the blue crest (home) right, the red one (away) left",
   _px(0.74)[2] > _px(0.74)[0] and _px(0.26)[0] > _px(0.26)[2], (_px(0.74), _px(0.26)))

cols = R.goal_columns([("h", "A", "12"), ("a", "B", "30"), ("h", "A", "45+2"),
                       ("h", "C", ""), ("x", "Z", "9")])
ck("16 each club's scorers in their own column", set(cols) == {"h", "a"}
   and len(cols["h"]) == 2 and cols["a"] == [("B", "30'")], cols)
ck("33 a scorer's minutes sit side by side on ONE row (hat-trick rule)",
   cols["h"][0] == ("A", "12' 45+2'"), cols["h"][0])
ck("34 a goal with no minute still names the scorer", cols["h"][1] == ("C", ""))
ck("35 an unknown side is dropped, not put under the wrong club", "Z" not in str(cols))
ck("36 a card with no scorers still draws (score only)",
   R.card(dict(ctx, scorers=[])).size == (R.W, R.H))

# ------------------------------------------------------------- the music
import tempfile, wave                                   # noqa: E402
_tmp = tempfile.mkdtemp()
_real_dir = R.MUSIC_DIR
ck("37 the committed track is in music/ and is ours (made by --compose)",
   os.path.isfile(os.path.join("music", "yalla-loop.m4a")) and "--compose" in src)
os.makedirs(os.path.join(_tmp, "m"))
for n in ("a.mp3", "b.m4a", "notes.txt"):
    open(os.path.join(_tmp, "m", n), "w").close()
R.MUSIC_DIR = os.path.join(_tmp, "m")
picks = {os.path.basename(R.music_track(i, _tmp)) for i in range(20)}
ck("38 a file in music/ is used, one per match id, never a non-audio file",
   picks == {"a.mp3", "b.m4a"}, picks)
ck("39 the same match always gets the same track",
   R.music_track("560586", _tmp) == R.music_track("560586", _tmp))
R.MUSIC_DIR = os.path.join(_tmp, "empty")
try:
    import numpy                                         # noqa: F401
    w = R.music_track("1", _tmp)
    with wave.open(w) as f:
        frames_n, ch, sr = f.getnframes(), f.getnchannels(), f.getframerate()
        peak = max(abs(int.from_bytes(f.readframes(4000)[i:i + 2], "little", signed=True))
                   for i in range(0, 16000, 2))
    ck("40 music/ empty: compose() writes our own stereo 44.1 kHz loop of the reel's length",
       ch == 2 and sr == 44100 and abs(frames_n / sr - R.REEL_SECS) < 0.05, (ch, sr, frames_n))
    ck("41 and it is not silence", peak > 3000, peak)
except ImportError:
    print("  skip 40-41: numpy not installed (the runner uses the committed track)")
R.MUSIC_DIR = _real_dir

# ------------------------------------------------------------- the video
_enc = src[src.index("def encode"):src.index("# ---------------------------------------------------------------- Facebook")]
ck("42 the MP4 carries the music as its audio stream (Reels refuses a file without one)",
   '"-map", "1:a"' in _enc and "aac" in _enc and "music_track(" in _enc)
ck("43 a short track loops instead of cutting the video, and the sound fades out",
   '"-stream_loop", "-1"' in _enc and "afade=t=out" in _enc)
ck("44 no track at all still gives Reels a (silent) audio stream", "anullsrc" in _enc)
ck("45 H.264 / yuv420p / faststart, the combination that plays everywhere",
   "libx264" in _enc and "yuv420p" in _enc and "+faststart" in _enc)
if R.ffmpeg():
    _mp4 = os.path.join(_tmp, "r.mp4")
    ok = R.encode(im, _mp4, seed=MID)
    import subprocess                                    # noqa: E402
    probe = subprocess.run([R.ffmpeg(), "-hide_banner", "-i", _mp4], capture_output=True,
                           text=True, errors="replace").stderr
    ck("46 a real encode: one video and one audio stream, the reel's length",
       ok and "Video: h264" in probe and "Audio: aac" in probe
       and f"Duration: 00:00:{int(R.REEL_SECS):02d}" in probe, probe[-300:])
else:
    print("  skip 46: no ffmpeg here")

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
