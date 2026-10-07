"""/insights - «التحليلات» (2026-10-07, user ask: «اعمل صفحة اسمها التحليلات
هنزل فيها تحليلات عن الماتشات»).

The /analysis pages were renamed «التوقعات» the same day (their URL stays -
indexed slugs are never renamed), which freed the name for this page: one
place for the site's ANALYTICAL writing, both kinds the user chose -

  * «تحليل»          kind="analysis": written by the editor in the admin
                     page (type selector), or by the AI later
  * «قبل المباراة»   kind="preview": the AI preview carrying our prediction
  * «بعد المباراة»   kind="report": the AI post-match report
  * «الجولة بالأرقام» round articles (round_brief.py): a source note
                     «round:<league>:<n>»

Match pieces link to their match page (article_href), exactly as everywhere
else. Only listable (non-thin) articles - the same set every other list uses.
Template: site_src/templates/insights.html."""
from site_lib.competitions import COMP_ORDER, COMP_SLUG
from site_lib.config import SITE_BASE, SITE_NAME, load
from site_lib.dates import art_reltime
from site_lib.arabic import round_ordinal
from site_lib.articles import byline, insight_kind, match_index, piece_place
from site_lib.names import comp_label
from site_lib.render import Markup, render
from site_lib.shell import foot, head, thumb_url, write
from site_lib.text import esc, strip_tags
from site_lib.urls import article_href

INSIGHT_KINDS = (("analysis", "تحليل"), ("preview", "قبل المباراة"),
                 ("report", "بعد المباراة"), ("round", "الجولة بالأرقام"))


def insights_page(articles, urls, m_all=None, fixtures=None):
    """Write /insights.html; returns how many pieces it lists.
    Filters (user 2026-10-07: «اعمل فلتر هنا بالدوري والجولة»): kind chips +
    a league select + a round select that lists the chosen league's rounds."""
    label = dict(INSIGHT_KINDS)
    idx = match_index(m_all, fixtures)
    picked = [(insight_kind(a), a) for a in articles]
    picked = sorted(((k, a) for k, a in picked if k),
                    key=lambda t: (t[1].get("pub_ts") or t[1].get("pub_date") or ""), reverse=True)
    rows = []
    for k, a in picked:
        img = thumb_url(a.get("image_url"))
        comp, rnd = piece_place(a, k, idx)
        rnd = str(rnd) if str(rnd or "").strip().isdigit() else ""
        rows.append({
            "k": k, "kl": label[k],
            "c": COMP_SLUG.get(comp, "") if comp else "", "r": rnd,
            "href": Markup(article_href(a)),
            "th": Markup(f'<span class="al-th" style="background-image:url(\'{esc(img)}\')"></span>'
                         if img else '<span class="al-th noimg">⚽</span>'),
            "title": a.get("title"),
            "summary": strip_tags(a.get("summary") or ""),
            "byline": byline(a),
            "when": Markup(art_reltime(a) or esc(a.get("pub_date") or "")),
        })
    counts = {k: sum(1 for r in rows if r["k"] == k) for k, _ in INSIGHT_KINDS}
    chips = [(k, lbl, counts[k]) for k, lbl in INSIGHT_KINDS if counts[k]]
    slug_comp = {v: c for c, v in COMP_SLUG.items()}
    present = {r["c"] for r in rows if r["c"]}
    order = [c for c in COMP_ORDER if COMP_SLUG.get(c) in present] +             sorted(slug_comp[s] for s in present if slug_comp.get(s) not in COMP_ORDER)
    leagues = [(COMP_SLUG[c], comp_label(c), sum(1 for r in rows if r["c"] == COMP_SLUG[c])) for c in order]
    # every round number that appears, with its Arabic ordinal, for the JS
    rounds = {r["r"]: round_ordinal(r["r"]) for r in rows if r["r"]}
    page_head = head(f"التحليلات: قراءات المباريات بالأرقام — {SITE_NAME}",
                     "تحليلات مباريات كرة القدم على يلا سكور: قراءات قبل المباراة بتوقعات النموذج، "
                     "تقارير ما بعد المباراة، «الجولة بالأرقام»، وتحليلات المحرر.",
                     SITE_BASE + "/insights.html", active="insights")
    write("insights.html", render("insights.html", page_head=Markup(page_head), rows=rows,
                                  chips=chips, leagues=leagues,
                                  rounds_json=Markup(__import__("json").dumps(rounds, ensure_ascii=False)),
                                  total=len(rows), page_foot=Markup(foot())))
    urls.append("/insights.html")
    return len(rows)
