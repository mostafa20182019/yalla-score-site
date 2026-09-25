"""Arabic dates and relative times («منذ …»).

Moved verbatim out of build_site.py (slice 3, 2026-09-25): the source
and its comments are exactly what they were there. Edit here; build_site
imports these back under the same names."""
import datetime
from site_lib.arabic import _AR_DAYS, _AR_MONTHS
from site_lib.text import esc


def fmt_day(d):
    try:
        dt = datetime.date.fromisoformat(d)
        return f"{_AR_DAYS[dt.weekday()]} {dt.day} {_AR_MONTHS[dt.month]} {dt.year}"
    except Exception:
        return d


def _ar_ago(n, one, two, few):
    """Arabic 'منذ N <unit>' with the correct plural form (1 / 2 / 3-10 / 11+)."""
    if n == 1:
        return f"منذ {one}"
    if n == 2:
        return f"منذ {two}"
    if 3 <= n <= 10:
        return f"منذ {n} {few}"
    return f"منذ {n} {one}"


def rel_ar(iso):
    """Build-time Arabic 'منذ X' (JS refines it in the visitor's browser)."""
    try:
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return ""
    now = datetime.datetime.now(dt.tzinfo) if dt.tzinfo else datetime.datetime.now()
    s = int((now - dt).total_seconds())
    if s < 0:
        s = 0
    if s < 60:
        return "منذ لحظات"
    m = s // 60
    if m < 60:
        return _ar_ago(m, "دقيقة", "دقيقتين", "دقائق")
    h = m // 60
    if h < 24:
        return _ar_ago(h, "ساعة", "ساعتين", "ساعات")
    return _ar_ago(h // 24, "يوم", "يومين", "أيام")


def art_reltime(a):
    """<time> element showing 'منذ X' for an article carrying pub_ts (full ISO
    timestamp, present on articles published since 2026-08-31). Older articles
    have only pub_date -> returns '' and the caller shows what it always did."""
    ts = a.get("pub_ts") or ""
    txt = rel_ar(ts) if ts else ""
    if not txt:
        return ""
    return f'<time class="reltime" datetime="{esc(ts)}">{esc(txt)}</time>'


def _epoch_ms(iso):
    """ISO timestamp (any offset, or a bare date) -> epoch ms, None if unreadable."""
    if not iso:
        return None
    try:
        d = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:                     # a bare pub_date: noon Cairo, as the RSS does
        d = d.replace(hour=12, tzinfo=datetime.timezone(datetime.timedelta(hours=3)))
    return int(d.timestamp() * 1000)


def _days_between(d1, d2):
    try:
        a = datetime.date.fromisoformat(d1)
        b_ = datetime.date.fromisoformat(d2)
        return (a - b_).days
    except Exception:
        return None
