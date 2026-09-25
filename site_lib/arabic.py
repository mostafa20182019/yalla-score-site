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
