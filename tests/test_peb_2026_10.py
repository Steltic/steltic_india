"""PEB release (2026-10, docs/PEB_TAPERED_SCOPE.md): welded / web-tapered I sections, the stepped tapered-member
model (peb_build), the PEB checks (peb_checks) and the four deliverables (peb_outputs: reactions.csv, bom.csv,
anchor_bolt_plan.svg, model.std), on the small portal of tests/_peb_fixture.py run through the full pipeline."""
import csv
import json
import math
import os
import re

import pytest

from _peb_fixture import COL_T, RAF_P, RAF_T, SPAN, NX, SX, mini_peb_cfg, stage_rag

import peb_build as PB
import sections as S


@pytest.fixture(autouse=True)
def _si_units():
    """Welded and tapered sections are defined in mm only: run every test in N-mm, whatever unit system an earlier
    test module left active (a kip-in preflight test does), and put it back afterwards."""
    import india_units as IU
    prev = IU.active_unit_system()
    IU.activate_si()
    yield
    if prev != "N-mm":
        IU.activate_kip_in()


# ------------------------------------------------------------------------------ sections and the stepped model
def test_parse_labels():
    assert PB.parse("TI300-1000X250X14X6") == ("tapered", 300.0, 1000.0, 250.0, 14.0, 6.0)
    assert PB.parse("WI550X220X10X5") == ("welded", 550.0, 220.0, 10.0, 5.0)


def test_section_at_and_segments():
    lab = "TI300-1000X250X14X6"
    assert PB.section_at(lab, 0.0) == "WI300X250X14X6"
    assert PB.section_at(lab, 1.0) == "WI1000X250X14X6"
    assert PB.section_at(lab, 0.5) == "WI650X250X14X6"
    assert PB.section_at(lab, 1.0 / 16.0) == "WI344X250X14X6"       # mid-depth of the first of 8 segments
    assert PB.n_segments(lab) == 8
    assert PB.depth(lab) == 1000.0


def test_welded_section_properties_and_mass():
    PB.ensure("WI550X220X10X5")
    p = S.props("WI550X220X10X5")
    assert p["A"] == pytest.approx(2 * 220 * 10 + 530 * 5)                       # 7,050 mm2
    assert p["Zx"] == pytest.approx(2 * 220 * 10 * 540 / 2 + 5 * 530 ** 2 / 4)  # plastic modulus 1.539e6 mm3
    assert p["plates"] == {"flange_mm": [220.0, 10.0], "web_mm": [530.0, 5.0]}
    assert PB.mass_kg("WI550X220X10X5", 1000.0) == pytest.approx(7050 * 7.85e-6 * 1000.0)


def test_effective_section_slender_web():
    """IS 800 3.7.2 (d): a 1000 x 6 web in E350 is slender; the effective section deducts the excess width."""
    import india_is800 as I8
    PB.ensure("WI1000X250X14X6")
    p = S.props("WI1000X250X14X6")
    assert I8.section_class_table2(p, 350.0)["section_class"] == "slender"
    r = I8.effective_section_3_7_2d(p, 350.0, welded=True)
    assert r["found"] and r["A_eff_mm2"] < r["A_gross_mm2"] and r["Ze_eff_mm3"] < r["Ze_gross_mm3"]
    eps = math.sqrt(250.0 / 350.0)
    assert r["web_d_eff_axial_mm"] == pytest.approx(42.0 * eps * 6.0, rel=1e-6)
    c = I8.compression_capacity(p, 350.0, KLz_mm=10000.0, KLy_mm=1800.0, welded=True)
    assert c["found"] and c["section_class_axial"] == "slender" and c["Pd_N"] > 0


# ------------------------------------------------------------------------------ IS 18168 route B material gate
def _cfg18168(apply):
    return {"apply_is18168": apply, "occupancy": {"use": "warehouse"}, "seis": {"zone": "III", "Z": 0.16},
            "jurisdiction": "india"}


