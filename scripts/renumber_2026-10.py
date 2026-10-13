#!/usr/bin/env python3
"""renumber_2026-10.py -- renumber the India example briefs so the most common building types come first.

Two modes:

  python3 renumber_2026-10.py repos <WS>          # rewrite the four git checkouts under <WS> (git mv + text rewrite)
  python3 renumber_2026-10.py tree <SRC> <DST>    # copy a gold / website tree <SRC> to <DST> with folders renamed
                                                  # and brief ids rewritten inside text files (SRC is never changed)

What is rewritten (both modes):
  * the brief ids IN_ExN (HR) and IN_CFS_ExN (CFS) in file / folder names and in every text file, by HR_MAP / CFS_MAP
    in ONE regex pass (no chained remapping);
  * in `repos` mode only: the reviewed short-form references listed in POST_EDITS (bare 'Ex5' etc. that clearly mean
    an India brief), applied after the token pass, and the same edits on the vendored HR copies;
  * record documents (RECORD_DOCS: changelogs, review / runbook logs) are NOT rewritten; they get a one-line note
    at the top saying they use the pre-2026-10 numbering.

What is NOT rewritten: bare short forms (Ex1, ex1, EX14, ...) outside POST_EDITS -- they are ambiguous with the US
example sets the same engines still carry (HR ex1 ... ex35, CFS ex1 ... ex30) and with internal test-fixture keys.
The example pickers (in1 ... in20) are rebuilt by the patch itself, not by this tool.

`repos` mode refuses to run twice: it stops when steltic_india/test_buildings/RENUMBERING_2026-10.md (the map the
renumbering commit adds) already exists. `tree` mode refuses an existing destination.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# old number -> new number. HR: the five new PEB briefs take 1-5; the 15 existing briefs follow, single-storey
# industrial first, then by height. CFS: portals first, then by storey count.
HR_MAP = {5: 6, 14: 7, 3: 8, 15: 9, 13: 10, 8: 11, 11: 12, 1: 13, 4: 14, 6: 15, 2: 16, 7: 17, 12: 18, 9: 19, 10: 20}
CFS_MAP = {2: 1, 15: 2, 5: 3, 10: 4, 11: 5, 14: 6, 1: 7, 8: 8, 13: 9, 3: 10, 6: 11, 4: 12, 7: 13, 9: 14, 12: 15}
assert sorted(HR_MAP) == list(range(1, 16)) and sorted(HR_MAP.values()) == list(range(6, 21))
assert sorted(CFS_MAP) == list(range(1, 16)) and sorted(CFS_MAP.values()) == list(range(1, 16))

TOKEN = re.compile(r"IN_(CFS_)?Ex(\d+)(?!\d)")
MARKER = "RENUMBERING_2026-10.md"
REPOS = ("steltic_india", "steltic_CFS_india", "steltic_nonlinear_india", "steltic_hub_india")

RECORD_NOTE = ("> **Numbering note (2026-10):** this is a dated record. Example brief numbers in it (IN_ExN, IN_CFS_ExN "
               "and short forms such as Ex9) use the numbering **before** the 2026-10 renumbering. Map: "
               "`steltic_india/test_buildings/RENUMBERING_2026-10.md`.\n\n")

# dated records: left as written, with RECORD_NOTE at the top (repo-relative paths)
RECORD_DOCS = {
    "steltic_india": ["CHANGES_2026-09-review.md", "docs/INDIA_COMPLETE_GAP_WAVE1.md", "docs/INDIA_COMPLETE_GAP_WAVE2.md",
                      "docs/INDIA_COMPLETE_GAP_WAVE3.md", "docs/INDIA_COMPLETE_GAP_WAVE4.md",
                      "docs/INDIA_HR_POLISH_WAVE_D.md"],
    "steltic_CFS_india": ["CHANGES_2026-09-review.md"],
    "steltic_nonlinear_india": ["CHANGES_2026-09-review.md", "docs/NL_REVIEW.md", "docs/NL_RUNBOOK.md",
                                "docs/USA_SYNC_REPORT.md", "docs/DDM_AGENT_SCOPE.md"],
    "steltic_hub_india": [],
}

# HR engine files vendored byte-identically into CFS and NL: an edit to the HR file is repeated on the copies
VENDOR_DIRS = {"steltic_CFS_india": "steel_engine/hr_vendor", "steltic_nonlinear_india": "snl/vendor_steltic_india"}

# reviewed short-form references (applied AFTER the token pass, so the 'old' strings are post-pass text)
POST_EDITS = {
    "steltic_india": {
        "steel_engine/india_seismic.py": [
            ("# NOTE (WP1.3 item 8, documented for the WP6 example rewrite): the example build scripts\n"
             "# IN_Ex17..Ex15 carry an ESM helper `_sa_g` that returns 1 + 15T for T <= 0.1 s -- that is the RSA\n"
             "# branch.  ESM uses 2.5 from T = 0 (6.4.2(a)); Ex13 VB_x 151.7 kN must be 161.2 kN.  Every job\n",
             "# NOTE (WP1.3 item 8, documented for the WP6 example rewrite): the example build scripts of\n"
             "# IN_Ex7, IN_Ex9-IN_Ex12 and IN_Ex17-IN_Ex20 (2026-10 numbering) carry an ESM helper `_sa_g` that\n"
             "# returns 1 + 15T for T <= 0.1 s -- that is the RSA branch.  ESM uses 2.5 from T = 0 (6.4.2(a));\n"
             "# IN_Ex10 VB_x 151.7 kN must be 161.2 kN.  Every job\n"),
        ],
        "steel_engine/design_pipeline.py": [("(WP6-fix, Ex11 gym 17 m girder)", "(WP6-fix, IN_Ex12 gym 17 m girder)")],
        "contract/IS800_WORKED_METHOD.md": [("Hand values: Ex10 element 73", "Hand values: IN_Ex20 element 73"),
                                            ("P/Pdy = 1.21. Ex12 level-1", "P/Pdy = 1.21. IN_Ex18 level-1")],
    },
    "steltic_CFS_india": {
        "steltic/agent.py": [("(fixtures: tests/fixtures/IN_CFS_Ex7, Ex5)", "(fixtures: tests/fixtures/IN_CFS_Ex7, IN_CFS_Ex3)"),
                             ("stud of the Ex1 reference building", "stud of the IN_CFS_Ex7 reference building")],
        "tests/usa_reference/test_india_complete_gap_wave1.py": [("IN_CFS_Ex7/Ex2", "IN_CFS_Ex7/IN_CFS_Ex1")],
        "steel_engine/india_cfs_portal.py": [("(owner ruling for CFS Ex5, Hyderabad Zone II", "(owner ruling for IN_CFS_Ex3, Hyderabad Zone II")],
        "steel_engine/india_cfs_frame_build.py": [("(the Ex10 high-bay", "(the IN_CFS_Ex4 high-bay")],
        "steel_engine/preflight.py": [("owner ruling for CFS Ex5", "owner ruling for IN_CFS_Ex3"),
                                      ("(Hyderabad Ex5) only", "(Hyderabad IN_CFS_Ex3) only")],
        "contract/README_AGENT.md": [("(or, Ex5, an elastic R = 1.0 portal)", "(or, IN_CFS_Ex3, an elastic R = 1.0 portal)")],
        "contract/AGENT_START.md": [("(the Hyderabad two-span portal, brief Ex5)", "(the Hyderabad two-span portal, brief IN_CFS_Ex3)"),
                                    ("All-CFS elastic portal (Ex5 only)", "All-CFS elastic portal (IN_CFS_Ex3 only)"),
                                    ("(`cfg['portal']`, Ex5)", "(`cfg['portal']`, IN_CFS_Ex3)")],
    },
    "steltic_nonlinear_india": {
        "steltic_ddm/model_gmnia.py": [("gravity gate, Ex1 roof beams)", "gravity gate, IN_Ex13 roof beams)")],
        "steltic_ddm/loads.py": [("gate: the Ex1 roof beams", "gate: the IN_Ex13 roof beams")],
        "contract/HOTSPOTS_ASCE_TO_INDIA.md": [("On tip after Ex1 partial merge", "On tip after IN_Ex13 partial merge"),
                                               ("plus the Ex1 ≥5% mass", "plus the IN_Ex13 ≥5% mass")],
        "docs/README_pushover.md": [("(same spirit as the Ex1 mass pick)", "(same spirit as the IN_Ex13 mass pick)")],
    },
    "steltic_hub_india": {},
}
# short-form table in CFS DESIGN_EG_INDEX.md: 'Ex1' / 'Ex5' are the CFS reference buildings
CFS_TABLE_SHORT = {"steltic_CFS_india": ["contract/DESIGN_EG_INDEX.md"]}


def sub_tokens(text: str) -> str:
    def f(m):
        cfs = m.group(1) or ""
        n = int(m.group(2))
        mp = CFS_MAP if cfs else HR_MAP
        return "IN_%sEx%d" % (cfs, mp.get(n, n))
    return TOKEN.sub(f, text)


def sub_cfs_short(text: str) -> str:
    """Bare 'ExN' -> 'IN_CFS_ExM' (only used on the CFS design-example index, whose short ids are CFS briefs)."""
    return re.sub(r"(?<![A-Za-z_])Ex(\d+)(?!\d)", lambda m: "IN_CFS_Ex%d" % CFS_MAP.get(int(m.group(1)), int(m.group(1))), text)


def is_text(p: Path) -> bool:
    try:
        b = p.read_bytes()
    except OSError:
        return False
    if b"\0" in b[:8192]:
        return False
    try:
        b.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def rewrite_file(p: Path, fn) -> bool:
    b = p.read_bytes()
    t = b.decode("utf-8")
    n = fn(t)
    if n != t:
        p.write_bytes(n.encode("utf-8"))
        return True
    return False


def git(repo: Path, *args) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def renamed(rel: str) -> str:
    return "/".join(sub_tokens(part) for part in rel.split("/"))


def do_repos(ws: Path) -> None:
    hr = ws / "steltic_india"
    if (hr / "test_buildings" / MARKER).exists():
        sys.exit("STOP: %s already exists -- the renumbering has been applied" % MARKER)
    report = []
    for name in REPOS:
        repo = ws / name
        files = [f for f in git(repo, "ls-files", "-z").split("\0") if f]
        records = set(RECORD_DOCS[name])
        # 1. text rewrite (token pass), records excluded
        changed = 0
        for rel in files:
            if rel in records:
                continue
            p = repo / rel
            if p.is_file() and is_text(p) and rewrite_file(p, sub_tokens):
                changed += 1
        # 2. reviewed short-form edits (+ the same edit on the vendored copies of an HR file)
        edits = dict(POST_EDITS[name])
        if name == "steltic_india":
            for vname, vdir in VENDOR_DIRS.items():
                for rel, pairs in POST_EDITS["steltic_india"].items():
                    if rel.startswith("steel_engine/"):
                        POST_EDITS[vname].setdefault(vdir + "/" + rel[len("steel_engine/"):], pairs)
        for rel, pairs in edits.items():
            p = repo / rel
            if not p.exists():
                continue
            t = p.read_text(encoding="utf-8")
            for old, new in pairs:
                if old not in t:
                    sys.exit("STOP: %s/%s: expected text not found: %r" % (name, rel, old[:80]))
                t = t.replace(old, new)
            p.write_text(t, encoding="utf-8", newline="")
        for rel in CFS_TABLE_SHORT.get(name, []):
            rewrite_file(repo / rel, sub_cfs_short)
        # 3. record notes
        for rel in records:
            p = repo / rel
            if p.exists():
                t = p.read_text(encoding="utf-8")
                if RECORD_NOTE not in t:
                    lines = t.split("\n", 1)
                    if lines[0].startswith("#"):
                        t = lines[0] + "\n\n" + RECORD_NOTE + (lines[1].lstrip("\n") if len(lines) > 1 else "")
                    else:
                        t = RECORD_NOTE + t
                    p.write_text(t, encoding="utf-8", newline="")
        # 4. renames (deepest first; two-phase through a temporary name so no move lands on an existing path)
        moves = sorted({(rel, renamed(rel)) for rel in files if renamed(rel) != rel and rel not in records})
        dirs_done = set()
        for old, new in moves:
            # move whole renamed directories once, else files
            o_parts, n_parts = old.split("/"), new.split("/")
            k = next(i for i, (a, b) in enumerate(zip(o_parts, n_parts)) if a != b)
            o_top, n_top = "/".join(o_parts[:k + 1]), "/".join(n_parts[:k + 1])
            if (o_top, n_top) in dirs_done:
                continue
            tmp = o_top + ".__renumber_tmp"
            git(repo, "mv", o_top, tmp)
            dirs_done.add((o_top, n_top))
        for o_top, n_top in sorted(dirs_done):
            git(repo, "mv", o_top + ".__renumber_tmp", n_top)
        report.append("%-26s %4d files rewritten, %3d paths renamed" % (name, changed, len(dirs_done)))
    print("\n".join(report))


def do_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        sys.exit("STOP: %s exists; give a new destination" % dst)
    n_files = n_txt = 0
    for root, dirs, files in os.walk(src):
        rel_root = Path(root).relative_to(src)
        out_root = dst / renamed(rel_root.as_posix()) if str(rel_root) != "." else dst
        out_root.mkdir(parents=True, exist_ok=True)
        for fn in files:
            s = Path(root) / fn
            d = out_root / sub_tokens(fn)
            if is_text(s) and s.suffix.lower() in (".html", ".htm", ".json", ".md", ".txt", ".py", ".csv", ".js", ".sh"):
                d.write_bytes(sub_tokens(s.read_bytes().decode("utf-8")).encode("utf-8"))
                n_txt += 1
            else:
                shutil.copy2(s, d)
            n_files += 1
    # website indexes ({"examples": [{"id": "IN_Ex13_...", "title": "Ex 1 · ...", ...}]}): retitle and re-sort
    import json
    for idx in dst.rglob("index.json"):
        try:
            d = json.loads(idx.read_text(encoding="utf-8"))
        except ValueError:
            continue
        ex = d.get("examples") if isinstance(d, dict) else None
        if not isinstance(ex, list) or not all(isinstance(e, dict) and TOKEN.match(str(e.get("id", ""))) for e in ex):
            continue
        for e in ex:
            num = int(TOKEN.match(e["id"]).group(2))
            if isinstance(e.get("title"), str):
                e["title"] = re.sub(r"^Ex\s*\d+", "Ex %d" % num, e["title"])
        ex.sort(key=lambda e: int(TOKEN.match(e["id"]).group(2)))
        idx.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("copied %d files (%d text files rewritten) to %s" % (n_files, n_txt, dst))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "repos":
        do_repos(Path(sys.argv[2]).resolve())
    elif len(sys.argv) == 4 and sys.argv[1] == "tree":
        do_tree(Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve())
    else:
        print(__doc__)
        sys.exit(2)
