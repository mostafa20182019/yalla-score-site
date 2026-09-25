"""HTML components: prediction buttons and bars, accuracy tables, video facades.

Moved verbatim out of build_site.py (slice 3, 2026-09-25): the source
and its comments are exactly what they were there. Edit here; build_site
imports these back under the same names."""
from site_lib.competitions import COMP_ORDER
from site_lib.matchdata import score_pill, score_txt
from site_lib.names import ar_team, comp_label
from site_lib.text import _pct, esc


def reel_slide(r, first=False):
    """One full-height slide of the TikTok-style vertical feed: tap to play
    (VIDEO_JS facade), swipe up for the next (CSS scroll-snap)."""
    vid = esc(r.get("video_id") or "")
    title = esc(r.get("title") or "")
    thumb = f"https://i.ytimg.com/vi/{vid}/oar2.jpg"          # vertical thumb
    fallback = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"  # crop if missing
    hint = '<div class="swipe-hint">اسحب لفوق للريل التالي ⬆</div>' if first else ""
    return (f'<section class="rslide">'
            f'<div class="vcard reel rstage" data-vid="{vid}" data-src="youtube">'
            f'<button type="button" class="vthumb" aria-label="تشغيل: {title}">'
            f'<img src="{thumb}" alt="{title}" loading="lazy" '
            f'onerror="this.onerror=null;this.src=\'{fallback}\'">'
            f'<span class="vplay" aria-hidden="true">▶</span></button>'
            f'<div class="rtitle">{title}</div>{hint}'
            f'</div></section>')


def video_facade(v):
    """A lightweight video 'facade': thumbnail + play button; the real iframe
    is injected by VIDEO_JS only when the visitor clicks (keeps the page fast).
    Supports source = "youtube" (default) | "dailymotion"."""
    vid = esc(v.get("video_id") or "")
    src = (v.get("source") or "youtube").lower()
    title = esc(v.get("title") or "")
    date = esc(v.get("pub_date") or "")
    if src == "dailymotion":
        thumb = f"https://www.dailymotion.com/thumbnail/video/{vid}"
    else:
        src = "youtube"
        thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
    meta = f'<p class="meta">{date}</p>' if date else ""
    return (f'<div class="vcard" data-vid="{vid}" data-src="{src}">'
            f'<button type="button" class="vthumb" aria-label="تشغيل الفيديو: {title}">'
            f'<img src="{thumb}" alt="{title}" loading="lazy" '
            f'onerror="this.style.display=\'none\';this.parentNode.classList.add(\'noimg\')">'
            f'<span class="vplay" aria-hidden="true">▶</span></button>'
            f'<div class="vb"><h3>{title}</h3>{meta}</div></div>')


def pred_btn(p):
    """«توقع يلا سكور» — the whole prediction on a match row, in ~110 bytes.

    The site's one differentiator was reachable only from /m/<id> or
    /analysis, and the numbers said nobody went: over 24 hours the home page
    and /matches were ~85% of all traffic and exactly one match page showed
    up at all, twice (2026-09-18). So the prediction now offers itself where
    the reader already is.

    What crosses the wire per row is five small numbers, not a rendered
    block: three probabilities, the modal scoreline and the confidence key.
    /matches is already a 1 MB page with 13% of its LCP samples in the
    "poor" band, so ~110 bytes x ~90 rows (about 10 KB, below the fold and
    behind a click) is the whole budget this feature gets. Everything else -
    the team names, the bar, the link to the full reading - is read at click
    time from markup the row already carries.
    """
    if not p:
        return ""
    top = p["top"][0]
    return ('<button type="button" class="pbtn" data-pp="'
            f'{round(p["ph"] * 100)},{round(p["pd"] * 100)},{round(p["pa"] * 100)}"'
            f' data-ps="{top[0]}-{top[1]}" data-pc="{esc(p["conf"])}">'
            'توقع يلا سكور</button>')