@pytest.mark.parametrize("apply", [True, False])
def test_material_gate_e350_route_b(apply):
    import india_is800_s12 as S12
    m = {"id": "c1", "grade": "E350 B0"}
    r = S12.material_gate(m, clause="12.11.1", props={}, cfg=_cfg18168(apply), system="SMF")
    if apply:
        assert r["ok"] is True and r["clause"].startswith("IS 18168:2023 5.2(a)")
    else:
        assert r["ok"] is False and r["clause"] == "IS 800:2007 12.11.1"


def test_material_gate_e250_unchanged_under_is18168():
    """E250 keeps the IS 800 E250B row (the jobs designed before route B report identical rows)."""
    import india_is800_s12 as S12
    m = {"id": "c1", "grade": "E250 B0"}
    a = S12.material_gate(m, clause="12.11.1", props={}, cfg=_cfg18168(True), system="SMF")
    b = S12.material_gate(m, clause="12.11.1", props={})
    assert a == b and a["ok"] is True and a["clause"] == "IS 800:2007 12.11.1"


# ------------------------------------------------------------------------------ CFS-free tonnage grouping
def test_tonnage_groups_secondary_struts():
    import peb_checks as PC
    cfg = {"secondary_members": [{"kind": "strut", "id": "roof-girder", "mass_kg": 100.0},
                                 {"kind": "strut", "id": "crane-bracket", "mass_kg": 40.0, "group": "crane"}],
           "peb_secondary": [{"id": "purlin", "mass_kg": 250.0}], "peb_connection_mass_kg": 30.0, "plan_area_m2": 10.0}
    r = PC.tonnage(cfg, {"ele": []}, {}, {}, peb=None)
    assert r["kg"]["bracing"] == 100.0 and r["kg"]["crane"] == 40.0
    assert r["kg"]["secondary"] == 250.0 and r["kg"]["connections"] == 30.0
    assert r["kg_per_m2"]["total"] == pytest.approx(42.0)


# ------------------------------------------------------------------------------ the mini portal, end to end
@pytest.fixture(scope="module")
def peb_job(tmp_path_factory):
    import pipeline as P
    jobs = tmp_path_factory.mktemp("peb_jobs")
    os.environ["STELTIC_TEST_JOBS"] = str(jobs)
    os.environ["STEEL_BUILDER_JOBS"] = str(jobs)
    cfg = mini_peb_cfg("peb_mini")
    stage_rag(os.path.join(str(jobs), "peb_mini"))
    out = P.design_and_report("peb_mini", cfg, do_report=False)
    root = out["root"]
    pkg = json.load(open(os.path.join(root, "design", "calc_package.json")))
    return out, root, pkg, cfg


def test_mini_runs_and_has_peb_block(peb_job):
    out, root, pkg, _ = peb_job
    assert not out.get("blocked"), out.get("error")
    peb = pkg["peb"]
    assert peb["errors"] == []
    for k in ("stations", "chains", "splices", "frame_stability", "members", "tonnage", "outputs"):
        assert k in peb, k
    # the analysis gates of a well-posed model (connections are not declared, so the status stays partial)
    assert pkg["gates"]["model_complete"] and pkg["gates"]["stability"]


def test_stepped_members_and_stations(peb_job):
    _, _, pkg, _ = peb_job
    peb = pkg["peb"]
    cols = [m for m in peb["members"].values() if m["kind"] == "column" and m["section"] == COL_T]
    assert len(cols) == 2                                        # the two columns of main frame i = 1
    secs = {r["section"] for rows in peb["stations"].values() for r in rows}
    assert PB.section_at(COL_T, 1.0 / 8.0) in secs or any(s.startswith("WI") for s in secs)
    # every station row carries a D/C and its governing check
    rows = [r for rs in peb["stations"].values() for r in rs]
    assert rows and all(isinstance(r.get("dc"), (int, float)) and r.get("governing_check") for r in rows)


