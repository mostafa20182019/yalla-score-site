"""The computed match readings («قراءة المباراة»): before the match and
after it, the table after the result, streaks and ordinals. Computed,
never generated.

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
from site_lib.arabic import _ORD_AR
from site_lib.competitions import COMP_TV
from site_lib.dates import _days_between, fmt_day
from site_lib.matchdata import _rt_class, _side_of, match_ratings, match_story
from site_lib.names import _club_pool, ar_team
from site_lib.stats import _cnt, _draws, _form_counts, _games, _losses, _per_game, _pts, _pts_phrase, _wins
from site_lib.text import _lam, _pct, esc, jsonld


# «الخسارة» is feminine in Arabic: الخسارة الثانية, not الخسارة الثاني
_ORD_AR_F = {n: (w + "ة") for n, w in _ORD_AR.items() if n <= 10}
def _ord_ar(n, fem=False):
    """Arabic ordinal, or the bare number for a place past the twentieth (the
    36-club Champions League league phase) - never «المركز رقم 24»."""
    n = int(n or 0)
    return (_ORD_AR_F if fem else _ORD_AR).get(n, str(n))


def _streak_ar(res):
    """Trailing run in a chronological W/D/L list, as Arabic - or ''."""
    if not res:
        return ""
    last, n = res[-1], 0
    for r in reversed(res):
        if r != last:
            break
        n += 1
    if n > 10:            # past the ordinals: plain and plural
        return f"{n} " + {"W": "انتصارات", "D": "تعادلات", "L": "خسائر"}[last] + " متتالية"
    if n >= 2:
        word = {"W": "الفوز", "D": "التعادل", "L": "الخسارة"}[last]
        return f"{word} {_ord_ar(n, fem=last == 'L')} على التوالي"
    unb = 0
    for r in reversed(res):
        if r == "L":
            break
        unb += 1
    return f"{unb} مباريات دون خسارة" if unb >= 4 else ""


def table_after(m, st, form_map, fin_comp, h_ar, a_ar):
    """«ماذا تغيّر في الجدول»: the club's place and points AFTER this match,
    read straight off the official table - never re-sorted by us (tie-break
    rules differ per league and a home-made order could be wrong).

    Only when the table describes THIS moment: the match must be the last
    finished match of both clubs in the competition, and the official `played`
    for each club must equal the finished matches we hold. Otherwise the
    numbers belong to a later round and the sentence would be false."""
    rows = (st or {}).get("table") or []
    if not rows or (st or {}).get("zeroed") or (st or {}).get("past"):
        return []
    fin = fin_comp or []
    pairs = []
    for raw, ar in ((m.get("home"), h_ar), (m.get("away"), a_ar)):
        played_by_club = [x for x in fin
                          if raw in (x.get("home"), x.get("away"))]
        if not played_by_club:
            return []
        last = played_by_club[-1]
        if (last.get("kickoff"), last.get("home"), last.get("away")) != \
           (m.get("kickoff"), m.get("home"), m.get("away")):
            return []                      # a later match has been played since
        row = next((r for r in rows if r.get("team") == raw), None)
        if row is None or row.get("pos") is None:
            return []
        if int(row.get("played") or 0) != len(played_by_club):
            return []                      # the table has not caught up (or is ahead)
        pairs.append((row, ar, (form_map or {}).get(raw) or []))
    out = []
    for row, ar, form in pairs:
        pos = int(row["pos"])
        line = f"{ar} في المركز {_ord_ar(pos)} برصيد {_pts(row.get('pts'))}"
        nb = next((r for r in rows if int(r.get("pos") or 0) == (pos - 1 if pos > 1 else 2)), None)
        if nb and nb.get("pts") is not None and row.get("pts") is not None:
            gap = abs(int(nb["pts"]) - int(row["pts"]))
            who = f"{ar_team(nb.get('team'))} ({_ord_ar(int(nb['pos']))})"
            if gap:
                line += f"، بفارق {_pts(gap)} {'خلف' if pos > 1 else 'أمام'} {who}"
            else:
                line += f"، متساويًا في النقاط مع {who}"
        streak = _streak_ar(form)
        line += f" — {streak}." if streak else "."
        out.append(line)
    return out


def _form_phrase(res, club):
    """«الأهلي في آخر 5 مباريات: 3 انتصارات وتعادلان» (+ the current run)."""
    l, w, d, ls = _form_counts(res)
    if len(l) < 3:
        return ""
    bits = [x for x in (_wins(w) if w else "", _draws(d) if d else "",
                        _losses(ls) if ls else "") if x]
    out = f"{club} في آخر {_games(len(l))}: " + " و".join(bits)
    st = _streak_ar(l)
    return out + (f" ({st})" if st else "")


def pre_match_read(m, h_ar, a_ar, comp_label_txt, st=None, form_map=None,
                   fin_comp=None, fin_all=None, pred=None):
    """«قراءة قبل المباراة» — (html, faq_html, weight) for an UPCOMING match.

    Layer 1 of the match-page rework (2026-09-14). The page could already tell
    you WHEN the match is and what the model thinks; it could not tell you how
    the two clubs arrive at it. Everything here is a restatement of the
    official table, the form list and the finished matches in the season pool -
    the same discipline as post_match_read(), so it can run on every fixture
    without turning into generated content.

    `weight` counts the substantive facts: the caller uses it to decide whether
    the page is worth indexing (an empty fixture page was the thin content
    AdSense rejected on 2026-09-04)."""
    rows = (st or {}).get("table") or []
    if (st or {}).get("zeroed") or (st or {}).get("past"):
        rows = []
    def row_of(raw):
        r = next((x for x in rows if x.get("team") == raw), None)
        return r if r and int(r.get("played") or 0) > 0 else None
    rh, ra = row_of(m.get("home")), row_of(m.get("away"))
    fm = form_map or {}
    fh, fa = fm.get(m.get("home")) or [], fm.get(m.get("away")) or []
    ps, weight = [], 0

    # 1. where the two clubs stand right now
    if rh and ra:
        ps.append(f"يدخل {h_ar} المباراة في المركز {_ord_ar(int(rh['pos']))} "
                  f"{_pts_phrase(rh.get('pts'))} من {_games(rh.get('played'))}، "
                  f"بينما يحتل {a_ar} المركز {_ord_ar(int(ra['pos']))} "
                  f"{_pts_phrase(ra.get('pts'))}.")
        weight += 1

    # 2. how they arrive: the last five, with the current run
    forms = [x for x in (_form_phrase(fh, h_ar), _form_phrase(fa, a_ar)) if x]
    if forms:
        ps.append("، و".join(forms) + ".")
        weight += len(forms)

    # 3. the goals: scored and conceded per game this season
    if rh and ra:
        ph_, pa_ = _per_game(rh), _per_game(ra)
        if ph_ and pa_:
            ps.append(f"هجوميًا، سجّل {h_ar} بمعدل {ph_[0]:.1f} هدف في المباراة "
                      f"واستقبل {ph_[1]:.1f}، مقابل {pa_[0]:.1f} و{pa_[1]:.1f} "
                      f"{_lam(a_ar)}.")
            weight += 1

    # 4. clean sheets, counted off the season pool
    for raw, club in ((m.get("home"), h_ar), (m.get("away"), a_ar)):
        ms = _club_pool(fin_comp, raw)
        if len(ms) >= 3:
            cs = sum(1 for x in ms
                     if (x["away_score"] if x.get("home") == raw else x["home_score"]) == 0)
            if cs >= 2:
                ps.append(f"حافظ {club} على نظافة شباكه في "
                          f"{_cnt(cs, 'مباراة واحدة', 'مباراتين', 'مباريات', 'مباراة')} "
                          f"من أصل {len(ms)} هذا الموسم.")
                weight += 1
                break

    # 5. the last time they met (any competition in the season pool)
    prev = sorted([x for x in (fin_all or [])
                   if {x.get("home"), x.get("away")} == {m.get("home"), m.get("away")}],
                  key=lambda x: x.get("kickoff") or "")
    if prev:
        lastm = prev[-1]
        hs_, as_ = lastm.get("home_score"), lastm.get("away_score")
        who = (ar_team(lastm.get("home")) if hs_ > as_
               else ar_team(lastm.get("away")) if as_ > hs_ else None)
        res = (f"بفوز {who} {max(hs_, as_)}-{min(hs_, as_)}" if who
               else f"بالتعادل {hs_}-{as_}")
        ps.append(f"آخر مواجهة بينهما كانت يوم {fmt_day(lastm['kickoff'])} "
                  f"وانتهت {res}.")
        weight += 1

    # 6. a short turnaround is a fact worth knowing before kick-off
    rest = []
    for raw, club in ((m.get("home"), h_ar), (m.get("away"), a_ar)):
        ms = _club_pool(fin_all, raw)
        if not ms:
            continue
        gap = _days_between(m.get("kickoff"), ms[-1].get("kickoff"))
        if gap is not None and 0 <= gap <= 3:
            opp = ar_team(ms[-1]["away"] if ms[-1].get("home") == raw else ms[-1]["home"])
            rest.append(f"{club} يلعب بعد {_cnt(gap, 'يوم واحد', 'يومين', 'أيام', 'يومًا')} "
                        f"فقط من مباراته أمام {opp}")
    if rest:
        ps.append("، و".join(rest) + ".")
        weight += 1

    # 7. what a win is worth - arithmetic on the CURRENT points, never a
    #    predicted position (other clubs play too, and tie-break rules differ)
    if rh and ra:
        stake = f"الفوز يرفع {h_ar} إلى {_pts(int(rh.get('pts') or 0) + 3)}"
        pos = int(rh["pos"])
        nb = next((r for r in rows if int(r.get("pos") or 0) == (pos - 1 if pos > 1 else 2)), None)
        if nb and nb.get("pts") is not None:
            diff = (int(rh.get("pts") or 0) + 3) - int(nb["pts"])
            # the neighbour in the table is often the opponent itself - naming
            # it twice in one sentence reads like two different clubs
            who = (f"{a_ar} نفسه" if nb.get("team") == m.get("away")
                   else f"{ar_team(nb.get('team'))} ({_ord_ar(int(nb['pos']))})")
            if diff > 0:
                stake += f"، أي {_pts(diff)} فوق {who} حاليًا"
            elif diff < 0:
                stake += f"، أي {_pts(-diff)} خلف {who} حاليًا"
            else:
                stake += f"، ليتساوى مع {who} حاليًا"
        stake += (f"، بينما يرفع الفوز {a_ar} إلى "
                  f"{_pts(int(ra.get('pts') or 0) + 3)}.")
        ps.append(stake)
        weight += 1

    if not ps:
        return "", "", 0
    html = (f'<section class="minfo st-analysis mread"><h2>قراءة قبل مباراة '
            f'{esc(h_ar)} و{esc(a_ar)}</h2><p>' + " ".join(esc(x) for x in ps)
            + '</p><p class="pd-note">الأرقام من جدول البطولة الرسمي ونتائج '
              'الموسم حتى تاريخ النشر، وتُحدَّث تلقائيًا حتى صافرة البداية.</p></section>')

    faq = []
    when = fmt_day(m["kickoff"]) + (f" في تمام {m['koff_time']} بتوقيت القاهرة"
                                    if m.get("koff_time") else "")
    faq.append((f"متى مباراة {h_ar} و{a_ar}؟",
                f"تُقام يوم {when} ضمن {comp_label_txt}."))
    ch = m.get("channel") or COMP_TV.get(m.get("competition"))
    faq.append((f"ما القناة الناقلة لمباراة {h_ar} و{a_ar}؟",
                f"تُنقل عبر {ch}." if ch else
                "لم تتوفر بعد معلومات القناة الناقلة لهذه المباراة، وتُحدَّث الصفحة فور توفرها."))
    if forms:
        faq.append((f"كيف يدخل {h_ar} و{a_ar} المباراة؟", "، و".join(forms) + "."))
    if pred:
        pick = max((("H", pred["ph"]), ("D", pred["pd"]), ("A", pred["pa"])),
                   key=lambda x: x[1])
        pick_ar = {"H": f"فوز {h_ar}", "D": "التعادل", "A": f"فوز {a_ar}"}[pick[0]]
        faq.append((f"ما توقع يلا سكور لمباراة {h_ar} و{a_ar}؟",
                    f"يرجّح النموذج {pick_ar} باحتمال {_pct(pick[1])}، والأهداف "
                    f"المتوقعة {pred['lh']:.1f} مقابل {pred['la']:.1f}. "
                    "هذه احتمالات إحصائية وليست نصيحة للمراهنة."))
    fhtml = ('<section class="minfo faq"><h2>أسئلة شائعة عن المباراة</h2>'
             + "".join(f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>'
                       for q, a in faq) + '</section>')
    fld = jsonld({"@context": "https://schema.org", "@type": "FAQPage",
                  "mainEntity": [{"@type": "Question", "name": q,
                                  "acceptedAnswer": {"@type": "Answer", "text": a}}
                                 for q, a in faq]})
    return html, fhtml + fld, weight


def post_match_read(m, e, flipped, h_ar, a_ar, hs, as_, comp_label_txt,
                    st=None, form_map=None, fin_comp=None):
    """(section_html, faq_html_plus_jsonld) for a finished match page."""
    story = match_story(e, flipped, h_ar, a_ar, hs, as_)
    rat = match_ratings(e, flipped, h_ar, a_ar)
    tbl = table_after(m, st, form_map, fin_comp, h_ar, a_ar)
    if not story and not rat and not tbl:
        return "", ""
    ps = []
    if story:
        ps.append("<p>" + " ".join(esc(x) for x in story) + "</p>")
    if rat:
        def chip(lbl, p):
            cls = _rt_class(p["rt"]) or "r6"
            return (f'<div class="mr-c"><span class="mr-l">{esc(lbl)}</span>'
                    f'<b><bdi>{esc(p["name"])}</bdi></b>'
                    f'<small><bdi>{esc(p["club"])}</bdi></small>'
                    f'<span class="rt-b {cls}">{p["rt"]:.1f}</span></div>')
        tie = rat["best_other"] and rat["best_other"]["rt"] >= rat["best"]["rt"]
        cards = [chip(f'الأفضل في {rat["best"]["club"]}' if tie else "الأفضل في اللقاء",
                      rat["best"])]
        if rat["best_other"]:
            cards.append(chip(f'الأفضل في {rat["best_other"]["club"]}', rat["best_other"]))
        if rat["low"]["rt"] < rat["best"]["rt"]:
            cards.append(chip("أقل تقييم", rat["low"]))
        s1, s2 = rat["sides"]
        ps.append('<div class="mr-grid">' + "".join(cards) + '</div>')
        ps.append(f'<p class="mr-avg">متوسط تقييم التشكيلة الأساسية: '
                  f'<bdi>{esc(s1["club"])}</bdi> <b>{s1["avg"]:.1f}</b> مقابل '
                  f'<bdi>{esc(s2["club"])}</bdi> <b>{s2["avg"]:.1f}</b> '
                  '<small>(تقييمات المصدر لكل لاعب، وهي نفسها الظاهرة على الملعب أدناه)</small></p>')
    if tbl:
        ps.append('<p><b>بعد هذه النتيجة:</b> ' + " ".join(esc(x) for x in tbl) + '</p>')
    html = (f'<section class="minfo st-analysis mread"><h2>قراءة مباراة '
            f'{esc(h_ar)} و{esc(a_ar)}</h2>' + "".join(ps) + '</section>')

    # FAQ: the same facts as questions (the shape /standings pages already use)
    sd = _side_of(flipped)
    scorers = [g for g in (e.get("goals") or []) if g.get("player")]
    faq = [(f"كم انتهت مباراة {h_ar} و{a_ar}؟",
            f"انتهت {h_ar} {hs}-{as_} {a_ar} في {comp_label_txt}.")]
    if scorers:
        names = [f'{g["player"]} ({g["minute"]}\u2032)' if g.get("minute") else g["player"]
                 for g in scorers]
        faq.append((f"من سجل أهداف مباراة {h_ar} و{a_ar}؟", "، ".join(names) + "."))
    if rat:
        _bo = rat["best_other"]
        if _bo and _bo["rt"] >= rat["best"]["rt"]:
            ans = (f'تساوى {rat["best"]["name"]} ({rat["best"]["club"]}) و{_bo["name"]} '
                   f'({_bo["club"]}) في أعلى تقييم بالمباراة بـ{rat["best"]["rt"]:.1f}.')
        else:
            ans = (f'{rat["best"]["name"]} لاعب {rat["best"]["club"]} بتقييم '
                   f'{rat["best"]["rt"]:.1f}، وهو الأعلى بين لاعبي التشكيلتين الأساسيتين.')
        faq.append((f"من أفضل لاعب في مباراة {h_ar} و{a_ar}؟", ans))
    if tbl:
        faq.append((f"ماذا تغيّر في الترتيب بعد مباراة {h_ar} و{a_ar}؟",
                    " ".join(tbl)))
    fhtml = ('<section class="minfo faq"><h2>أسئلة شائعة عن المباراة</h2>'
             + "".join(f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>'
                       for q, a in faq) + '</section>')
    fld = jsonld({"@context": "https://schema.org", "@type": "FAQPage",
                  "mainEntity": [{"@type": "Question", "name": q,
                                  "acceptedAnswer": {"@type": "Answer", "text": a}}
                                 for q, a in faq]})
    return html, fhtml + fld
