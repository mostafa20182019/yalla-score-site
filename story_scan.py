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
# the global clubs beyond the curated seven (user, 2026-10-22: more spotlight
# on the big clubs) - the "global" lane's shortlist, same clustering
GLOBAL_QUERIES = ["بايرن ميونخ", "باريس سان جيرمان", "يوفنتوس", "إنتر ميلان", "ميلان",
                  "أتلتيكو مدريد", "دورتموند", "توتنهام", "نابولي", "النصر السعودي", "الهلال السعودي"]
CLUB_QUERIES = ["ريال مدريد", "برشلونة", "ليفربول", "مانشستر يونايتد",
                "مانشستر سيتي", "أرسنال", "تشيلسي", "طرابزون سبور"]
# Sudanese football (user 2026-11-13: the Facebook audience growing from
# Sudan). ITS OWN LANE since 2026-11-19: six days after the rule not one
# article had named «الهلال السوداني» or «منتخب السودان». Measured that day:
# the two queries returned 4 and 2 fresh headlines, EVERY story on ONE outlet,
# so none passed MIN_OUTLETS = 3, and one that had would have sorted under
# the Al Ahly and Real Madrid stories and fallen off the 15. So: its own
# queries, asked of Google News' SUDAN edition as well (25 items in two days
# there against 2 in Egypt's), a bar of TWO outlets, and one seat of the
# shortlist kept for its best story. The article's own source gate
# (article_put.py: two independent domains) is untouched.
SUDAN_QUERIES = ["الهلال السوداني", "منتخب السودان", "الدوري السوداني"]
SUDAN_EDITION = "SD"

MAX_AGE_H = 30      # "the last ~24h", with room for a slot that ran late
LANE_MIN_OUTLETS = {"sudan": 2}   # a lane's own bar; every other lane uses MIN_OUTLETS
MIN_OUTLETS = 3     # a shortlist bar, NOT the source gate: article_put.py
                    # still demands two independent domains in the article
                    # itself. Three outlets on the wire just means the story
                    # is worth a look. Measured 2026-09-19: 2+ gives 64
                    # stories (useless), 3+ gives 23, 5+ gives 4.
COVERED_DAYS = 4    # how far back to look for "we already wrote this"
MAX_CANDIDATES = 15
# other sports and the women's sides: «out of scope» in the prompt, but they
# took seats of the fifteen (2026-11-19: Al Ahly basketball, the handball
# Super Cup twice, a Mediterranean forum, one-leg football, Real Madrid
# women - five of fifteen). Whole phrases only: «لمسة اليد» is football.
OFF_SCOPE = ("كرة السلة", "سلة الأهلي", "سلة الزمالك", "كرة اليد", "يد الأهلي", "يد الزمالك",
             "سوبر اليد", "الكرة الطائرة", "طائرة الأهلي", "طائرة الزمالك", "كرة الماء",
             "سيدات", "للسيدات", "الكرة النسائية", "الساق الواحدة", "منتدى", "ألعاب القوى",
             "التنس", "السباحة", "الهوكي", "التايكوندو", "الجودو", "المصارعة")


# «سلة <club>» / «طائرة <club>»: the word alone, before a name - any club's
# basketball or volleyball side, not only the two listed above
_OFF_WORD = re.compile(r"(^|[\s:«\"])(سلة|طائرة)\s+\S")


def off_scope(title):
    t = title or ""
    return any(x in t for x in OFF_SCOPE) or bool(_OFF_WORD.search(t))


def outlet_key(src):
    """One outlet, one key: «winwin», «winwin.com» and «www.winwin.com» were
    three outlets to the counter - with a bar of two that would let ONE site
    pass as two. Lower-case, no «www.», no trailing domain ending."""
    s = (src or "").strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^www\.", "", s)
    s = re.sub(r"\.(com|net|org|info|tv|news|eg|sd|sa|qa|ae|ma|dz|tn|co\.uk)(\.[a-z]{2})?/?$", "", s)
    return s.strip() or "?"


