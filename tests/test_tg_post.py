r"""The Telegram channel (2026-09-20).

    python tests/test_tg_post.py      (from the repo root)

Built because search sends nobody (7 pages indexed, 732 «Discovered – not
indexed») and Facebook is a channel we do not own. It reuses Facebook's
machinery on purpose, so the tests are the same lessons: the claim is the lock,
the page must be live before the link goes out, and the message must not repeat
itself — `fb_post` is a FINISHED Facebook post (title line, prose, a bare URL,
a call to action, hashtags), not a summary.
"""
import os, re, sys, types
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import tg_post as T
# the channel is paused (user 2026-11-12); the behaviour tests below run with it
# open, and the pause itself is checked at the end
_PAUSED = T.CHANNEL_PAUSED
T.CHANNEL_PAUSED = False
import store

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

ART = {
    "article_id": "557",
    "title": "لودوجوريتس يغلق ملف عودة عبد المجيد",
    "image_url": "https://elgoon.com/media/x.jpg",
    "fb_post": ("لودوجوريتس يغلق ملف عودة عبد المجيد\n"
                "أكد المدير الفني أن اللاعب حسم قراره بمواصلة مسيرته في أوروبا.\n"
                "⚽ خاض 4 مباريات فقط بواقع 276 دقيقة.\n"
                "التفاصيل الكاملة على الموقع 👇\n"
                "https://elgoon.com/a/557.html\n"
                "#الجون #الزمالك #حسام_عبد_المجيد"),
}
msg = T.message(ART)

# ------------------------------------------------------------- the message
ck("1 the title is bold, once", msg.count(ART["title"]) == 1 and msg.startswith("<b>"))
ck("2 the prose survives", "حسم قراره بمواصلة مسيرته" in msg)
ck("3 the bare URL inside the Facebook text is dropped",
   "https://elgoon.com/a/557.html" not in msg)
ck("4 exactly ONE link, and it is the canonical extensionless form",
   msg.count("elgoon.com") == 1 and 'href="https://elgoon.com/a/557"' in msg)
ck("5 the «… على الموقع 👇» call to action is dropped", "👇" not in msg)
ck("6 the writer's own hashtags are kept (richer than anything computed here)",
   "#الجون #الزمالك #حسام_عبد_المجيد" in msg)
ck("7 it fits a photo caption", len(msg) <= T.CAPTION_MAX, f"{len(msg)} of {T.CAPTION_MAX}")

long_art = dict(ART, fb_post=ART["title"] + "\n" + ("كلمة " * 400))
lm = T.message(long_art)
ck("8 an over-long piece is trimmed, not truncated mid-link",
   len(lm) <= T.CAPTION_MAX and lm.rstrip().endswith("#الجون") is False
   and 'href="https://elgoon.com/a/557"' in lm, len(lm))

# a match report posts the MATCH url, like Facebook (the article lives there)
rep = dict(ART, kind="report", match_id="560586", fb_post="عنوان\nنص")
ck("9 a match report links to /m/<id>, not /a/<id>",
   'href="https://elgoon.com/m/560586"' in T.message(rep))

# ------------------------------------------------------------- the guards
src = open("tg_post.py", encoding="utf-8").read()
ck("10 the claim comes BEFORE the post (the duplicate lock)",
   src.index("store.claim(KIND") < src.index("mid = send(art)"))
ck("11 a failed or deferred post releases the claim",
   src.count("store.release(KIND, aid)") >= 2)
ck("12 nothing is posted before the page is live on the edge",
   "FB.wait_live(link)" in src and src.index("FB.wait_live") < src.index("mid = send(art)"))
ck("13 its dedup namespace is its own, not Facebook's", T.KIND == "tg" and T.KIND != "article")
ck("14 no token, no crash: it says what it would post and exits 0",
   T.auto(dry=True) == 0)

wf = open(".github/workflows/publish.yml", encoding="utf-8").read()
step = wf[wf.index("Post new articles to Telegram"):][:600]
# (2026-09-25: the deploy gate - these steps now require that the deploy
# ACTUALLY RAN, steps.deploy.outcome == 'success', not just that main did
# not move: a red gate skips the deploy and must skip the announcements too)
ck("15 it runs after a real deploy and can never fail the publish",
   "steps.deploy.outcome == 'success'" in step and "continue-on-error: true" in step)
