"""The fixed pages: 404, privacy, about, contact, terms, editorial, reels,
videos.

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
from site_lib.config import CONTACT_EMAIL, EDITOR_EMAIL, EDITOR_NAME, EDITOR_ROLE, FB_PAGE_URL, REF_TODAY, SHOW_REELS, SHOW_VIDEOS, SITE_BASE, SITE_NAME, TG_CHANNEL_URL, _src
from site_lib.media import VIDEO_CATS
from site_lib.render import Markup, render
from site_lib.shell import foot, head, write
from site_lib.snippets import REELS_FEED_JS, VIDEO_JS
from site_lib.text import esc, jsonld
from site_lib.widgets import reel_slide, video_facade


def _page_404():
    """/404 - served by Cloudflare for any missing asset; not in the sitemap on
    purpose. Text: site_src/templates/404.html. The auto-retry (snippets/
    nf_retry_js.html) exists for one real case: an article page can 404 for a
    minute or two right around a deploy while the reader already holds a newer
    home page - the page re-checks itself and reloads the moment the URL starts
    resolving. Bounded: a genuinely dead link stops polling after ~2 minutes."""
    page_head = Markup(head(f"الصفحة غير موجودة — {SITE_NAME}",
                            "الصفحة التي تبحث عنها غير موجودة.",
                            SITE_BASE + "/404.html"))
    write("404.html", render("404.html", page_head=page_head,
                             retry_js=Markup(_src("snippets/nf_retry_js.html")),
                             page_foot=Markup(foot())))


def _page_privacy_policy(urls):
    """/privacy (required for AdSense). The text is site_src/templates/privacy.html;
    this function only hands it the pieces that change (templated 2026-09-25)."""
    contact = (Markup(f'راسِلنا على <a href="mailto:{esc(CONTACT_EMAIL)}">{esc(CONTACT_EMAIL)}</a>.')
               if CONTACT_EMAIL else 'يمكنك التواصل معنا عبر قنواتنا الرسمية.')
    write("privacy.html", render(
        "privacy.html",
        page_head=Markup(head("سياسة الخصوصية — " + SITE_NAME,
                              "سياسة الخصوصية وملفات تعريف الارتباط والإعلانات في موقع يلا سكور.",
                              SITE_BASE + "/privacy.html")),
        ref_today=REF_TODAY,
        contact=contact,
        page_foot=Markup(foot())))
    urls.append("/privacy.html")


def _page_about(urls):
    """/about and /editors (AdSense / E-E-A-T identity pages). Text:
    site_src/templates/about.html + editors.html (templated 2026-09-25)."""
    common = dict(site_name=SITE_NAME)
    write("about.html", render(
        "about.html",
        page_head=Markup(head("من نحن — " + SITE_NAME,
                              "تعرّف على يلا سكور: موقع عربي لأخبار كرة القدم ونتائج المباريات وجداول الترتيب.",
                              SITE_BASE + "/about.html")),
        page_foot=Markup(foot()), **common))
    urls.append("/about.html")

    # /editors - publisher identity for the AdSense / E-E-A-T review (2nd
    # rejection 2026-09-04 cited low value content); linked from every
    # article byline, the footer and /about
    page_head = Markup(head("فريق التحرير — " + SITE_NAME,
                            f"من يقف خلف {SITE_NAME}: مدير التحرير، طريقة عملنا في التحقق من الأخبار، وكيف تتواصل معنا للتصحيح.",
                            SITE_BASE + "/editors.html"))
    page_ld = Markup(jsonld({
        "@context": "https://schema.org", "@type": "ProfilePage",
        "name": f"فريق التحرير — {SITE_NAME}", "url": SITE_BASE + "/editors.html",
        "mainEntity": {"@type": "Person", "name": EDITOR_NAME, "jobTitle": EDITOR_ROLE,
                       "email": f"mailto:{EDITOR_EMAIL}", "url": SITE_BASE + "/editors.html",
                       "worksFor": {"@type": "Organization", "name": SITE_NAME, "url": SITE_BASE}},
    }))
    write("editors.html", render(
        "editors.html", page_head=page_head, page_ld=page_ld, page_foot=Markup(foot()),
        editor_name=EDITOR_NAME, editor_role=EDITOR_ROLE, editor_email=EDITOR_EMAIL,
        fb_page_url=FB_PAGE_URL, tg_channel_url=TG_CHANNEL_URL, **common))
    urls.append("/editors.html")


def _page_contact(urls):
    """/contact - text in site_src/templates/contact.html (templated 2026-09-25)."""
    write("contact.html", render(
        "contact.html",
        page_head=Markup(head("اتصل بنا — " + SITE_NAME,
                              "تواصل مع فريق يلا سكور للاستفسارات والتصحيحات والإعلانات.",
                              SITE_BASE + "/contact.html")),
        contact_email=CONTACT_EMAIL, page_foot=Markup(foot())))
    urls.append("/contact.html")


def _page_terms(urls):
    """/terms - text in site_src/templates/terms.html (templated 2026-09-25)."""
    write("terms.html", render(
        "terms.html",
        page_head=Markup(head("شروط الاستخدام — " + SITE_NAME,
                              "شروط استخدام موقع يلا سكور: حدود المسؤولية وقواعد استخدام المحتوى.",
                              SITE_BASE + "/terms.html")),
        site_name=SITE_NAME, page_foot=Markup(foot())))
    urls.append("/terms.html")


def _page_editorial(urls):
    """/editorial (the E-E-A-T editorial policy, incl. the AI disclosure) - text in
    site_src/templates/editorial.html (templated 2026-09-25)."""
    write("editorial.html", render(
        "editorial.html",
        page_head=Markup(head("السياسة التحريرية — " + SITE_NAME,
                              "منهج يلا سكور التحريري: التحقق من مصادر متعددة، صياغة أصلية، صور مرخصة، وتصحيح علني للأخطاء.",
                              SITE_BASE + "/editorial.html")),
        editor_name=EDITOR_NAME, page_foot=Markup(foot())))
    urls.append("/editorial.html")


def _page_reels(reels, urls):
    """/reels - vertical shorts. Template: site_src/templates/reels.html."""
    page_head = Markup(head(f"ريلز كرة القدم — {SITE_NAME}",
                            "ريلز كرة القدم — مقاطع قصيرة: مهارات وأهداف ولقطات ممتعة بالفيديو.",
                            SITE_BASE + "/reels.html", active="reels"))
    slides = [Markup(reel_slide(r, first=(i == 0))) for i, r in enumerate(reels or [])]
    html_ = render("reels.html", page_head=page_head, slides=slides,
                   video_js=Markup(VIDEO_JS), reels_js=Markup(REELS_FEED_JS),
                   page_foot=Markup(foot()))
    if SHOW_REELS:
        write("reels.html", html_)
        urls.append("/reels.html")


def _page_videos(videos, urls):
    """/videos, grouped by competition (item.cat: "wc" | "epl" | "laliga" | absent
    -> "misc"); empty groups are skipped. Template: site_src/templates/videos.html."""
    page_head = Markup(head(f"فيديوهات كرة القدم — {SITE_NAME}",
                            "فيديوهات كأس العالم 2026 والدوري الإنجليزي والدوري الإسباني على يلا سكور.",
                            SITE_BASE + "/videos.html", active="videos"))
    groups = []
    if videos:
        by_cat = {}
        for v in videos:
            by_cat.setdefault((v.get("cat") or "misc"), []).append(v)
        for key, label in VIDEO_CATS:
            if by_cat.get(key):
                # the label was always printed raw (it is our own constant)
                groups.append((Markup(label), [Markup(video_facade(v)) for v in by_cat[key]]))
    html_ = render("videos.html", page_head=page_head, has_videos=bool(videos),
                   groups=groups, video_js=Markup(VIDEO_JS), page_foot=Markup(foot()))
    if SHOW_VIDEOS:
        write("videos.html", html_)
        urls.append("/videos.html")
