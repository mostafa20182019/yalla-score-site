# -*- coding: utf-8 -*-
"""Every workflow parses the way GitHub parses it (2026-10-22): a second
`env:` on one step made daily-article.yml invalid, GitHub dropped the whole
workflow, and four hours of article slots - and so of Facebook posts - went
by with nothing but a red "workflow file" run on each push. PyYAML keeps the
last of two duplicate keys silently; GitHub refuses the file. This loader
refuses it too.

    python tests/test_workflow_yaml.py     (from the repo root)
"""
import glob, os, sys
import yaml
sys.stdout.reconfigure(encoding="utf-8")


class Strict(yaml.SafeLoader):
    pass


def _no_dup(loader, node, deep=False):
    keys = [loader.construct_object(k, deep=deep) for k, _ in node.value]
    dup = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dup:
        raise ValueError(f"duplicate key(s) {dup} at line {node.start_mark.line + 1}")
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


Strict.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_dup)
fails = []
for f in sorted(glob.glob(os.path.join(".github", "workflows", "*.yml"))):
    try:
        y = yaml.load(open(f, encoding="utf-8"), Loader=Strict)
        inputs = (((y.get(True) or y.get("on") or {}) or {}).get("workflow_dispatch") or {}).get("inputs") or {}
        assert len(inputs) <= 10, f"{len(inputs)} workflow_dispatch inputs (GitHub allows 10)"
        print("  ok  ", f)
    except Exception as e:                      # noqa: BLE001
        print("  FAIL", f, "-", e)
        fails.append(f)
print()
print("ALL WORKFLOWS PARSE" if not fails else f"{len(fails)} BROKEN: " + ", ".join(fails))
sys.exit(1 if fails else 0)
