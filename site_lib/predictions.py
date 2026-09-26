"""Prediction widgets: rows, the popup, the confidence chip, the «why»
block, the per-match block, power/timing tables, the record filter.

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
import analysis as AN
import datetime
import json
from site_lib.arabic import _AR_DAYS, _AR_MONTHS
from site_lib.config import REF_TODAY, _src
from site_lib.crests import local_crest
from site_lib.matchdata import score_pill
from site_lib.names import ar_team
from site_lib.stats import AN_games, _goals, form_dots
from site_lib.text import _pct, _signed_pct, esc
from site_lib.ticker import _tk_date
from site_lib.urls import match_url
from site_lib.widgets import prob_bar, prob_legend


AN_DISCLAIMER = ('التوقعات احتمالات إحصائية من نموذج يلا سكور مبنية على نتائج الموسم الحالي فقط، '
                 'وليست نصيحة للمراهنة. كلما زاد عدد المباريات زادت دقة النموذج.')
# Everything here is namespaced ppop-*, NOT pp-*: «.pp» and its family
# (.pp-ava, .pp-fb) are the player markers on the pitch graphic, and the last
# two class collisions in this stylesheet (.tl, .pp) both shipped broken to
# the user's phone. A JS hook that shares a prefix with a positioned element
# is the same bug waiting.
#
# The dialog is ONE element per page, filled at click time from the button's
# data- attributes and the row around it. It ends with a link to the match
# page rather than restating what is there: the popup answers the question,
# the page explains the answer, and the click that follows is earned instead
# of being the only way in.
PRED_POP = _src("snippets/pred_pop.html")
PRED_POP = PRED_POP.replace("__CONF_AR__",
                            json.dumps(AN.CONF_AR, ensure_ascii=False))
def pred_pop(parts):
    """The dialog — but only on a page that actually rendered a button.

    A club page whose next fixture has no prediction, or a standings page in a
    gap between rounds, would otherwise carry 2.6 KB of markup nothing can
    open."""
    return PRED_POP if any('class="pbtn"' in x for x in parts) else ""


def conf_chip(conf):
    return f'<span class="conf conf-{esc(conf)}">{esc(AN.CONF_AR.get(conf, ""))}</span>'


def pred_row(m, p):
    """Compact prediction row for the analysis pages (links to the match page)."""
    h, a = ar_team(m.get("home")), ar_team(m.get("away"))
    def crest(u):
        return f'<img src="{esc(local_crest(u))}" alt="" loading="lazy">' if u else '<span class="ph">⚽</span>'
    top = p["top"][0]
    link = match_url(m) or "#"
    when = f'{_tk_date(m.get("kickoff"))}{(" · " + m["koff_time"]) if m.get("koff_time") else ""}'
    fav = h if p["ph"] >= max(p["pd"], p["pa"]) else a if p["pa"] >= p["pd"] else "التعادل"
    return (f'<a class="prow" href="{esc(link)}">'
            f'<span class="pr-when">{esc(when)}</span>'
            f'<span class="pr-teams"><span class="pr-t">{crest(m.get("home_badge"))}<bdi>{esc(h)}</bdi></span>'
            f'<span class="pr-vs">×</span>'
            f'<span class="pr-t">{crest(m.get("away_badge"))}<bdi>{esc(a)}</bdi></span></span>'
            + f'<span class="pr-bw">{prob_bar(p)}{prob_legend(p, home=h, away=a)}</span>' +
            f'<span class="pr-meta">'
            f'<span class="pr-fav">الأرجح: <b>{esc(fav)}</b></span>'
            # score_pill, not a bare "2-1": as one LTR run the HOME number
            # lands on the away side and an RTL reader gets the prediction
            # backwards. Same bug the record page was fixed for on
            # 2026-09-16; measured still live here on 2026-09-18, the home
            # 2 sitting under the away club.
            f'<span class="pr-score">النتيجة الأكثر احتمالًا '
            + score_pill(top[0], top[1], "sc-in") + '</span>'
            + conf_chip(p["conf"]) + '</span></a>')


def why_block(m, p, ex, cal):
    """«لماذا رجّح النموذج هذا التوقع؟» — the prediction taken apart.

    Every site in this market shows a score and a table. What none of them
    shows is the arithmetic behind its own number, and that is the one page
    element here that cannot be copied from a feed: each line below is a term
    that appears literally in analysis.lambdas(), printed with this match's
    values (AN.explain returns them, it does not re-derive anything).

    It also ends with the model's own track record AT THIS confidence — from
    the frozen log, so a confident-looking prediction carries the rate at
    which past confident predictions actually came true. A number that
    explains itself and then admits how often it has been wrong is the
    opposite of the scaled, templated page Google penalises.

    Silent when the league has no finished matches to average (a pre-season
    table tells us nothing) - the same rule the readings follow.
    """
    if not ex or not p or (ex["n_h"] == 0 and ex["n_a"] == 0):
        return ""
    # The published prediction may come from the ORACLE model (the nightly
    # PL/SQL file, when it is fresh) while explain() re-derives python's
    # lambdas. The two are meant to be identical - that is the standing rule,
    # and 10/10 leagues matched when it was set. If they ever drift, the
    # decomposition would be describing a DIFFERENT prediction than the one on
    # the page, so say nothing rather than something that does not add up.
    if abs(ex["lh"] - p.get("lh", ex["lh"])) > 0.05 or \
       abs(ex["la"] - p.get("la", ex["la"])) > 0.05:
        return ""
    h, a = ar_team(m.get("home")), ar_team(m.get("away"))
    li = []
    li.append(f'<li><b>نقطة البداية — متوسط هذا الدوري:</b> صاحب الأرض يسجّل '
              f'{ex["mu_home"]:.2f} هدف في المباراة والضيف {ex["mu_away"]:.2f}.</li>')
    # the two clubs' own numbers, each against the league average
    def side(club, d_att, d_def_other, other):
        bits = []
        if abs(d_att) >= 0.05:
            bits.append(f'هجوم {esc(club)} {_signed_pct(d_att)} عن متوسط الدوري')
        else:
            bits.append(f'هجوم {esc(club)} عند متوسط الدوري تقريبًا')
        if abs(d_def_other) >= 0.05:
            # the word carries the direction, so the number must not carry it
            # too ("يستقبل −14% أقل" is a double negative)
            bits.append(f'ودفاع {esc(other)} يستقبل {abs(d_def_other) * 100:.0f}% '
                        f'{"أكثر" if d_def_other > 0 else "أقل"} من المتوسط')
        return " ".join(bits)
    li.append(f'<li><b>{esc(h)}:</b> {side(h, ex["d_att_h"], ex["d_def_a"], a)}.</li>')
    li.append(f'<li><b>{esc(a)}:</b> {side(a, ex["d_att_a"], ex["d_def_h"], h)}.</li>')
    if abs(ex["elo_edge"]) >= 0.01:
        li.append(f'<li><b>فارق القوة:</b> تقييم {esc(h)} {round(ex["elo_h"])} مقابل '
                  f'{round(ex["elo_a"])} لـ{esc(a)}، ويضيف النموذج {round(ex["elo_hfa"])} '
                  f'نقطة لعامل الأرض — الأثر {_signed_pct(ex["elo_edge"])} على أرقام '
                  f'{esc(h)} ومثلها في الاتجاه المعاكس على أرقام {esc(a)}.</li>')
    li.append(f'<li><b>الناتج:</b> {ex["lh"]:.1f} هدف متوقع لـ{esc(h)} و{ex["la"]:.1f} '
              f'لـ{esc(a)}، ومن توزيع بواسون على هذين الرقمين تخرج النسب '
              f'{_pct(p["ph"])} و{_pct(p["pd"])} و{_pct(p["pa"])}.</li>')
    top = max(p["ph"], p["pd"], p["pa"])
    b = AN.stated_bucket(cal, top)
    rec = ""
    if b:
        rec = (f'<p class="pd-note">وللأمانة: في المرات السابقة التي قال فيها النموذج '
               f'احتمالًا بين {b["lo"]}% و{b["hi"]}%، تحقّق ما قاله في '
               f'<b>{b["hits"]}</b> من <b>{b["n"]}</b> مرة. '
               f'<a href="/predictions.html">السجل كاملًا</a>.</p>')
    small = ""
    if min(ex["n_h"], ex["n_a"]) < 4:
        small = ('<p class="pd-note">عدد المباريات المنتهية لأحد الفريقين هذا الموسم قليل، '
                 'فالأرقام أعلاه تميل إلى متوسط الدوري أكثر من الطبيعي.</p>')
    return (f'<section class="minfo predict why"><h2>لماذا رجّح النموذج هذا التوقع؟</h2>'
            f'<p class="pd-line">النموذج لا يقرأ الأخبار — يحسب. وهذه هي الأرقام نفسها '
            f'التي دخلت المعادلة:</p><ul class="why-list">' + "".join(li) + '</ul>'
            + small + rec + '</section>')


def pred_block(m, p, logged, comp_stats, params=None, cal=None):
    """«توقع يلا سكور» section on a match page. Upcoming: live model output.
    Finished (with a frozen prediction): what we said vs what happened."""
    h, a = ar_team(m.get("home")), ar_team(m.get("away"))
    st = (m.get("status") or "").upper()
    if st == "UPCOMING" and p:
        top = " · ".join(f'<b>{i}-{j}</b> ({_pct(q)})' for i, j, q in p["top"])
        hs, as_ = comp_stats.get(m.get("home")), comp_stats.get(m.get("away"))
        facts = []
        if hs and hs["played"]:
            facts.append(f'{esc(h)}: {_goals(hs["gf"])} له و{_goals(hs["ga"])} عليه في {AN_games(hs["played"])} '
                         f'(تقييم القوة {round(hs["elo"])})')
        if as_ and as_["played"]:
            facts.append(f'{esc(a)}: {_goals(as_["gf"])} له و{_goals(as_["ga"])} عليه في {AN_games(as_["played"])} '
                         f'(تقييم القوة {round(as_["elo"])})')
        return (f'<section class="minfo predict"><h2>توقع يلا سكور لمباراة {esc(h)} و{esc(a)}</h2>'
                f'<div class="pd-heads"><span>{esc(h)} <b>{_pct(p["ph"])}</b></span>'
                f'<span>تعادل <b>{_pct(p["pd"])}</b></span><span>{esc(a)} <b>{_pct(p["pa"])}</b></span></div>'
                + prob_bar(p) +
                f'<p class="pd-line">الأهداف المتوقعة: <b>{p["lh"]:.1f}</b> لـ{esc(h)} و<b>{p["la"]:.1f}</b> لـ{esc(a)} · '
                f'أكثر من 2.5 هدف: <b>{_pct(p["over25"])}</b> · يسجل الفريقان: <b>{_pct(p["btts"])}</b></p>'
                f'<p class="pd-line">النتائج الأكثر احتمالًا: {top}</p>'
                + (f'<p class="pd-facts">{" — ".join(facts)}</p>' if facts else "")
                + f'<p class="pd-note">{conf_chip(p["conf"])} {AN_DISCLAIMER} '
                  '<a href="/analysis.html">كيف يعمل النموذج؟</a></p></section>'
                + (why_block(m, p, AN.explain(comp_stats, params, m.get("home"), m.get("away")),
                             cal) if params else ""))
    if st == "FINISHED" and logged and logged.get("hs") is not None:
        pick_ar = {"H": f"فوز {h}", "D": "التعادل", "A": f"فوز {a}"}[logged["pick"]]
        verdict = ('<span class="hit ok">✔ أصاب التوقع</span>' if logged.get("hit")
                   else '<span class="hit no">✘ لم يُصب التوقع</span>')
        fake = {"ph": logged["ph"], "pd": logged["pd"], "pa": logged["pa"]}
        return (f'<section class="minfo predict"><h2>ماذا توقع نموذج يلا سكور قبل المباراة؟</h2>'
                + prob_bar(fake) +
                f'<p class="pd-line">{prob_legend(fake, "pd-probs", h, a)}</p>'
                f'<p class="pd-line">رجّح النموذج <b>{esc(pick_ar)}</b> باحتمال {_pct(max(fake.values()))} '
                f'ونتيجة <b>{esc(logged.get("score", ""))}</b>، وانتهت المباراة <b>{logged["hs"]}-{logged["as"]}</b>. {verdict}</p>'
                f'<p class="pd-note">{AN_DISCLAIMER} <a href="/predictions.html">سجل التوقعات كاملًا (إصابةً وخطأ)</a></p></section>')
    return ""


def power_table(comp, stats, params, form_map):
    """Club strength table for one competition, ranked by Elo."""
    rows = sorted(stats.values(), key=lambda r: -r["elo"])
    if not rows:
        return ""
    mu = params["mu"]
    out = ['<div class="tbl-wrap"><table class="ptable"><thead><tr>'
           '<th>#</th><th class="tl">النادي</th><th title="تقييم القوة (Elo)">القوة</th><th>لعب</th>'
           '<th title="أهداف له لكل مباراة">له/م</th><th title="أهداف عليه لكل مباراة">عليه/م</th>'
           '<th title="مؤشر الهجوم مقارنة بمتوسط الدوري">هجوم</th><th title="مؤشر الدفاع مقارنة بمتوسط الدوري (الأقل أفضل)">دفاع</th>'
           '<th>ن/م</th><th>آخر 5</th></tr></thead><tbody>']
    for i, r in enumerate(rows, 1):
        att, dfc = AN.strength(r, mu)
        pg = r["played"] or 1
        crest = f'<img src="{esc(local_crest(r["badge"]))}" alt="" loading="lazy">' if r.get("badge") else ""
        out.append(f'<tr><td>{i}</td><td class="tl">{crest}<bdi>{esc(ar_team(r["team"]))}</bdi></td>'
                   f'<td><b>{round(r["elo"])}</b></td><td>{r["played"]}</td>'
                   f'<td>{r["gf"] / pg:.2f}</td><td>{r["ga"] / pg:.2f}</td>'
                   f'<td class="{"good" if att > 1.1 else "bad" if att < 0.9 else ""}">{att:.2f}</td>'
                   f'<td class="{"good" if dfc < 0.9 else "bad" if dfc > 1.1 else ""}">{dfc:.2f}</td>'
                   f'<td>{r["pts"] / pg:.2f}</td><td>{form_dots((form_map or {}).get(r["team"]) or r["form"])}</td></tr>')
    out.append('</tbody></table></div>')
    return "".join(out)


def timing_bars(timing, title):
    tot = sum(timing.values()) or 1
    mx = max(timing.values()) or 1
    bars = "".join(
        f'<div class="tb"><span class="tb-l">{esc(lbl)}</span>'
        f'<span class="tb-bar"><i style="width:{timing[lbl] / mx * 100:.0f}%"></i></span>'
        f'<span class="tb-v">{timing[lbl]} <small>({timing[lbl] / tot * 100:.0f}%)</small></span></div>'
        for lbl, _, _ in AN.MINUTE_BUCKETS)
    return f'<div class="timing"><h3>{esc(title)}</h3>{bars}</div>'


# ===========================================================================
# «سجل التوقعات» — /predictions.html (2026-09-14)
#
# The user's ask: a full prediction history that shows the model FAILING as
# loudly as it succeeds. The site already froze every prediction before
# kick-off and scored it after; what it published was one number - 47%
# direction accuracy - which is the weakest thing we measure and the least
# informative. The record now leads with calibration (when we say 30%, does it
# happen 30% of the time?), keeps the naive baseline next to the hit rate, and
# prints the most confident MISSES beside the most confident hits.
#
# Everything is computed from the frozen log; nothing here can be edited after
# a match, which is the only reason a record like this is worth anything.
# ===========================================================================
# Every row stays in the HTML - the record is meant to be complete, and a
# crawler must see all of it - but the reader gets PAGE_STEP at a time; 151
# rows already make a 30,000-pixel page and the record only grows.
PRED_FILTER_JS = _src("snippets/pred_filter_js.html")
def _rec_day_label(d):
    """«اليوم · 15 سبتمبر» for the record's day headers. The date belongs on
    the group, not repeated on all 166 rows (user, 2026-09-16)."""
    try:
        dt = datetime.date.fromisoformat(d)
    except Exception:
        return esc(d or "")
    today = datetime.date.fromisoformat(REF_TODAY)
    lead = ("اليوم" if dt == today
            else "أمس" if dt == today - datetime.timedelta(days=1)
            else _AR_DAYS[dt.weekday()])
    year = f" {dt.year}" if dt.year != today.year else ""
    return f"{lead} · {dt.day} {_AR_MONTHS[dt.month]}{year}"
