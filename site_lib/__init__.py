"""Pieces of build_site.py, split out one slice at a time (2026-09-25 on).

Every slice is proven byte-identical with tools/repro_build.py before it
ships. build_site re-imports what moved under the same names, so callers
(`import build_site as b; b.AR_TEAM`) do not change."""
