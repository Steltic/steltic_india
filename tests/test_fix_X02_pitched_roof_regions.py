"""X02 (HR-E-05, HR-A-15, HR-B-16, CFS-A-15 pitch): true-slope pitched portal roofs (cfg['roof_planes']) and region
roofs (cfg['roof_regions']).

Reference: the HR-E-05 2-D hand portal -- 24 m span, 8 m eave, 3 m rise, WPB600X300X211.92 columns,
NPB600X220X154.47 rafters, fixed bases, 1.5DL + 1.5SL balanced, frames at 7.5 m.  The load (D 0.35 + S 1.2905 kN/m2)
gives w = 18.46 kN/m of plan, which reproduces the finding's FLAT-rafter hand values (knee 793 / base 389 kNm); the
pitched values are then computed by an independent 2-D OpenSees model built in this test (knee 641 / base 530 kNm;
the finding quotes 621 / 506 kNm, 3-5 % lower) and the engine's 3-D model must agree within 3 %."""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "steel_engine"))

COL = "WPB600X300X211.92"
RAF = "NPB600X220X154.47"
PUR = "NPB300X150X36.53"
D_ROOF, SNOW = 0.35, 1.2905
PLANE = {"axis": "X", "eave_coords_mm": [0.0, 24000.0], "ridge_coord_mm": 12000.0, "eave_z_mm": 8000.0,
         "ridge_z_mm": 11000.0, "rafter_sec": RAF, "ridge_sec": PUR}


def _portal_cfg(**kw):
    import engine3d as E
    E.activate_si_units()
    cfg = dict(units="N-mm", NX=1, NY=2, SX=24000.0, SY=7500.0, heights=[8000.0], D_floor=0.0, D_roof=D_ROOF,
               L_floor=0.0, Lr=0.75, clad=0.0, snow=SNOW, col=COL, beam=RAF,
               col_sec=lambda i, j, k, perim: COL, beam_sec=lambda i, j, k, d: RAF if d == "X" else PUR,
               col_strong=lambda i, j, nx, ny: "X",
               releases=lambda i, j, k, d: ("both", "none") if d == "Y" else ("none", "none"),
               self_weight=False, roof_planes=[dict(PLANE)])
    cfg.update(kw)
    return cfg


def _ref_2d(w_plan, rise, E=None, L=24000.0, h=8000.0):
    """Independent 2-D OpenSees portal (fixed bases): vertical load w_plan (N/mm of PLAN) on both rafters, split
    into the member-local components by hand.  Returns (knee M, base M, eave spread) in N-mm / mm."""
    import openseespy.opensees as ops
    import sections as S
    import engine3d as EN
    E = E or EN.E
    c, r = S.props(COL), S.props(RAF)
    ops.wipe(); ops.model("basic", "-ndm", 2, "-ndf", 3)
    ops.node(1, 0.0, 0.0); ops.node(2, 0.0, h); ops.node(3, L / 2, h + rise); ops.node(4, L, h); ops.node(5, L, 0.0)
    ops.fix(1, 1, 1, 1); ops.fix(5, 1, 1, 1)
    ops.geomTransf("Linear", 1)
    ops.element("elasticBeamColumn", 1, 1, 2, c["A"], E, c["Ix"], 1)
    ops.element("elasticBeamColumn", 2, 2, 3, r["A"], E, r["Ix"], 1)
    ops.element("elasticBeamColumn", 3, 3, 4, r["A"], E, r["Ix"], 1)
    ops.element("elasticBeamColumn", 4, 5, 4, c["A"], E, c["Ix"], 1)
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    Ls = math.hypot(L / 2, rise); co, si = (L / 2) / Ls, rise / Ls
    ws = w_plan * co                                   # per slope length
    ops.eleLoad("-ele", 2, "-type", "-beamUniform", -ws * co, -ws * si)     # rising rafter: x=(c,s), y=(-s,c)
    ops.eleLoad("-ele", 3, "-type", "-beamUniform", -ws * co, ws * si)      # falling rafter: x=(c,-s), y=(s,c)
    ops.system("BandGeneral"); ops.numberer("Plain"); ops.constraints("Plain")
    ops.integrator("LoadControl", 1.0); ops.algorithm("Linear"); ops.analysis("Static")
    assert ops.analyze(1) == 0
    knee, base = abs(ops.eleForce(1)[5]), abs(ops.eleForce(1)[2])
    spread = ops.nodeDisp(4, 1) - ops.nodeDisp(2, 1)
    ops.wipe()
    return knee, base, spread


