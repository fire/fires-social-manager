#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright (c) 2026 K. S. Ernest (iFire) Lee and fires-social-manager contributors
#
# Runs every gate. The negative controls run FIRST and unconditionally: if a
# gate cannot fail on input that is known to be broken, then it passing on real
# input means nothing, and every result after it is decoration.
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/.." && pwd)"
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
  [ $rc -eq 0 ] && echo "=== all self-tests PASS ===" || echo "=== SELF-TESTS FAILED ==="
  exit $rc
fi

if [ $rc -ne 0 ]; then
  echo "=== refusing to report gate results while a control is broken ==="
  exit 1
fi

echo
echo "=== gates ==="
# bash 3.2 (the macOS default) errors on an empty array under `set -u`, so
# build the optional argument as two plain scalars instead.
store_flag=""; store_val=""
if [ -n "${FSM_STORE:-}" ]; then store_flag="--store"; store_val="$FSM_STORE"; fi
if [ -n "$store_flag" ]; then
  "$py" "$here/check_no_personal_data.py" "$root" "$store_flag" "$store_val" || rc=1
else
  "$py" "$here/check_no_personal_data.py" "$root" || rc=1
fi
echo
"$py" "$here/check_no_hardcoded_ids.py" "$root" || rc=1
echo
"$py" "$here/check_license.py" "$root" || rc=1

echo
[ $rc -eq 0 ] && echo "=== ALL GATES PASS ===" || echo "=== GATES FAILED ==="
exit $rc
