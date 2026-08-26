#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright (c) 2026 K. S. Ernest (iFire) Lee and fires-social-manager contributors
"""G7 - dual licensing means the reader chooses.

Two files, not one. A single LICENSE cannot offer a choice, so a project that
ships one has not dual licensed anything; it has picked for you. This gate
asserts both files exist, that each is the licence it claims to be, and that
every source file says which pair it is offered under.

The licence texts are compared by digest with the copyright line normalized
out, so re-attributing a file is not mistaken for relicensing it, while
swapping the text for GPL is caught immediately.

Exit 0 clean, 1 on any finding, 2 on a precondition error.
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile

APACHE_DIGEST = "172b0fe5b69f0d23947310c4878fbe10b04f1539eb2450b5dc5e7b4dee649e0a"
MIT_DIGEST = "7c9b48b52decb9837c70f608678129e1ac79e056829c8d1e82e8cdd8aed562f8"

SPDX = "SPDX-License-Identifier: Apache-2.0 OR MIT"
SPDX_LINES = 3  # must appear in the first three lines, where a reader looks

SOURCE_SUFFIXES = (".ex", ".exs", ".py", ".heex", ".js", ".css", ".sh", ".zig")

# Generated, vendored, or format-bound files that cannot carry a comment.
EXEMPT_NAMES = ("mix.lock", "package-lock.json", ".formatter.exs")


def normalized_digest(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        lines = [ln for ln in fh if not ln.lower().lstrip().startswith("copyright (c)")]
    text = " ".join(" ".join(lines).split())
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def tracked_files(root):
    out = subprocess.run(["git", "-C", root, "ls-files", "-z"],
                         capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\0") if p]


def mix_projects(root, paths):
    """Every directory holding a mix.exs is a project and needs its own pair."""
    return sorted({os.path.dirname(p) for p in paths if os.path.basename(p) == "mix.exs"})


def check_pair(root, rel_dir, findings):
    where = os.path.join(root, rel_dir) if rel_dir else root
    label = rel_dir or "."
    apache = os.path.join(where, "LICENSE-APACHE")
    mit = os.path.join(where, "LICENSE-MIT")
    single = os.path.join(where, "LICENSE")

    if not os.path.exists(apache) or not os.path.exists(mit):
        if os.path.exists(single):
            findings.append((label, "dual-license-needs-two-files",
                             "found LICENSE but not LICENSE-APACHE + LICENSE-MIT"))
        else:
            missing = [n for n, p in (("LICENSE-APACHE", apache), ("LICENSE-MIT", mit))
                       if not os.path.exists(p)]
            findings.append((label, "license-file-missing", ", ".join(missing)))
        return

    for name, path, want in (("LICENSE-APACHE", apache, APACHE_DIGEST),
                             ("LICENSE-MIT", mit, MIT_DIGEST)):
        got = normalized_digest(path)
        if got != want:
            findings.append((os.path.join(label, name), "license-text-altered",
                             "digest %s, expected %s" % (got[:12], want[:12])))


def check_spdx(root, paths, findings):
    for rel in paths:
        if not rel.endswith(SOURCE_SUFFIXES):
            continue
        if os.path.basename(rel) in EXEMPT_NAMES:
            continue
        if rel.startswith("gates/fixtures/"):
            continue
        full = os.path.join(root, rel)
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as fh:
                head = [next(fh, "") for _ in range(SPDX_LINES)]
        except OSError:
            continue
        if not any(SPDX in ln for ln in head):
            findings.append((rel, "spdx-header-missing",
                             "first %d lines lack %r" % (SPDX_LINES, SPDX)))


def check_citation(root, findings):
    """CITATION.cff must exist somewhere and offer both licences.

    Parsed without PyYAML: the fields we require are flat scalars and a short
    inline or block sequence, so a regex over the text is enough and keeps the
    gate stdlib-only.
    """
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "_build", "deps", "node_modules")]
        if "CITATION.cff" in filenames:
            hits.append(os.path.join(dirpath, "CITATION.cff"))
    if not hits:
        findings.append(("CITATION.cff", "citation-missing",
                         "no CITATION.cff anywhere in the tree"))
        return
    for path in hits:
        rel = os.path.relpath(path, root)
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        if not re.search(r"^cff-version:\s*1\.2\.0\s*$", text, re.M):
            findings.append((rel, "citation-version", "cff-version must be 1.2.0"))
        licenses = parse_license_field(text)
        if licenses is None:
            findings.append((rel, "citation-license-missing", "no license: field"))
        elif not ({"Apache-2.0", "MIT"} <= licenses):
            findings.append((rel, "citation-license-not-dual",
                             "license must offer Apache-2.0 and MIT, got %s"
                             % (sorted(licenses) or "nothing")))


def parse_license_field(text):
    r"""Read `license:` as either an inline flow sequence or a block sequence.

    `\s*` in a multiline regex crosses newlines, so a naive
    `^license:\s*(.+)$` silently reads only the first item of

        license:
          - Apache-2.0
          - MIT

    and a gate that sees one of two licences and reports the pair as broken is
    worse than no gate. Walk the lines instead.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("license:"):
            continue
        rest = line[len("license:"):].strip()
        if rest:
            # Inline: `license: MIT` or `license: [Apache-2.0, MIT]`
            return {t.strip().strip("'\"")
                    for t in rest.strip("[]").split(",") if t.strip()}
        # Block sequence: subsequent indented `- ` entries.
        out = set()
        for nxt in lines[i + 1:]:
            if not nxt.strip():
                continue
            if not nxt.startswith((" ", "\t")):
                break
            item = nxt.strip()
            if not item.startswith("- "):
                break
            out.add(item[2:].strip().strip("'\""))
        return out
    return None