def _static(cfg, nseg=6):
    import openseespy.opensees as ops
    import static_model as SM
    ops.wipe()
    m = SM.build_static(cfg, "Linear", nseg)
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    return m


def _col_end_moments(m, n1):
    import openseespy.opensees as ops
    for c in m["cols"]:
        if c["n1"] == n1:
            lf = ops.eleResponse(c["tag"], "localForce")
            return abs(lf[5]), abs(lf[11])
    raise KeyError(n1)


def test_hand_portal_knee_and_base_match_independent_2d_model():
    import engine3d as E
    import static_model as SM
    import openseespy.opensees as ops
    cfg = _portal_cfg()
    w = 1.5 * (D_ROOF + SNOW) * 7500.0 / 1000.0                     # N/mm of plan on the middle frame
    kf, bf, _ = _ref_2d(w, 1e-6)
    assert kf == pytest.approx(793e6, rel=0.01) and bf == pytest.approx(389e6, rel=0.01)   # finding, flat rafters
    kp, bp, spread2d = _ref_2d(w, 3000.0)
    assert kp == pytest.approx(621e6, rel=0.05) and bp == pytest.approx(506e6, rel=0.06)   # finding's hand values
    m = _static(cfg)
    lev = SM.apply_gravity_state(cfg, m, 1.5, 0.0, 0.0, fS=1.5, self_weight=False)
    assert SM._solve_newton() == 0
    base, knee = _col_end_moments(m, E.ntag(0, 1, 0))
    assert knee == pytest.approx(kp, rel=0.03) and base == pytest.approx(bp, rel=0.03)
    base_r, knee_r = _col_end_moments(m, E.ntag(1, 1, 0))
    assert knee_r == pytest.approx(knee, rel=1e-6) and base_r == pytest.approx(base, rel=1e-6)   # symmetric
    # the eaves spread freely (no diaphragm tie across the span): the same spread as the 2-D portal
    spread = ops.nodeDisp(E.ntag(1, 1, 1), 1) - ops.nodeDisp(E.ntag(0, 1, 1), 1)
    assert spread == pytest.approx(spread2d, rel=0.03) and spread > 5.0
    # total vertical roof load = load x PLAN area (24 x 15 m), within 1 %
    assert lev[1] == pytest.approx(1.5 * (D_ROOF + SNOW) * 24.0 * 15.0 * 1000.0, rel=0.01)


def test_roof_dead_in_seismic_weight_and_model_complete():
    import engine3d as E
    import static_model as SM
    cfg = _portal_cfg()
    info = E.build(cfg, "Linear")
    raf = [e for e in info["ele"] if e[2] == RAF]
    assert len(raf) == 6                                              # 3 frames x 2 rafters, through an apex node
    assert E.floor_area_mm2(cfg, 1) == pytest.approx(24000.0 * 15000.0)
    comp = E.seismic_weight_components(cfg, 1)
    assert comp["dead"] == pytest.approx(D_ROOF * 24.0 * 15.0 * 1000.0, rel=1e-9)   # N: roof dead by plan area
    assert E.floor_beam_gaps(cfg) == []                               # no model_complete gap across the span
    assert not [f for f in SM.pitched_roof_findings(cfg) if f[0] == "ERROR"]
    # gable cladding: W carries the two gable triangles (static model: the gable-end rafters carry them)
    import static_model as SM2
    import openseespy.opensees as ops
    cc = _portal_cfg(clad=0.3)
    E.build(cc, "Linear")
    per = 2 * (24.0 + 15.0)
    assert E.seismic_weight_components(cc, 1)["cladding"] == pytest.approx(
        0.3 * (per * 4.0 + 24.0 * 3.0) * 1000.0, rel=1e-9)            # half the walls + 2 x (24 x 3 / 2)
    m = _static(cc)
    grav = SM2.apply_gravity_state(cc, m, 1.0, 0.0, 0.0, self_weight=False)[1]
    assert grav == pytest.approx((D_ROOF * 360.0 + 0.3 * (per * 4.0 + 24.0 * 3.0)) * 1000.0, rel=0.01)
    # self-weight of the sloped rafters is binned to the eave level
    cfg2 = _portal_cfg(self_weight=True)
    E.build(cfg2, "Linear")
    assert E.seismic_weight_components(cfg2, 1)["self_weight"] > 0.0


