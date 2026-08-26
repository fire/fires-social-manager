#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright (c) 2026 K. S. Ernest (iFire) Lee and fires-social-manager contributors
#
# Runs every gate against a target repository.
#
# The negative controls run FIRST and unconditionally: if a gate cannot fail on
# input that is known to be broken, then it passing on real input means
# nothing, and every result after it is decoration.
#
#   gates/all.sh --self-test        only the controls
#   gates/all.sh                    controls, then gates, against this repo
#   gates/all.sh /path/to/repo      controls, then gates, against another repo
#
# The target is separate from where the gates live, because the gates live in
# the manifest repository and the other ten repositories are what they have to
# check.
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
py="${PYTHON:-python3}"
rc=0

gates=(check_no_personal_data.py check_no_hardcoded_ids.py check_license.py)

echo "=== negative controls ==="
for g in "${gates[@]}"; do
  if ! "$py" "$here/$g" --self-test; then
    echo "  ^ $g cannot fail on known-broken input; every later result is void."
    rc=1
  fi
done

if [ "${1:-}" = "--self-test" ]; then
  if [ $rc -eq 0 ]; then echo "=== all self-tests PASS ==="; else echo "=== SELF-TESTS FAILED ==="; fi
  exit $rc
fi

if [ $rc -ne 0 ]; then
  echo "=== refusing to report gate results while a control is broken ==="
  exit 1
fi

target="${1:-$(cd "$here/.." && pwd)}"
echo
echo "=== gates: $target ==="

# bash 3.2 (the macOS default) errors on an empty array under `set -u`, so
# build the optional argument as two plain scalars instead.
store_flag=""; store_val=""
if [ -n "${FSM_STORE:-}" ]; then store_flag="--store"; store_val="$FSM_STORE"; fi
if [ -n "$store_flag" ]; then
  "$py" "$here/check_no_personal_data.py" "$target" "$store_flag" "$store_val" || rc=1
else
  "$py" "$here/check_no_personal_data.py" "$target" || rc=1
fi
echo
"$py" "$here/check_no_hardcoded_ids.py" "$target" || rc=1
echo
# Only the manifest repository publishes a CITATION.cff of its own; the other
# ten link it from 2-contract. Ask for it where it belongs and not elsewhere.
if [ -f "$target/CITATION.cff" ] || [ -f "$target/default.xml" ]; then
  "$py" "$here/check_license.py" "$target" || rc=1
else
  "$py" "$here/check_license.py" "$target" --no-citation || rc=1
fi

echo
if [ $rc -eq 0 ]; then echo "=== ALL GATES PASS ==="; else echo "=== GATES FAILED ==="; fi
exit $rc
