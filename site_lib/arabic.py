"""Arabic calendar words and ordinals.

Moved verbatim out of build_site.py (slice 2, 2026-09-25) - the source
text and its comments are exactly what they were there. Edit here;
build_site imports these back under the same names."""

_AR_DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]  # weekday() 0..6

_AR_MONTHS = ["", "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
              "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]

# ===========================================================================
# «قراءة المباراة» — layer 2 of the match-page rework (2026-09-14).
#
# The page had every number and said nothing. These functions read the data
# that is already on it: the events timeline becomes a story, the rating
# badges already printed on the pitch chips become "who decided this match",
# and the official table becomes "what the result changed".
#
# Same discipline as standings_analysis(): every clause is a restatement of
# data we publish, plus arithmetic on minutes, the running score and the
# table. Nothing is inferred, nothing is generated - so this can run on all
# 483 match pages without becoming scaled auto-written content, and a page
# whose data is incomplete simply says less.
# ===========================================================================
_ORD_AR = {1: "الأول", 2: "الثاني", 3: "الثالث", 4: "الرابع", 5: "الخامس",
           6: "السادس", 7: "السابع", 8: "الثامن", 9: "التاسع", 10: "العاشر",
           11: "الحادي عشر", 12: "الثاني عشر", 13: "الثالث عشر", 14: "الرابع عشر",
           15: "الخامس عشر", 16: "السادس عشر", 17: "السابع عشر", 18: "الثامن عشر",
           19: "التاسع عشر", 20: "العشرين"}


# «الجولة السادسة»: feminine ordinals for a round (2026-10-07, the /analysis
# hub label next to each league). Up to 49 - no league here has more rounds;
# anything else falls back to the digits.
_ORD_F = {1: "الأولى", 2: "الثانية", 3: "الثالثة", 4: "الرابعة", 5: "الخامسة",
          6: "السادسة", 7: "السابعة", 8: "الثامنة", 9: "التاسعة", 10: "العاشرة"}
_ORD_F_UNIT = {**_ORD_F, 1: "الحادية"}
_TENS_F = {2: "العشرون", 3: "الثلاثون", 4: "الأربعون"}


def round_ordinal(n):
    """6 -> «السادسة», 11 -> «الحادية عشرة», 21 -> «الحادية والعشرون»."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return str(n)
    if n in _ORD_F:
        return _ORD_F[n]
    if 11 <= n <= 19:
        return f"{_ORD_F_UNIT[n - 10]} عشرة"
    t, u = divmod(n, 10)
    if t in _TENS_F:
        return _TENS_F[t] if u == 0 else f"{_ORD_F_UNIT[u]} و{_TENS_F[t]}"
    return str(n)


def rounds_label(rounds):
    """{6} -> «الجولة السادسة», {8, 9} -> «الجولتان الثامنة والتاسعة»;
    "" when there is nothing (or too much) to name."""
    rs = sorted({int(r) for r in rounds if str(r).strip().isdigit()})
    if len(rs) == 1:
        return f"الجولة {round_ordinal(rs[0])}"
    if len(rs) == 2:
        return f"الجولتان {round_ordinal(rs[0])} و{round_ordinal(rs[1])}"
    return ""
