# -*- coding: utf-8 -*-
"""story_scan.py — hand the daily-article run a shortlist instead of a search.

WHY THIS IS NOT A GATE. It was meant to be one: run in seconds, decide
whether anything qualifies, and skip the Claude step when nothing does.
Both candidate signals were measured on 2026-09-19 and neither
discriminates:

  * outlets on a story — 64 clusters carried by 2+ outlets, 63 of them not
    already on the site. There is ALWAYS a 2-outlet story; the bar is noise.
  * articles published so far today — 8, 7, 2, 8, 4 over 09-14..09-18. A cap
    of three would have cut two eight-article days to three. It predicts
    nothing.

A gate built on either would have skipped real articles or saved nothing,
so it is not built. What IS true is where the time goes: a run spends its
first minutes fetching thirteen Google News queries, clustering them and
checking them against the archive — work that is deterministic, costs no
model tokens, and is identical every run. So this does that part, writes
the result to /tmp/story_candidates.json, and the prompt starts from the
shortlist. The model still decides; it just does not have to go and look
first.

It cannot cost an article: if the file is missing, empty or thin, the
prompt's own step 1 still tells the run to search the queries itself.
Every failure here is silent and harmless.

Usage:
  python story_scan.py                    # writes /tmp/story_candidates.json
  python story_scan.py --out PATH         # somewhere else
"""
import sys, io, os, json, re, urllib.parse, datetime

sys.stdout.reconfigure(encoding="utf-8")     # cp1252 console would crash
sys.stderr.reconfigure(encoding="utf-8")     # stderr defaults to backslashreplace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_data as FD

# The prompt's own queries, in its own order: Egyptian first (the site's
# core), then the curated clubs. Keep these in step with
# .github/prompts/daily-article.md step 1.
EGY_QUERIES = ["الدوري المصري", "الأهلي", "الزمالك", "بيراميدز", "منتخب مصر"]
CLUB_QUERIES = ["ريال مدريد", "برشلونة", "ليفربول", "مانشستر يونايتد",
                "مانشستر سيتي", "أرسنال", "تشيلسي", "طرابزون سبور"]

MAX_AGE_H = 30      # "the last ~24h", with room for a slot that ran late
MIN_OUTLETS = 3     # a shortlist bar, NOT the source gate: article_put.py
                    # still demands two independent domains in the article
                    # itself. Three outlets on the wire just means the story
                    # is worth a look. Measured 2026-09-19: 2+ gives 64
                    # stories (useless), 3+ gives 23, 5+ gives 4.
COVERED_DAYS = 4    # how far back to look for "we already wrote this"
MAX_CANDIDATES = 15


def rss(query):
    """Headlines for one query: [(title, outlet, age_hours, link)]."""
    url = ("https://news.google.com/rss/search?q="
           + urllib.parse.quote(query) + "&hl=ar&gl=EG&ceid=EG:ar")
    xml = FD.http_get(url)
    now = datetime.datetime.now(datetime.timezone.utc)
    out = []
    for m in re.finditer(r"<item\b[^>]*>(.*?)</item>", xml, re.S):
        block = m.group(1)

        def tag(t):
            mm = re.search(rf"<{t}\b[^>]*>(.*?)</{t}>", block, re.S)
            return FD._unescape(mm.group(1)) if mm else ""

        title, src, link = tag("title"), tag("source"), tag("link")
        if not title:
            continue
        age = 0.0
        pub = tag("pubDate")
        if pub:
            try:
                from email.utils import parsedate_to_datetime
                age = (now - parsedate_to_datetime(pub)).total_seconds() / 3600
            except Exception:
                age = 0.0
        out.append((title, src, age, link))
    return out


def covered_tokens():
    """Token sets of everything we published in the last COVERED_DAYS."""
    cut = (datetime.date.today()
           - datetime.timedelta(days=COVERED_DAYS)).isoformat()
    toks = []
    doc = json.load(io.open("data/articles.json", encoding="utf-8"))
    for res in doc.get("results") or []:
        for a in res.get("items") or []:
            if (a.get("pub_date") or "") >= cut:
                toks.append(FD._title_tokens(a.get("title"), None))
    return toks


def scan():
    """-> (candidates, report lines)."""
    lines, items = [], []
    for q in EGY_QUERIES + CLUB_QUERIES:
        try:
            got = rss(q)
        except Exception as e:
            lines.append(f"  !! «{q}» failed ({e}) - skipped")
            continue
        fresh = [x for x in got if x[2] <= MAX_AGE_H]
        # an Egyptian reader cannot open these, so they are not sources
        items += [x for x in fresh
                  if not any(b in (x[1] or "") for b in FD.BLOCKED_SOURCE_NAMES)]
        lines.append(f"  {q}: {len(fresh)} fresh of {len(got)}")

    clusters = []            # [tokens, {outlets}, title, [links], min_age]
    for title, src, age, link in items:
        tok = FD._title_tokens(title, src)
        if not tok:
            continue
        for c in clusters:
            if FD._same_story(tok, c[0]):
                c[1].add(src or "?")
                if link and len(c[3]) < 4:
                    c[3].append(link)
                c[4] = min(c[4], age)
                break
        else:
            clusters.append([tok, {src or "?"}, title, [link] if link else [], age])

    strong = [c for c in clusters if len(c[1]) >= MIN_OUTLETS]
    done = covered_tokens()
    new = [c for c in strong
           if not any(FD._same_story(c[0], d) for d in done)]
    new.sort(key=lambda c: (-len(c[1]), c[4]))
    lines.append(f"  -> {len(clusters)} distinct stories, {len(strong)} on "
                 f"{MIN_OUTLETS}+ outlets, {len(new)} of those not yet on the site")

    cands = [{"title": c[2], "outlets": sorted(c[1]), "n_outlets": len(c[1]),
              "hours_ago": round(c[4], 1), "links": c[3]}
             for c in new[:MAX_CANDIDATES]]
    return cands, lines


def main():
    out = "/tmp/story_candidates.json"
    if "--out" in sys.argv:
        out = sys.argv[sys.argv.index("--out") + 1]
    try:
        cands, lines = scan()
    except Exception as e:
        # Never break the run. No file = the prompt searches for itself,
        # exactly as it did before this step existed.
        print(f"story_scan failed ({e}) - no shortlist, the run will search "
              "the queries itself", file=sys.stderr)
        return 0

    payload = {"generated": datetime.datetime.now(
                   datetime.timezone.utc).isoformat(timespec="seconds"),
               "window_hours": MAX_AGE_H, "min_outlets": MIN_OUTLETS,
               "covered_days": COVERED_DAYS, "candidates": cands}
    with io.open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    report = [f"story_scan: {len(cands)} candidate stories -> {out}"] + lines
    report += [f"  · [{c['n_outlets']} outlets, {c['hours_ago']}h] {c['title'][:88]}"
               for c in cands[:8]]
    print("\n".join(report), file=sys.stderr)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with io.open(summary, "a", encoding="utf-8") as f:
            f.write("### 🔎 قائمة الأخبار المرشّحة (قبل تشغيل Claude)\n```\n"
                    + "\n".join(report) + "\n```\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
