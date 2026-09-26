"""/analysis, /analysis/<league> and the frozen prediction record
(/predictions).

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
import analysis as AN
import datetime
import os
from site_lib.competitions import COMP_ORDER, COMP_SLUG
from site_lib.config import DIST, REF_TODAY, SITE_BASE, SITE_NAME
from site_lib.crests import comp_icon
from site_lib.names import ar_team, comp_has_table, comp_label
from site_lib.predictions import AN_DISCLAIMER, PRED_FILTER_JS, _rec_day_label, power_table, pred_row, timing_bars
from site_lib.render import Markup, render
from site_lib.shell import _LASTMOD, foot, head, write
from site_lib.stats import _games
from site_lib.text import _pct, esc, jsonld
from site_lib.urls import breadcrumb_ld
from site_lib.widgets import _calls_html, _pred_item_html, accuracy_html, calibration_html, ga_table, model_explainer, ratings_table


def prediction_history_page(plog, acc):
    """/predictions.html — every frozen prediction, scored, with the model's
    calibration and its misses. Returns the url (or None when nothing scored).
    Markup: site_src/templates/predictions.html (templated 2026-09-26)."""
    a = (acc or {}).get("all")
    rows = AN.history(plog)
    if not a or not rows:
        return None
    cal = AN.calibration(plog)
    ex = AN.extremes(plog)
    first = min(r.get("kickoff") or "" for r in rows)
    last = max(r.get("kickoff") or "" for r in rows)
    title = f"سجل توقعات يلا سكور: الإصابات والإخفاقات كاملة — {SITE_NAME}"
    desc = (f"كل توقع أصدره نموذج يلا سكور مُثبَّتًا قبل المباراة ومقارنًا بالنتيجة: "
            f"{a['n']} مباراة مقيَّمة، نسبة إصابة الاتجاه {_pct(a['hit_rate'])} مقابل "
            f"{_pct(a['home_baseline'])} لمعيار ساذج، ومعايرة الاحتمالات كاملة.")
    url = "/predictions.html"
    tiles = [(a["n"], "مباراة مقيَّمة"),
             (_pct(a["hit_rate"]), "إصابة الاتجاه"),
             (_pct(a["home_baseline"]), "معيار ساذج: فوز الأرض دائمًا"),
             (f'{a["brier"]:.3f}', "Brier (الأقل أفضل · 0.667 عشوائي)"),
             (a["score_hits"], "نتيجة مضبوطة"),
             (f'{cal["ece"] * 100:.1f}', "انحراف المعايرة (نقطة مئوية)")]

    # per competition, with the sample size in front of every rate
    comps = (acc or {}).get("comps") or {}
    comp_rows = []
    for comp in COMP_ORDER + [c for c in comps if c not in COMP_ORDER]:
        c = comps.get(comp)
        if not c:
            continue
        comp_rows.append({"label": comp_label(comp), "small": c["n"] < 20, "n": c["n"],
                          "rate": _pct(c["hit_rate"]), "brier": f'{c["brier"]:.3f}'})

    # the two models, apart and NOT as a race. Since 2026-09-24 every new
    # prediction is python's (one model, the user's decision); the Oracle rows
    # are its record before that date, kept exactly as scored - history is
    # not rewritten
    srcs = (acc or {}).get("by_src") or {}
    src_rows = None
    if len(srcs) > 1:
        src_rows = []
        for k in sorted(srcs):
            v = srcs[k]
            if not v:
                continue
            nm = {"oracle": "نموذج Oracle (PL/SQL)", "python": "نموذج بايثون"}.get(k, k)
            src_rows.append({"label": nm, "n": v["n"], "rate": _pct(v["hit_rate"]),
                             "brier": f'{v["brier"]:.3f}'})

    # the full record
    comp_opts = [(c, comp_label(c))
                 for c in (COMP_ORDER + [c for c in comps if c not in COMP_ORDER]) if c in comps]
    # grouped by day: the date is a header, not a column repeated on every line
    days = []
    for e in rows:
        day = e.get("kickoff") or ""
        if not days or day != days[-1][0]:
            days.append((day, Markup(_rec_day_label(day)), []))
        days[-1][2].append(Markup(_pred_item_html(e)))

    faq = [
        ("هل توقعات يلا سكور دقيقة؟",
         f"على {a['n']} مباراة مقيَّمة أصاب النموذج اتجاه النتيجة في {_pct(a['hit_rate'])} من الحالات، "
         f"مقابل {_pct(a['home_baseline'])} لو توقعنا فوز صاحب الأرض دائمًا. الأهم أن الاحتمالات "
         f"نفسها مُعايَرة: متوسط انحرافها {cal['ece'] * 100:.1f} نقطة مئوية عمّا يحدث فعلًا."),
        ("هل تُعدَّل التوقعات بعد المباراة؟",
         "لا. يُثبَّت التوقع في قاعدة البيانات قبل انطلاق المباراة ولا يُعدَّل ولا يُحذف بعدها، "
         "والسجل يعرض الإخفاقات كما يعرض الإصابات."),
        ("ماذا يعني مؤشر Brier؟",
         "قياس لجودة الاحتمالات: صفر يعني توقعًا مثاليًا، و0.667 يعني تخمينًا عشوائيًا بين ثلاث نتائج. "
         f"النموذج عند {a['brier']:.3f} حاليًا."),
        ("هل هذه نصيحة للمراهنة؟",
         "لا. الأرقام تحليلية مبنية على نتائج الموسم الحالي فقط، ولا تصلح أساسًا لأي رهان."),
    ]
    faq_ld = jsonld({"@context": "https://schema.org", "@type": "FAQPage",
                     "mainEntity": [{"@type": "Question", "name": q,
                                     "acceptedAnswer": {"@type": "Answer", "text": v}}
                                    for q, v in faq]})
    crumbs_ld = breadcrumb_ld([("أخبار", SITE_BASE + "/"),
                               ("تحليلات وتوقعات", SITE_BASE + "/analysis.html"),
                               ("سجل التوقعات", SITE_BASE + url)])
    write("predictions.html", render(
        "predictions.html",
        page_head=Markup(head(title, desc, SITE_BASE + url, active="analysis")),
        first=first, last=last, tiles=tiles,
        calibration=Markup(calibration_html(cal)), calls=Markup(_calls_html(ex)),
        comp_rows=comp_rows, show_comps=bool(comps), src_rows=src_rows, comp_opts=comp_opts, n_rows=len(rows),
        days=days, faq=faq, faq_ld=Markup(faq_ld), crumbs_ld=Markup(crumbs_ld),
        page_foot=Markup(foot()), filter_js=Markup(PRED_FILTER_JS)))
    _LASTMOD[url] = REF_TODAY
    return url


def analysis_pages(matches, upcoming, preds, plog, acc, tstats, lparams, pins, sins,
                   forms, has_table=None):
    """Write /analysis.html (hub) + /analysis/<slug>.html per league. Returns urls.
    Markup: site_src/templates/analysis.html + analysis_league.html (templated
    2026-09-26); the pieces are built here in the same order as before."""
    urls = []
    today = datetime.date.fromisoformat(REF_TODAY)
    wk = (today + datetime.timedelta(days=7)).isoformat()
    by_comp = {}
    for m in upcoming:
        p = preds.get(str(m.get("match_id")))
        if p and (m.get("kickoff") or "") <= wk:
            by_comp.setdefault(m.get("competition"), []).append((m, p))
    for ms in by_comp.values():
        ms.sort(key=lambda t: (t[0].get("kickoff") or "", t[0].get("koff_time") or ""))
    comps = [c for c in COMP_ORDER if c in tstats] + [c for c in tstats if c not in COMP_ORDER]
    n_pred = sum(len(v) for v in by_comp.values())
    # ---- hub ----
    page_head = head("تحليلات وتوقعات المباريات بالأرقام — يلا سكور",
                     "توقعات مباريات الأسبوع باحتمالات مبنية على بيانات الموسم، تقييم قوة الأندية، تحليل اللاعبين، "
                     "وسجل شفاف لدقة التوقعات في الدوري المصري وأبرز الدوريات.",
                     SITE_BASE + "/analysis.html", active="analysis")
    crumbs_ld = breadcrumb_ld([("أخبار", SITE_BASE + "/"), ("تحليلات", SITE_BASE + "/analysis.html")])
    nav = [(COMP_SLUG[c], Markup(comp_icon(c)), comp_label(c)) for c in comps if c in COMP_SLUG]
    week = []
    for c in comps:
        rows = by_comp.get(c)
        if not rows:
            continue
        week.append({"icon": Markup(comp_icon(c)), "slug": COMP_SLUG.get(c, ""), "label": comp_label(c),
                     "rows": [Markup(pred_row(m, p)) for m, p in rows[:8]],
                     "more": len(rows) if len(rows) > 8 and c in COMP_SLUG else 0})
    # power snapshot: top 5 per league
    power = []
    for c in comps:
        rows = sorted(tstats[c].values(), key=lambda r: -r["elo"])[:5]
        if not rows or all(r["played"] == 0 for r in rows):
            continue
        power.append({"icon": Markup(comp_icon(c)), "label": comp_label(c),
                      "rows": [(ar_team(r["team"]), round(r["elo"])) for r in rows],
                      "slug": COMP_SLUG[c] if c in COMP_SLUG else None})
    # players snapshot: best-rated across leagues (n>=2)
    best = []
    for c, d in pins.items():
        for r in d.get("ratings", [])[:5]:
            best.append(dict(r, comp=c))
    best.sort(key=lambda r: (-r["avg"], -r["n"]))
    best_rows = [{"name": r["name"], "club": r["club"], "comp": comp_label(r["comp"]), "n": r["n"],
                  "avg": f'{r["avg"]:.2f}'} for r in best[:12]]
    write("analysis.html", render(
        "analysis.html", page_head=Markup(page_head), crumbs_ld=Markup(crumbs_ld),
        n_comps=len(comps), n_pred=n_pred, nav=nav, week=week, disclaimer=Markup(AN_DISCLAIMER),
        power=power, best=best_rows, accuracy=Markup(accuracy_html(acc)),
        explainer=Markup(model_explainer()), page_foot=Markup(foot())))
    urls.append("/analysis.html")
    # ---- per-league pages ----
    for c in comps:
        slug = COMP_SLUG.get(c)
        if not slug:
            continue
        label = comp_label(c)
        stats, params = tstats[c], lparams[c]
        if not stats:
            continue
        page_head = head(f"تحليلات {label}: توقعات المباريات وقوة الأندية واللاعبون — يلا سكور",
                         f"توقعات مباريات {label} القادمة باحتمالات مبنية على نتائج الموسم، ترتيب قوة الأندية (Elo) "
                         f"ومؤشرات الهجوم والدفاع، توقيت الأهداف، وأعلى اللاعبين تقييمًا.",
                         SITE_BASE + f"/analysis/{slug}.html", active="analysis")
        crumbs_ld = breadcrumb_ld([("أخبار", SITE_BASE + "/"), ("تحليلات", SITE_BASE + "/analysis.html"),
                                   (label, SITE_BASE + f"/analysis/{slug}.html")])
        # all upcoming of this comp within 14 days
        wk2 = (today + datetime.timedelta(days=14)).isoformat()
        rows = sorted([(m, preds[str(m["match_id"])]) for m in upcoming
                       if m.get("competition") == c and str(m.get("match_id")) in preds and (m.get("kickoff") or "") <= wk2],
                      key=lambda t: (t[0].get("kickoff") or "", t[0].get("koff_time") or ""))
        pred_rows = [Markup(pred_row(m, p)) for m, p in rows]
        power_html = Markup(power_table(c, stats, params, forms.get(c, {})))
        pi = pins.get(c)
        si = sins.get(c)
        players = None
        if pi or si:
            players = ""
            if si and si.get("ga"):
                players += ga_table(si["ga"], si.get("share", []), "الأكثر مساهمة في الأهداف (أهداف + صناعة)")
            if pi and pi.get("ratings"):
                players += ratings_table(pi["ratings"][:10], "أعلى اللاعبين تقييمًا (مرتان أساسيًا على الأقل)")
            players = Markup(players)
        timing = None
        if pi and sum(pi["timing"].values()) >= 10:
            late = sorted(pi["club_late"].items(), key=lambda kv: -kv[1]["late_share"])[:3]
            early = sorted(pi["club_late"].items(), key=lambda kv: -(kv[1]["early"] / kv[1]["total"]))[:3]
            timing = {
                "goals": sum(pi["timing"].values()), "games": _games(pi["n_matches"]),
                "bars": Markup(timing_bars(pi["timing"], "الأهداف حسب فترة المباراة (بالدقائق)")),
                "late": Markup('، '.join(f'<bdi>{esc(k)}</bdi> ({v["late"]} من {v["total"]})'
                                         for k, v in late if v["late"])) if late else None,
                "early": Markup('، '.join(f'<bdi>{esc(k)}</bdi> ({v["early"]} من {v["total"]})'
                                          for k, v in early if v["early"])) if early else None}
        ca = {"all": acc["comps"].get(c), "comps": {}, "recent": [e for e in acc.get("recent", []) if e.get("comp") == c]}
        # the standings page exists only for a competition with ONE table; a
        # cup (CAF CL) has group tables and no /standings page, so linking it
        # unconditionally left a dead link on that league's analysis page
        write(f"analysis/{slug}.html", render(
            "analysis_league.html", page_head=Markup(page_head), crumbs_ld=Markup(crumbs_ld),
            label=label, slug=slug, games=_games(params["n"]), gpm=f'{(params["gpm"] or 0):.2f}',
            home_win=_pct(params["home_win"]) if params["home_win"] is not None else None,
            draw=_pct(params["draw"]) if params["home_win"] is not None else None,
            rows=pred_rows, disclaimer=Markup(AN_DISCLAIMER), power=power_html,
            players=players, timing=timing, accuracy=Markup(accuracy_html(ca, anchor=False)),
            has_table=bool((has_table or set()) and comp_has_table(c, has_table)),
            page_foot=Markup(foot())))
        urls.append(f"/analysis/{slug}.html")
    return urls


def _page_analysis_hub_analysis_league(_acc, _comps_with_table, _lparams, _pins, _plog, _preds,
                                       _sins, _tstats, _upcoming, forms, matches, urls):
    """/analysis hub + /analysis/<league> + /predictions (the markup still lives
    in analysis_pages() and prediction_history_page() - their own templating
    step)."""
    os.makedirs(os.path.join(DIST, "analysis"), exist_ok=True)
    _hist_url = prediction_history_page(_plog, _acc)
    if _hist_url:
        urls.append(_hist_url)
        print(f"  + prediction history: {_acc['all']['n']} scored predictions")
    _an_urls = analysis_pages(matches, _upcoming, _preds, _plog, _acc, _tstats, _lparams,
                              _pins, _sins, forms, _comps_with_table)
    urls.extend(_an_urls)
    print(f"  + analysis pages: {len(_an_urls)}")