ck("16 it gets the store credentials, or the claim would be a no-op json write",
   "CF_D1_ID" in step and "TG_BOT_TOKEN" in step and "TG_CHAT_ID" in step)

# ------------------------------------------------------------- live cards (2026-11-12)
# the goal / full-time card goes to the channel right after Facebook, once
_mem = {}
_st = (store.get_post, store.claim, store.record_post, store.release)
store.get_post = lambda k, r: _mem.get((k, r))
store.claim = lambda k, r, title=None, score=None: (k, r) not in _mem and not _mem.update({(k, r): {"post_id": None}})
store.record_post = lambda k, r, pid, title=None, score=None, og_ok=False: _mem.update({(k, r): {"post_id": pid}})
store.release = lambda k, r: _mem.pop((k, r), None)
_sent = []
_photo, _call = T._send_photo_bytes, T.call
T._send_photo_bytes = lambda img, cap: (_sent.append(("photo", cap)) or {"ok": True, "result": {"message_id": 77}})
T.call = lambda m, p: (_sent.append((m, p.get("text"))) or {"ok": True, "result": {"message_id": 78}})
os.environ.pop("TG_BOT_TOKEN", None)
ck("17 no token -> nothing sent, nothing claimed", T.send_card("goal", "1:1", b"png", "⚽ هدف") is None and not _sent and not _mem)
os.environ["TG_BOT_TOKEN"], os.environ["TG_CHAT_ID"] = "t", "@c"
try:
    first = T.send_card("goal", "1:1", b"png", "⚽ هدف - سطر")
    again = T.send_card("goal", "1:1", b"png", "⚽ هدف - سطر")
    ck("18 the card goes out as a photo once, the second call is a no-op",
       first == "77" and again is None and _sent == [("photo", "⚽ هدف - سطر")] and _mem[("tg-goal", "1:1")]["post_id"] == "77")
    ck("19 no picture -> the text", T.send_card("ft", "9", None, "🏁 انتهت") == "78" and _sent[-1] == ("sendMessage", "🏁 انتهت"))
    T._send_photo_bytes = lambda img, cap: (_ for _ in ()).throw(RuntimeError("down"))
    ck("20 a Telegram error never raises and releases the claim",
       T.send_card("goal", "2:1", b"png", "x") is None and ("tg-goal", "2:1") not in _mem)
finally:
    T._send_photo_bytes, T.call = _photo, _call
    store.get_post, store.claim, store.record_post, store.release = _st
    os.environ.pop("TG_BOT_TOKEN", None); os.environ.pop("TG_CHAT_ID", None)
fbwf = open(".github/workflows/fb-post.yml", encoding="utf-8").read()
fbstep = fbwf[fbwf.index("- name: Post new articles to Facebook"):][:900]
ck("21 the Facebook step that posts goal / whistle cards carries the Telegram secrets",
   "TG_BOT_TOKEN: ${{ secrets.TG_BOT_TOKEN }}" in fbstep and "TG_CHAT_ID: ${{ secrets.TG_CHAT_ID }}" in fbstep)
fbsrc = open("fb_post.py", encoding="utf-8").read()
ck("22 goal_post mirrors every goal, whistle_post only the full-time card",
   '_tg_card("goal", ref, img, caption)' in fbsrc and 'if kind == "ft":' in fbsrc and '_tg_card("ft", ref, img, caption)' in fbsrc)

# ------------------------------------------------------------- the pause (2026-11-12)
T.CHANNEL_PAUSED = True
os.environ['TG_BOT_TOKEN'], os.environ['TG_CHAT_ID'] = 't', '@c'
_sent2 = []
_c2 = T.call
T.call = lambda m, p: (_sent2.append(m) or {'ok': True, 'result': {'message_id': 1}})
try:
    ck('23 paused: a live card sends nothing', T.send_card('goal', '5:1', None, 'x') is None and not _sent2)
    ck('24 paused: the article run sends nothing and exits 0', T.auto() == 0 and not _sent2)
finally:
    T.call = _c2
    os.environ.pop('TG_BOT_TOKEN', None); os.environ.pop('TG_CHAT_ID', None)
ck('25 the channel ships PAUSED (user 2026-11-12)', _PAUSED is True)

print()
print(f"{len(fails)} FAILED: {', '.join(fails)}" if fails else "ALL TELEGRAM TESTS PASSED")
sys.exit(1 if fails else 0)