def test_splices_apex_and_rafter(peb_job):
    _, _, pkg, _ = peb_job
    kinds = {v["kind"] for v in pkg["peb"]["splices"].values()}
    assert {"apex", "rafter_splice"} <= kinds


def test_frame_stability_lambda_cr(peb_job):
    _, _, pkg, _ = peb_job
    fs = pkg["peb"]["frame_stability"]
    assert fs["Y"]["found"] and fs["Y"]["AF"] > 1.0 and fs["Y"]["lambda_cr"] > 1.0
    row = next(c for c in fs["checks"] if "Y sway" in c["name"])
    assert row["value"] == 5.0 and row["limit"] == pytest.approx(fs["Y"]["lambda_cr"])   # 'required 5 / provided'


def test_restraints_from_flange_braces(peb_job):
    """D-T1: rafter segments take LLT from the purlin (top) / fly-brace (bottom) spacing along the slope; column
    segments from the girts and fly braces; the major-axis buckling section is the member's smallest section."""
    import engine3d as E
    _, _, _, cfg = peb_job
    info = E.build(cfg, "Linear")
    slope = math.sqrt(1.0 + (600.0 / (SPAN / 2.0)) ** 2)
    raf = [t for (t, kind, sec, n1, n2) in info["ele"] if (PB.member_of(t) or {}).get("kind") == "rafter"
           and (PB.member_of(t) or {}).get("section") == RAF_T]
    col = [t for (t, kind, sec, n1, n2) in info["ele"] if (PB.member_of(t) or {}).get("section") == COL_T]
    assert raf and col
    o = PB.overrides(cfg, raf[0])                       # the first segment at the knee: purlins at 1.2 m
    assert o["LLT_sag_mm"] == pytest.approx(1200.0 * slope, rel=1e-3)
    assert o["LLT_hog_mm"] == pytest.approx(1200.0 * slope, rel=1e-3)     # fly braces at 1.2 / 2.4 m
    assert o["c1"] == 1.0
    oc = PB.overrides(cfg, col[0])                      # column base segment: girt / fly brace at 1.5 / 3.0 m
    assert oc["Lz_mm"] == pytest.approx(6000.0) and oc["Ly_mm"] == pytest.approx(3000.0)
    assert oc["buckling_section"] == PB.section_at(COL_T, 0.0)     # smallest section of the member


def test_tonnage_matches_element_masses(peb_job):
    _, _, pkg, _ = peb_job
    t = pkg["peb"]["tonnage"]
    assert t["plan_area_m2"] == pytest.approx(NX * SX / 1000.0 * SPAN / 1000.0)
    assert t["total_kg"] == pytest.approx(sum(v["kg"] for v in t["by_element"].values()), abs=0.5)
    assert t["kg"]["primary"] > 0 and t["kg"]["bracing"] > 0


def test_member_schedule_mass_and_depths(peb_job):
    _, root, _, _ = peb_job
    rows = list(csv.DictReader(open(os.path.join(root, "design", "member_schedule.csv"))))
    tap = [r for r in rows if r.get("peb_member") and float(r["start_depth_mm"]) != float(r["end_depth_mm"])]
    assert tap, "no tapered segment with different end depths"
    assert all(float(r["mass_kg"]) > 0 for r in rows if r.get("mass_kg"))


def test_reactions_bom_anchor_plan(peb_job):
    _, root, _, _ = peb_job
    d = os.path.join(root, "design")
    rx = list(csv.DictReader(open(os.path.join(d, "reactions.csv"))))
    cases = {r.get("case") for r in rx}
    assert {"DL", "EQ_X", "EQ_Y"} <= cases
    bom = open(os.path.join(d, "bom.csv")).read()
    assert "kg/m2 of plan" in bom and "TOTAL (take-off)" in bom
    svg = open(os.path.join(d, "anchor_bolt_plan.svg")).read()
    assert svg.lstrip().startswith("<svg") or "<svg" in svg[:300]