def done_btn(e):
    """«توقعنا قبل المباراة» — the same button on a match that is over.

    Stronger than the pre-match one, and for one reason: a probability
    before kickoff is a claim, a probability beside the final score is a
    claim the reader can CHECK. That is the whole point of /predictions,
    and /predictions is a page nobody visits — /matches is where they are.

    Everything here comes from the FROZEN log row, written the day the
    prediction was made and never touched again (analysis.update_log:
    `if old.get("hs") is not None: continue`). Recomputing it today from
    today's Elo would be marking our own homework with the answers in
    front of us, and it would quietly turn the site's one honest number
    into a lie. `hit` is carried rather than derived for the same reason:
    the log decides what counted, not this renderer.

    And it appears on the misses exactly as it does on the hits — 21 of
    the 54 finished rows in today's window were wrong. A button that only
    showed up when we were right would destroy the credibility it exists
    to build.
    """
    if not e or e.get("hs") is None or e.get("as") is None:
        return ""     # in the log but not played yet, or never scored
    return ('<button type="button" class="pbtn" data-pp="'
            f'{round(e["ph"] * 100)},{round(e["pd"] * 100)},{round(e["pa"] * 100)}"'
            f' data-ps="{esc(e.get("score") or "")}"'
            f' data-pr="{e["hs"]}-{e["as"]}"'
            f' data-hit="{1 if e.get("hit") else 0}">'
            'توقعنا قبل المباراة</button>')


def prob_bar(p):
    """Three-segment 1X2 bar (home = brand blue, draw = grey, away = slate).

    PURELY VISUAL since 2026-09-16: the numbers used to be printed inside the
    segments, but a number does not fit in a narrow one, so a lopsided
    prediction rendered as "20% 72%" or "87%" — two outside reviewers read that
    as a missing third probability, twice. A bar that states two of three
    numbers and a line underneath that states all three is two partial
    readings of one thing; if a reviewer is confused by it, a reader is too.
    So the bar shows the shape and prob_legend() says the numbers, once.
    """
    ph, pd, pa = p["ph"], p["pd"], p["pa"]
    def seg(cls, v):
        return f'<span class="pb-seg pb-{cls}" style="width:{v * 100:.1f}%"></span>' 
    return ('<div class="pbar" role="img" aria-label="'
            f'فوز الأرض {_pct(ph)}، تعادل {_pct(pd)}، فوز الضيف {_pct(pa)}">'
            + seg("h", ph) + seg("d", pd) + seg("a", pa) + '</div>')


def prob_legend(p, cls="pr-probs", home=None, away=None):
    """The three probabilities in words — and the bar's key.

    Each one carries a swatch in its segment's colour, so the reader can see
    which slice is which without a number being crammed into a 12-pixel
    segment. This is the ONLY place the percentages are printed (see
    prob_bar), which is the point: one statement, never a partial one."""
    def one(k, label, cls_):
        # .prb, not .pp: «.pp» is already the player marker on the pitch
        # graphic (position:absolute) and these three collapsed onto the bar
        return (f'<span class="prb"><i class="prb-{cls_}"></i>{esc(label)} '
                f'<b>{_pct(p[k])}</b></span>')
    # The clubs by NAME whenever the caller knows them (user, 2026-09-18:
    # «خلى هنا اسماء الفرق»). الأرض/الضيف is the fallback for a caller that
    # has only the numbers — it makes the reader map a generic word onto a
    # club that is written two lines up, which is work the page can do.
    return (f'<span class="{cls}">' + one("ph", home or "الأرض", "h")
            + one("pd", "تعادل", "d") + one("pa", away or "الضيف", "a") + '</span>')


def ratings_table(rows, title):
    if not rows:
        return ""
    out = [f'<div class="tbl-wrap"><h3>{esc(title)}</h3><table class="ptable"><thead><tr><th>#</th>'
           '<th class="tl">اللاعب</th><th class="tl">النادي</th><th>المركز</th><th>مباريات</th><th>متوسط التقييم</th><th>أفضل</th></tr></thead><tbody>']
    for i, r in enumerate(rows, 1):
        out.append(f'<tr><td>{i}</td><td class="tl"><bdi>{esc(r["name"])}</bdi></td><td class="tl"><bdi>{esc(r["club"])}</bdi></td>'
                   f'<td>{esc(r.get("pos") or "")}</td><td>{r["n"]}</td><td><b>{r["avg"]:.2f}</b></td><td>{r["best"]:.1f}</td></tr>')
    out.append('</tbody></table></div>')
    return "".join(out)


