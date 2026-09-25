"""League tables, scorers, form, Elo - the numbers behind the readings.

Moved verbatim out of build_site.py (slice 3, 2026-09-25): the source
and its comments are exactly what they were there. Edit here; build_site
imports these back under the same names."""
from site_lib.names import _gnorm, _team_link, ar_team
from site_lib.text import _pval, esc, jsonld


def _cnt(n, one, two, few, many):
    """Arabic count with proper agreement: 1 -> one ("نقطة واحدة"),
    2 -> two ("نقطتان"), 3-10 -> "n few" ("5 نقاط"), 0/11+ -> "n many" ("12 نقطة")."""
    n = int(n or 0)
    if n == 0:
        return f"دون {few}"          # "دون أهداف" / "دون خسائر"
    if n == 1:
        return one
    if n == 2:
        return two
    if 3 <= n <= 10:
        return f"{n} {few}"
    return f"{n} {many}"


def _pts(n):   return _cnt(n, "نقطة واحدة", "نقطتين", "نقاط", "نقطة")


def _games(n): return _cnt(n, "مباراة واحدة", "مباراتين", "مباريات", "مباراة")


def _goals(n): return _cnt(n, "هدف واحد", "هدفين", "أهداف", "هدفًا")


def _wins(n):  return _cnt(n, "فوز واحد", "فوزين", "انتصارات", "فوزًا")


def _draws(n): return _cnt(n, "تعادل واحد", "تعادلين", "تعادلات", "تعادلًا")


def _losses(n): return _cnt(n, "خسارة واحدة", "خسارتين", "خسائر", "خسارة")


def _assists(n): return _cnt(n, "تمريرة حاسمة واحدة", "تمريرتين حاسمتين",
                             "تمريرات حاسمة", "تمريرة حاسمة")


def _players(n): return _cnt(n, "لاعبًا واحدًا", "لاعبين", "لاعبين", "لاعبًا")


def _lil(name):
    """«لـ» before a club name, with the ل+ال elision Arabic requires:
    القناة -> للقناة, not «لـالقناة»."""
    name = (name or "").strip()
    return ("لل" + name[2:]) if name.startswith("ال") else ("لـ" + name)