def _parse_staad(path):
    txt = open(path).read().splitlines()
    sec, joints, members, loads, cur, slave, combos = None, {}, {}, {}, None, [], []
    for ln in txt:
        s = ln.strip()
        if not s or s.startswith("*"):
            continue
        if s in ("JOINT COORDINATES", "MEMBER INCIDENCES", "MEMBER PROPERTY", "SUPPORTS", "MEMBER RELEASE",
                 "MEMBER TRUSS", "CONSTANTS", "DEFINE MATERIAL START"):
            sec = s
            continue
        if s in ("JOINT LOAD", "MEMBER LOAD", "SELFWEIGHT Y -1"):
            continue
        if s.startswith("LOAD COMBINATION"):
            combos.append(s); sec = "COMB"; continue
        if s.startswith("LOAD "):
            cur = int(s.split()[1]); loads[cur] = []; sec = "LOAD"; continue
        if s.startswith("SLAVE"):
            slave.append(s); continue
        if sec == "JOINT COORDINATES":
            a = s.rstrip(";").split()
            joints[int(a[0])] = tuple(float(x) for x in a[1:4])
        elif sec == "MEMBER INCIDENCES":
            a = s.rstrip(";").split()
            members[int(a[0])] = (int(a[1]), int(a[2]))
        elif sec == "LOAD" and re.match(r"^\d+ UNI PY ", s):
            a = s.split()
            loads[cur].append((int(a[0]), float(a[3])))
    return joints, members, loads, slave, combos


def test_staad_parse_back(peb_job):
    """5.7 (4): parse model.std back -- joint and member counts equal the model, and the roof dead / imposed member
    loads sum to the load on the roof plan within 0.1 %."""
    out, root, pkg, cfg = peb_job
    st = pkg["peb"]["outputs"]["staad"]
    joints, members, loads, slave, combos = _parse_staad(os.path.join(root, "model.std"))
    assert len(joints) == st["n_joints"] and len(members) == st["n_members"]
    assert st["n_masters"] == 1 and any(s.startswith("SLAVE") for s in slave)
    area_mm2 = NX * SX * SPAN
    for lc, q in ((1, cfg["D_roof"]), (2, cfg["Lr"])):
        tot = 0.0
        for m, w in loads[lc]:
            a, b = members[m]
            dx = joints[b][0] - joints[a][0]
            dz = joints[b][2] - joints[a][2]
            tot += -w * math.hypot(dx, dz)                    # PY per projected (plan) length, kN/mm
        assert tot == pytest.approx(q * area_mm2 / 1e6, rel=1e-3), lc
    assert combos and not any("WM" in c or "W_" in c for c in combos)


# ------------------------------------------------------------------------------ end plates: patterns, reversal, column flange
def test_end_plate_layout_symmetric_and_one_sided():
    import peb_checks as PC
    PB.ensure("WI500X250X20X14")
    hf = 480.0
    ep = {"rows": [{"h_mm": hf + 60.0}, {"h_mm": hf - 60.0}, {"h_mm": hf - 180.0}]}
    sym = PC.end_plate_layout(ep, "WI500X250X20X14", symmetric=True)
    # mirrored about mid-depth: -60, 60, 180 added; nothing coincides -> 6 rows of 2
    assert sym["rows_mm"] == pytest.approx([-60.0, 60.0, 180.0, 300.0, 420.0, 540.0])
    assert sym["n_bolts"] == 12
    one = PC.end_plate_layout(ep, "WI500X250X20X14", symmetric=False)
    assert one["n_bolts"] == 6
    # reverse sign: the declared rows measured from the other flange (the extension row is on the compression side)
    assert sorted(r["h_mm"] for r in one["reverse_rows"]) == pytest.approx([60.0, 180.0])
    # rows that coincide within 30 mm are one row (a shared mid-depth row)
    ep2 = {"rows": [{"h_mm": hf + 60.0}, {"h_mm": hf - 60.0}, {"h_mm": 250.0}]}
    assert PC.end_plate_layout(ep2, "WI500X250X20X14", symmetric=True)["n_bolts"] == 10


