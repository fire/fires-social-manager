#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright (c) 2026 K. S. Ernest (iFire) Lee and fires-social-manager contributors
"""G0 - no personal data leaves this machine.

The repositories are public. The VRCX-derived store is not, and it holds real
people's names, bios, movements and social graph. This gate is the boundary,
and it runs on pre-commit AND pre-push, because pre-push is the last moment
before bytes leave the disk.

Two groups of check:

  A. Structural. Always runs. VRChat identifiers, avatar/image URLs, absolute
     home paths, and data files under version control.
  B. Store-derived. Runs only when a normalized store is passed with --store.
     Greps tracked files for display names, bios and memo text taken from that
     store. CI has no store, so this group is NOT APPLICABLE there rather than
     skipped -- an inapplicable check and a skipped check are different things,
     and only the second one is a lie.

Exit 0 clean, 1 on any finding, 2 on a usage or precondition error. A
precondition that cannot be met is a FAIL, never a pass.
"""

import argparse
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile

# --- Structural patterns -------------------------------------------------

UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

# A reserved, all-zero namespace is what synthetic fixtures use. It is not a
# person, so it is not a leak, and G0 must not cry wolf about it.
RESERVED = re.compile(r"(usr|wrld|wld|avtr|grp)_0{8}-0{4}-0{4}-0{4}-0{12}", re.I)

CHECKS = [
    ("vrchat-user-id", re.compile(r"\busr_" + UUID)),
    ("vrchat-entity-id", re.compile(r"\b(?:wrld|wld|avtr|grp|file|prop)_" + UUID)),
    ("vrcx-table-prefix", re.compile(r"\busr[0-9a-f]{32}\b", re.I)),
    ("vrchat-asset-url", re.compile(r"https?://[\w.-]*vrchat(?:\.cloud|\.com)/\S+", re.I)),
    ("absolute-home-path", re.compile(r"(?:/Users/|/home/|C:\\\\Users\\\\)[A-Za-z0-9._-]+/")),
]

DATA_SUFFIXES = (
    ".sqlite3", ".sqlite", ".db", ".db3", ".sqlite3-wal", ".sqlite3-shm",
    ".csv", ".jsonl", ".ndjson", ".parquet", ".7z",
)