def test_apex_on_a_grid_line_and_flat_tie_refused():
    """Ridge on a grid line (xcoords 0 / 12 / 24 m, no column at the ridge): the lifted grid node is the apex; the
    level area comes from the grid cells; no horizontal tie is drawn."""
    import engine3d as E
    import openseespy.opensees as ops
    cfg = _portal_cfg(NX=2, SX=12000.0, xcoords=[0.0, 12000.0, 24000.0],
                      plan=lambda k, nx, ny: {(i, j) for i in range(3) for j in range(3) if k > 1 or i != 1})
    cfg["present"] = {0: {(i, j) for i in (0, 2) for j in range(3)}, 1: {(i, j) for i in range(3) for j in range(3)}}
    info = E.build(cfg, "Linear")
    assert ops.nodeCoord(E.ntag(1, 1, 1))[2] == pytest.approx(11000.0)
    assert not any(e[1] == "col" and e[4] == E.ntag(1, 1, 1) for e in info["ele"])
    assert E.floor_area_mm2(cfg, 1) == pytest.approx(24000.0 * 15000.0)
    assert E.floor_beam_gaps(cfg) == []


def test_member_wind_normal_to_slope_split_at_ridge():
    import engine3d as E
    import static_model as SM
    import openseespy.opensees as ops
    cfg = _portal_cfg()
    pw, pl = -0.8, -0.4                                                # kN/m2, uplift (+ = towards the roof)
    for sign, (p_lo, p_hi) in ((1, (pw, pl)), (-1, (pl, pw))):
        m = _static(cfg)
        pat = {"wind_axis": "X", "sign": sign, "roof_windward_kNm2": pw, "roof_leeward_kNm2": pl}
        tot = SM.member_wind_loads(cfg, m, pat, 1.0)
        Ls = math.hypot(12000.0, 3000.0)
        assert tot["roof_N"] == pytest.approx((pw + pl) * Ls * 15000.0 / 1000.0, rel=1e-9)   # on the SLOPE area
        assert SM._solve_newton() == 0
        ops.reactions()
        Rz_lo = sum(ops.nodeReaction(E.ntag(0, j, 0), 3) for j in range(3))
        Rz_hi = sum(ops.nodeReaction(E.ntag(1, j, 0), 3) for j in range(3))
        # vertical resultant of a normal pressure = p x PLAN area of each slope (12 x 15 m)
        assert Rz_lo + Rz_hi == pytest.approx((p_lo + p_hi) * 12.0 * 15.0 * 1000.0, rel=1e-6)
        # the windward slope (larger uplift) pulls harder on its own side
        assert (Rz_lo < Rz_hi) == (abs(p_lo) > abs(p_hi))