def test_reverse_demand_picks_the_opposite_sign():
    import peb_checks as PC
    reg = {7: ("beam", "WI500X250X20X14", 10, 11)}
    rec = lambda mi: [0.0, 0.0, 0.0, 0.0, mi, 0.0]
    envt = {7: {"records": {"1.5DL+1.5LL": rec(-5.0e8), "0.9DL+1.5WL": rec(2.0e8), "1.2DL+1.2LL+1.2WL": rec(-3.0e8)}}}
    assert PC.reverse_demand(reg, envt, 10) == (2.0e8, "0.9DL+1.5WL")
    envt1 = {7: {"records": {"1.5DL+1.5LL": rec(-5.0e8)}}}
    assert PC.reverse_demand(reg, envt1, 10) == (0.0, None)


def _mini_connections(cfg, col_flange_t=None):
    import peb_build as PB_
    knee = PB_.section_at(RAF_T, 0.0)
    hf = S.props(knee)["d"] - S.props(knee)["tf"]
    ep = {"rows": [{"h_mm": hf + 60.0, "n_pairs": 1}, {"h_mm": hf - 60.0, "n_pairs": 1},
                   {"h_mm": hf - 160.0, "n_pairs": 1}],
          "d_mm": 20, "grade": "10.9", "t_plate_mm": 20.0, "fy_plate_MPa": 250.0, "be_mm": 100.0, "lv_mm": 45.0,
          "le_mm": 50.0, "pretensioned": True, "bolt_type": "HSFG"}
    spec = {"type": "end_plate", "end_plate": ep, "bolt_type": "HSFG", "weld_type": "cjp", "symmetric": True,
            "plate_b_mm": 200.0, "gauge_mm": 100.0,
            "bom_plates": [{"item": "knee test plates", "part": "test plate", "size": "1 x 1 x 1", "qty_per_joint": 2,
                            "kg_each": 1.5}]}
    if col_flange_t:
        spec["column_flange_t_mm"] = col_flange_t
    hfp = S.props(RAF_P)["d"] - S.props(RAF_P)["tf"]
    sp = {"rows": [{"h_mm": hfp + 60.0, "n_pairs": 1}, {"h_mm": hfp - 60.0, "n_pairs": 1}], "d_mm": 20,
          "grade": "10.9", "t_plate_mm": 20.0, "fy_plate_MPa": 250.0, "be_mm": 100.0, "lv_mm": 45.0, "le_mm": 50.0,
          "pretensioned": True, "bolt_type": "HSFG"}
    cfg = dict(cfg)
    cfg["connections"] = {
        "beam_column": {knee: spec},
        "knee_panel": {"diagonal_stiffener": {"n": 2, "b_mm": 60.0, "t_mm": 10.0, "fy_MPa": 250.0},
                       "flange_stiffener": {"n": 2, "b_mm": 60.0, "t_mm": 10.0, "fy_MPa": 250.0}},
        "rafter_splice": {"apex": {"end_plate": dict(sp), "symmetric": True, "plate_b_mm": 180.0,
                                   # a joint bolted to a column flange (as a canopy-beam root) declares the column:
                                   # here only to exercise the column-flange row of splice_records
                                   "column_section": PB_.section_at(COL_T, 1.0), "gauge_mm": 100.0},
                          "rafter_splice": {"end_plate": dict(sp), "symmetric": False, "plate_b_mm": 180.0}}}
    return cfg


