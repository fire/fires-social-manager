#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright (c) 2026 K. S. Ernest (iFire) Lee and fires-social-manager contributors
"""G4 - the social manager is generic for all people.

G0 and this gate look at some of the same bytes for different reasons. G0
asks "is a real person's data in the repository". G4 asks "would this code
work for somebody who is not the author". A hardcoded id fails G4 even when
it belongs to nobody, because the defect is the assumption, not the leak.

VRCX puts the account's own VRChat id in its TABLE NAMES
(usr65de0001..._feed_gps). Every observer is therefore discovered at runtime,
and anything that shortcuts that discovery is what this gate exists to catch.

Exit 0 clean, 1 on any finding, 2 on a precondition error.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

RESERVED = re.compile(r"(usr|wrld|wld|avtr|grp)_0{8}-0{4}-0{4}-0{4}-0{12}", re.I)

# Where a rule is legitimately allowed to live, because that module is the one
# whose job is to know about the source format.
# A rule that forbids a literal string has to spell that string out, so these
# two necessarily appear in this file and in the pre-commit config. They are
# rule text, not personal data -- G0 does not look for them at all, and the
# fixture directory is skipped by both gates. The scope is a tuple of prefixes
# where each rule is allowed to be quiet.
SCOPED = {
    "vrcx-config-key": ("6-datasource/vrcx/", "gates/", ".pre-commit-config.yaml"),
    "vrcx-default-path": ("6-datasource/vrcx/", "gates/", ".pre-commit-config.yaml"),
}

CHECKS = [
    # A VRChat identifier written into source is a single-account assumption.
    ("hardcoded-vrchat-id",
     re.compile(r"\b(?:usr|wrld|wld|avtr|grp)_" + UUID)),
    # The dash-stripped form is worse: it is half of a table name.
    ("hardcoded-table-prefix",
     re.compile(r"\busr[0-9a-f]{32}\b", re.I)),
    # A per-user table name spelled out rather than composed from a discovered
    # prefix.
    ("hardcoded-table-name",
     re.compile(r"\busr[0-9a-f]{32}_[a-z_]+", re.I)),
    # Someone's home directory is not a configuration value.
    ("hardcoded-home-path",
     re.compile(r"(?:/Users/|/home/|C:\\\\Users\\\\)[A-Za-z0-9._-]+/")),
    # lastuserloggedin names ONE user, so using it to attribute the machine
    # wide gamelog_* tables is hardcoding by inference. Allowed only in the
    # datasource, which reads it as data.
    ("vrcx-config-key",
     re.compile(r"lastuserloggedin", re.I)),
    # The VRCX install location is discovered from the OS, never spelled out.
    ("vrcx-default-path",
     re.compile(r"Library/Application Support/VRCX|AppData\\\\Roaming\\\\VRCX|\.local/share/VRCX")),
]

SKIP_SUFFIXES = (".woff2", ".woff", ".ttf", ".otf", ".png", ".jpg", ".jpeg",
                 ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz", ".tar",
                 ".sqlite3", ".db")

# Prose may name an id to explain a decision; code may not. RFDs and the plan
# live in 2-contract and are documentation, not behaviour.
DOC_PREFIXES = ("2-contract/", "docs/")
DOC_SUFFIXES = (".md",)

ALLOWLIST_NAME = "gates/allowed_ids.txt"


def tracked_files(root):
    out = subprocess.run(["git", "-C", root, "ls-files", "-z"],
                         capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\0") if p]


def load_allowlist(root):
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
                bad.append((ALLOWLIST_NAME, lineno,
                            "allowlist-entry-without-reason", line))
                continue
            allowed.add(line.split("# reason:")[0].strip())
    return allowed, bad


def is_doc(rel):
    return rel.startswith(DOC_PREFIXES) or rel.endswith(DOC_SUFFIXES)


def scan(root, paths, allowed):
    findings = []
    for rel in paths:
        if rel == ALLOWLIST_NAME or rel.startswith("gates/fixtures/"):
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
        doc = is_doc(rel)
        for lineno, line in enumerate(text.splitlines(), 1):
            for code, rx in CHECKS:
                scope = SCOPED.get(code)
                if scope and rel.startswith(tuple(scope)):
                    continue
                for m in rx.finditer(line):
                    hit = m.group(0)
                    if RESERVED.search(hit) or hit in allowed:
                        continue
                    # Documentation may cite an identifier to explain itself.
                    # Code may not. G0 still forbids a real one either way.
                    if doc and code in ("hardcoded-vrchat-id",
                                        "hardcoded-table-prefix",
                                        "hardcoded-table-name",
                                        "vrcx-default-path",
                                        "vrcx-config-key"):
                        continue
                    findings.append((rel, lineno, code, hit))
    return findings


FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "g4")

# Control inputs live in gates/fixtures/, not in this file -- see the note in
# check_no_personal_data.py. Every fixture identifier is synthetic.
DEFECT_FILES = {
    "hardcoded-vrchat-id": "hardcoded-vrchat-id.ex",
    "hardcoded-table-prefix": "hardcoded-table-prefix.ex",
    "hardcoded-table-name": "hardcoded-table-name.ex",
    "hardcoded-home-path": "hardcoded-home-path.ex",
    "vrcx-config-key": "vrcx-config-key.ex",
    "vrcx-default-path": "vrcx-default-path.ex",
}
CLEAN_FILE = "clean.ex"


def _fixture(name):
    path = os.path.join(FIXTURES, name)
    if not os.path.exists(path):
        raise SystemExit("G4 FAIL: control fixture %s is missing. A control "
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
    failures = _controls_are_tracked(
        "G4", FIXTURES, list(DEFECT_FILES.values()) + [CLEAN_FILE])
    tmp = tempfile.mkdtemp(prefix="g4-selftest-")
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
        found = scan(tmp, paths, allowed) + bad
        got = {c for (_f, _l, c, _h) in found}
        want = set(DEFECT_FILES)
        for missing in sorted(want - got):
            failures.append("control NOT caught: %s" % missing)
        for extra in sorted(got - want):
            failures.append("unexpected finding on control input: %s" % extra)
        for (f, _l, c, _h) in found:
            if f == CLEAN_FILE:
                failures.append("false positive on clean input: %s" % c)

        # The scoped rules must go quiet inside the datasource, and only there.
        sub = os.path.join(tmp, "6-datasource", "vrcx")
        os.makedirs(sub, exist_ok=True)
        with open(os.path.join(sub, "configs.ex"), "w", encoding="utf-8") as fh:
            fh.write(_fixture("vrcx-config-key.ex"))
        other = os.path.join(tmp, "3-interactor", "normalize")
        os.makedirs(other, exist_ok=True)
        with open(os.path.join(other, "leak.ex"), "w", encoding="utf-8") as fh:
            fh.write(_fixture("vrcx-config-key.ex"))
        subprocess.run(["git", "-C", tmp, "add", "-A"], check=True)
        found2 = scan(tmp, tracked_files(tmp), allowed)
        scoped_hits = {f for (f, _l, c, _h) in found2 if c == "vrcx-config-key"}
        if any(h.startswith("6-datasource/vrcx/") for h in scoped_hits):
            failures.append("scoped rule fired inside its own scope")
        if any(h.startswith("gates/") for h in scoped_hits):
            failures.append("scoped rule fired inside gates/, where rules live")
        if not any(h.startswith("3-interactor/") for h in scoped_hits):
            failures.append("scoped rule did NOT fire outside its scope")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print("G4 SELF-TEST FAIL")
        for f in failures:
            print("  " + f)
        return 1
    print("G4 self-test PASS (%d controls + 2 scope controls)" % len(DEFECT_FILES))
    return 0


def main():
    ap = argparse.ArgumentParser(description="G4: no hardcoded identities")
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()

    root = os.path.abspath(args.root)
    if not os.path.isdir(os.path.join(root, ".git")):
        print("G4 FAIL: %s is not a git repository." % root)
        return 2
    paths = tracked_files(root)
    allowed, findings = load_allowlist(root)
    findings = findings + scan(root, paths, allowed)
    print("G4  tracked files: %d" % len(paths))
    if findings:
        print("\nG4 FAIL: %d finding(s)" % len(findings))
        for f in sorted(findings):
            print("  %s:%s  %s  %s" % f)
        return 1
    print("\nG4 PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
