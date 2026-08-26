#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0 OR MIT
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
ln -sf ../../hooks/pre-push "$root/.git/hooks/pre-push"
echo "installed: .git/hooks/pre-push -> hooks/pre-push"
"$root/gates/all.sh" --self-test