def scorers_read(label, season, sc, asst, table, pool):
    """Editorial reading of a top-scorer chart, computed from the numbers we
    already publish — the same answer /standings got on 2026-09-06 when a bare
    table was judged thin content.

    Ten names is a list, not a page. What makes it a page is what the list
    MEANS: who leads and by how much, how much of his club's season he is
    carrying, whether one club owns the chart, who creates rather than
    finishes, and where all of it sits against the league's own goal rate.

    Every sentence restates data on this site (the chart, the official table,
    the season pool). Nothing is estimated, and each fact is skipped when its
    input is missing — which is also what decides whether the page is worth
    indexing: returns (html, faq_html, weight).
    """
    sc = [x for x in (sc or []) if x.get("name")]
    if not sc:
        return "", "", 0
    facts, faq = [], []
    top_v = _pval(sc[0])
    leaders = [x for x in sc if _pval(x) == top_v]
    gf_by = {}
    for r in (table or []):
        if r.get("team"):
            gf_by[_gnorm(r["team"])] = r

    # 1. the lead, and what it is worth
    if len(leaders) == 1:
        nxt = next((_pval(x) for x in sc if _pval(x) < top_v), None)
        gap = (f" بفارق {_goals(top_v - nxt)} عن أقرب منافسيه"
               if nxt is not None and top_v > nxt else " بالتساوي مع أقرب منافسيه")
        facts.append(f'يتصدر <b>{esc(sc[0]["name"])}</b> ({esc(sc[0].get("team") or "")}) '
                     f'قائمة هدافي {esc(label)} بـ{_goals(top_v)}{gap}.')
        faq.append((f"من هداف {label} الآن؟",
                    f"{sc[0]['name']} ({sc[0].get('team') or ''}) برصيد {_goals(top_v)} "
                    f"في موسم {season}."))
    else:
        # name EVERY leader while they fit in a sentence: capping at three
        # under a count of four read «بين 4 لاعبين (a، b، c)» and dropped
        # Zizo from his own shared lead (ChatGPT site audit, 2026-09-21).
        # Past five names, say «منهم» so the sentence stops claiming to be
        # the full list instead of silently contradicting the count.
        if len(leaders) <= 5:
            names, pre = "، ".join(esc(x["name"]) for x in leaders), ""
        else:
            names, pre = "، ".join(esc(x["name"]) for x in leaders[:3]), "منهم "
        facts.append(f'تُقسَم صدارة هدافي {esc(label)} بين {_players(len(leaders))} '
                     f'({pre}{names}) برصيد {_goals(top_v)} لكل منهم.')
        faq_names = ("، ".join(x["name"] for x in leaders) if len(leaders) <= 5
                     else "، ".join(x["name"] for x in leaders[:3]) + " وآخرون")
        faq.append((f"من هداف {label} الآن؟",
                    f"الصدارة مشتركة بين {_players(len(leaders))} برصيد {_goals(top_v)} لكل منهم: "
                    + faq_names + "."))

    # 2. how much of his club's season the leader is carrying
    row = gf_by.get(_gnorm(sc[0].get("team")))
    if row and (row.get("gf") or 0) > 0 and top_v <= row["gf"]:
        share = round(top_v * 100 / row["gf"])
        # named, never «وسجّل وحده»: the lead above may be shared, and an
        # unnamed pronoun would then point at whichever name came first
        facts.append(f'وسجّل <b>{esc(sc[0]["name"])}</b> {_goals(top_v)} من أصل '
                     f'{_goals(row["gf"])} {esc(_lil(row["team"]))} هذا الموسم، '
                     f'أي {share}% من أهداف ناديه.')

    # 3. one club owning the chart
    clubs = {}
    for x in sc:
        if x.get("team"):
            clubs.setdefault(_gnorm(x["team"]), [x["team"], 0])[1] += 1
    top_club = max(clubs.values(), key=lambda v: v[1]) if clubs else None
    if top_club and top_club[1] >= 2:
        facts.append(f'ويضع {esc(top_club[0])} {_players(top_club[1])} من صفوفه '
                     f'داخل أعلى {len(sc)} هدافين.')

    # 4. the creators, and anyone doing both
    if asst:
        a0 = asst[0]
        facts.append(f'وفي صناعة الأهداف يتقدم <b>{esc(a0["name"])}</b> '
                     f'({esc(a0.get("team") or "")}) بـ{_assists(_pval(a0))}.')
        faq.append((f"من أكثر صانعي الأهداف في {label}؟",
                    f"{a0['name']} ({a0.get('team') or ''}) برصيد {_assists(_pval(a0))}."))
        both = [x["name"] for x in sc
                if any(_gnorm(y.get("name")) == _gnorm(x.get("name")) for y in asst)]
        if both:
            facts.append('واللافت أن ' + "، ".join(esc(n) for n in both)
                         + (' حاضر في القائمتين: بين الهدافين وصنّاع الأهداف معًا.'
                            if len(both) == 1 else
                            ' حاضرون في القائمتين معًا.'))

    # 5. the league's own scale
    if pool:
        g = sum(int(m["home_score"]) + int(m["away_score"]) for m in pool)
        n = len(pool)
        if n and g:
            top_sum = sum(_pval(x) for x in sc)
            facts.append(f'وللمقارنة، سجّل {esc(label)} {g} هدفًا في {_games(n)} '
                         f'هذا الموسم (بمعدل {g / n:.2f} للمباراة)، فأعلى {len(sc)} هدافين '
                         f'يمثلون {round(top_sum * 100 / g)}% منها.')
            faq.append((f"كم هدفًا سُجّل في {label} هذا الموسم؟",
                        f"{g} هدفًا في {_games(n)} منتهية، بمعدل {g / n:.2f} هدف في المباراة "
                        f"حتى تاريخ التحديث."))

    faq.append(("متى تُحدَّث قائمة الهدافين؟",
                "تُحدَّث تلقائيًا من مصدر بيانات المباريات كل ربع ساعة تقريبًا، "
                "فتظهر أهداف كل جولة بعد نهايتها مباشرة."))

    html = (f'<section class="minfo st-analysis"><h2>قراءة في صدارة هدافي {esc(label)}</h2>'
            + "".join(f"<p>{t}</p>" for t in facts) + '</section>')
    fhtml = ('<section class="minfo faq"><h2>أسئلة شائعة عن هدافي ' + esc(label) + '</h2>'
             + "".join(f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>'
                       for q, a in faq) + '</section>')
    fld = jsonld({"@context": "https://schema.org", "@type": "FAQPage",
                  "mainEntity": [{"@type": "Question", "name": q,
                                  "acceptedAnswer": {"@type": "Answer", "text": a}}
                                 for q, a in faq]})
    return html, fhtml + fld, len(facts)


