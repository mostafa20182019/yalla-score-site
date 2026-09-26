"""The site's pages, one module per page type (slice 8 of the build_site split,
2026-09-26). build_site.build() calls them in order; each module imports only
from site_lib (never build_site). Proven byte-identical with
tools/repro_build.py + tools/prove_same.sh before it shipped."""