def test_partial_snow_split_at_plane_ridge():
    import static_model as SM
    cfg = _portal_cfg(D_roof=0.0)
    full = SM.apply_gravity_state(cfg, _static(cfg), 0.0, 0.0, 0.0, fS=1.0, self_weight=False)[1]
    lo = SM.apply_gravity_state(cfg, _static(cfg), 0.0, 0.0, 0.0, fS=1.0, self_weight=False,
                                snow_pattern=("X", "lo"))[1]
    assert full == pytest.approx(SNOW * 360.0 * 1000.0, rel=1e-9)
    assert lo == pytest.approx(0.5 * full, rel=1e-9)                  # one full slope, split at the ridge (12 m)
    cfg["roof_planes"][0].update(ridge_coord_mm=8000.0)              # asymmetric gable: ridge at 8 m
    lo = SM.apply_gravity_state(cfg, _static(cfg), 0.0, 0.0, 0.0, fS=1.0, self_weight=False,
                                snow_pattern=("X", "lo"))[1]
    assert lo == pytest.approx(full * 8.0 / 24.0, rel=1e-9)


def test_modal_and_lateral_with_eave_spread_free_diaphragm():
    import engine3d as E
    import static_model as SM
    import openseespy.opensees as ops
    cfg = _portal_cfg(self_weight=True)
    mp = E.modal_props(cfg)
    assert any(md["mass_x"] > 0.99 for md in mp["modes"])             # the master carries the roof mass
    assert mp["m"][1] * E.g == pytest.approx(E.floor_w(cfg, 1), rel=1e-9)
    m = _static(cfg, 4)
    ops.load(E.mtag(1), 60e3, 0.0, 0.0, 0.0, 0.0, 0.0)
    assert SM._solve_newton() == 0
    V = []
    for c in m["cols"]:
        lf = ops.eleResponse(c["tag"], "localForce")
        V.append(abs(lf[1]))
    assert V == pytest.approx([10e3] * 6, rel=1e-3)                   # frames share equally, both columns
    ux = [ops.nodeDisp(E.ntag(i, 1, 1), 1) for i in (0, 1)]
    assert ux[0] == pytest.approx(ux[1], rel=1e-3) and ux[0] > 0.0    # drift measured at the eave nodes


def test_validation_findings():
    import roof_geometry as RG
    cfg = _portal_cfg(snow_partial={"axis": "X"})
    assert RG.validate(cfg) == []
    assert any(s == "WARN" and "4.3" in m for s, m in RG.validate(_portal_cfg()))      # snow without snow_partial
    bad = _portal_cfg(roof_planes=[dict(PLANE, ridge_coord_mm=30000.0)])
    assert any(s == "ERROR" and "ridge_coord_mm" in m for s, m in RG.validate(bad))
    bad = _portal_cfg(roof_planes=[dict(PLANE, eave_z_mm=7000.0)])
    assert any(s == "ERROR" and "storey level" in m for s, m in RG.validate(bad))
    w = _portal_cfg(roof_pitch_deg=5.0, snow_partial={"axis": "X"})
    assert any(s == "WARN" and "Table 6" in m for s, m in RG.validate(w))
    assert not RG.validate(_portal_cfg(roof_pitch_deg=14.0, snow_partial={"axis": "X"}))


def test_flat_model_without_planes_is_unchanged():
    """No roof_planes / roof_regions: the parametric static model and its loads are the legacy ones."""
    import engine3d as E
    import static_model as SM
    cfg = _portal_cfg(NX=2, SX=12000.0, roof_planes=None, deck_span="Y")
    m = _static(cfg, 2)
    assert "rp" not in m["beams"][0] and len(m["beams"]) == 2 * 3 + 3 * 2
    lev = SM.apply_gravity_state(cfg, m, 1.0, 0.0, 0.0, self_weight=False)
    assert lev[1] == pytest.approx(D_ROOF * 24.0 * 15.0 * 1000.0, rel=1e-9)


