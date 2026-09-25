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
pre-built pieces). html.escape (the site's esc()) and markupsafe differ only
in how they write a quote (&#x27; vs &#39;) - both are the same character to
every browser.
"""
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


_env = Environment(
    loader=_JoinedLinesLoader(TEMPLATES, encoding="utf-8"),
    autoescape=True,
    # a missing variable is a bug in the page function, not an empty string on
    # the live site
    undefined=StrictUndefined,
    keep_trailing_newline=False,
)


def render(name, **ctx):
    """Render site_src/templates/<name> with ctx."""
    return _env.get_template(name).render(**ctx)