def ga_table(rows, share, title):
    if not rows:
        return ""
    sh = {(s["name"], s["team"]): s for s in share}
    out = [f'<div class="tbl-wrap"><h3>{esc(title)}</h3><table class="ptable"><thead><tr><th>#</th>'
           '<th class="tl">اللاعب</th><th class="tl">النادي</th><th>أهداف</th><th>صناعة</th><th>أ+ص</th>'
           '<th title="نسبة أهدافه من أهداف ناديه">من أهداف ناديه</th></tr></thead><tbody>']
    for i, r in enumerate(rows, 1):
        s = sh.get((r["name"], r["team"]))
        out.append(f'<tr><td>{i}</td><td class="tl"><bdi>{esc(r["name"])}</bdi></td><td class="tl"><bdi>{esc(ar_team(r["team"]))}</bdi></td>'
                   f'<td>{r["g"]}</td><td>{r["a"]}</td><td><b>{r["g"] + r["a"]}</b></td>'
                   f'<td>{(_pct(s["share"]) + " (" + str(s["g"]) + "/" + str(s["club_goals"]) + ")") if s else "—"}</td></tr>')
    out.append('</tbody></table></div>')
    return "".join(out)


def accuracy_html(acc, anchor=True):
    a = acc.get("all")
    hid = ' id="accuracy"' if anchor else ""
    if not a:
        return (f'<section class="minfo"{hid}><h2>دقة التوقعات</h2><p>يُثبَّت كل توقع قبل انطلاق المباراة ثم يُقارَن '
                'بالنتيجة الفعلية بعد صافرة النهاية. يبدأ هذا السجل بالظهور بعد أول مباريات تُلعب منذ إطلاق القسم.</p></section>')
    out = [f'<section class="minfo"{hid}><h2>دقة التوقعات</h2>'
           f'<div class="acc-tiles"><div class="tile"><b>{a["n"]}</b><span>مباراة مقيَّمة</span></div>'
           f'<div class="tile"><b>{_pct(a["hit_rate"])}</b><span>إصابة الاتجاه (فوز/تعادل/خسارة)</span></div>'
           f'<div class="tile"><b>{_pct(a["home_baseline"])}</b><span>لو توقعنا فوز الأرض دائمًا</span></div>'
           f'<div class="tile"><b>{a["brier"]:.3f}</b><span>مؤشر Brier (الأقل أفضل، 0.667 = عشوائي)</span></div>'
           f'<div class="tile"><b>{a["score_hits"]}</b><span>نتيجة مضبوطة</span></div></div>']
    if acc.get("comps"):
        out.append('<div class="tbl-wrap"><table class="ptable"><thead><tr><th class="tl">البطولة</th><th>مباريات</th><th>إصابة الاتجاه</th><th>Brier</th></tr></thead><tbody>')
        for comp in COMP_ORDER + [c for c in acc["comps"] if c not in COMP_ORDER]:
            c = acc["comps"].get(comp)
            if c:
                out.append(f'<tr><td class="tl">{esc(comp_label(comp))}</td><td>{c["n"]}</td><td>{_pct(c["hit_rate"])}</td><td>{c["brier"]:.3f}</td></tr>')
        out.append('</tbody></table></div>')
    if acc.get("recent"):
        out.append('<h3>آخر المباريات المقيَّمة</h3><ul class="acc-list">')
        for e in acc["recent"]:
            pick_ar = {"H": ar_team(e["home"]), "D": "تعادل", "A": ar_team(e["away"])}[e["pick"]]
            out.append(f'<li><bdi>{esc(ar_team(e["home"]))} '
                       f'{score_pill(e["hs"], e["as"], "sc-in")} {esc(ar_team(e["away"]))}</bdi> — '
                       f'توقعنا <b>{esc(pick_ar)}</b> ({_pct(max(e["ph"], e["pd"], e["pa"]))}) '
                       + ('<span class="hit ok">✔</span>' if e.get("hit") else '<span class="hit no">✘</span>') + '</li>')
        out.append('</ul>')
    out.append('<p class="hintline"><a href="/predictions.html">السجل الكامل: كل توقع بإصابته '
               'وخطئه، ومعايرة الاحتمالات ←</a></p>')
    out.append('</section>')
    return "".join(out)


