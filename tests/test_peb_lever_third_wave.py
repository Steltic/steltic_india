"""PEB-LEVERS, third wave (2026-10, handoff P11): the study runner's contract for the Hub.

* a job spec inferred from a PEB job's own cfg.py (scripts/peb_lever_infer.py), so a Hub project needs no
  hand-written spec in scripts/peb_lever_jobs.py;
* `--list-variants --json`: the runner's switches, each job's spec source and its variants per ladder (no run);
* `--cfs-python`: the CFS engine (purlin / girt design) in its own interpreter;
* `--progress-json`: one machine-readable line per progress event.

Nothing here sizes a shed: the inference builds the small test portal of tests/fixtures/peb_levers_mini once (no
analysis), and the runner is stopped by its time budget before its first variant.

Optional: with STELTIC_PEB_GOLDS=<folder holding the IN_Ex1..IN_Ex4 gold job folders> the specs inferred from the
golds' cfg.py are compared with the hand-written ones (identical on 2026-10-30).
"""
import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (os.path.join(ROOT, "steel_engine"), os.path.join(ROOT, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import peb_autosize as A          # noqa: E402
import peb_lever_infer as INF     # noqa: E402
import peb_lever_study as L       # noqa: E402

MINI = os.path.join(HERE, "fixtures", "peb_levers_mini")
EX1 = "IN_Ex1_PEB_factory_shed_tapered_Bengaluru"
SCRIPT = os.path.join(ROOT, "scripts", "peb_lever_study.py")


def _mini_job(root, name="MY_PEB_SHED"):
    """The mini test portal as an engineer's own PEB job: cfg.py plus a secondary design script (its PURLIN / GIRT /
    FY constants are all the inference reads from it)."""
    d = os.path.join(str(root), name)
    os.makedirs(os.path.join(d, "secondary"))
    shutil.copy(os.path.join(MINI, "cfg.py"), os.path.join(d, "cfg.py"))
    with open(os.path.join(d, "secondary", "secondary_is801.py"), "w") as f:
        f.write('PURLIN = {"section": "LZ200X60X20X2", "spacing_mm": 1500.0}\n'
                'GIRT = {"section": "LZ200X60X20X2", "spacing_mm": 1500.0}\nFY = 240.0\n')
    return d


@pytest.fixture(scope="module")
def mini(tmp_path_factory):
    root = tmp_path_factory.mktemp("lev3")
    return _mini_job(root)


# ------------------------------------------------------------------------------------------- spec inference
def test_spec_is_inferred_from_the_jobs_cfg(mini):
    """The mini portal's spec, as tests/test_peb_levers_2026_10.SPEC writes it by hand (the fabrication limits are the
    briefs' defaults here), plus the fields the study needs (Lr, secondary, brace)."""
    spec = INF.infer_spec(mini)
    assert spec["_source"] == "inferred from cfg.py"
    assert spec["job"] == "MY_PEB_SHED"
    assert spec["members"] == {"COL_T": {"group": "column"}, "RAF_T": {"group": "rafter"}, "RAF_P": {"group": "rafter"}}
    assert sorted(sorted(x) for x in spec["links"]) == [["COL_T.D1", "RAF_T.D0"], ["RAF_P.D", "RAF_T.D1"]]
    assert spec["knee_column"] == "COL_T"
    assert spec["splice_faces"] == {"apex": ["RAF_P", 1.0], "rafter_splice": ["RAF_P", 0.0]}
    assert spec["base_consts"] == ["COL_T"]
    assert (spec["frame_line"], spec["base"], spec["dado_height_mm"]) == (1, "pinned", None)
    assert spec["seismic"] == {"zone": "II", "I": 1.0, "R_consts": {"R_Y": "y", "R_X": "x"}, "route": "OMRF"}
    assert spec["Lr_const"] == "LR" and spec["brace"] == {"const": "BRACE"}
    assert spec["secondary"]["script"] == "secondary/secondary_is801.py"
    assert spec["secondary"]["consts"] == {"purlin": "PURLIN", "girt": "GIRT", "fy": "FY"}
    assert spec["secondary"]["span_mm"] == 6000.0
    assert spec["fab"] == INF.FAB_DEFAULT
    # the wind column of the fixture shares RAF_P's label: the role comes from the main-frame members, and it is said
    assert any("RAF_P" in n and "main-frame" in n for n in spec["_notes"])
    # the inferred spec drives the study's variant list like a hand-written one
    names = [n for n, kw, st, nt in L.variants_for(spec, ladder="full") if kw is not None]
    assert names[0] == "strict" and "rods" in names and "market" in names


def test_inference_refuses_with_reasons(tmp_path):
    with pytest.raises(INF.InferError) as e:
        INF.infer_spec(str(tmp_path / "nothing_here"))
    assert "no cfg.py" in str(e.value)
    d = tmp_path / "not_a_peb"
    d.mkdir()
    (d / "cfg.py").write_text("cfg = {'name': 'frame', 'NX': 2}\n")
    with pytest.raises(INF.InferError) as e:
        INF.infer_spec(str(d))
    assert "no PEB members" in str(e.value)
    (d / "cfg.py").write_text("raise RuntimeError('broken job script')\n")
    with pytest.raises(INF.InferError) as e:
        INF.infer_spec(str(d))
    assert "broken job script" in str(e.value)


def _registry():
    """A synthetic PEB registry (as peb_build makes it) for the inference rules: two frame lines 1, 2 with a tapered
    column and two rafters, gable lines 0, 3 (pinned-top posts, gravity rafters), a braced-frame column, a canopy."""
    mem, chains, grav = {}, {}, set()
    t = [0]

    def add(mid, kind, sec, line, n0, n1, chain, releases=None, gravity=False):
        t[0] += 1
        mem[mid] = {"id": mid, "kind": kind, "section": sec, "node_start": n0, "node_end": n1, "elements": [t[0]],
                    "chain": chain, "line": line}
        chains.setdefault(chain, {"id": chain, "kind": kind, "releases": releases})
        if gravity:
            grav.add(t[0])

    for q in (1, 2):
        for j in (0, 1):
            add("C%d-%d" % (q, j), "column", "TI300-800X200X12X6", (q, j), 100 * q + j, 1000 + 100 * q + j, "C%d-%d" % (q, j))
        add("R%d-a" % q, "rafter", "TI800-450X200X12X6", q, 1000 + 100 * q, 5000 + q, "R%d" % q)
        add("R%d-b" % q, "rafter", "WI450X180X10X5", q, 5000 + q, 9000 + q, "R%d" % q)
        add("K%d" % q, "canopy", "TI400-200X150X8X5", q, 1000 + 100 * q, 7000 + q, "K%d" % q)
    for q in (0, 3):
        add("G%d" % q, "column", "WI300X180X8X5", (q, 0), 10 * q, 20 * q, "G%d" % q, releases="J")
        add("GR%d" % q, "rafter", "WI350X160X8X5", q, 20 * q, 30 * q, "GR%d" % q, gravity=True)
    add("B1", "column", "WI500X400X30X12", (1, 5), 77, 78, "B1", releases="J")
    splices = {9001: {"kind": "rafter_splice", "gravity": False, "sec_left": "WI450X200X12X6",
                      "sec_right": "WI450X180X10X5"},
               9002: {"kind": "apex", "gravity": True, "sec_left": "WI350X160X8X5", "sec_right": "WI350X160X8X5"}}
    return {"members": mem, "chains": chains, "splices": splices, "gravity": grav}


def _ep(d, tf, tw, doubler=0.0):
    return {"rows": [{"h_mm": 1.0, "n_pairs": 1}], "hf_mm": d - tf, "web_t_mm": tw + doubler}


def _ns(**over):
    cfg = {"base": "mixed", "cladding_brittle": True, "Lr": 0.75, "D_roof_collateral": 0.2, "D_roof_pv": 0.15,
           "system_y": "SMRF", "seis": {"zone": "IV", "I": 1.0},
           "connections": {
               "beam_column": {"WI800X200X12X6": {"end_plate": _ep(800, 12, 6)}},
               "rafter_splice": {"apex": {"end_plate": _ep(450, 10, 5, doubler=6.0)},
                                 "rafter_splice": {"end_plate": _ep(450, 10, 5)},
                                 "WI350X160X8X5": {"end_plate": _ep(350, 8, 5)},
                                 "canopy_root": {"end_plate": _ep(400, 8, 5)}},
               "column_base": {"lateral_col:WI350X200X12X6": {"fixed": True, "shear_key": {"size": "k"}},
                               "lateral_col:WI500X400X30X12": {"fixed": False, "shear_key": {"size": "k"}},
                               "WI300X180X8X5": {"fixed": False}}}}
    cfg.update(over)
    ns = {"cfg": cfg, "NX": 3, "GABLE": (0, 3), "GIRTS": [3000.0, 4500.0], "SX": 7500.0}
    return ns, cfg


SRC = '''COL = "TI300-800X200X12X6"
RAF_K = "TI800-450X200X12X6"
RAF_B = "WI450X180X10X5"
CAN = "TI400-200X150X8X5"
G_COL = "WI300X180X8X5"
G_RAF = "WI350X160X8X5"
COL_BR = "WI500X400X30X12"
BRACE = "WPB160X160X30.44"
LR = 0.75
R_Y, R_X = 5.0, 4.5
'''


def _rules_job(tmp_path, monkeypatch, src=SRC, **over):
    d = tmp_path / "RULES_JOB"
    (d / "secondary").mkdir(parents=True)
    (d / "cfg.py").write_text(src)
    (d / "secondary" / "secondary_is801.py").write_text("PURLIN = {}\nGIRT = {}\nFY = 240.0\n")
    ns, cfg = _ns(**over)
    ns.update({k: v for k, v in INF.literal_constants(str(d / "cfg.py")).items()})
    peb = _registry()
    monkeypatch.setattr(INF, "_model", lambda job_dir, notes: (ns, cfg, peb))
    return str(d)


def test_inference_rules(tmp_path, monkeypatch):
    """Roles, moment-frame membership, ties, joint faces, bases, dado and route on a synthetic registry."""
    spec = INF._infer_here(_rules_job(tmp_path, monkeypatch))
    assert spec["members"] == {"COL": {"group": "column"}, "RAF_K": {"group": "rafter"}, "RAF_B": {"group": "rafter"},
                               "CAN": {"group": "rafter", "sfrs": False}, "G_COL": {"group": "column", "sfrs": False},
                               "G_RAF": {"group": "rafter", "sfrs": False}}
    # the braced-frame column (pinned top, a lateral base) is kept at its size, and the note says why
    assert "COL_BR" not in spec["members"] and any("COL_BR" in n and "braced-frame" in n for n in spec["_notes"])
    # knee: column top 800 = knee rafter start 800 (tied); splice: rafter end 450 = body 450 (tied)
    assert sorted(sorted(x) for x in spec["links"]) == [["COL.D1", "RAF_K.D0"], ["RAF_B.D", "RAF_K.D1"]]
    assert spec["knee_column"] == "COL"
    # the apex plate carries a 6 mm web doubler: still RAF_B's face; a joint keyed by a section label is left out
    assert spec["splice_faces"] == {"apex": ["RAF_B", 1.0], "rafter_splice": ["RAF_B", 0.0], "canopy_root": ["CAN", 0.0]}
    assert spec["base_consts"] == ["COL"]
    assert spec["base"] == "fixed" and any("mixed" in n for n in spec["_notes"])
    assert spec["dado_height_mm"] == 3000.0 and any("lowest girt" in n for n in spec["_notes"])
    assert spec["frame_line"] == 1
    assert spec["seismic"] == {"zone": "IV", "I": 1.0, "R_consts": {"R_Y": "y", "R_X": "x"}, "route": "SMRF_IS18168"}
    assert spec["secondary"]["nonpermanent"] == {"collateral": 0.2, "pv": 0.15}
    assert spec["secondary"]["span_mm"] == 7500.0 and spec["Lr_const"] == "LR"


def test_inference_names_what_is_missing(tmp_path, monkeypatch):
    src = SRC.replace("LR = 0.75\n", "").replace("R_Y, R_X = 5.0, 4.5\n", "").replace(
        'G_RAF = "WI350X160X8X5"', 'G_RAF = "WI450X180X10X5"')
    d = _rules_job(tmp_path, monkeypatch, src=src, base="mixed", system_y="braced",
                   connections={"column_base": {}, "rafter_splice": {}})
    with pytest.raises(INF.InferError) as e:
        INF._infer_here(d)
    why = " | ".join(e.value.reasons)
    assert "RAF_B and G_RAF are both WI450X180X10X5" in why or "G_RAF and RAF_B are both" in why
    assert "no R constants" in why and "roof imposed-load constant" in why
    assert "neither an ordinary nor a special moment frame" in why
    assert "column base (pinned / fixed) is not stated" in why


@pytest.mark.skipif(not os.environ.get("STELTIC_PEB_GOLDS"), reason="STELTIC_PEB_GOLDS not set (the gold job folders)")
def test_inferred_specs_of_the_golds_equal_the_hand_written_ones():
    from peb_lever_jobs import JOB_SPECS
    for job, hand in JOB_SPECS.items():
        inf = INF.infer_spec(os.path.join(os.environ["STELTIC_PEB_GOLDS"], job))
        for k, v in hand.items():
            if k == "solar":
                continue
            got = inf.get(k)
            if k == "links":
                v, got = sorted(sorted(x) for x in v), sorted(sorted(x) for x in got)
            if k == "base_consts":
                v, got = sorted(v), sorted(got)
            assert got == v, (job, k)


# ------------------------------------------------------------------------------------------- the runner's contract
def test_job_spec_prefers_the_hand_written_spec(mini):
    spec, src, notes = L.job_spec(EX1, "/nowhere")
    assert src == L.SPEC_HAND and spec is L.JOB_SPECS[EX1] and notes == []
    spec, src, notes = L.job_spec("MY_PEB_SHED", os.path.dirname(mini))
    assert src == L.SPEC_INFERRED and spec["job"] == "MY_PEB_SHED" and "_notes" not in spec
    assert not L.solar_ok("MY_PEB_SHED", spec) and L.solar_ok(EX1, L.JOB_SPECS[EX1])


def test_list_variants_json_contract(mini):
    """--list-variants --json: one JSON document, nothing sized -- the hand-written spec of IN_Ex1, the inferred spec
    of an engineer's job, and the reasons for a job with neither."""
    r = subprocess.run([sys.executable, "-I", SCRIPT, "--list-variants", "--json", "--job", EX1, "--job", "MY_PEB_SHED",
                        "--job", "NO_SUCH_JOB", "--jobs-root", os.path.dirname(mini), "--work", os.path.dirname(mini)],
                       capture_output=True, text=True, timeout=600, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    assert r.returncode == 0, r.stderr[-2000:]
    line = next(x for x in reversed(r.stdout.strip().splitlines()) if x.startswith("{"))
    c = json.loads(line)
    assert c["contract"] == "peb_lever_study" and c["version"] == L.CONTRACT_VERSION
    o = c["options"]
    assert o["ladders"] == ["full", "short"] and o["cfs_python"] and o["spec_from_cfg"] and o["progress_json"]
    assert c["progress"]["prefix"] == L.PROGRESS_PREFIX and c["variant_order"] == list(L.VARIANT_ORDER)
    assert EX1 in c["specs"] and "MY_PEB_SHED" not in c["specs"]
    j1 = c["jobs"][EX1]
    assert j1["spec_source"] == L.SPEC_HAND and j1["solar"] is True and j1["zone"] == "II" and j1["route"] == "OMRF"
    for lad in ("full", "short"):
        want = [n for n, kw, st, nt in L.variants_for(L.JOB_SPECS[EX1], solar=True, ladder=lad)]
        assert [v["name"] for v in j1["variants_by_ladder"][lad]] == want
    by = {v["name"]: v for v in j1["variants_by_ladder"]["full"]}
    assert by["rods"]["compliance"] == "not compliant" and by["base_key_analysis"]["compliance"] == "reading"
    assert by["omrf_r3"]["applies"] is False and by["omrf_r3"]["compliance"] == "n/a"
    assert by["cum:ltb_gradient"]["alias"] == "ltb_gradient" and by["cum:ltb_gradient"]["sized"] is False
    assert by["strict"]["sized"] is True
    mj = c["jobs"]["MY_PEB_SHED"]
    assert mj["spec_source"] == L.SPEC_INFERRED and mj["solar"] is False and mj["members"] == ["COL_T", "RAF_P", "RAF_T"]
    assert any("RAF_P" in n for n in mj["spec_notes"])
    nj = c["jobs"]["NO_SUCH_JOB"]
    assert nj["spec_source"] is None and any("no cfg.py" in e for e in nj["error"])


def test_code_status_reads_like_the_outputs():
    cs = L.code_status
    assert cs("compliant") == "compliant" and cs("published (owner rulings)") == "compliant"
    assert cs("market practice, not compliant") == "not compliant" and cs("NOT COMPLIANT (market practice)") == "not compliant"
    assert cs("reading rejected by ruling O1") == "reading" and cs("n/a") == "n/a"
    for s in ("compliant", "not compliant", "reading rejected by ruling O1", "n/a", "old treatment (unconservative)"):
        tag = L._tag(s)
        assert ('class="tag nc"' in tag) == (cs(s) == "not compliant")


# ------------------------------------------------------------------------------------------- --cfs-python
def _fake_python(tmp_path, out):
    """An 'interpreter' that records its arguments and answers like the secondary-candidates probe."""
    p = tmp_path / "fake_cfs_python"
    p.write_text("#!/bin/sh\necho \"$@\" >> %s\necho '[[\"LZ200X60X20X2\", 200.0, 2.0, 5.5]]'\n" % out)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


@pytest.mark.skipif(sys.platform == "win32", reason="a shell-script interpreter")
def test_the_cfs_engine_runs_in_its_own_interpreter(tmp_path, monkeypatch):
    assert A.cfs_python() == sys.executable
    log = tmp_path / "calls.txt"
    monkeypatch.setattr(A, "CFS_PY", _fake_python(tmp_path, log))
    rows = A.secondary_candidates("IS811_Fy240", str(tmp_path / "cfs"), "LZ200X60X20X2", 6000.0)
    assert rows == [["LZ200X60X20X2", 200.0, 2.0, 5.5]]
    assert "-I -c" in log.read_text()


def test_cfs_python_is_checked_before_any_sizing(tmp_path):
    with pytest.raises(SystemExit) as e:
        L.check_cfs_python(sys.executable, str(tmp_path / "no_cfs_checkout"))
    assert "cannot import the CFS engine" in str(e.value)
    with pytest.raises(SystemExit) as e:
        L.check_cfs_python(str(tmp_path / "no_python"), str(tmp_path))
    assert "cannot be run" in str(e.value)


# ------------------------------------------------------------------------------------------- --progress-json
def _args(tmp, **kw):
    a = argparse.Namespace(jobs_root=str(tmp / "jobs"), work=str(tmp / "study"), cfs_root=str(tmp / "cfs"),
                           published_root=str(tmp / "pub"), variants="", max_runs=1, resume=True, solar=False,
                           render=False, stop_after_min=0.0, cfs_python="")
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def test_progress_events_and_the_spec_record(tmp_path, mini, capsys, monkeypatch):
    """With --progress-json the runner prints the plan, the budget stop and the end of the job as JSON lines; the
    spec it used is written next to the study, with its source."""
    a = _args(tmp_path, jobs_root=os.path.dirname(mini), stop_after_min=1.0)
    monkeypatch.setattr(L, "PROGRESS_JSON", True)
    monkeypatch.setattr(L, "T_START", time.time() - 120.0)
    st = L.run_job("MY_PEB_SHED", a)
    assert st["stopped_before"] == "strict" and st["spec_source"] == L.SPEC_INFERRED
    ev = [json.loads(x[len(L.PROGRESS_PREFIX):]) for x in capsys.readouterr().out.splitlines()
          if x.startswith(L.PROGRESS_PREFIX)]
    kinds = [e["event"] for e in ev]
    assert kinds == ["plan", "budget", "job_done"]
    assert ev[0]["variants"][0] == "strict" and ev[0]["n"] == len(ev[0]["variants"])
    assert ev[0]["spec_source"] == L.SPEC_INFERRED and "rods" in ev[0]["variants"]
    assert ev[1]["before"] == "strict" and ev[2]["stopped_before"] == "strict"
    rec = json.load(open(os.path.join(a.work, "MY_PEB_SHED", "job_spec.json")))
    assert rec["_source"] == L.SPEC_INFERRED and rec["members"]["COL_T"] == {"group": "column"}
    # without the switch: no JSON lines
    monkeypatch.setattr(L, "PROGRESS_JSON", False)
    L.run_job("MY_PEB_SHED", a)
    assert L.PROGRESS_PREFIX not in capsys.readouterr().out
