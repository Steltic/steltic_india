"""Third wave (2026-10), agent SECT: Indian section families for the hot-rolled golds IN_Ex7 ... IN_Ex20.

P3 (HR side)  a tie between two load combinations is broken by the fixed order of the combination list, whatever
              PYTHONHASHSEED is (design_pipeline._top_records keeps the list order)
P6 sizer      steel_engine/hr_autosize.py: catalogue by role (IS 808 MB / WB / HB, IS 1161 CHS), the order of
              preference (rolled E250 -> rolled E350 -> built-up), built-up labels, the cfg rewrite, the grade map,
              the connection designers (fin plates and CHS brace ends checked with the engine's own capacity
              functions), the base / splice adapters and their step-up rules
"""
import json
import math
import os
import subprocess
import sys

import pytest

import _ex1_fixture  # noqa: F401  (puts steel_engine on sys.path)

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(os.path.dirname(HERE), "steel_engine")


def _az():
    import hr_autosize as AZ
    return AZ


# ------------------------------------------------------------------------------------------------ P3 (HR side)
_TOP_RECORDS_SCRIPT = r"""
import json, sys
sys.path.insert(0, ENGINE_DIR)
import design_pipeline as DP
labels = ["1.5DL+1.5LL", "1.5DL+1.5LL+N_X", "1.5DL+1.5LL-N_X", "1.5DL+1.5LL+N_Y", "1.5DL+1.5LL-N_Y"] + \
         ["1.2DL+1.2LL%s1.2EQ_%s[%s]+0.3EQ_Z" % (s, d, e) for s in "+-" for d in "XY" for e in ("ea", "eb")]
recs = {l: [-1000.0, 50.0, 10.0, 5.0] + [0.0] * 9 for l in labels}     # all tied
print(json.dumps(list(DP._top_records(recs, k=8))))
"""


