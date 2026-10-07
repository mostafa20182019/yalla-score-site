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
from site_lib.config import SITE_BASE, SITE_NAME
from site_lib.dates import art_reltime
from site_lib.articles import byline, insight_kind
from site_lib.render import Markup, render
from site_lib.shell import foot, head, thumb_url, write
from site_lib.text import esc, strip_tags
from site_lib.urls import article_href

INSIGHT_KINDS = (("analysis", "تحليل"), ("preview", "قبل المباراة"),
                 ("report", "بعد المباراة"), ("round", "الجولة بالأرقام"))


def insights_page(articles, urls):
    """Write /insights.html; returns how many pieces it lists."""
    label = dict(INSIGHT_KINDS)
    picked = [(insight_kind(a), a) for a in articles]
    picked = sorted(((k, a) for k, a in picked if k),
                    key=lambda t: (t[1].get("pub_ts") or t[1].get("pub_date") or ""), reverse=True)
    rows = []
    for k, a in picked:
        img = thumb_url(a.get("image_url"))
        rows.append({
            "k": k, "kl": label[k],
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
    page_head = head(f"التحليلات: قراءات المباريات بالأرقام — {SITE_NAME}",
                     "تحليلات مباريات كرة القدم على يلا سكور: قراءات قبل المباراة بتوقعات النموذج، "
                     "تقارير ما بعد المباراة، «الجولة بالأرقام»، وتحليلات المحرر.",
                     SITE_BASE + "/insights.html", active="insights")
    write("insights.html", render("insights.html", page_head=Markup(page_head), rows=rows,
                                  chips=chips, total=len(rows), page_foot=Markup(foot())))
    urls.append("/insights.html")
    return len(rows)
