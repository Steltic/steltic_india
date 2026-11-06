"""Engine checks 3 (2026-11-07, branch fix/2026-11-engine-checks-3): the reviewer's low notes N1-N3 on the consistency
guards of engine checks 2 (briefs/ENG_REVIEW.md, "Branch 2 review"), each on a real gold package.

N1  the ponding guard judges the roof's real span (a roof plane's eave-to-eave span, else the longest grid bay), not a
    roof group's longest element: a PEB portal's rafters are short tapered pieces (IN_Ex1: 9 m of a 30 m span); and,
    by the slope ruling (2026-11-07), only a long span flatter than 1 in 20 or of unknown slope.
N2  a declared composite_scope clears the composite guard only with the worksheet the engine builds from it.
N3  the seismic-joint guard is cleared by the 7.11.3 separation record or a check tagged as the seismic joint, not by
    any designed label with 'separation' in it.

The fixtures are cut from the gold runs on the e45a65d engine (gold/runs/eng10; gold/tools/make_fixtures_c3.py) to
what consistency._consultancy_issues reads; 'issues_e45a65d' is that engine's own result on the full package.
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (os.path.join(ROOT, "steel_engine"), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

DATA = os.path.join(HERE, "fixtures", "engine_checks_2026_11")


def _fx(name):
    return json.load(open(os.path.join(DATA, name + ".json")))


def _issues(cfg, pkg, word):
    import consistency as CC
    return [i for i in CC._consultancy_issues(cfg, pkg) if word in i]


# ============================================================================================================== N1
def _roof_el(pkg):
    return [m["inputs"]["length_mm"] / 1000.0 for m in pkg["members"] if m["inputs"]["role"] == "roof"]


def test_N1_ponding_guard_reads_the_PEB_portal_span_and_slope():
    """IN_Ex1 (the published PEB shed, no cfg['ponding']): its roof groups' longest element is 9.04 m (the WI550
    rafter piece) on a 30 m portal.  The guard now reads the roof plane: 30 m eave to eave at 1 in 10.  Under the slope
    ruling (a long span flatter than 1 in 20, or of unknown slope) a 1 in 10 portal stays quiet; the same portal at
    1 in 50 fires, and the IS 875 (Part 4) 4.4 screen record clears it."""
    import consistency as CC
    fx = _fx("IN_Ex1_PEB_guard")
    cfg, pkg = fx["cfg"], fx["pkg"]
    assert fx["issues_e45a65d"] == []                                            # e45a65d: quiet
    assert max(_roof_el(pkg)) < 12.0
    roofs = CC._roofs_for_ponding(cfg, pkg, _roof_el(pkg))
    assert roofs[0][0] == 30.0 and abs(roofs[0][1] - 0.1) < 1e-9 and roofs[0][2] == "roof plane 0 span eave to eave"
    assert _issues(cfg, pkg, "ponding") == []                                   # 1 in 10: not a small slope
    pl = copy.deepcopy(cfg["roof_planes"][0])
    run = pl["ridge_coord_mm"] - min(pl["eave_coords_mm"])
    pl["ridge_z_mm"] = pl["eave_z_mm"] + run / 50.0                             # the same portal at 1 in 50
    flat = dict(cfg, roof_planes=[pl])
    hit = _issues(flat, pkg, "ponding")
    assert len(hit) == 1 and "roof plane 0 span eave to eave 30.0 m, slope 1 in 50 (the roof plane)" in hit[0]
    assert "IS 800 Table 6" in hit[0] and "180/40 = 4.5" in hit[0] and "not an IS criterion" in hit[0]
    screened = dict(pkg, ponding={"clause": "IS 875 (Part 4):2021 4.4", "ok": True, "value": 18.0, "limit": 300.0})
    assert _issues(flat, screened, "ponding") == []


def test_N1_flat_roof_span_is_the_grid_bay_and_an_unknown_slope_fires():
    """Without roof planes the span is the longest grid bay the roof beams span: IN_Ex16's 7.5 m bays stay quiet.
    With one 15 m bay (its roof beams still recorded in 7.5 m pieces) the guard fires while the slope is unknown or
    flatter than 1 in 20 (IN_Ex10's form: ponding.roof_slope 1 in 60, here without its screen record), and is quiet
    at a declared 1 in 10 pitch (cfg['roof_pitch_deg'])."""
    import math
    fx = _fx("IN_Ex16_composite_guard")
    cfg, pkg = fx["cfg"], fx["pkg"]
    assert _issues(cfg, pkg, "ponding") == []
    wide = dict(cfg, xcoords=[0.0, 15000.0] + [15000.0 + 7500.0 * i for i in range(1, int(cfg["NX"]))])
    hit = _issues(wide, pkg, "ponding")
    assert len(hit) == 1 and "longest grid bay (roof beam span) 15.0 m, slope unknown (not declared)" in hit[0]
    sixty = dict(wide, ponding={"span_mm": 15000.0, "roof_slope": 1.0 / 60.0, "delta_mm": 20.0})
    hit = _issues(sixty, pkg, "ponding")
    assert len(hit) == 1 and "slope 1 in 60 (cfg['ponding'].roof_slope)" in hit[0]
    pitched = dict(wide, roof_pitch_deg=math.degrees(math.atan(0.1)))
    assert _issues(pitched, pkg, "ponding") == []


# ============================================================================================================== N2
def test_N2_composite_scope_clears_only_with_the_worksheet():
    """IN_Ex16 (composite deck, composite_scope 'bare_steel', the worksheet evaluated): quiet.  The same package
    whose worksheet failed to build (composite_design {'status': 'error'}) or was not written: the declared scope
    alone no longer clears the guard."""
    fx = _fx("IN_Ex16_composite_guard")
    cfg, pkg = fx["cfg"], fx["pkg"]
    assert cfg["composite_scope"] == "bare_steel" and pkg["composite_design"]["status"] == "evaluated"
    assert _issues(cfg, pkg, "COMPOSITE") == []
    failed = dict(pkg, composite_design={"status": "error", "error": "KeyError: 'construction_stage'",
                                         "blocks_complete": True})
    assert len(_issues(cfg, failed, "COMPOSITE")) == 1
    gone = {k: v for k, v in pkg.items() if k != "composite_design"}
    assert len(_issues(cfg, gone, "COMPOSITE")) == 1
    # honest found:false stubs (no scope declared) still clear it (H6)
    import india_is800 as I8
    stubs = dict(pkg, composite_design={"status": "stubs", "chI_worksheet": I8.composite_is11384_worksheet_stubs({})})
    assert _issues({k: v for k, v in cfg.items() if k != "composite_scope"}, stubs, "COMPOSITE") == []


# ============================================================================================================== N3
def test_N3_seismic_joint_needs_the_separation_record_or_a_tagged_check():
    """IN_Ex12's link unit (its 7.11.3 separation from the adjacent units recorded) read as a two-wing plan: quiet.
    Without the separation record it fires, and an unrelated designed check with 'separation' in its label (a brace
    gusset's edge separation) does not clear it; a check tagged as the seismic joint (or 7.11.3) does."""
    fx = _fx("IN_Ex12_unitB_joint_guard")
    cfg, pkg = dict(fx["cfg"], arch="SMF school, two wings joined by this link"), fx["pkg"]
    assert pkg["deformation_compatibility"]["separation"]
    assert _issues(cfg, pkg, "seismic-joint") == []
    nosep = copy.deepcopy(pkg)
    nosep["deformation_compatibility"]["separation"] = []
    assert len(_issues(cfg, nosep, "seismic-joint")) == 1
    other = copy.deepcopy(nosep)
    other["capacity_design"]["checks"]["gusset_edge_separation@b12"] = {"dc": 0.4}
    assert len(_issues(cfg, other, "seismic-joint")) == 1
    for label in ("seismic_joint_width@A-B", "IS 1893 7.11.3 gap A-B"):
        tagged = copy.deepcopy(nosep)
        tagged["capacity_design"]["checks"][label] = {"value": 80.0, "limit": 100.0, "dc": 0.8}
        assert _issues(cfg, tagged, "seismic-joint") == [], label