def test_p3_top_records_keep_the_combination_order_for_any_hash_seed():
    outs = set()
    for seed in ("0", "1", "2", "3"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        r = subprocess.run([sys.executable, "-c", "ENGINE_DIR = %r\n" % ENGINE + _TOP_RECORDS_SCRIPT], env=env, capture_output=True,
                           text=True, timeout=120)
        assert r.returncode == 0, r.stderr[-2000:]
        outs.add(r.stdout.strip().splitlines()[-1])
    assert len(outs) == 1
    order = json.loads(outs.pop())
    # the kept combinations appear in the order of the combination list
    full = ["1.5DL+1.5LL", "1.5DL+1.5LL+N_X", "1.5DL+1.5LL-N_X", "1.5DL+1.5LL+N_Y", "1.5DL+1.5LL-N_Y"] + \
           ["1.2DL+1.2LL%s1.2EQ_%s[%s]+0.3EQ_Z" % (s, d, e) for s in "+-" for d in "XY" for e in ("ea", "eb")]
    assert order == [l for l in full if l in order]


def test_p3_tied_member_check_governs_with_the_first_combination_in_the_list():
    import design_pipeline as DP
    import india_is800 as I8
    import static_model as SM
    recs = {"1.5DL+1.5LL": [-200e3, 40e6, 0.0, 30e3, 40e6, -40e6, 0.0, 0.0, 40e6, 30e3, 0.0, 0.0, 0.0],
            "1.5DL+1.5LL+N_X": [-200e3, 40e6, 0.0, 30e3, 40e6, -40e6, 0.0, 0.0, 40e6, 30e3, 0.0, 0.0, 0.0]}
    m = {"id": "e1", "tag": 1, "section": "MB300", "grade": "E250 B0", "role": "beam", "L_mm": 6000.0, "Kz": 1.0,
         "Ky": 1.0, "LLT_sag_mm": 1500.0, "LLT_hog_mm": 1500.0}
    for order in (list(recs), list(reversed(list(recs)))):
        rr = {k: recs[k] for k in order}
        cf = SM.combo_forces_for_member_check(DP._top_records(rr), "beam")
        r = I8.member_check_is800(m, cf, cfg={})
        assert r["governing_combo"] == order[0]


# ------------------------------------------------------------------------------------------------ catalogue
def test_rolled_families_lightest_first_and_only_their_family():
    AZ = _az()
    mb = AZ.rolled("MB")
    assert mb[0] == "MB100" and mb[-1] == "MB600"
    assert all(l.startswith("MB") for l in mb)
    ms = [AZ.mass_kg_m(l) for l in mb]
    assert ms == sorted(ms)
    hb = AZ.rolled("HB")
    assert hb and all(l.startswith("HB") for l in hb)
    chs = AZ.rolled("CHS")
    assert chs[0].startswith("CHS") and AZ.mass_kg_m(chs[0]) <= AZ.mass_kg_m(chs[-1])


def test_order_of_preference_rolled_e250_then_e350_then_built_up():
    AZ = _az()
    c = AZ.candidates({"role": "column", "families": ["HB"], "built_up": "box"})
    tiers = [t for (_, _, t) in c]
    assert tiers == sorted(tiers)
    assert c[0][1] == "E250 B0" and c[0][0].startswith("HB")
    e350 = [x for x in c if x[2] == 1]
    assert e350 and all(x[1] == "E350 B0" and x[0].startswith("HB") for x in e350)
    bu = [x for x in c if x[2] == 2]
    assert bu and all(x[0].startswith("BOX") and x[1] == "E350 B0" for x in bu)
    # braces: IS 1161 tubes only, no IS 2062 grade (the tube grade comes from the cfg)
    b = AZ.candidates({"role": "brace"})
    assert b and all(l.startswith("CHS") and g is None for (l, g, _) in b)
    # beams: MB / WB rolled, then welded plate I
    bm = AZ.candidates({"role": "beam", "built_up": "welded_I", "max_depth_mm": 600})
    assert bm[0][0].startswith(("MB", "WB")) and any(l.startswith("WI") for (l, _, _) in bm)


def test_built_up_labels_parse_register_and_mass():
    AZ = _az()
    import sections as S
    assert AZ.box_label(450, 450, 28) == "BOX450X450X28"
    # depth first, as the golds' labels: BOX450X400X25 is 450 deep (major axis plane), 400 wide
    assert AZ.parse_built_up("BOX450X400X25") == ("box", (400.0, 450.0, 25.0, 25.0))
    assert AZ.box_label(400, 450, 25) == "BOX450X400X25"
    AZ.register("BOX450X400X25")
    assert S.props("BOX450X400X25")["d"] == 450.0 and S.props("BOX450X400X25")["bf"] == 400.0
    assert AZ.wi_label(700, 300, 25, 14) == "WI700X300X25X14"
    AZ.register("BOX430X430X28")
    p = S.props("BOX430X430X28")
    A = 2 * 430 * 28 + 2 * (430 - 56) * 28
    assert abs(p["A"] - A) < 1e-6
    assert abs(AZ.mass_kg_m("BOX430X430X28") - A * 7.85e-3) < 1e-6
    cs = AZ.custom_sections({"a": "BOX430X430X28", "b": "MB300", "c": "WI700X300X25X14"})
    assert set(cs) == {"BOX430X430X28", "WI700X300X25X14"}
    assert cs["WI700X300X25X14"]["type"] == "welded_I" and cs["BOX430X430X28"]["tf_mm"] == 28.0


def test_built_up_catalogue_is_sorted_and_respects_limits():
    AZ = _az()
    boxes = AZ.built_up_catalogue("box", min_depth=300, max_depth=450)
    ms = [AZ.mass_kg_m(l) for l in boxes]
    assert ms == sorted(ms)
    for l in boxes:
        k, (B, D, tf, tw) = AZ.parse_built_up(l)
        assert 300 <= B <= 450 and (B - 2 * tf) / tf >= 6.0


# ------------------------------------------------------------------------------------------------ cfg rewrite
SRC = '''"""doc"""
import math
# the groups
SECTIONS = {"col": "HB300", "beam": "MB400"}   # trailing comment
X = 1
GRADE_BY_SECTION = {}
CONNECTIONS = {"beam_shear": {}}
cfg = dict(a=SECTIONS["col"])
'''


def test_rewrite_source_replaces_only_the_named_literals_and_keeps_comments():
    AZ = _az()
    out = AZ.rewrite_source(SRC, {"SECTIONS": {"col": "BOX400X400X25", "beam": "MB450"},
                                  "GRADE_BY_SECTION": {"lateral_col:BOX400X400X25": "E350 B0"}})
    assert "# the groups" in out and '"""doc"""' in out and "X = 1" in out
    lit = AZ.read_literals(out, ("SECTIONS", "GRADE_BY_SECTION", "CONNECTIONS"))
    assert lit["SECTIONS"] == {"col": "BOX400X400X25", "beam": "MB450"}
    assert lit["GRADE_BY_SECTION"] == {"lateral_col:BOX400X400X25": "E350 B0"}
    assert lit["CONNECTIONS"] == {"beam_shear": {}}
    with pytest.raises(KeyError):
        AZ.rewrite_source(SRC, {"NOPE": 1})


def test_grade_map_keys_by_engine_role_and_skips_the_job_grade():
    AZ = _az()
    x = {"c1": ("BOX450X450X28", "E350 B0"), "c2": ("HB300", "E250 B0"), "b": ("MB400", None),
         "br": ("CHS219.1X8", None)}
    roles = {"c1": ["lateral_col"], "c2": ["gravity_col"], "b": ["floor"], "br": ["brace"]}
    g = AZ.grade_map(x, roles, "E250 B0", base={"MC200": "E250 B0"})
    assert g == {"MC200": "E250 B0", "lateral_col:BOX450X450X28": "E350 B0"}


# ------------------------------------------------------------------------------------------------ connections
def test_fin_plate_designer_passes_the_engine_checks_and_fits_the_web():
    AZ = _az()
    import india_connections as C
    for sec, V in (("MB300", 120e3), ("MB450", 350e3), ("MB600", 600e3)):
        sp = AZ.design_fin_plate(sec, V)
        assert sp is not None
        assert AZ.fin_plate_fits(sec, sp["bolts"]["n_bolts"] // sp.get("bolt_lines", 1), sp["bolts"]["d_mm"])
        kw = {k: v for k, v in sp.items() if k in ("t_plate_mm", "h_plate_mm", "fy_plate_MPa", "fu_plate_MPa", "bolts",
                                                    "block_shear_areas", "cjp")}
        r = C.fin_plate_shear_checks(V_N=V, **kw)
        assert r["ok"] is True and r["dc"] <= 0.9 + 1e-9
        e, p, d0 = AZ.BOLT_GEOM[sp["bolts"]["d_mm"]]
        rows = sp["bolts"]["n_bolts"] // sp.get("bolt_lines", 1)
        assert sp["h_plate_mm"] == 2 * e + (rows - 1) * p
        import india_connection_design as CD
        sl = CD.hsfg_slip_checks(sp["bolts"], sp["bolt_type"], V / 1.5, V, slip_surface=sp["slip_surface"])
        assert sl["slip_service_10_4_3"]["dc"] <= 0.9 + 1e-9
        # the spec goes through the engine's own beam-end connection wiring (bolt dict: IS 800 10.3 inputs only)
        r2 = CD.beam_shear_connection_checks({"connections": {"beam_shear": {sec: sp}}}, {"section": sec}, V)
        assert r2["ok"] is True


def test_chs_brace_end_spec_geometry():
    AZ = _az()
    sp = AZ.brace_end_chs_spec("CHS219.1X8", 20.0, 400.0)
    import sections as S
    p = S.props("CHS219.1X8")
    assert sp["An_mm2"] == pytest.approx(p["A"] - 2 * 8.0 * 22.0, abs=0.1)
    assert sp["gusset"]["Avg_mm2"] == 2 * 400.0 * 20.0 and sp["gusset"]["w_start_mm"] == pytest.approx(219.1)
    bw = 219.1 + 2 * 400.0 * math.tan(math.radians(30))
    assert sp["moment_capacity_Nmm"] == pytest.approx(20.0 * bw ** 2 / 4 * 250.0 / 1.1)
    assert sp["welds"]["n_sides"] == 4 and sp["weld_type"] == "cjp"


def test_cover_plate_joint_develops_the_factor_on_the_beam_plastic_moment():
    AZ = _az()
    import india_connections as C
    import sections as S
    for beam in ("MB400", "MB600", "WB500"):
        sp = AZ.cover_plate_joint_spec(beam)
        p = S.props(beam)
        cp = sp["cover_plate"]
        r = C.cover_plate_moment_capacity(Zp_beam_mm3=p["Zx"], fy_beam_MPa=250.0, d_beam_mm=p["d"],
                                          plate_b_mm=cp["plate_b_mm"], plate_t_mm=cp["plate_t_mm"],
                                          fy_plate_MPa=cp["fy_plate_MPa"])
        assert r["capacity_Nmm"] >= 1.32 * p["Zx"] * 250.0 / 1.1 * 0.999 or cp["plate_t_mm"] >= 50


def test_base_adapter_keeps_projections_and_bumps_by_failing_row():
    AZ = _az()
    tpl = {"B_mm": 600.0, "L_mm": 700.0, "t_plate_mm": 40.0, "fy_plate_MPa": 240.0, "fixed": True,
           "anchors": {"n_total": 4, "n_tension": 2, "d_mm": 24, "grade": "8.8", "n_per_row": 2, "Anb_mm2": 353.0,
                       "embedment": {"method": "bond", "L_mm": 600.0}}}
    import sections as S
    sp = AZ.adapt_base(tpl, "HB200", "HB300")
    dB = S.props("HB300")["bf"] - S.props("HB200")["bf"]
    dL = S.props("HB300")["d"] - S.props("HB200")["d"]
    assert sp["B_mm"] >= 600.0 + dB - 1e-9 and sp["L_mm"] >= 700.0 + dL - 1e-9
    assert sp["B_mm"] % 50 == 0 and sp["L_mm"] % 50 == 0
    assert AZ.adapt_base(tpl, "HB300", "HB200") == tpl                 # a smaller column keeps the plate
    b = AZ.bump_base(tpl, ["column base (base-e1): plate_thickness", "column base (base-e1): anchor_tension_10_3_5",
                           "column base (base-e1): anchorage_embedment"])
    assert b["t_plate_mm"] > 40.0 and b["anchors"]["d_mm"] == 30 and b["anchors"]["Anb_mm2"] == 561.0
    assert b["anchors"]["embedment"]["L_mm"] == 850.0
    assert tpl["t_plate_mm"] == 40.0                                    # the template is not changed in place


def test_splice_adapter_resizes_flange_plates_to_the_new_flange():
    AZ = _az()
    import sections as S
    tpl = {"type": "flange_plates", "plate": {"A_mm2": 3600.0, "fy_MPa": 250.0, "t_mm": 12.0},
           "bolts": {"n_bolts": 6, "d_mm": 20, "grade": "8.8", "t_mm": 10.5}}
    sp = AZ.adapt_splice(tpl, "WPB300X300X69.8", "HB250")
    p = S.props("HB250")
    assert sp["plate"]["A_mm2"] == pytest.approx(p["bf"] * 12.0, abs=0.1)
    assert sp["bolts"]["t_mm"] == pytest.approx(min(p["tf"], 12.0), abs=0.01)
    up = AZ.bump_splice(sp, ["column splice: bolts_10_3", "column splice: plate_yield_6_2"])
    assert up["bolts"]["n_bolts"] == 8 and up["plate"]["t_mm"] == 14.0
    assert AZ.adapt_splice({"none": True, "note": "x"}, "HB250", "HB300") == {"none": True, "note": "x"}
