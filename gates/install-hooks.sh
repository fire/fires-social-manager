#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright (c) 2026 K. S. Ernest (iFire) Lee and fires-social-manager contributors
#
# Arms the pre-push data gate on EVERY repository, not only the one holding the
# gates.
#
# Run it from anywhere inside a synced workspace and it walks every project the
# manifest placed. Run it inside a bare clone of the manifest repository and it
# arms that one. Ten of the eleven repositories hold no gates of their own, and
# two of them are the ones that touch the VRCX database, so arming only the
# manifest repository would leave the data unguarded exactly where it lives.
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
manifest_root="$(cd "$here/.." && pwd)"
hook="$manifest_root/hooks/pre-push"

[ -x "$hook" ] || { echo "no hook at $hook"; exit 1; }

arm() { # repo_worktree
  local wt="$1" gd
  gd="$(cd "$wt" && git rev-parse --absolute-git-dir 2>/dev/null)" || return 1
  mkdir -p "$gd/hooks"
  # Copy rather than symlink: a repo-managed .git is itself a symlink into
  # .repo/projects, and a relative link out of it does not resolve.
  cp "$hook" "$gd/hooks/pre-push"
  chmod +x "$gd/hooks/pre-push"
  printf "  armed  %s\n" "$wt"
}

# Find the workspace, if we are in one.
ws=""
d="$PWD"
while [ "$d" != "/" ]; do
  [ -d "$d/.repo" ] && { ws="$d"; break; }
  d="$(dirname "$d")"
done
if [ -z "$ws" ] && [ -d "$manifest_root/../.repo" ]; then
  ws="$(cd "$manifest_root/../.." && pwd)"
fi

n=0
if [ -n "$ws" ]; then
  echo "workspace: $ws"
  for wt in "$ws"/[1-7]-*/*/; do
    [ -e "$wt/.git" ] || continue
    arm "${wt%/}" && n=$((n+1))
  done
  # The manifest checkout inside .repo is a repository too.
  [ -d "$ws/.repo/manifests" ] && { arm "$ws/.repo/manifests" && n=$((n+1)); }
else
  echo "no workspace found; arming this repository only"
fi

# And the manifest working copy this script lives in.
arm "$manifest_root" && n=$((n+1))

echo
echo "armed $n repositor$([ "$n" = 1 ] && echo y || echo ies)"
echo
"$here/all.sh" --self-test
