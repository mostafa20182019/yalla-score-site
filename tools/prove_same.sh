#!/bin/bash
# prove_same.sh OLD_DIR NEW_DIR - the second half of the refactor proof (the
# first half is tools/repro_build.py run in both). Exits 0 ONLY when both
# builds exist, are full-size, and are byte-identical.
#
# Why the ceremony (2026-09-25): a proof once reported "0 files differ" when
# the NEW build had never run - its worktree did not exist yet, diff printed
# its error to stderr and the counted output was empty. A check that can pass
# without its input is not a check.
O="$1/dist"; N="$2/dist"
for d in "$O" "$N"; do
  [ -f "$d/index.html" ] || { echo "PROOF INVALID: $d/index.html missing"; exit 2; }
done
no=$(find "$O" -type f | wc -l); nn=$(find "$N" -type f | wc -l)
echo "files: old $no, new $nn"
[ "$no" -gt 1000 ] || { echo "PROOF INVALID: the old build is too small to mean anything"; exit 2; }
out=$(mktemp)
if diff -rq "$O" "$N" > "$out" 2>&1; then echo "PROOF OK: 0 files differ"; exit 0; fi
echo "PROOF FAILED: $(wc -l < "$out") difference(s)"; head -20 "$out"; exit 1