# Binary and vendored things a text scan should not walk into.
SKIP_SUFFIXES = (".woff2", ".woff", ".ttf", ".otf", ".png", ".jpg", ".jpeg",
                 ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz", ".tar")

ALLOWLIST_NAME = "gates/allowed_ids.txt"


def tracked_files(root):
    out = subprocess.run(
        ["git", "-C", root, "ls-files", "-z"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [p for p in out.split("\0") if p]


def load_allowlist(root):
    """Every allowlist entry must carry a trailing '# reason:' comment.

    An allowlist without reasons becomes a place to hide things, so an entry
    that does not say why is itself a finding.
    """
    path = os.path.join(root, ALLOWLIST_NAME)
    allowed, bad = set(), []
    if not os.path.exists(path):
        return allowed, bad
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "# reason:" not in line:
                bad.append((ALLOWLIST_NAME, lineno, "allowlist-entry-without-reason", line))
                continue
            allowed.add(line.split("# reason:")[0].strip())
    return allowed, bad


def scan_structural(root, paths, allowed):
    findings = []
    for rel in paths:
        if rel == ALLOWLIST_NAME or rel.startswith("gates/fixtures/"):
            continue
        if rel.endswith(DATA_SUFFIXES):
            findings.append((rel, 0, "data-file-tracked", rel))
            continue
        if rel.endswith(SKIP_SUFFIXES):
            continue
        full = os.path.join(root, rel)
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except (OSError, IsADirectoryError):
            continue
        if "\0" in text[:4096]:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for code, rx in CHECKS:
                for m in rx.finditer(line):
                    hit = m.group(0)
                    if RESERVED.search(hit) or hit in allowed:
                        continue
                    findings.append((rel, lineno, code, hit))
    return findings


# --- Store-derived checks ------------------------------------------------

MIN_TERM = 5  # shorter strings collide with ordinary English and prose


def store_terms(store_path, limit=20000):
    """Pull the things that identify a person out of a normalized store.

    Reads only; opens immutable so a live store is never disturbed.
    """
    uri = "file:%s?immutable=1" % store_path.replace("?", "%3f")
    con = sqlite3.connect(uri, uri=True)
    try:
        have = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        terms = set()
        # text_value is where every interned human string lands. If the store
        # is encrypted the column holds ciphertext, and scanning it is
        # harmless -- ciphertext will not appear in a source file either.
        for table, col in (("text_value", "value"),
                           ("display_names", "text"),
                           ("bios", "text")):
            if table not in have:
                continue
            try:
                rows = con.execute(
                    "SELECT DISTINCT %s FROM %s LIMIT ?" % (col, table), (limit,))
            except sqlite3.Error:
                continue
            for (v,) in rows:
                if isinstance(v, str) and len(v.strip()) >= MIN_TERM:
                    terms.add(v.strip())
        return terms
    finally:
        con.close()


def scan_store(root, paths, terms):
    findings = []
    if not terms:
        return findings
    for rel in paths:
        if rel.startswith("gates/fixtures/") or rel.endswith(SKIP_SUFFIXES):
            continue
        full = os.path.join(root, rel)
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        for term in terms:
            idx = text.find(term)
            if idx != -1:
                lineno = text.count("\n", 0, idx) + 1
                findings.append((rel, lineno, "store-term-in-source", term[:40]))
    return findings


# --- Negative controls ---------------------------------------------------

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "g0")

# The control inputs live in gates/fixtures/, not in this file. A gate that
# spells out what it forbids trips itself, and exempting the gate's own source
# would be a hole big enough to hide a real identifier in. Every fixture
# identifier is synthetic, so the fixtures are safe to publish.
DEFECT_FILES = {
    "vrchat-user-id": "vrchat-user-id.ex",
    "vrchat-entity-id": "vrchat-entity-id.ex",
    "vrcx-table-prefix": "vrcx-table-prefix.ex",
    "vrchat-asset-url": "vrchat-asset-url.ex",
    "absolute-home-path": "absolute-home-path.ex",
    "data-file-tracked": "data-file-tracked.jsonl",
}
CLEAN_FILE = "clean.ex"


def _fixture(name):
    path = os.path.join(FIXTURES, name)
    if not os.path.exists(path):
        raise SystemExit("G0 FAIL: control fixture %s is missing. A control "
                         "that cannot run is a FAIL, not a skip." % path)
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _controls_are_tracked(gate, fixtures_dir, names):
    """A control fixture that git does not track is not a control.

    It passes on the machine that wrote it and fails on every fresh clone.
    That is exactly how this check came to exist: `.gitignore` matched
    `*.jsonl`, the data-file control was never committed, the self-test read
    it off local disk and reported PASS, and CI -- with only tracked files --
    could not run it at all.
    """
    repo = os.path.dirname(fixtures_dir)
    try:
        out = subprocess.run(["git", "-C", repo, "ls-files", "-z", fixtures_dir],
                             capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        # No git here at all. Genuinely inapplicable, and said out loud
        # rather than passed over.
        print("%s  control-tracking: NOT APPLICABLE (no git repository)" % gate)
        return []
    tracked = {os.path.basename(p) for p in out.split("\0") if p}
    return ["control fixture not tracked by git: %s" % n
            for n in sorted(names) if n not in tracked]


def self_test():
    """Assert EXACTLY the planted defects are found, and nothing on clean input.

    'At least one finding' would pass for a gate that reports everything, so
    the count is checked both ways.
    """
    failures = _controls_are_tracked(
        "G0", FIXTURES, list(DEFECT_FILES.values()) + [CLEAN_FILE])
    tmp = tempfile.mkdtemp(prefix="g0-selftest-")
    try:
        subprocess.run(["git", "-C", tmp, "init", "-q"], check=True)
        for _code, name in DEFECT_FILES.items():
            with open(os.path.join(tmp, name), "w", encoding="utf-8") as fh:
                fh.write(_fixture(name))
        with open(os.path.join(tmp, CLEAN_FILE), "w", encoding="utf-8") as fh:
            fh.write(_fixture(CLEAN_FILE))
        subprocess.run(["git", "-C", tmp, "add", "-A"], check=True)

        paths = tracked_files(tmp)
        allowed, bad = load_allowlist(tmp)
        found = scan_structural(tmp, paths, allowed) + bad

        got = {code for (_f, _l, code, _h) in found}
        want = set(DEFECT_FILES)
        for missing in sorted(want - got):
            failures.append("control NOT caught: %s" % missing)
        for extra in sorted(got - want):
            failures.append("unexpected finding on control input: %s" % extra)
        for (f, _l, code, _h) in found:
            if f == CLEAN_FILE:
                failures.append("false positive on clean input: %s" % code)

        # An allowlist entry without a reason must itself be a finding.
        os.makedirs(os.path.join(tmp, "gates"), exist_ok=True)
        synthetic = CHECKS[0][1].search(_fixture("vrchat-user-id.ex")).group(0)
        with open(os.path.join(tmp, ALLOWLIST_NAME), "w", encoding="utf-8") as fh:
            fh.write(synthetic + "\n")
        _allowed2, bad2 = load_allowlist(tmp)
        if not any(c == "allowlist-entry-without-reason" for (_f, _l, c, _h) in bad2):
            failures.append("control NOT caught: allowlist-entry-without-reason")

        # And with a reason it must suppress that one id and nothing else.
        with open(os.path.join(tmp, ALLOWLIST_NAME), "w", encoding="utf-8") as fh:
            fh.write(synthetic + "  # reason: negative control\n")
        allowed3, bad3 = load_allowlist(tmp)
        found3 = scan_structural(tmp, paths, allowed3) + bad3
        if any(c == "vrchat-user-id" for (_f, _l, c, _h) in found3):
            failures.append("allowlist with a reason failed to suppress its entry")
        if not any(c == "vrchat-entity-id" for (_f, _l, c, _h) in found3):
            failures.append("allowlist suppressed more than its own entry")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print("G0 SELF-TEST FAIL")
        for f in failures:
            print("  " + f)
        return 1
    print("G0 self-test PASS (%d structural controls + 3 allowlist controls)" % len(DEFECT_FILES))
    return 0


def main():
    ap = argparse.ArgumentParser(description="G0: no personal data in the repository")
    ap.add_argument("root", nargs="?", default=".", help="repository root")
    ap.add_argument("--store", help="normalized store to take person-identifying terms from")
    ap.add_argument("--self-test", action="store_true", help="run the negative controls")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    root = os.path.abspath(args.root)
    if not os.path.isdir(os.path.join(root, ".git")):
        print("G0 FAIL: %s is not a git repository; the gate cannot enumerate "
              "tracked files, and an unmet precondition is a FAIL." % root)
        return 2

    paths = tracked_files(root)
    allowed, findings = load_allowlist(root)
    findings = findings + scan_structural(root, paths, allowed)

    if args.store:
        if not os.path.exists(args.store):
            print("G0 FAIL: --store %s does not exist. Asked to run the "
                  "store check, could not; that is a FAIL." % args.store)
            return 2
        findings += scan_store(root, paths, store_terms(args.store))
        group_b = "ran against %s" % args.store
    else:
        group_b = "NOT APPLICABLE (no --store given; CI has no store)"

    print("G0  tracked files: %d" % len(paths))
    print("G0  group A structural: ran")
    print("G0  group B store-derived: %s" % group_b)

    if findings:
        print("\nG0 FAIL: %d finding(s)" % len(findings))
        for (f, lineno, code, hit) in sorted(findings):
            print("  %s:%s  %s  %s" % (f, lineno, code, hit))
        print("\nThe data does not leave this machine. Remove it, or add a")
        print("justified line to %s." % ALLOWLIST_NAME)
        return 1

    print("\nG0 PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
