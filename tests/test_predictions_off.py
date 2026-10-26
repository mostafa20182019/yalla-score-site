# -*- coding: utf-8 -*-
"""The predictions switch (user, 2026-10-25: «عايز نوقف نموذج التوقعات من الموقع
بشكل كامل، هنبقى نرجعله بعدين. مش عايز أي حاجة تخص التوقعات على الموقع ولا في
بوستات الفيس القادمة»).

    python tests/test_predictions_off.py     (from the repo root)

One constant, site_lib/config.py PREDICTIONS_ON. These checks hold while it is
False; with it True only the switch-independent unit checks run, so turning
the model back on never needs this file edited.
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
os.environ["FB_PREDICTIONS"] = "on"          # the switch must win over the repo variable

from site_lib.config import PREDICTIONS_ON    # noqa: E402
from site_lib import pred_off as P            # noqa: E402

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)

print(f"PREDICTIONS_ON = {PREDICTIONS_ON}")

# ---------------------------------------------- the sanitizer (always checked)
ck("1a a preview title loses the model prefix", P.strip_title("توقع يلا سكور: الفتح × الأهلي") == "قبل المباراة: الفتح × الأهلي")
ck("1b other titles are untouched", P.strip_title("الأهلي يفوز 2-0") == "الأهلي يفوز 2-0")
body = ("<p>مقدمة.</p><h2>توقع يلا سكور</h2><p>نموذج يلا سكور يرجّح فوز برايتون باحتمال 58%.</p><p>ثانية.</p>"
        "<h2>الأرقام التي تحسم اللقاء</h2><ul><li>سجل 23 هدفًا.</li><li>رجّح النموذج التعادل.</li></ul>"
        "<h2>ما وراء النتائج: الأهداف المتوقعة</h2><p>xG 1.4 مقابل 0.6.</p>"
        "<h2>هل أصاب توقع يلا سكور؟</h2><p>نعم.</p>")
out = P.strip_body(body)
ck("2a the «توقع يلا سكور» and «هل أصاب…» sections go whole", "توقع يلا سكور" not in out and "ثانية" not in out and "نعم." not in out, out)
ck("2b a list item that speaks for the model goes, its neighbours stay", "رجّح النموذج" not in out and "سجل 23 هدفًا" in out, out)
ck("2c xG («الأهداف المتوقعة») is match data and stays", "الأهداف المتوقعة" in out and "xG 1.4" in out, out)
ck("2d the plain content stays", "مقدمة." in out and "الأرقام التي تحسم اللقاء" in out, out)
ck("3 a summary keeps only its plain sentences",
   P.strip_sentences("الفتح يستضيف الأهلي. نموذج يلا سكور يرجّح الأهلي.") == "الفتح يستضيف الأهلي.")
faq = [{"q": "متى المباراة؟", "a": "الأحد"}, {"q": "ما توقع يلا سكور؟", "a": "الأهلي 50%"},
       {"q": "من الأقرب؟", "a": "يرجّح النموذج الأهلي"}]
ck("4 the FAQ drops what asks or answers about the model", P.strip_faq(faq) == faq[:1], P.strip_faq(faq))
src = [{"name": "365scores", "url": "x", "note": "التشكيلتان والتقييمات، وتوقع يلا سكور قبل المباراة"},
       {"name": "سجل توقعات يلا سكور", "url": "https://yallascore.site/predictions", "note": ""},
       {"name": "ترتيب الدوري", "url": "https://yallascore.site/standings/egypt", "note": "النقاط"}]
s2 = P.strip_sources(src)
ck("5 a source that IS the model goes; one that mentions it keeps its name without the phrase",
   len(s2) == 2 and s2[0]["note"] == "التشكيلتان والتقييمات" and s2[1]["name"] == "ترتيب الدوري", s2)
fb = "توقع يلا سكور: الفتح × الأهلي\nالأهلي متصدر.\n🤖 نموذج يلا سكور: الأهلي 50%\nالتفاصيل 👇\nhttps://yallascore.site/m/1"
ck("6 a Facebook text loses the model line and the title prefix",
   P.strip_lines(fb) == "قبل المباراة: الفتح × الأهلي\nالأهلي متصدر.\nالتفاصيل 👇\nhttps://yallascore.site/m/1", P.strip_lines(fb))
art = {"title": "توقع يلا سكور: x", "summary": "s.", "body": body, "fb_post": fb, "faq": faq, "sources": src}
ck("7 hide_predictions changes the record and leaves no mark", P.hide_predictions([art]) == 1
   and not any(P.has_marks(art[k] if isinstance(art[k], str) else str(art[k])) for k in ("title", "summary", "body", "fb_post", "faq")))

if not PREDICTIONS_ON:
    # ------------------------------------------------------------ the site
    import site_lib.shell as SH
    hd = SH.head("t", "d", "https://yallascore.site/", active="home")
    ft = SH.foot()
    ck("8a no «التوقعات» nav tab", "/analysis" not in hd and "التوقعات" not in hd)
    ck("8b no footer links to the model's pages", "/analysis" not in ft and "/predictions" not in ft)
    b_src = io.open("build_site.py", encoding="utf-8").read()
    ck("9a the build hides the articles' prediction parts", "hide_predictions(articles_all)" in b_src)
    ck("9b ...empties the predictions for every page", "_preds, _plog = {}, {}" in b_src)
    ck("9c ...skips /analysis + /predictions", "if PREDICTIONS_ON:            # /analysis" in b_src)
    ck("9d ...and build-info still reports the running model (health would warn on 0)",
       "copy_media_and_build_info(_preds_all" in b_src)
    f_src = io.open("site_pages/files.py", encoding="utf-8").read()
    ck("10 the model's URLs answer 302 (temporary) to /matches",
       '"/analysis/*"' in f_src and '/matches 302' in f_src)
    h_src = io.open("site_pages/home.py", encoding="utf-8").read()
    ck("11 the home has no record strip (the home is the match centre only since 2026-10-26)", "home_record_strip" not in h_src)
    # ------------------------------------------------------------ the posts
    import fb_post as FB
    ck("12a FB_PREDICTIONS=on in the environment does not win over the switch", FB.FB_PREDICTIONS is False)
    ck("12b a preview «توقع يلا سكور:» is a prediction post (skipped)",
       FB.is_prediction_post({"kind": "preview", "title": "توقع يلا سكور: x", "fb_post": ""}))
    fbs = io.open("fb_post.py", encoding="utf-8").read()
    ck("12c a report's model line is stripped before posting", "message = _strip_pred(message)" in fbs)
    tgs = io.open("tg_post.py", encoding="utf-8").read()
    ck("13 Telegram skips prediction posts and strips the line too",
       "FB.is_prediction_post(art)" in tgs and "FB._strip_pred(" in tgs)
    import article_put as AP
    ck("14a article_put refuses a draft that speaks for the model",
       AP.prediction_off_problems({"title": "توقع يلا سكور: x", "body": "<p>a</p>"}) != [])
    ck("14b and passes plain xG prose",
       AP.prediction_off_problems({"title": "x", "body": "<p>الأهداف المتوقعة 1.4</p>", "fb_post": "x"}) == [])
    mb = io.open("match_brief.py", encoding="utf-8").read()
    ck("15 match briefs carry no prediction / prediction_check",
       'if kind == "preview" and b.PREDICTIONS_ON' in mb and "prediction_check(m) if b.PREDICTIONS_ON else None" in mb)
    rb = io.open("round_brief.py", encoding="utf-8").read()
    ck("16 round briefs carry no predictions and no model links", "if preds and PREDICTIONS_ON" in rb)
    for p in (".github/prompts/daily-article.md", ".github/prompts/match-article.md", ".github/prompts/round-article.md"):
        ck(f"17 {os.path.basename(p)} says the predictions are switched off",
           "PREDICTIONS ARE SWITCHED OFF" in io.open(p, encoding="utf-8").read())

print()
print(f"{len(fails)} FAILED: {', '.join(fails)}" if fails else "ALL PREDICTIONS-OFF TESTS PASSED")
sys.exit(1 if fails else 0)