def standings_analysis(comp, label, season, rows, form_map, scorers, up_next, zeroed=False):
    """Editorial reading of a league table, generated ONLY from the numbers we
    already publish (AdSense 'low value content' remediation: a bare table is
    thin; the same page with an explanation, a title-race reading, form notes
    and an FAQ is a real guide). Returns (html, faq_jsonld_or_empty).
    Every sentence is a restatement of table/form/scorer data — no guesses."""
    rows = [r for r in rows if r.get("team")]
    if not rows:
        return "", ""
    if zeroed or all(int(r.get("played") or 0) == 0 for r in rows):
        html = (f'<section class="minfo st-analysis"><h2>عن ترتيب {esc(label)} {esc(season)}</h2>'
                f'<p>الموسم الجديد من {esc(label)} لم ينطلق بعد، لذلك يظهر الجدول بقائمة الأندية '
                f'المشاركة ({len(rows)} فريقًا) وكل الأرقام عند الصفر. بمجرد انتهاء أول مباراة يتحدّث '
                'الجدول تلقائيًا بالنقاط والأهداف وفارق الأهداف ونتائج آخر خمس مباريات لكل فريق.</p>'
                '<p><b>كيف تُقرأ الأعمدة؟</b> لعب = عدد المباريات، ف/ت/خ = الفوز والتعادل والخسارة، '
                'له/عليه = الأهداف المسجلة والمستقبلة، الفارق = له ناقص عليه، النقاط = 3 لكل فوز '
                'ونقطة لكل تعادل.</p></section>')
        return html, ""
    T = lambda r: _team_link(comp, r.get("team"))
    N = lambda r: ar_team(r.get("team"))
    lead, second = rows[0], (rows[1] if len(rows) > 1 else None)
    gap = int(lead.get("pts") or 0) - int((second or {}).get("pts") or 0)
    ps = []
    ps.append(f'<p>يتصدر {T(lead)} ترتيب {esc(label)} برصيد <b>{_pts(lead.get("pts"))}</b> من '
              f'{_games(lead.get("played"))} '
              f'({_wins(lead.get("won"))}، {_draws(lead.get("draw"))}، {_losses(lead.get("lost"))})'
              + (f'، بفارق {_pts(gap)} عن {T(second)} صاحب المركز الثاني.'
                 if second and gap > 0 else
                 (f'، متساويًا في النقاط مع {T(second)} الثاني الذي يفصله عنه فارق الأهداف '
                  f'({lead.get("gd")} مقابل {second.get("gd")}).' if second else '.'))
              + '</p>')
    top3 = rows[:3]
    if len(rows) >= 4:
        ps.append('<p>المربع الأمامي حتى الآن: ' + '، '.join(
            f'{T(r)} ({_pts(r.get("pts"))})' for r in rows[:4]) + '.</p>')
    played = [r for r in rows if int(r.get("played") or 0) > 0]
    if played:
        best_att = max(played, key=lambda r: (int(r.get("gf") or 0), -int(r.get("ga") or 0)))
        best_def = min(played, key=lambda r: (int(r.get("ga") or 0), -int(r.get("gf") or 0)))
        best_gd = max(played, key=lambda r: int(r.get("gd") or 0))
        worst_gd = min(played, key=lambda r: int(r.get("gd") or 0))
        ps.append(f'<p><b>الهجوم والدفاع:</b> أقوى خط هجوم هو {T(best_att)} بـ{_goals(best_att.get("gf"))}، '
                  f'وأقل شباك استقبالًا للأهداف {T(best_def)} '
                  + (f'بـ{_goals(best_def.get("ga"))} فقط. ' if int(best_def.get("ga") or 0) else 'بشباك لم تستقبل أي هدف حتى الآن. ')
                  + f'أفضل فارق أهداف يملكه {T(best_gd)} ({"+" if int(best_gd.get("gd") or 0) > 0 else ""}{best_gd.get("gd")})، '
                  f'وأسوأ فارق عند {T(worst_gd)} ({worst_gd.get("gd")}).</p>')
    fm = form_map or {}
    def _last5(r):
        return (fm.get(r.get("team")) or [])[-5:]
    hot = sorted([r for r in rows if len(_last5(r)) >= 3],
                 key=lambda r: (-_last5(r).count("W"), _last5(r).count("L")))[:3]
    cold = [r for r in rows if len(_last5(r)) >= 3 and _last5(r).count("W") == 0]
    if hot:
        ps.append('<p><b>الفرق في أفضل حالاتها:</b> ' + '، '.join(
            f'{T(r)} ({_wins(_last5(r).count("W"))} في آخر {_games(len(_last5(r)))})' for r in hot)
            + (f'. أما الفرق التي لم تحقق أي فوز في آخر مبارياتها فهي: '
               + '، '.join(T(r) for r in cold[:4]) + '.' if cold else '.') + '</p>')
    bottom = rows[-3:] if len(rows) >= 6 else []
    if bottom:
        ps.append('<p><b>قاع الجدول:</b> ' + '، '.join(
            f'{T(r)} ({_pts(r.get("pts"))})' for r in bottom)
            + ' — هذه الفرق تحتاج إلى تحسين سريع في النتائج قبل أن تتسع الفجوة مع منطقة الأمان.</p>')
    top_sc = (scorers or [None])[0]
    if top_sc and top_sc.get("name"):
        ps.append(f'<p><b>هداف البطولة:</b> {esc(top_sc["name"])} ({esc(ar_team(top_sc.get("team")))}) '
                  f'برصيد {_goals(top_sc.get("goals") or top_sc.get("value"))}'
                  + (f'، يليه {esc(scorers[1]["name"])} بـ{_goals(scorers[1].get("goals") or scorers[1].get("value"))}.'
                     if len(scorers) > 1 else '.') + '</p>')
    nxt = up_next[0] if up_next else None
    if nxt:
        ps.append(f'<p><b>الجولة القادمة:</b> تُستكمل مباريات {esc(label)} يوم {esc(nxt.get("kickoff"))} '
                  f'بلقاء {esc(ar_team(nxt.get("home")))} و{esc(ar_team(nxt.get("away")))}'
                  + (f' و{_games(len(up_next) - 1)} أخرى' if len(up_next) > 1 else '')
                  + ' — القائمة الكاملة أسفل الصفحة، وكل مباراة لها صفحتها بالتشكيل والأهداف.</p>')
    ps.append('<p><b>كيف تُقرأ الأعمدة؟</b> «لعب» عدد المباريات، «ف/ت/خ» الفوز والتعادل والخسارة، '
              '«له» الأهداف المسجلة و«عليه» المستقبلة، «الفارق» = له ناقص عليه، و«النقاط» = 3 نقاط '
              'لكل فوز ونقطة لكل تعادل. عند التساوي في النقاط تُطبَّق معايير الفصل الواردة في لائحة '
              'البطولة (فارق الأهداف والأهداف المسجلة، وفي بعض البطولات المواجهات المباشرة أولًا). '
              'النقاط الملوّنة بجوار كل فريق هي نتائج آخر خمس مباريات من الأقدم إلى الأحدث.</p>')
    html = (f'<section class="minfo st-analysis"><h2>قراءة في ترتيب {esc(label)} {esc(season)}</h2>'
            + "".join(ps) + '</section>')
    # FAQ — answers are the same data in question form
    faq = [(f"من يتصدر {label} حاليًا؟",
            f"{N(lead)} يتصدر برصيد {_pts(lead.get('pts'))} من {_games(lead.get('played'))}"
            + (f"، بفارق {_pts(gap)} عن {N(second)}." if second and gap > 0 else "."))]
    if second:
        faq.append((f"كم الفارق بين الأول والثاني في {label}؟",
                    f"{_pts(gap)} بين {N(lead)} ({lead.get('pts')}) و{N(second)} ({second.get('pts')})."
                    if gap else f"لا فارق في النقاط: {N(lead)} و{N(second)} متساويان برصيد {_pts(lead.get('pts'))}، ويفصل بينهما فارق الأهداف."))
    if top_sc and top_sc.get("name"):
        faq.append((f"من هو هداف {label} هذا الموسم؟",
                    f"{top_sc['name']} لاعب {ar_team(top_sc.get('team'))} برصيد {_goals(top_sc.get('goals') or top_sc.get('value'))} حتى الآن."))
    faq.append(("كيف يُحسب فارق الأهداف؟",
                "فارق الأهداف = الأهداف المسجلة (له) ناقص الأهداف المستقبلة (عليه). يُستخدم كأحد معايير الفصل بين الفرق المتساوية في النقاط."))
    if nxt:
        faq.append((f"متى الجولة القادمة في {label}؟",
                    f"أقرب مباراة يوم {nxt.get('kickoff')}: {ar_team(nxt.get('home'))} ضد {ar_team(nxt.get('away'))} (التوقيت بتوقيت القاهرة في صفحة المباريات)."))
    faq.append(("كم مرة يتحدّث جدول الترتيب؟",
                "يتحدّث الجدول تلقائيًا كل ربع ساعة تقريبًا من مصدر بيانات المباريات، فتظهر النتائج بعد صافرة النهاية مباشرة."))
    fhtml = ('<section class="minfo faq"><h2>أسئلة شائعة عن ' + esc(label) + '</h2>'
             + "".join(f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>' for q, a in faq)
             + '</section>')
    fld = jsonld({"@context": "https://schema.org", "@type": "FAQPage",
                  "mainEntity": [{"@type": "Question", "name": q,
                                  "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]})
    return html, fhtml + fld


def AN_games(n):
    return _games(n)


def _scored(m):
    return m.get("home_score") is not None and m.get("away_score") is not None


def _finished_by_comp(fixtures, pool=None):
    """competition -> chronological FINISHED matches with scores.

    From the season pool when the build has one (fixtures ∪ matches_archive ∪
    results_archive, de-duplicated by analysis.season_matches - the
    very matches the Elo model replays), from the rounds data alone otherwise.

    2026-09-13: fixtures.json arrived with La Liga cut to rounds [4, 5] after a
    degraded feed answer (fetch_data.merge_fixture_rounds now stops that at the
    source) and the «آخر 5» column collapsed to one or two dots. The pool still
    held the season, so the standings columns read from it: a truncated
    fixtures file can no longer empty them."""
    out = {}
    for comp, ms in (pool or {}).items():
        out[comp] = [m for m in ms if m.get("status") == "FINISHED" and _scored(m)]
    for f in fixtures:
        comp = f.get("competition")
        if comp in out:
            continue
        ms = []
        for rd in f.get("rounds", []):
            ms.extend(rd.get("matches", []))
        out[comp] = [m for m in ms if m.get("status") == "FINISHED" and _scored(m)]
    for ms in out.values():
        ms.sort(key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""))
    return out


def compute_elo(fixtures, pool=None):
    """competition -> {team: (rating, played)} from the finished matches
    (_finished_by_comp), chronological. Plain Elo: start 1500, K=28, home adv +70.
    Only a fallback for the league tiles when a league has no official table."""
    out = {}
    for comp, ms in _finished_by_comp(fixtures, pool).items():
        r, n = {}, {}
        for m in ms:
            h, a = m.get("home"), m.get("away")
            rh, ra = r.get(h, 1500.0), r.get(a, 1500.0)
            e = 1.0 / (1 + 10 ** ((ra - (rh + 70)) / 400))
            hs, aw = m["home_score"], m["away_score"]
            sc = 1.0 if hs > aw else 0.5 if hs == aw else 0.0
            r[h], r[a] = rh + 28 * (sc - e), ra + 28 * ((1 - sc) - (1 - e))
            n[h], n[a] = n.get(h, 0) + 1, n.get(a, 0) + 1
        out[comp] = {t: (r[t], n[t]) for t in r}
    return out


def team_form(fixtures, standings=None, pool=None):
    """competition -> team -> chronological 'W'/'D'/'L' list: finished matches
    from the season pool (see _finished_by_comp; the rounds data when there is
    no pool), LIVE matches with a score from the rounds data.

    Reconciled with the official table (2026-09-13, user: Barcelona «لعب 5»
    but four dots): within ONE fetch, football-data's standings already
    counted Levante x Barcelona while its fixtures still said LIVE 1-3 - the
    feed flips a match to FINISHED minutes after it updates the table. So when
    the table says a club has played MORE matches than we have finished for
    it, the club's LIVE match with a score (there is at most one) counts as
    decided too. When the fixture flips to FINISHED it is counted the normal
    way, never twice."""
    form = {}
    pending = {}                     # comp -> team -> results of LIVE matches with a score

    def _res(m):
        hs, aw = m["home_score"], m["away_score"]
        return ("W" if hs > aw else "D" if hs == aw else "L",
                "W" if aw > hs else "D" if hs == aw else "L")

    for comp, ms in _finished_by_comp(fixtures, pool).items():
        d = form.setdefault(comp, {})
        for m in ms:
            rh, ra = _res(m)
            d.setdefault(m.get("home"), []).append(rh)
            d.setdefault(m.get("away"), []).append(ra)
    for f in fixtures:
        comp = f.get("competition")
        ms = []
        for rd in f.get("rounds", []):
            ms.extend(rd.get("matches", []))
        ms = [m for m in ms if _scored(m) and m.get("status") == "LIVE"]
        ms.sort(key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""))
        form.setdefault(comp, {})
        pd_ = pending.setdefault(comp, {})
        for m in ms:
            rh, ra = _res(m)
            pd_.setdefault(m.get("home"), []).append(rh)
            pd_.setdefault(m.get("away"), []).append(ra)
    for st in standings or []:
        comp = st.get("competition")
        if comp not in form:
            continue
        for row in st.get("table") or []:
            team, played = row.get("team"), row.get("played")
            if team is None or played is None:
                continue
            have = len(form[comp].get(team, []))
            extra = pending.get(comp, {}).get(team, [])
            if played > have and extra:
                form[comp].setdefault(team, []).extend(extra[-(played - have):])
    return form


def form_dots(results):
    """Last-5 form as colored dots (oldest -> newest)."""
    if not results:
        return '<span class="fm-none">—</span>'
    return "".join(f'<span class="fm fm-{r.lower()}" title="{ {"W":"فوز","D":"تعادل","L":"خسارة"}[r] }"></span>'
                   for r in results[-5:])


def chart_is_current(rows, season_goals, max_played):
    """The 365scores charts keep serving LAST season's list until a new season
    produces numbers. Such a list always overshoots the season it claims to
    describe: more goals than the whole competition scored, or more
    appearances than the busiest team has played."""
    if not rows:
        return False
    if sum(_pval(x) for x in rows) > (season_goals or 0):
        return False
    if max_played and max((x.get("played") or 0) for x in rows) > max_played:
        return False
    return True


def league_pcts(fin):
    """Share-of-matches figures for one competition (from finished matches)."""
    n = len(fin)
    if not n:
        return ""
    over = sum(1 for _, m in fin if m["home_score"] + m["away_score"] >= 3)
    draws = sum(1 for _, m in fin if m["home_score"] == m["away_score"])
    homes = sum(1 for _, m in fin if m["home_score"] > m["away_score"])
    clean = sum(1 for _, m in fin if min(m["home_score"], m["away_score"]) == 0)
    cells = [("3 أهداف أو أكثر", over), ("تعادلات", draws),
             ("فوز أصحاب الأرض", homes), ("شباك نظيفة", clean)]
    out = ['<div class="pct-grid">']
    for label, cnt in cells:
        pc = round(cnt * 100 / n)
        out.append(f'<div class="pct" title="{cnt} من {n} مباراة">'
                   f'<span class="pct-l">{label}</span><b>{pc}%</b>'
                   f'<span class="pct-bar"><i style="width:{pc}%"></i></span>'
                   f'<span class="pct-s">{cnt} من {n}</span></div>')
    out.append('</div>')
    return "".join(out)


def _form_counts(res, n=5):
    l = (res or [])[-n:]
    return l, l.count("W"), l.count("D"), l.count("L")


def _pts_phrase(n):
    """«برصيد 10 نقاط» / «دون أي نقاط» — _pts(0) alone gives «دون نقاط», which
    reads wrong after «برصيد»."""
    n = int(n or 0)
    return f"برصيد {_pts(n)}" if n else "دون أي نقاط"


def _per_game(row):
    g = int(row.get("played") or 0)
    if not g:
        return None
    return (int(row.get("gf") or 0) / g, int(row.get("ga") or 0) / g)
