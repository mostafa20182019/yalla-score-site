# -*- coding: utf-8 -*-
"""The SEO gate: the rules the audit of 2026-11-06 put in the prompts, as checks.

    article_put.py --check draft.json            # runs them (validate -> seo_problems)
    python seo_gate.py draft.json [brief.json]   # the same, on its own

A rule the writer can ignore is a wish; a rule the gate refuses on is a rule
(the same reason every editorial rule here is a test). Each problem names the
fix, so a one-shot writer run can repair the draft and re-check.

What is checked (news, previews, reports and round reviews alike unless noted):

  title     30-72 characters; no colon prefix («تقرير:», «قبل المباراة:»,
            «تحليل:», «توقع الجون:», «عاجل:», «رسميًا:»); no «×» (people
            type «مباراة X وY»). Preview: «موعد مباراة» + both clubs.
            Report: both clubs + the score (or «نتيجة مباراة»). Round
            review: starts with «ترتيب …» or «نتائج الجولة …».
  summary   60-160 characters - it is the meta description.
  lead      the first paragraph does not repeat the summary.
  h2        at least three; at least one carries the story's entity (a word
            of the title, or a club of the match) - five bare template
            headings in 200+ articles was the audit's finding.
  links     internal links in the body: 3 for news, 2 for a match piece;
            each target must exist (/team/<slug>, /standings|/scorers|
            /fixtures/<slug>, /a/<id>, /m/<id>); a match piece never links
            its own match page (the article is rendered inside it).
  faq       at least two pairs; the first in the searcher's words (starts
            with متى / كم / من / ما / هل / أين); a preview's first asks
            the kick-off (موعد/متى), a report's first asks the result
            (نتيجة); no «متى لعبت» after the whistle.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

BAD_PREFIXES = ("تقرير:", "تقرير :", "قبل المباراة:", "تحليل:", "توقع الجون:", "عاجل:",
                "رسميًا:", "رسميا:", "رسمياً:")
GENERIC_H2 = {"ماذا حدث؟", "الخلفية", "ماذا قالت المصادر؟", "الأرقام", "ما التالي؟"}
QUESTION_STARTS = ("متى", "كم", "من", "ما", "هل", "أين", "ماذا", "لماذا", "كيف")
_STOP = {"مباراة", "الدوري", "أمام", "بعد", "قبل", "خلال", "اليوم", "المصري", "الفريق",
         "نادي", "لاعب", "الجولة", "موعد", "نتيجة", "المباراة", "بطولة", "دوري", "أبطال",
         "الموسم", "الجديد", "يعلن", "رسميًا", "رسميا", "مواجهة", "والقناة", "الناقلة",
         "أوروبا", "كأس", "مصر", "عاصمة", "بنتيجة", "يفوز", "يهزم", "على", "ضد"}

_cache = {}


def _load(name):
    p = os.path.join(HERE, "data", name)
    if name not in _cache:
        try:
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
            if isinstance(d, dict) and "results" in d:
                d = d["results"][0]["items"]
            _cache[name] = d
        except Exception:
            _cache[name] = None
    return _cache[name]


def _known_targets():
    """slug/id sets the link check resolves against (None = data not here)."""
    if "targets" in _cache:
        return _cache["targets"]
    sys.path.insert(0, HERE)
    try:
        from site_lib.clubs import TEAM_PAGES
        from site_lib.competitions import COMP_SLUG
        teams = {tp["slug"] for tp in TEAM_PAGES}
        comps = set(COMP_SLUG.values())
    except Exception:
        teams = comps = None
    arts = _load("articles.json")
    art_ids = {str(a.get("article_id")) for a in arts} if arts else None
    mids = set()
    for name in ("matches.json", "matches_archive.json"):
        d = _load(name)
        if d:
            mids |= {str(m.get("match_id")) for m in d if m.get("match_id")}
    fx = _load("fixtures.json")
    if fx:
        for comp in fx:
            for rd in comp.get("rounds") or []:
                mids |= {str(m.get("match_id")) for m in rd.get("matches") or [] if m.get("match_id")}
    _cache["targets"] = {"teams": teams, "comps": comps, "arts": art_ids, "matches": mids or None}
    return _cache["targets"]


def _strip(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def _words(s):
    return {w.strip("،:.,؟!\"'()«»—-") for w in (s or "").split()}


def _entity_words(title):
    return {w for w in _words(title) if len(w) >= 4 and w not in _STOP}


def internal_links(body):
    """(path, kind) for every link into our own site in the body."""
    out = []
    for href in re.findall(r'href="([^"]+)"', body or ""):
        h = href.strip()
        m = re.match(r"https?://(?:www\.)?(?:elgoon\.com|yallascore\.site)(/.*)?$", h)
        if m:
            h = m.group(1) or "/"
        if not h.startswith("/"):
            continue
        path = h.split("?")[0].split("#")[0]
        if path.endswith(".html"):
            path = path[:-5]
        out.append(path)
    return out


def seo_problems(rec, brief=None):
    out = []
    if os.environ.get("SEO_GATE") == "0":
        # tests of the OTHER gates (sources, numbers, rescue) use skeleton
        # drafts; they switch this one off. Never set in a workflow.
        return out
    kind = rec.get("kind")
    if kind == "analysis":
        return out
    is_match = kind in ("preview", "report")
    is_round = isinstance(brief, dict) and brief.get("kind") == "round-review"
    title = (rec.get("title") or "").strip()
    summary = (rec.get("summary") or "").strip()
    body = rec.get("body") or ""

    # ---- title
    if title and not 30 <= len(title) <= 72:
        out.append(f"title is {len(title)} characters - keep it 45-65 (Google cuts longer ones)")
    for p in BAD_PREFIXES:
        if title.startswith(p):
            out.append(f"title starts with «{p}» - no colon prefix; say the news or the match in the searcher's words")
            break
    if "×" in title or " x " in title.lower():
        out.append("title joins the clubs with «×» - write «مباراة X وY», that is what people type")
    mb = (brief or {}).get("match") if isinstance(brief, dict) else None
    if is_match and mb:
        h, a = mb.get("home") or "", mb.get("away") or ""
        if h and a and not (h in title and a in title):
            out.append(f"a {kind} title names BOTH clubs: «{h}» and «{a}»")
        if kind == "preview" and "موعد" not in title:
            out.append("a preview title starts with «موعد مباراة X وY …» (… «والقناة الناقلة» when it fits)")
        if kind == "report":
            sc = mb.get("score")
            if "نتيجة مباراة" not in title and not (sc and sc in title):
                out.append(f"a report title carries the result: «نتيجة مباراة X وY {sc or 'h-a'}: …» "
                           f"or «X يفوز على Y {sc or 'h-a'}..»")
    if is_round and title and not (title.startswith("ترتيب") or title.startswith("نتائج الجولة")):
        out.append("a round review's title starts with «ترتيب {البطولة} بعد الجولة N:» "
                   "(or «نتائج الجولة N من {البطولة}:» when there is no table)")

    # ---- summary = meta description
    if summary and len(summary) > 160:
        out.append(f"summary is {len(summary)} characters - it is the page's meta description, "
                   "keep it to ONE sentence of 110-155 characters that carries the answer")
    elif summary and len(summary) < 60:
        out.append(f"summary is {len(summary)} characters - too short for a meta description "
                   "(110-155, with the entity and the answer)")

    # ---- lead paragraph vs summary
    paras = [_strip(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", body, re.S)]
    paras = [p for p in paras if p]
    if paras and summary:
        lead = paras[0]
        if lead == summary or (len(summary) > 60 and (summary[:70] in lead or lead[:70] in summary)):
            out.append("the first paragraph repeats the summary - the page prints the summary "
                       "right above it; open with who/what/when and the one number that matters")

    # ---- h2s carry the entity
    h2s = [_strip(x) for x in re.findall(r"<h2[^>]*>(.*?)</h2>", body, re.S)]
    if body and len(h2s) < 3:
        out.append(f"{len(h2s)} <h2> heading(s) - the structure needs at least three")
    if h2s:
        ents = _entity_words(title)
        if is_match and mb:
            ents |= {mb.get("home") or "", mb.get("away") or ""} - {""}
        carried = any(any(e and e in h for e in ents) for h in h2s)
        if not carried:
            out.append("no <h2> carries the story's entity (a club or a name from the title) - "
                       "«إصابة بن بوعلي: ماذا حدث؟», «ترتيب الدوري المصري بعد المباراة», not the bare template headings")

    # ---- internal links
    links = internal_links(body)
    need = 2 if is_match else 3
    if body and len(links) < need:
        out.append(f"{len(links)} internal link(s) in the body - at least {need}: "
                   "/team/<slug>, /standings/<slug>, /m/<match_id> or /a/<id>, each resolved from the data")
    T = _known_targets()
    own = f"/m/{rec.get('match_id')}" if is_match and rec.get("match_id") else None
    for path in links:
        if own and path == own:
            out.append(f"links its own match page {own} - the article is rendered INSIDE it; "
                       "link the club page or the standings instead")
            continue
        m = re.match(r"^/(team|standings|scorers|fixtures|a|m)/([^/]+)$", path)
        if not m:
            continue
        sec, key = m.groups()
        if sec == "team" and T["teams"] is not None and key not in T["teams"]:
            out.append(f"link target /team/{key} does not exist - slugs: {', '.join(sorted(T['teams']))}")
        elif sec in ("standings", "scorers", "fixtures") and T["comps"] is not None and key not in T["comps"]:
            out.append(f"link target /{sec}/{key} does not exist - slugs: {', '.join(sorted(T['comps']))}")
        elif sec == "a" and T["arts"] is not None and key not in T["arts"]:
            out.append(f"link target /a/{key} is not an article in data/articles.json - link one that exists")
        elif sec == "m" and T["matches"] is not None and key not in T["matches"]:
            out.append(f"link target /m/{key} is not a match in the data - take the id from data/matches.json or fixtures.json")

    # ---- faq in the searcher's words
    faq = [f for f in (rec.get("faq") or []) if isinstance(f, dict) and f.get("q") and f.get("a")]
    if body and len(faq) < 2:
        out.append(f"{len(faq)} FAQ pair(s) - at least two, in the words people search")
    if faq:
        q1 = faq[0]["q"].strip()
        if not q1.startswith(QUESTION_STARTS):
            out.append(f"the first FAQ question «{q1[:50]}» must start with متى / كم / من / ما / هل / لماذا / كيف")
        if kind == "preview" and not ("موعد" in q1 or q1.startswith("متى")):
            out.append("a preview's first FAQ asks the kick-off: «متى موعد مباراة X وY وما القناة الناقلة؟»")
        if kind == "report" and "نتيجة" not in q1:
            out.append("a report's first FAQ asks the result: «ما نتيجة مباراة X وY؟»")
        for f in faq:
            if "متى لعبت" in f["q"] or "متى أقيمت" in f["q"]:
                out.append(f"FAQ «{f['q'][:50]}» - nobody searches when a match was played after the whistle; "
                           "ask the result, the scorers or the table instead")
                break
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    with open(sys.argv[1], encoding="utf-8") as fh:
        rec = json.load(fh)
    if isinstance(rec, dict) and "results" in rec:
        rec = rec["results"][0]["items"][0]
    brief = None
    if len(sys.argv) > 2:
        with open(sys.argv[2], encoding="utf-8") as fh:
            brief = json.load(fh)
    probs = seo_problems(rec, brief)
    for p in probs:
        print("  - " + p)
    print("seo: ok" if not probs else f"seo: {len(probs)} problem(s)")
    sys.exit(1 if probs else 0)