def calibration_html(cal):
    """The reliability table: what we said vs what happened, per band."""
    bs = [b for b in cal["buckets"] if b["n"] >= 10]
    if not bs:
        return ""
    out = ['<section class="minfo" id="calibration"><h2>هل احتمالاتنا صادقة؟ (معايرة النموذج)</h2>',
           '<p>كل توقع يقول ثلاثة أرقام: احتمال فوز الأرض، والتعادل، وفوز الضيف — '
           f'أي <b>{cal["statements"]}</b> احتمالًا معلنًا في <b>{cal["matches"]}</b> مباراة. '
           'هنا نجمع كل احتمال في نطاقه ونقارنه بما حدث فعلًا: لو قلنا «30%» في مئة حالة، '
           'المفروض تقع نحو ثلاثين منها. هذا هو المقياس الحقيقي لنموذج احتمالي، '
           'وليس عدد المرات التي أصاب فيها أعلى احتمال.</p>',
           '<div class="tbl-wrap"><table class="ptable"><thead><tr><th class="tl">النطاق</th>'
           '<th>عدد الحالات</th><th>قلنا (متوسط)</th><th>حدث فعلًا</th><th>الفارق</th>'
           '</tr></thead><tbody>']
    for b in bs:
        diff = b["actual"] - b["stated"]
        cls = "good" if abs(diff) <= 0.05 else "bad" if abs(diff) > 0.12 else ""
        sign = "+" if diff > 0 else ""
        out.append(f'<tr><td class="tl" dir="ltr">{b["lo"]}–{b["hi"]}%</td><td>{b["n"]}</td>'
                   f'<td>{_pct(b["stated"])}</td><td><b>{_pct(b["actual"])}</b></td>'
                   f'<td class="{cls}" dir="ltr">{sign}{diff * 100:.1f}</td></tr>')
    out.append('</tbody></table></div>')
    out.append(f'<p class="hintline">متوسط انحراف المعايرة (ECE): <b>{cal["ece"] * 100:.1f}</b> نقطة مئوية — '
               'كلما اقترب من الصفر كانت الاحتمالات أصدق. النطاقات التي تقل حالاتها عن عشرة لا تُعرض '
               'لأن عيّنتها أصغر من أن تقول شيئًا.</p>')
    out.append('</section>')
    return "".join(out)


def _pred_item_html(e):
    """One prediction in the record: the verdict first (an RTL reader meets it
    immediately), the match and its real score, then one muted line with what
    we said. A six-column table put the verdict at the far end of the row and
    repeated the date on every line - this reads instead of being decoded."""
    mid = e.get("match_id")
    h, a = ar_team(e.get("home")), ar_team(e.get("away"))
    pick_ar = {"H": f"فوز {h}", "D": "تعادل", "A": f"فوز {a}"}.get(e.get("pick"), "—")
    conf = max(e.get("ph") or 0, e.get("pd") or 0, e.get("pa") or 0)
    hit = 1 if e.get("hit") else 0
    verdict = "أصاب" if hit else "أخطأ"
    # score_pill, NOT "2-0" text: between two names in an RTL row a glued score
    # is one LTR bidi run and lands home-score-left = next to the AWAY club
    # (measured 2026-09-16).
    score = score_pill(e.get("hs"), e.get("as"), "sc-in")
    exact = ' <span class="pf-exact" title="أصبنا النتيجة بالضبط">🎯</span>' if e.get("score_hit") else ""
    tag, href = ("a", f' href="/m/{esc(mid)}.html"') if mid else ("div", "")
    return (f'<{tag} class="rec-i {"ok" if hit else "no"}"{href} data-hit="{hit}" '
            f'data-comp="{esc(e.get("comp") or "")}" data-day="{esc(e.get("kickoff") or "")}">'
            f'<span class="rec-v" title="{verdict}" aria-label="{verdict}">{"✔" if hit else "✘"}</span>'
            f'<span class="rec-m"><span class="rec-t"><bdi>{esc(h)}</bdi> {score} '
            f'<bdi>{esc(a)}</bdi>{exact}</span>'
            f'<span class="rec-s">قلنا <b>{esc(pick_ar)}</b> بنسبة {_pct(conf)} '
            f'<i class="rec-d">· أقرب نتيجة {score_txt(e.get("score"), "sc-in sc-s")}</i>'
            f'<i class="rec-lg">· {esc(comp_label(e.get("comp") or ""))}</i></span></span>'
            f'<span class="rec-c">{esc(comp_label(e.get("comp") or ""))}</span>'
            f'</{tag}>')


