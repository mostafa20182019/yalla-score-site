"""Flag articles whose photo probably shows the wrong club.

Why this exists: on 2026-09-08 the user spotted a Pyramids preview illustrated
with Mohamed Chibi in his MOROCCO days. The rule against former-club shirts was
already in both article prompts — and the article had written the violation into
its own credit line ("خلال مشواره الكروي في المغرب"). Worse, the file was named
`mohamed-chibi-pyramids.jpg`, so the next article searching media/ for a
Pyramids photo would reuse it believing it was one. That is how the same bad
photo reached two articles.

The credit line is the most honest description we have of a photo: it is written
by the same pass that chose it. So the check is:

  suspect if the credit names a CLUB that is not one of the article's clubs,
  or if it carries a "different era" phrase while never naming the article's club

A national-team photo ("مع منتخب مصر") is explicitly allowed by the editorial
rule, so it is never a suspect. That keeps the list short enough to act on —
a noisy audit gets ignored, which is worse than no audit.

Second check, added 2026-09-12 after the user caught a preview of a match being
played THAT DAY illustrated with Steven Gerrard, retired since 2016. The club
test above passed cleanly: the credit named Liverpool, the shirt was Liverpool's,
the file was honestly named. Only the PERSON was a decade out of the story, and
the credit admitted it — «أسطورة ليفربول السابق ... عام 2014». So:

  suspect if the credit marks its subject as past — former / legend / retired, or
  a photo year three seasons old or more — and that subject is not named in the
  article's own title or summary

The second half is what keeps it quiet: on «جيرارد يعود إلى مرشحي تدريب طرابزون»
the very same photo is right, because Gerrard IS the story. A person photo is
only allowed to illustrate a piece he is still part of.

Usage:  python tools_audit_images.py            # the suspects
        python tools_audit_images.py --pool     # every photo used twice or more
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_site as B      # AR_TEAM + TEAM_PAGES: the club vocabulary already exists

# "this photo is from another time" phrases. On their own they are innocent —
# "بقميص الزمالك" on a Zamalek story is exactly right — so they only count when
# the article's own club is missing from the credit.
ERA_MARKERS = ["خلال مشواره", "خلال فترة تدريبه", "خلال فترته", "عندما كان",
               "بقميص", "سابقًا", "السابق", "أرشيفية", "قناة النادي", "أيام"]
NT_MARKERS = ["منتخب", "المنتخب"]

# "this person is no longer in the present tense of the story"
PAST_MARKERS = ["السابق", "السابقة", "أسطورة", "اعتزل", "المعتزل", "سابقًا", "سابقا"]
# a photo this old cannot show anyone's current situation
STALE_YEAR = 2023


def credit_subject(credit):
    """The name a credit opens with: «صورة: ستيفن جيرارد، أسطورة ليفربول...»
    -> «ستيفن جيرارد». Our credits are written to one shape by the article
    prompts, so the opening clause is reliably who or what the photo shows."""
    t = credit.split("صورة:", 1)[-1] if "صورة:" in credit else credit
    for sep in ("،", " خلال", " بقميص", " مع ", " في ", " أثناء", " عند", " —", " - "):
        i = t.find(sep)
        if i > 0:
            t = t[:i]
    return t.strip(" :—-‏")


def person_out_of_story(a, credit):
    """The second check. Returns a reason, or None when the photo is fine."""
    past = [m for m in PAST_MARKERS if m in credit]
    years = [int(y) for y in re.findall(r"(?:19|20)\d\d", credit)]
    stale = [y for y in years if y < STALE_YEAR]
    if not past and not stale:
        return None
    subject = credit_subject(credit)
    if not subject or len(subject) < 4:
        return None
    # a ground, a crowd or a trophy does not go out of date the way a person does
    if any(w in subject for w in ("استاد", "ملعب", "جماهير", "مدرجات", "كأس", "شعار", "مقر")):
        return None
    text = (a.get("title") or "") + " " + (a.get("summary") or "")
    if subject in text:
        return None                     # he IS the story - the photo is right
    # a surname match is enough: «ستيفن جيرارد» vs a title that says «جيرارد»
    if any(len(w) >= 4 and w in text for w in subject.split()):
        return None
    bits = []
    if past:
        bits.append(", ".join(past))
    if stale:
        bits.append(str(min(stale)))
    return (f"the credit calls its subject «{subject}» past ({'; '.join(bits)}) "
            f"and the article is not about him")


def club_vocabulary():
    """Arabic club names the site knows: the curated pages + every AR_TEAM value."""
    names = {tp["name"] for tp in B.TEAM_PAGES}
    for v in getattr(B, "AR_TEAM", {}).values():
        if v and len(v) >= 4:
            names.add(v)
    return sorted(names, key=len, reverse=True)


def main():
    d = json.load(open(os.path.join(HERE, "data", "articles.json"), encoding="utf-8"))
    arts = d["results"][0]["items"]
    vocab = club_vocabulary()

    by_file, suspects = {}, []
    for a in arts:
        img = a.get("image_url") or ""
        if "/media/" not in img:
            continue
        fn = img.rsplit("/", 1)[-1]
        credit = a.get("image_credit") or ""
        rec = by_file.setdefault(fn, {"ids": [], "credit": credit})
        rec["ids"].append(str(a.get("article_id")))
        if credit:
            rec["credit"] = credit
        if not credit:
            continue

        # check 2 runs first and for EVERY article: it compares the photo's
        # subject with this article's own words, so it needs no club vocabulary
        # and works on a piece about a club we do not curate
        stale_person = person_out_of_story(a, credit)
        if stale_person:
            suspects.append({"file": fn, "id": str(a.get("article_id")),
                             "credit": credit, "why": stale_person})
            continue

        mine = {tp["name"] for tp in B.TEAM_PAGES if B._team_news(tp, a)}
        if not mine:
            continue                        # not about a curated club: nothing to compare
        if any(m in credit for m in NT_MARKERS):
            continue                        # national-team kit is allowed
        named = [c for c in vocab if c in credit]
        # "خلال مباراة أمام بورنموث" names the OPPONENT, not the kit he wears —
        # that is context, not a violation, and it was most of the noise
        def is_opponent(club):
            i = credit.find(club)
            before = credit[max(0, i - 14):i]
            return any(m in before for m in ("أمام", "ضد", "مباراة مع", "لقاء مع", "مواجهة"))
        others = [c for c in named if c not in mine and not is_opponent(c)]
        mine_named = any(c in credit for c in mine)
        era = [m for m in ERA_MARKERS if m in credit]
        why = None
        if others:
            why = f"the credit names {' / '.join(sorted(set(others))[:3])}, the article is about {' / '.join(sorted(mine))}"
        elif era and not mine_named:
            why = f"era wording ({', '.join(era)}) and the credit never names {' / '.join(sorted(mine))}"
        if why:
            suspects.append({"file": fn, "id": str(a.get("article_id")),
                             "credit": credit, "why": why})

    # group by file AND reason: one photo can be wrong on one article for one
    # reason and merely flagged on another for a different one, and printing a
    # single reason over both ids blames the wrong article
    grouped = {}
    for s in suspects:
        g = grouped.setdefault((s["file"], s["why"]),
                               {"ids": [], "credit": s["credit"], "why": s["why"]})
        g["ids"].append(s["id"])

    print(f"photos in use: {len(by_file)} | suspect photos: {len(grouped)} "
          f"| articles affected: {len(suspects)}\n")
    for (fn, _why), g in sorted(grouped.items(), key=lambda kv: -len(kv[1]["ids"])):
        print(f"  {fn}   (articles: {', '.join(g['ids'])})")
        print(f"    credit : {g['credit'][:130]}")
        print(f"    why    : {g['why']}\n")

    if "--pool" in sys.argv[1:]:
        print("--- photos reused by more than one article ---")
        for fn, rec in sorted(by_file.items(), key=lambda kv: -len(kv[1]["ids"])):
            if len(rec["ids"]) > 1:
                print(f"  {len(rec['ids'])}x {fn}  -> {rec['credit'][:90]}")
    return 1 if grouped else 0


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