@pytest.fixture(scope="module")
def peb_conn_job(tmp_path_factory):
    import pipeline as P
    jobs = tmp_path_factory.mktemp("peb_conn_jobs")
    os.environ["STELTIC_TEST_JOBS"] = str(jobs)
    os.environ["STEEL_BUILDER_JOBS"] = str(jobs)
    cfg = _mini_connections(mini_peb_cfg("peb_conn"))
    stage_rag(os.path.join(str(jobs), "peb_conn"))
    out = P.design_and_report("peb_conn", cfg, do_report=False)
    pkg = json.load(open(os.path.join(out["root"], "design", "calc_package.json")))
    return out, out["root"], pkg, cfg


def _rows(pkg, prefix):
    return {ch["name"]: ch for v in pkg["connections"] if v["id"].startswith(prefix) for ch in v["checks"]}


def test_knee_reverse_and_column_flange_rows(peb_conn_job):
    import peb_checks as PC
    _, _, pkg, cfg = peb_conn_job
    rows = _rows(pkg, "conn-peb-knee-")
    rev = rows["knee end plate, both signs (D-T7: 1.2 Mp of the face section)"]
    cf = rows["column flange at the end-plate bolt rows (T-stub flange and column web, both signs)"]
    st = rows["column stiffeners at the rafter flange levels (flange force)"]
    knee = PB.section_at(RAF_T, 0.0)
    ep = cfg["connections"]["beam_column"][knee]["end_plate"]
    # symmetric pattern: the reverse capacity is the primary one; demand 1.2 Mp of the face section
    assert rev["limit"] == pytest.approx(PC.end_plate_capacity(ep, cfg)["capacity_Nmm"])
    assert rev["value"] == pytest.approx(1.2 * PC._mp(knee, cfg))
    # the flange-level stiffeners carry at least the flange force of the connection moment (D-T7)
    pb = S.props(knee)
    assert st["value"] >= 1.2 * PC._mp(knee, cfg) / (pb["d"] - pb["tf"]) - 1.0
    # the column flange (10 mm here) is a weaker T-stub flange than the 20 mm end plate
    assert cf["value"] == pytest.approx(rev["value"]) and 0 < cf["limit"] < rev["limit"]
    # a thicker knee-zone flange plate raises it
    cfg2 = _mini_connections(mini_peb_cfg("peb_conn_b"), col_flange_t=25.0)
    ep2 = dict(ep, t_plate_mm=25.0, lv_mm=100.0 / 2.0 - S.props(PB.section_at(COL_T, 1.0))["tw"] / 2.0 - 8.0)
    assert PC.end_plate_capacity(ep2, cfg2)["capacity_Nmm"] > cf["limit"]


def test_splice_reverse_rows(peb_conn_job):
    _, _, pkg, _ = peb_conn_job
    apex = [v for v in pkg["connections"] if v["id"].startswith("conn-peb-splice-") and "apex" in v["type"]]
    spl = [v for v in pkg["connections"] if v["id"].startswith("conn-peb-splice-") and "rafter splice" in v["type"]]
    assert apex and spl
    a = {c["name"]: c for c in apex[0]["checks"]}
    # apex (D-T7): 1.2 Mp in either sign, the symmetric pattern gives the same capacity both ways
    assert a["end-plate moment, reverse sign (apex joint)"]["limit"] == a["end-plate moment (apex joint)"]["limit"]
    # a joint that declares its column gets the column-flange T-stub row (both signs)
    cfr = a["column flange at the end-plate bolt rows (T-stub flange, both signs)"]
    assert cfr["value"] == pytest.approx(max(a["end-plate moment (apex joint)"]["value"],
                                             a["end-plate moment, reverse sign (apex joint)"]["value"]))
    assert 0 < cfr["limit"]
    s = {c["name"]: c for c in spl[0]["checks"]}
    r = s["end-plate moment, reverse sign (rafter splice)"]
    # one-sided splice: the reverse capacity comes from the declared rows measured from the other flange (lower)
    assert r["limit"] is None or r["limit"] < s["end-plate moment (rafter splice)"]["limit"]
    assert "one-sided" in r["cite"]