def rss(query, edition="EG"):
    """Headlines for one query: [(title, outlet, age_hours, link)]. `edition`
    is the Google News country edition (EG by default, SD for Sudan)."""
    url = ("https://news.google.com/rss/search?q="
           + urllib.parse.quote(query) + f"&hl=ar&gl={edition}&ceid={edition}:ar")
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
    # every query belongs to a lane: egypt / club (the curated seven) / global
    lanes = ([(q, "egypt", "EG") for q in EGY_QUERIES] + [(q, "club", "EG") for q in CLUB_QUERIES]
             + [(q, "global", "EG") for q in GLOBAL_QUERIES]
             # the Sudanese queries from both editions: Egypt's and Sudan's own
             + [(q, "sudan", ed) for q in SUDAN_QUERIES for ed in ("EG", SUDAN_EDITION)])
    dropped = 0
    for q, lane, ed in lanes:
        try:
            got = rss(q, ed)
        except Exception as e:
            lines.append(f"  !! «{q}» ({ed}) failed ({e}) - skipped")
            continue
        fresh = [x for x in got if x[2] <= MAX_AGE_H]
        kept = [x for x in fresh if not off_scope(x[0])]
        dropped += len(fresh) - len(kept)
        # an Egyptian reader cannot open these, so they are not sources
        items += [tuple(x) + (lane,) for x in kept
                  if not any(b in (x[1] or "") for b in FD.BLOCKED_SOURCE_NAMES)]
        lines.append(f"  {q}{'' if ed == 'EG' else ' [' + ed + ']'}: {len(fresh)} fresh of {len(got)}")
    if dropped:
        lines.append(f"  ({dropped} headline(s) of other sports / women's sides left out)")

    clusters = []            # [tokens, {outlets}, title, [links], min_age, lane]
    for title, src, age, link, lane in items:
        tok = FD._title_tokens(title, src)
        if not tok:
            continue
        for c in clusters:
            if FD._same_story(tok, c[0]):
                c[1].add(outlet_key(src))
                c[6].add(src or "?")
                if lane == "sudan":
                    c[5] = "sudan"            # a story the Sudan queries also found is a Sudan story
                if link and len(c[3]) < 4:
                    c[3].append(link)
                c[4] = min(c[4], age)
                break
        else:
            clusters.append([tok, {outlet_key(src)}, title, [link] if link else [], age, lane, {src or "?"}])

    strong = [c for c in clusters if len(c[1]) >= LANE_MIN_OUTLETS.get(c[5], MIN_OUTLETS)]
    done = covered_tokens()
    new = [c for c in strong
           if not any(FD._same_story(c[0], d) for d in done)]
    new.sort(key=lambda c: (-len(c[1]), c[4]))
    lines.append(f"  -> {len(clusters)} distinct stories, {len(strong)} on "
                 f"{MIN_OUTLETS}+ outlets, {len(new)} of those not yet on the site")

    top = new[:MAX_CANDIDATES]
    # the Sudan lane's seat: its best story is on the list even when fifteen
    # bigger ones are - it takes the last seat, it is not added on top
    sud = [c for c in new if c[5] == "sudan"]
    if sud and not any(c[5] == "sudan" for c in top):
        top = top[:MAX_CANDIDATES - 1] + [sud[0]]
        lines.append("  (the Sudan lane's best story takes the last seat)")
    cands = [{"title": c[2], "outlets": sorted(c[6]), "n_outlets": len(c[1]),
              "hours_ago": round(c[4], 1), "links": c[3], "lane": c[5]}
             for c in top]
    return cands, lines


def run_lane(hour_utc=None):
    """The run's lane from the UTC hour of the six daily slots (06, 08, 11,
    14, 17, 19): three lead with Egypt, three with the global clubs - the
    two alternate through the day. Any other hour (a hand-dispatched run)
    is "egypt", the site's core."""
    import datetime as _dt
    h = _dt.datetime.now(_dt.timezone.utc).hour if hour_utc is None else int(hour_utc)
    return "global" if h in (8, 14, 19) else "egypt"


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
