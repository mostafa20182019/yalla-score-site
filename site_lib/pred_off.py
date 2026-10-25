# -*- coding: utf-8 -*-
"""The predictions switch, the text side (user, 2026-10-25: «عايز نوقف نموذج
التوقعات من الموقع بشكل كامل، هنبقى نرجعله بعدين»). See PREDICTIONS_ON in
site_lib/config.py for every surface it turns off.

Existing articles carry prediction parts written while the model was on: 142
bodies have an «توقع يلا سكور» / «هل أصاب توقع يلا سكور؟» section, 53 titles
start «توقع يلا سكور:», 87 FAQs ask what the model said, and most of their
Facebook texts carry a «🤖» model line. hide_predictions() takes those parts
out IN MEMORY at build time - D1 and the export keep the full text, so turning
the switch back on restores every article exactly as it was.

The rules are deliberately narrow: our model's own words («توقع يلا سكور»,
«نموذج يلا سكور», «رجّح النموذج»…), its percentages («احتمال … 58%»), the
betting disclaimer that only ever travels with them, and links to the model's
pages. «الأهداف المتوقعة» (xG) is match data, not a prediction, and stays.
"""
import re

from site_lib.config import PREDICTIONS_ON

MARKS = ("توقع يلا سكور", "توقعات يلا سكور", "نموذج يلا سكور", "رجّح النموذج", "يرجّح النموذج",
         "يرجح النموذج", "رجح النموذج", "النموذج يرجّح", "النموذج يرجح", "توقع النموذج", "توقعات النموذج",
         "ليست نصيحة للمراهنة", "🤖", "/predictions", "/analysis")
# a probability in prose: «احتمال 58%», «باحتمال 22%», «احتمالات الفوز … 40%»
_PROB = re.compile(r"احتمال[^.<\n]{0,60}?\d+\s*[%٪]")
_TITLE = re.compile(r"^\s*توقع(?:ات)?\s+يلا\s+سكور\s*(?:قبل\s+المباراة)?\s*[:：]\s*")
_H2_SECTION = re.compile(r"<h2\b[^>]*>(?P<h>(?:(?!</h2>).)*)</h2>(?P<rest>.*?)(?=<h2\b|\Z)", re.S)
_BLOCK = re.compile(r"<(p|li|blockquote)\b[^>]*>(?:(?!</\1>).)*</\1>", re.S)
_EMPTY_LIST = re.compile(r"<(ul|ol)\b[^>]*>\s*</\1>", re.S)
_SENT = re.compile(r"(?<=[.!؟])\s+")
# FAQ: anything that asks or answers about the model (word-start «توقع» so the
# xG «المتوقعة» stays)
_FAQ_WORDS = re.compile(r"(?<!\w)(?:توقع|توقعات|النموذج|احتمال)")


def has_marks(text):
    t = text or ""
    return any(k in t for k in MARKS) or bool(_PROB.search(t))


def strip_title(title):
    """«توقع يلا سكور: ليفربول يستضيف برايتون» -> «قبل المباراة: ليفربول يستضيف برايتون»."""
    t = title or ""
    return _TITLE.sub("قبل المباراة: ", t) if _TITLE.match(t) else t


def strip_body(html):
    """Drop the sections headed by the model, then any paragraph/list item that
    still speaks for it, then lists left empty."""
    if not html:
        return html
    html = _H2_SECTION.sub(lambda m: "" if has_marks(m.group("h")) else m.group(0), html)
    html = _BLOCK.sub(lambda m: "" if has_marks(m.group(0)) else m.group(0), html)
    return _EMPTY_LIST.sub("", html)


def strip_sentences(text):
    """Plain text (a summary): keep the sentences that do not speak for the model."""
    if not text:
        return text
    return " ".join(s for s in _SENT.split(text) if not has_marks(s)).strip()


def strip_lines(text):
    """A Facebook / Telegram text: drop the model's lines, re-title a preview."""
    if not text:
        return text
    lines = text.split("\n")
    out = []
    for i, ln in enumerate(lines):
        if i == 0:
            ln = strip_title(ln)
        if has_marks(ln):
            continue
        out.append(ln)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def strip_faq(faq):
    if not isinstance(faq, list):
        return faq
    keep = []
    for q in faq:
        if isinstance(q, dict):
            txt = f'{q.get("q") or ""} {q.get("a") or ""}'
            if has_marks(txt) or _FAQ_WORDS.search(txt):
                continue
        keep.append(q)
    return keep


# «…التشكيلتان والتقييمات، وتوقع يلا سكور قبل المباراة» in a source note: the
# phrase goes, the source (365scores, our standings page) stays
_SRC_PHRASE = re.compile(r"\s*[،,]?\s*(?:و)?(?:سجل\s+)?(?:توقع(?:ات)?|نموذج)\s+يلا\s+سكور[^،,]*")


def strip_sources(sources):
    """A source that IS the model (its record page, «نموذج يلا سكور») goes;
    a source that only mentions it keeps its name with the phrase removed."""
    if not isinstance(sources, list):
        return sources
    keep = []
    for s in sources:
        if isinstance(s, dict):
            url, name = str(s.get("url") or ""), str(s.get("name") or "")
            if "/predictions" in url or "/analysis" in url or has_marks(name):
                continue
            if has_marks(s.get("note")):
                s = dict(s, note=_SRC_PHRASE.sub("", str(s["note"])).strip(" ،,"))
                if has_marks(s["note"]):
                    s["note"] = ""
        keep.append(s)
    return keep


def hide_predictions(articles):
    """In place, on the build's in-memory articles. Returns how many changed."""
    n = 0
    for a in articles or []:
        before = (a.get("title"), a.get("summary"), a.get("body"), a.get("fb_post"),
                  str(a.get("faq")), str(a.get("sources")))
        a["title"] = strip_title(a.get("title"))
        a["summary"] = strip_sentences(a.get("summary"))
        a["body"] = strip_body(a.get("body"))
        if a.get("fb_post"):
            a["fb_post"] = strip_lines(a["fb_post"])
        if a.get("faq"):
            a["faq"] = strip_faq(a["faq"])
        if a.get("sources"):
            a["sources"] = strip_sources(a["sources"])
        if before != (a.get("title"), a.get("summary"), a.get("body"), a.get("fb_post"),
                      str(a.get("faq")), str(a.get("sources"))):
            n += 1
    return n


def post_text_ok(text):
    """For the posting scripts: True when the text may go out under the switch."""
    return PREDICTIONS_ON or not has_marks(text)
