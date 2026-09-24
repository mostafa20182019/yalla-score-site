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
import store

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

ART = {
    "article_id": "557",
    "title": "لودوجوريتس يغلق ملف عودة عبد المجيد",
    "image_url": "https://yallascore.site/media/x.jpg",
    "fb_post": ("لودوجوريتس يغلق ملف عودة عبد المجيد\n"
                "أكد المدير الفني أن اللاعب حسم قراره بمواصلة مسيرته في أوروبا.\n"
                "⚽ خاض 4 مباريات فقط بواقع 276 دقيقة.\n"
                "التفاصيل الكاملة على الموقع 👇\n"
                "https://yallascore.site/a/557.html\n"
                "#يلا_سكور #الزمالك #حسام_عبد_المجيد"),
}
msg = T.message(ART)

# ------------------------------------------------------------- the message
ck("1 the title is bold, once", msg.count(ART["title"]) == 1 and msg.startswith("<b>"))
ck("2 the prose survives", "حسم قراره بمواصلة مسيرته" in msg)
ck("3 the bare URL inside the Facebook text is dropped",
   "https://yallascore.site/a/557.html" not in msg)
ck("4 exactly ONE link, and it is the canonical extensionless form",
   msg.count("yallascore.site") == 1 and 'href="https://yallascore.site/a/557"' in msg)
ck("5 the «… على الموقع 👇» call to action is dropped", "👇" not in msg)
ck("6 the writer's own hashtags are kept (richer than anything computed here)",
   "#يلا_سكور #الزمالك #حسام_عبد_المجيد" in msg)
ck("7 it fits a photo caption", len(msg) <= T.CAPTION_MAX, f"{len(msg)} of {T.CAPTION_MAX}")

long_art = dict(ART, fb_post=ART["title"] + "\n" + ("كلمة " * 400))
lm = T.message(long_art)
ck("8 an over-long piece is trimmed, not truncated mid-link",
   len(lm) <= T.CAPTION_MAX and lm.rstrip().endswith("#يلا_سكور") is False
   and 'href="https://yallascore.site/a/557"' in lm, len(lm))

# a match report posts the MATCH url, like Facebook (the article lives there)
rep = dict(ART, kind="report", match_id="560586", fb_post="عنوان\nنص")
ck("9 a match report links to /m/<id>, not /a/<id>",
   'href="https://yallascore.site/m/560586"' in T.message(rep))

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
ck("15 it runs after a real deploy and can never fail the publish",
   "fresh == 'true'" in step and "continue-on-error: true" in step)
ck("16 it gets the store credentials, or the claim would be a no-op json write",
   "CF_D1_ID" in step and "TG_BOT_TOKEN" in step and "TG_CHAT_ID" in step)

print()
print(f"{len(fails)} FAILED: {', '.join(fails)}" if fails else "ALL TELEGRAM TESTS PASSED")
sys.exit(1 if fails else 0)