GPL_SNIPPET = ("GNU GENERAL PUBLIC LICENSE\n Version 3, 29 June 2007\n"
               "Everyone is permitted to copy and distribute verbatim copies.\n")


def self_test():
    tmp = tempfile.mkdtemp(prefix="g7-selftest-")
    failures = []
    here = os.path.dirname(os.path.abspath(__file__))
    real_root = os.path.dirname(here)
    try:
        # Control 1: a single LICENSE is not dual licensing.
        one = os.path.join(tmp, "single")
        os.makedirs(one)
        with open(os.path.join(one, "LICENSE"), "w") as fh:
            fh.write("MIT License\n")
        f1 = []
        check_pair(one, "", f1)
        if not any(c == "dual-license-needs-two-files" for (_p, c, _d) in f1):
            failures.append("control NOT caught: dual-license-needs-two-files")

        # Control 2: swapping the text for GPL must be caught.
        two = os.path.join(tmp, "gpl")
        os.makedirs(two)
        shutil.copy(os.path.join(real_root, "LICENSE-MIT"),
                    os.path.join(two, "LICENSE-MIT"))
        with open(os.path.join(two, "LICENSE-APACHE"), "w") as fh:
            fh.write(GPL_SNIPPET)
        f2 = []
        check_pair(two, "", f2)
        if not any(c == "license-text-altered" for (_p, c, _d) in f2):
            failures.append("control NOT caught: license-text-altered")

        # Control 3: re-attributing the copyright must NOT be caught.
        three = os.path.join(tmp, "reattributed")
        os.makedirs(three)
        shutil.copy(os.path.join(real_root, "LICENSE-APACHE"),
                    os.path.join(three, "LICENSE-APACHE"))
        with open(os.path.join(real_root, "LICENSE-MIT")) as src, \
                open(os.path.join(three, "LICENSE-MIT"), "w") as dst:
            for ln in src:
                dst.write("Copyright (c) 2099 Somebody Else\n"
                          if ln.lower().startswith("copyright (c)") else ln)
        f3 = []
        check_pair(three, "", f3)
        if f3:
            failures.append("false positive: re-attribution read as relicensing (%s)"
                            % f3[0][1])

        # Control 4: a source file with no SPDX header must be caught, and one
        # with it must not.
        four = os.path.join(tmp, "spdx")
        os.makedirs(four)
        subprocess.run(["git", "-C", four, "init", "-q"], check=True)
        with open(os.path.join(four, "bad.ex"), "w") as fh:
            fh.write("defmodule Bad do\nend\n")
        with open(os.path.join(four, "good.ex"), "w") as fh:
            fh.write("# %s\ndefmodule Good do\nend\n" % SPDX)
        subprocess.run(["git", "-C", four, "add", "-A"], check=True)
        f4 = []
        check_spdx(four, tracked_files(four), f4)
        codes = {p for (p, c, _d) in f4 if c == "spdx-header-missing"}
        if "bad.ex" not in codes:
            failures.append("control NOT caught: spdx-header-missing")
        if "good.ex" in codes:
            failures.append("false positive: spdx header present but reported")

        # Control 5a: the block-sequence form must be read WHOLE. This is the
        # shape the real file uses, and the regex it replaces read only its
        # first item -- a control that missed it would have certified the bug.
        block = "cff-version: 1.2.0\nlicense:\n  - Apache-2.0\n  - MIT\n"
        if parse_license_field(block) != {"Apache-2.0", "MIT"}:
            failures.append("block-sequence license read as %r, expected both"
                            % (parse_license_field(block),))
        if parse_license_field("cff-version: 1.2.0\nlicense: [Apache-2.0, MIT]\n") \
                != {"Apache-2.0", "MIT"}:
            failures.append("inline-sequence license not read as both")
        if parse_license_field("cff-version: 1.2.0\n") is not None:
            failures.append("absent license field did not read as absent")

        # Control 5: a CITATION.cff offering only one licence must be caught.
        five = os.path.join(tmp, "cff")
        os.makedirs(five)
        with open(os.path.join(five, "CITATION.cff"), "w") as fh:
            fh.write("cff-version: 1.2.0\nlicense:\n  - Apache-2.0\n")
        f5 = []
        check_citation(five, f5)
        if not any(c == "citation-license-not-dual" for (_p, c, _d) in f5):
            failures.append("control NOT caught: citation-license-not-dual")

        # And a missing CITATION.cff entirely.
        six = os.path.join(tmp, "nocff")
        os.makedirs(six)
        f6 = []
        check_citation(six, f6)
        if not any(c == "citation-missing" for (_p, c, _d) in f6):
            failures.append("control NOT caught: citation-missing")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print("G7 SELF-TEST FAIL")
        for f in failures:
            print("  " + f)
        return 1
    print("G7 self-test PASS (4 must-fail + 2 must-not-fail + 3 parse controls)")
    return 0


def main():
    ap = argparse.ArgumentParser(description="G7: dual Apache-2.0 OR MIT, in two files")
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--no-citation", action="store_true",
                    help="the manifest repo links CITATION.cff from 2-contract")
    args = ap.parse_args()
    if args.self_test:
        return self_test()

    root = os.path.abspath(args.root)
    if not os.path.isdir(os.path.join(root, ".git")):
        print("G7 FAIL: %s is not a git repository." % root)
        return 2

    paths = tracked_files(root)
    findings = []
    check_pair(root, "", findings)
    for proj in mix_projects(root, paths):
        check_pair(root, proj, findings)
    check_spdx(root, paths, findings)
    if not args.no_citation:
        check_citation(root, findings)

    print("G7  tracked files: %d, mix projects: %d"
          % (len(paths), len(mix_projects(root, paths))))
    if findings:
        print("\nG7 FAIL: %d finding(s)" % len(findings))
        for f in sorted(findings):
            print("  %s  %s  %s" % f)
        return 1
    print("\nG7 PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