# ---------------------------------------------------------------- region roofs (HR-B-16)
def _lplan_cfg(**kw):
    """2-storey L-plan: level 1 = bays (0,0), (1,0), (0,1); level 2 = the bar (0,0), (1,0).  The leg's roof is at
    level 1 (cfg['roof_regions'] = {1: [(0, 1)]})."""
    import engine3d as E
    E.activate_si_units()
    lvl1 = {(i, j) for i in range(3) for j in range(2)} | {(0, 2), (1, 2)}
    lvl2 = {(i, j) for i in range(3) for j in range(2)}
    cfg = dict(units="N-mm", NX=2, NY=2, SX=6000.0, SY=6000.0, heights=[4000.0, 4000.0], D_floor=4.0, D_roof=2.5,
               L_floor=3.0, Lr=0.75, snow=0.6, clad=0.0, partition_load_kNm2=1.0, col="WPB300X300X117.03",
               beam="NPB300X150X36.53", self_weight=False, deck_span=None,
               plan=lambda k, nx, ny: lvl2 if k == 2 else lvl1, roof_regions={1: [(0, 1)]})
    cfg.update(kw)
    return cfg


def test_region_roof_loads_on_the_lower_roof():
    import static_model as SM
    cfg = _lplan_cfg()
    bar, leg = 72.0, 36.0                                             # m2
    g = lambda *a, **kw: SM.apply_gravity_state(cfg, _static(cfg, 2), *a, self_weight=False, **kw)
    assert g(1.0, 0.0, 0.0)[1] == pytest.approx((4.0 * bar + 2.5 * leg) * 1000.0, rel=1e-9)
    assert g(0.0, 1.0, 0.0)[1] == pytest.approx((3.0 + 1.0) * bar * 1000.0, rel=1e-9)   # no floor imposed on the leg
    assert g(0.0, 0.0, 1.0)[1] == pytest.approx(0.75 * leg * 1000.0, rel=1e-9)          # roof imposed on the leg
    s = g(0.0, 0.0, 0.0, fS=1.0)
    assert s[1] == pytest.approx(0.6 * leg * 1000.0, rel=1e-9) and s[2] == pytest.approx(0.6 * bar * 1000.0, rel=1e-9)
    # without the region the leg is loaded as a floor (legacy)
    cfg0 = _lplan_cfg(roof_regions=None)
    assert SM.apply_gravity_state(cfg0, _static(cfg0, 2), 0.0, 1.0, 0.0, self_weight=False)[1] == \
        pytest.approx(4.0 * (bar + leg) * 1000.0, rel=1e-9)
    # region-specific dead load
    cfg["roof_regions"] = {1: {"bays": [(0, 1)], "D": 1.5}}
    assert SM.apply_gravity_state(cfg, _static(cfg, 2), 1.0, 0.0, 0.0, self_weight=False)[1] == \
        pytest.approx((4.0 * bar + 1.5 * leg) * 1000.0, rel=1e-9)


def test_region_roof_seismic_weight_and_wind():
    import engine3d as E
    import static_model as SM
    cfg = _lplan_cfg(snow=2.0)
    E.build(cfg, "Linear")
    c = E.seismic_weight_components(cfg, 1)
    pp = max(0.5, 1.0)
    assert c["dead"] == pytest.approx((4.0 * 72.0 + 2.5 * 36.0) * 1000.0, rel=1e-9)
    assert c["partitions"] == pytest.approx(pp * 72.0 * 1000.0, rel=1e-9)             # none on the roof bay
    assert c["imposed"] == pytest.approx(0.25 * 3.0 * 72.0 * 1000.0, rel=1e-9)        # Table 10 share on floors only
    assert c["snow"] == pytest.approx(0.2 * 2.0 * 36.0 * 1000.0, rel=1e-9)            # 7.3.5 on the lower roof
    # member wind reaches the lower roof (and only its bay at level 1)
    m = _static(cfg, 2)
    tot = SM.member_wind_loads(cfg, m, {"wind_axis": "X", "roof_windward_kNm2": -0.4, "roof_leeward_kNm2": -0.4}, 1.0)
    assert tot["roof_N"] == pytest.approx(-0.4 * (72.0 + 36.0) * 1000.0, rel=1e-9)