def _calls_html(ex):
    """The most confident hits and the most confident misses, side by side and
    the same size. A record that shows only the hits is an advert."""
    if not (ex["best"] or ex["worst"]):
        return ""
    def col(title, rows, cls):
        if not rows:
            return f'<div class="calls-c"><h3>{esc(title)}</h3><p class="hintline">لا شيء بعد.</p></div>'
        items = []
        for e in rows:
            h, a = ar_team(e.get("home")), ar_team(e.get("away"))
            pick_ar = {"H": h, "D": "تعادل", "A": a}.get(e.get("pick"), "—")
            conf = max(e.get("ph") or 0, e.get("pd") or 0, e.get("pa") or 0)
            items.append(f'<li><bdi>{esc(h)} {score_pill(e.get("hs"), e.get("as"), "sc-in")} {esc(a)}</bdi>'
                         f'<span>قلنا <b><bdi>{esc(pick_ar)}</bdi></b> بنسبة {_pct(conf)}</span></li>')
        return f'<div class="calls-c {cls}"><h3>{esc(title)}</h3><ul>{"".join(items)}</ul></div>'
    return ('<section class="minfo"><h2>أوضح إصاباتنا وأوضح إخفاقاتنا</h2>'
            '<div class="calls">'
            + col("أصاب النموذج وهو واثق", ex["best"], "ok")
            + col("أخطأ النموذج وهو واثق", ex["worst"], "no")
            + '</div><p class="hintline">أعلى التوقعات ثقةً في الاتجاهين — تُعرض معًا بالحجم نفسه.</p></section>')


def model_explainer():
    return ('<section class="minfo explain" id="model"><h2>كيف يعمل نموذج يلا سكور؟</h2>'
            '<p>القسم لا يعتمد على آراء أو توقعات شخصية، بل على أرقام المباريات الفعلية التي يجمعها الموقع '
            'كل ربع ساعة. لكل بطولة يبني النموذج ثلاث طبقات:</p><ol>'
            '<li><b>تقييم القوة (Elo):</b> يبدأ كل نادٍ برصيد 1500 نقطة، ويربح أو يخسر نقاطًا بعد كل مباراة '
            'بحسب النتيجة وقوة الخصم، مع ميزة صغيرة لصاحب الأرض. الفوز على فريق قوي يرفع التقييم أكثر من الفوز على فريق ضعيف.</li>'
            '<li><b>مؤشرا الهجوم والدفاع:</b> متوسط أهداف كل نادٍ له وعليه مقارنة بمتوسط الدوري، مع تخفيف أثر العيّنات '
            'الصغيرة في بداية الموسم حتى لا يبدو فريق «لا يُقهر» بعد مباراتين.</li>'
            '<li><b>الأهداف المتوقعة والاحتمالات:</b> من المؤشرين ومتوسط أهداف الأرض والضيف في الدوري يُحسب عدد الأهداف '
            'المتوقع لكل فريق، ثم توزيع بواسون على كل النتائج الممكنة يعطي احتمالات الفوز والتعادل والخسارة، '
            'والنتائج الأكثر ترجيحًا، واحتمال تجاوز 2.5 هدف وتسجيل الفريقين.</li></ol>'
            '<p><b>الشفافية:</b> يُثبَّت كل توقع قبل انطلاق المباراة ولا يُعدَّل بعدها، ثم يُقارَن بالنتيجة الفعلية في '
            '<a href="#accuracy">سجل الدقة</a> أعلاه، إلى جانب مقياس ساذج (توقع فوز الأرض دائمًا) حتى يعرف القارئ إن كان '
            'النموذج يضيف شيئًا فعلًا.</p>'
            '<p><b>حدود النموذج:</b> لا يعرف الإصابات ولا الإيقافات ولا تغيّر المدرب، ويعتمد على الموسم الحالي فقط '
            'فتكون عيّنته صغيرة في الجولات الأولى (نُشير إلى ذلك بوسم «عيّنة صغيرة»). لذلك تُقرأ التوقعات كاحتمالات '
            'وليست حقائق، وهي ليست نصيحة للمراهنة.</p></section>')
