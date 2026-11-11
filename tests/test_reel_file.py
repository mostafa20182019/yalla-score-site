r"""A finished reel file posted as it is (2026-11-11).

    python tests/test_reel_file.py

The user had a hand-made reel built («أبرز مباريات الغد» - AFCON qualifiers +
Nations League) and said «جهّز النشر». fb-post.yml's `moment` input with the
value `file:<name>` (all ten inputs GitHub allows are taken) runs
`fb_reel.py --post-file <name>`: drafts/reels/<name>.mp4 goes up with
drafts/reels/<name>.txt as its caption, once per name (store kind reel, ref
file:<name>). Nothing is rendered on the runner - the file he watched is the
file that is posted.
"""
import io, os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import fb_reel as R                                       # noqa: E402

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

calls = []
R.store.get_post = lambda kind, ref: None
R.store.claim = lambda kind, ref, title=None: calls.append(("claim", kind, ref)) or True
R.store.record_post = lambda kind, ref, vid, title=None: calls.append(("record", kind, ref, vid))
R.store.release = lambda kind, ref: calls.append(("release", kind, ref))
R.post_reel = lambda token, path, cap: calls.append(("post", os.path.basename(path), cap.split("\n")[0])) or "v123"

ck("1 a bad name is refused before anything is read", R.file_post("t", "../x") == 1 and not calls)
ck("2 a name with no file on main: 1, nothing claimed", R.file_post("t", "no-such-reel") == 1 and not calls)
name = "next-2026-11-12"
have = os.path.exists(os.path.join(R.REEL_DRAFTS, name + ".mp4"))
if have:
    ck("3 without a token: nothing claimed or posted", R.file_post("", name) == 0 and not calls)
    ck("4 posted once: claim, upload with the caption's first line, record",
       R.file_post("t", name) == 0
       and [c[0] for c in calls] == ["claim", "post", "record"]
       and calls[0][1:] == ("reel", f"file:{name}") and calls[1][1] == f"{name}.mp4"
       and "أبرز مباريات الغد" in calls[1][2] and calls[2][3] == "v123", calls)
    calls.clear()
    R.post_reel = lambda *a: (_ for _ in ()).throw(RuntimeError("refused"))
    ck("5 a refused upload releases the claim (a later run can try again)",
       R.file_post("t", name) == 1 and [c[0] for c in calls] == ["claim", "release"], calls)
    calls.clear()
    R.store.get_post = lambda kind, ref: {"post_id": "v1"}
    ck("6 already posted: 0, nothing claimed", R.file_post("t", name) == 0 and not calls)
else:
    print("  skip 3-6 (the draft reel has been cleaned up)")

wf = io.open(".github/workflows/fb-post.yml", encoding="utf-8").read()
ck("7 fb-post.yml: `moment: file:<name>` runs --post-file, before the moment-script branch",
   'if [ "${MOMENT#file:}" != "$MOMENT" ]; then' in wf
   and 'python fb_reel.py --post-file "${MOMENT#file:}"' in wf
   and wf.index("--post-file") < wf.index("moment_reel.py --script"))

print(f"\n{len(fails)} FAILED" if fails else "\nALL OK")
sys.exit(1 if fails else 0)
