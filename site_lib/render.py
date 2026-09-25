"""Jinja2 page templates (2026-09-25, the templating step of the build_site split).

Templates live in site_src/templates/. A page function prepares its data in
Python and calls render("privacy.html", ...) - the HTML itself is no longer a
chain of strings appended in Python.

THE ONE RULE OF THESE TEMPLATES: the template's own lines are joined with NO
separator. The site has always shipped each page body as one long line (the
Python built it with "".join(parts)), and a template written one-tag-per-line
must produce the same bytes. So the LOADER strips every line of the template
source and joins them with "" before Jinja compiles it. That keeps templates
readable and the output identical - as long as a line is NEVER broken in the
middle of text (the break would silently delete the space the reader needs).
Break between tags, or between a tag and its text, never inside a sentence.

It is the SOURCE that is joined, not the output: values put into the page
(head(), foot(), anything with its own line breaks) arrive untouched. The
first version joined the rendered output and flattened head()'s own newlines -
caught by a byte comparison of one page before anything shipped.

Autoescape is ON: a value passed in is escaped unless it is already HTML, in
which case the caller wraps it with Markup() (head(), foot() and similar
pre-built pieces). The escaping is the site's own - html.escape, what esc()
has always done - through `finalize`, not markupsafe's: the two write quotes
differently (&quot; vs &#34;), and article titles do contain quotes. Same
safety, same bytes. None prints as nothing, like esc(None).
"""
import html
import os

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup  # noqa: F401  (re-exported for page functions)

TEMPLATES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "site_src", "templates")


class _JoinedLinesLoader(FileSystemLoader):
    """FileSystemLoader that joins each template's stripped source lines."""

    def get_source(self, environment, template):
        src, filename, uptodate = super().get_source(environment, template)
        return "".join(line.strip() for line in src.splitlines()), filename, uptodate


def _finalize(value):
    if value is None:
        return ""
    if hasattr(value, "__html__"):
        return value
    return Markup(html.escape(str(value), quote=True))


_env = Environment(
    loader=_JoinedLinesLoader(TEMPLATES, encoding="utf-8"),
    autoescape=True,
    finalize=_finalize,
    # a missing variable is a bug in the page function, not an empty string on
    # the live site
    undefined=StrictUndefined,
    keep_trailing_newline=False,
)


def render(template, /, **ctx):
    """Render site_src/templates/<template> with ctx. The template name is
    positional-only so a page may pass a variable of ANY name - the club page
    passes `name` (the club), which collided with this argument when it was
    called `name` (caught before shipping, 2026-09-26)."""
    return _env.get_template(template).render(**ctx)