def test_bom_bolts_and_extra_plates(peb_conn_job):
    _, root, pkg, _ = peb_conn_job
    rows = list(csv.reader(open(os.path.join(root, "design", "bom.csv"))))
    items = {r[0]: r for r in rows if r}
    n_knees = 2                                              # main frame i = 1, two fixed-chain columns
    assert items["knee bolts"][5] == str(12 * n_knees)       # 3 rows, mirrored (symmetric) -> 6 rows of 2
    assert items["knee test plates"][5] == str(2 * n_knees)
    assert float(items["knee test plates"][6]) == pytest.approx(1.5 * 2 * n_knees)


def test_rail_spread_opt_in():
    pytest.importorskip("openseespy.opensees")
    import engine3d as E
    import india_units as IU
    IU.activate_si()
    crane = {"capacity_kN": 200.0, "crab_kN": 40.0, "bridge_kN": 180.0, "span_mm": 19500.0, "hook_approach_mm": 1000.0,
             "wheel_base_mm": 3500.0, "gantry_span_mm": 6000.0, "class": "III", "type": "electric", "span_axis": "X",
             "bracket_eccentricity_mm": 0.0, "operation": "pendant", "rail_height_mm": 6000.0}
    cfg = {"NX": 1, "NY": 1, "SX": 20000.0, "SY": 6000.0, "heights": [6000.0], "base": "fixed",
           "col": "WPB300X300X100.85", "beam": "WPB900X300X291.46", "units": "N-mm", "jurisdiction": "india",
           "D_floor": 0.5, "D_roof": 0.5, "L_floor": 0.0, "Lr": 0.75, "clad": 0.0, "self_weight": False,
           "crane": dict(crane, bracket_nodes={"L": E.ntag(0, 0, 1), "R": E.ntag(1, 0, 1)})}
    assert "rail_spread" not in E.india_crane_sway(cfg)
    cfg["crane"]["check_rail_spread"] = True
    r = E.india_crane_sway(cfg)
    rs = r["rail_spread"]
    assert rs["limit_mm"] == pytest.approx(10.0) and rs["ok"] and rs["mm"] >= 0.0
    # the surge moves both rails the same way: the change of gauge is far below the frame sway
    assert rs["mm"] < r["sway_mm"]
    assert rs["pattern"].startswith("Rmax at ")


def test_end_plate_web_tension_and_no_negative_prying():
    import india_connections as C
    base = dict(rows=[{"h_mm": 640.0}, {"h_mm": 520.0}, {"h_mm": 400.0}], d_mm=30, grade="10.9", t_plate_mm=40.0,
                fy_plate_MPa=240.0, be_mm=110.0, lv_mm=45.0, le_mm=50.0)
    r0 = C.end_plate_moment_capacity(**base)
    # a thin web caps the two rows inside the flange (h < hf = 580) at be tw fy / gamma_m0; the row outside is not capped
    r1 = C.end_plate_moment_capacity(**base, web_t_mm=6.0, web_fy_MPa=350.0, hf_mm=580.0)
    cap = 110.0 * 6.0 * 350.0 / 1.1
    assert r1["rows_web_tension_governs"] == 2
    assert r1["capacity_Nmm"] == pytest.approx(2 * r0["Te_per_bolt_N"] * 640.0 + cap * (520.0 + 400.0))
    # a thick web does not change it
    r2 = C.end_plate_moment_capacity(**base, web_t_mm=40.0, web_fy_MPa=350.0, hf_mm=580.0)
    assert r2["capacity_Nmm"] == pytest.approx(r0["capacity_Nmm"])
    # no 'negative prying': the capacity does not fall as the plate gets thicker
    caps = [C.end_plate_moment_capacity(**dict(base, t_plate_mm=t))["capacity_Nmm"] for t in (40.0, 50.0, 56.0, 63.0)]
    assert all(b >= a - 1.0 for a, b in zip(caps, caps[1:]))
