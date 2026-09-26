"""The build()-to-page glue from slice 4: the _UNSET sentinel a page
function's unpassed inputs default to, and _bound (the names build()
actually bound). ONE _UNSET for the whole build - test_build_split pins it.

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""


# ---- slice 4: build()'s page sections as functions (tools/extract_sections.py) ----
_UNSET = object()      # 'this build() variable was not bound at the call'
def _bound(scope, names):
    return {k: scope[k] for k in names if k in scope}
