"""The head-to-head pages (/h2h/<slug>) - «مواجهات الأهلي والزمالك» (2026-11-13).

One function, called once by build(); the data rules live in site_lib/h2h.py.
Every sentence here is computed from the meetings list - one fact per
sentence (the plain-wording rule), never generated. Slugs are indexed URLs."""
import os

from site_lib import h2h as H
from site_lib.clubs import TEAM_PAGES
from site_lib.competitions import COMP_SLUG
from site_lib.config import DIST, REF_TODAY, SITE_BASE, SITE_NAME
from site_lib.crests import local_crest
from site_lib.dates import art_reltime, day_month
from site_lib.matchdata import score_pill
from site_lib.names import _team_news, ar_team, comp_label
from site_lib.render import Markup, render
from site_lib.shell import foot, head, thumb_url, write
from site_lib.stats import _cnt
from site_lib.tables import match_row
from site_lib.text import esc, jsonld
from site_lib.urls import article_href, breadcrumb_ld, match_url


def h2h_pages(articles, m_all, urls):
    """/h2h/<slug> for every pair in site_lib.h2h.PAIRS that has at least
    four meetings on record. Markup: h2h.html. Returns how many were written."""
    os.makedirs(os.path.join(DIST, "h2h"), exist_ok=True)

    def games_n(n, two="مباراتين"):
        return _cnt(n, "مباراة واحدة", two, "مباريات", "مباراة")

    def crest_of(club, league):
        for m in sorted(m_all.values(), key=lambda m: m.get("kickoff") or "", reverse=True):
            if m.get("competition") != league:
                continue
            for side in ("home", "away"):
                if ar_team(m.get(side)) == club and m.get(side + "_badge"):
                    return local_crest(m[side + "_badge"])
        return ""

    written = 0
    for pair in H.PAIRS:
        a, b, slug = pair["a"], pair["b"], pair["slug"]
        notes = H.load_notes(pair)
        games = H.meetings(pair, H.load_history(pair), m_all)
        if len(games) < 4:
            print(f"  ! h2h {slug}: only {len(games)} meeting(s) on record - no page")
            continue
        n = len(games)
        t = H.tally(games, pair, notes)
        last, oldest = games[0], games[-1]
        nxt = H.next_meeting(pair, m_all, REF_TODAY)
        url = f"/h2h/{slug}.html"

        def won(club):
            w = t["wins"][club]
            return f"لم يفز {club} في أي مباراة." if not w else f"فاز {club} في {games_n(w)}."

        draws = ("لم تنتهِ أي مباراة بالتعادل." if not t["draws"]
                 else f"انتهت {games_n(t['draws'], 'مباراتان')} بالتعادل.")
        lead = (f"لعب {a} و{b} {games_n(n)} منذ {H.ar_month_year(oldest['date'])} في كل البطولات. "
                f"{won(a)} {won(b)} {draws}")
        last_txt = (f"{H.score_line(last)} في {H.comp_base(last['comp'])} "
                    f"يوم {H.ar_date(last['date'])}.")

        def goals(club):
            return (f"سجل {club} "
                    + _cnt(t["goals"][club], "هدفًا واحدًا", "هدفين", "أهداف", "هدفًا") + ".")

        goals_txt = [goals(a), goals(b)]
        if t["awarded"]:
            # worded so the number needs no agreement (1, 2 or more read right)
            goals_txt.append(f"مباريات حُسمت بقرار إداري ولا تُحسب أهدافها: {t['awarded']}.")

        # the facts list: each line one fact, each from the list below it
        facts = [f"آخر مباراة: {last_txt}"]
        for club in (a, b):
            g = H.last_win(games, club)
            if g and g is not last:
                # an awarded result says so: «3 - 0» alone reads as a played win
                _nt = (notes.get(g["date"]) or {}).get("note")
                facts.append(f"آخر فوز لفريق {club}: {H.score_line(g)} يوم {H.ar_date(g['date'])}"
                             + (f" ({_nt})." if _nt else "."))
        big = H.biggest_win(games, notes)
        if big:
            facts.append(f"أكبر فوز: {H.score_line(big)} في {H.comp_base(big['comp'])} "
                         f"يوم {H.ar_date(big['date'])}.")
        run_club, run_n = H.unbeaten_run(games, pair)
        if run_n >= 3:
            facts.append(f"{run_club} لم يخسر في آخر {games_n(run_n)} بين الفريقين.")

        rows = []
        for g in games:
            nt = notes.get(g["date"]) or {}
            w = H.winner(g) or nt.get("winner")
            rows.append({"date": H.ar_date(g["date"]), "iso": Markup(g["date"]), "comp": g["comp"],
                         "home": g["home"], "away": g["away"],
                         "home_w": w == g["home"], "away_w": w == g["away"],
                         "pill": Markup(score_pill(g["hg"], g["ag"], "h2h-sc")),
                         "note": nt.get("note") or "",
                         "href": Markup(f"/m/{g['ours']}.html") if g["ours"] else ""})

        comps = [{"name": c, "n": k, "a": wa, "d": d, "b": wb}
                 for c, k, wa, d, wb in H.by_competition(games, pair)]

        next_row = ""
        if nxt:
            next_row = match_row(nxt, show_time=True, show_comp=True, show_date=True,
                                 link=match_url(nxt))
            next_txt = (f"{ar_team(nxt.get('home'))} ضد {ar_team(nxt.get('away'))} "
                        f"يوم {day_month(nxt.get('kickoff'), weekday=True)}"
                        + (f" الساعة {nxt.get('koff_time')} بتوقيت القاهرة" if nxt.get("koff_time") else "")
                        + f" في {comp_label(nxt.get('competition'))}.")
        else:
            next_txt = "لم يُعلن موعد المباراة القادمة بعد. يظهر هنا فور تحديده."

        tps = {tp["slug"]: tp for tp in TEAM_PAGES}
        ta, tb = tps.get(pair["a_slug"]), tps.get(pair["b_slug"])
        news = []
        for art in [x for x in articles if ta and tb and _team_news(ta, x) and _team_news(tb, x)][:6]:
            _t = art_reltime(art)
            _img = thumb_url(art.get("image_url"))
            news.append({"href": Markup(article_href(art)), "title": art["title"],
                         "th": Markup(f'<span class="al-th"><img src="{esc(_img)}" alt="" loading="lazy" decoding="async"></span>'
                                      if _img else '<span class="al-th noimg">⚽</span>'),
                         "when": Markup(_t) if _t else ""})

        times = lambda k: _cnt(k, "مرة واحدة", "مرتين", "مرات", "مرة")   # noqa: E731
        faq = [(f"كم مرة فاز {a} على {b} في آخر {games_n(n)}؟",
                (f"فاز {a} {times(t['wins'][a])}." if t["wins"][a] else f"لم يفز {a}.") + " "
                + (f"فاز {b} {times(t['wins'][b])}." if t["wins"][b] else f"لم يفز {b}.") + " " + draws),
               (f"ما نتيجة آخر مباراة بين {a} و{b}؟", last_txt),
               (f"متى مباراة {a} و{b} القادمة؟", next_txt)]
        if big:
            faq.append((f"ما أكبر فوز بين {a} و{b} في آخر {games_n(n)}؟",
                        f"{H.score_line(big)} في {H.comp_base(big['comp'])} يوم {H.ar_date(big['date'])}."))
        faq_ld = jsonld({"@context": "https://schema.org", "@type": "FAQPage",
                         "mainEntity": [{"@type": "Question", "name": q,
                                         "acceptedAnswer": {"@type": "Answer", "text": ans}}
                                        for q, ans in faq]})

        title = f"مواجهات {a} و{b}: نتائج آخر {games_n(n)} والمباراة القادمة | {SITE_NAME}"
        desc = f"{lead} آخر مباراة: {last_txt}"
        ca, cb = crest_of(a, pair["league"]), crest_of(b, pair["league"])
        page_head = head(title, desc, SITE_BASE + url)
        crumbs_ld = breadcrumb_ld([("الرئيسية", SITE_BASE + "/"),
                                   ("المباريات", SITE_BASE + "/matches.html"),
                                   (f"مواجهات {a} و{b}", SITE_BASE + url)])

        def crest_img(src, club):
            return Markup(f'<img class="h2h-crest" src="{esc(src)}" alt="{esc(club)}" '
                          'width="56" height="56" loading="eager">' if src else "")

        lslug = COMP_SLUG.get(pair["league"])
        write(f"h2h/{slug}.html", render(
            "h2h.html", page_head=Markup(page_head), crumbs_ld=Markup(crumbs_ld),
            a=a, b=b, a_slug=Markup(pair["a_slug"]), b_slug=Markup(pair["b_slug"]),
            crest_a=crest_img(ca, a), crest_b=crest_img(cb, b),
            n_txt=games_n(n), since=H.ar_month_year(oldest["date"]), lead=lead,
            wins_a=t["wins"][a], wins_b=t["wins"][b], draws=t["draws"],
            goals_txt=goals_txt, facts=facts, rows=rows, comps=comps,
            next_row=Markup(next_row), next_txt=next_txt, news=news,
            faq=[{"q": q, "a": ans} for q, ans in faq], faq_ld=Markup(faq_ld),
            league_slug=Markup(lslug or ""), league_ar=comp_label(pair["league"]),
            page_foot=Markup(foot())))
        urls.append(url)
        written += 1
    print(f"  + head-to-head pages: {written}")
    return written
