"""
example_build_ebf.py  --  REFERENCE eccentrically braced frame (EBF) job built with the JSON frame builder (X06, HR-B-20).

Read this with frame_build.py (the builder and the full `gold` schema).  An EBF needs things the regular-grid
example_build cannot draw: the beam of a braced bay is split into beam - LINK - beam at off-grid work points, the two
braces run from the storey-below column nodes to the link ends (centre-link chevron), and every link is DECLARED to the
pipeline in info['links'] so that design_pipeline.ebf_links_model_data gives it role 'link' and
india_is800_s12.ebf_link_checks runs IS 18168:2023 11 / 12.3 on it:

    info['links'] = [{tag, e_mm, bay_L_mm, dir, storey, brace_tags, beam_tags, column_tags,
                      end_stiffeners {both_sides, width_mm (combined), t_mm}, intermediate_stiffener_spacing_mm,
                      braced_both_flanges, connected_to_column, continuous_link_beam, doubler}]

frame_build writes those records itself for every gold["ebf_bays"] bay (stiffeners sized to IS 18168 11.4 from the
link section: combined width bf - 2 tw + 2 mm, t = max(0.75 tw, 10) + 2 mm, spacing min(30 tw - 0.2 d, e/2) - 5 mm).
Link-end node tags: k*100000 + 50000/60000 + i*100 + j (X bays), 70000/80000 + j*100 + i (Y bays).

Design rules the example follows (IS 18168:2023):
  * the link is an I-section meeting Table 2 (iv), no doubler (11.1); the beam outside the link is the SAME section
    (continuous_link_beam), so it must also meet Table 2 (i) -- NPB350X170X66.05 meets both, many WPB flanges do not
    (b/tf > the beam limit); the SFRS columns meet the Table 2 column limits (WPB260X260X114.4);
  * shear link: e < 1.6 MpL / VpL (11.3);
  * link rotation (L/e) x R x elastic storey drift <= 0.08 rad (12.3.3.1) -- keep L/e moderate and the frame stiff;
  * the links are not connected to the columns (centre link, 12.3.1) and are braced at both flanges (12.3.3.2).

    import example_build_ebf as XE, pipeline
    cfg = XE.ebf_example_cfg()
    pipeline.design_and_report(XE.NAME, cfg)

The loads below are ILLUSTRATIVE numbers for the example (not RAG retrievals); a real job retrieves every load and
code value (contract/AGENT_START.md) and declares them in load_plan['retrieval'].  The example declares no connection
geometry (cfg['connections']), so the connection rows (brace ends, 12.3.4.4 beam-column joints of the storey-2 braces,
bases, splices) stay 'not evaluated' and the design status is EXAMPLE_ONLY; the members, the links and the
capacity-protected members pass (tests/test_fix_X06.py).
"""
from __future__ import annotations

import copy
import math

NAME = "IN_EBF_example"

# 3 x 2 bays of 6 m, two 3.6 m storeys; centre-link chevron EBFs on the four faces
EBF_GOLD = {
    "ebf_bays": {"1-2": [["X", 1, 0], ["X", 1, 2], ["Y", 0, 0], ["Y", 3, 1]]},
    "e_link_mm": 900.0,
    "ebf_beam_sec": {"X": {"1-2": "NPB350X170X66.05"}, "Y": {"1-2": "NPB350X170X66.05"}},
    "ebf_link_sec": {"X": {"1-2": "NPB350X170X66.05"}, "Y": {"1-2": "NPB350X170X66.05"}},
    "ebf_brace_sec": {"1-2": "WPB200X200X74.01"},
    "col_sec": {"lateral": {"1-2": "WPB260X260X114.4"}, "gravity": {"1-2": "WPB200X200X42.26"}},
    "beam_sec": {"floor_X": "NPB450X190X77.58", "floor_Y": "NPB450X190X77.58",
                 "roof_X": "NPB400X180X66.31", "roof_Y": "NPB400X180X66.31"},
    "sfrs_base": "fixed", "gravity_base": "pinned",
}


# The clauses the example's numbers come from.  A real job stores each live hit (rag/<file> + a verbatim quote,
# contract/AGENT_START.md); these rows only name the clause, so the example's design status stays PARTIAL (evidence).
EXAMPLE_RETRIEVAL = [
    {"stem": "IS_1893_Part_1_2016", "query": "response reduction factor R eccentrically braced SBF Table 9", "found": True,
     "cite": "IS 1893 (Part 1):2016 Table 9 (ii)(c) -- special braced frame with eccentric braces: R = 5.0",
     "note": "EXAMPLE row (not a stored live hit)"},
    {"stem": "IS_1893_Part_1_2016", "query": "zone factor Z Table 3 zone IV", "found": True,
     "cite": "IS 1893 (Part 1):2016 Table 3 -- Zone IV: Z = 0.24", "note": "EXAMPLE row (not a stored live hit)"},
    {"stem": "IS_1893_Part_1_2016", "query": "Ta all other buildings 7.6.2(c) 0.09h/sqrt(d)", "found": True,
     "cite": "IS 1893 (Part 1):2016 7.6.2(c): Ta = 0.09 h / sqrt(d)", "note": "EXAMPLE row (not a stored live hit)"},
    {"stem": "IS_875_Part_2_1987", "query": "office rooms imposed floor load Table 1", "found": True,
     "cite": "IS 875 (Part 2):1987 Table 1 -- office floors (EXAMPLE value 3.0 kN/m2 used)",
     "note": "EXAMPLE row (not a stored live hit)"},
    {"stem": "IS_875_Part_3_2015", "query": "basic wind speed Annex A", "found": False, "cite": None,
     "note": "EXAMPLE: wind not evaluated (load_plan.no_wind)"},
    {"stem": "IS_18168_2023", "query": "shear link length e 1.6 MpL/VpL 11.3", "found": True,
     "cite": "IS 18168:2023 11 / 12.3 -- EBF links (ebf_link_checks)", "note": "EXAMPLE row (not a stored live hit)"},
]


def ebf_example_cfg(name=NAME, gold=None, zone="IV", Z=0.24, I=1.0, R=5.0, soil="II", heights_m=(3.6, 3.6)):
    """The complete HR cfg of the EBF example: geometry in metres (normalised to N-mm by frame_build.attach_gold),
    illustrative gravity loads, IS 1893 ESM summary / story forces recomputed from the model's seismic weight
    (W = model mass), IS 800 Table 4 combinations generated by the engine ('auto'), RSA."""
    import engine3d as E
    import frame_build as FB
    gold = copy.deepcopy(gold or EBF_GOLD)
    NX, NY, bay, heights = 3, 2, 6.0, [float(h) for h in heights_m]
    cfg = {
        "name": name, "system": "EBF", "arch": "EBF", "jurisdiction": "india", "units": "m", "metric": True,
        "si_native": True, "NX": NX, "NY": NY, "bay_x": bay, "bay_y": bay, "heights": list(heights),
        "D_floor": 3.0, "D_roof": 2.0, "L_floor": 3.0, "Lr": 0.75, "clad": 0.5, "snow": 0.0,
        "partition_load_kNm2": 1.0, "partition_seismic_kNm2": 1.0, "partitions": True,
        "E": 200000.0, "base": "fixed", "diaphragm": "rigid", "floor_system": "one-way composite deck", "deck_span": "Y",
        "model": {"bases": "EBF columns fixed, gravity columns pinned",
                  "joints": "simple shear joints except the EBF beam-link-beam lines (rigid)",
                  "gravity": "framed"},
        "col": "WPB200X200X42.26", "beam": "NPB300X165X39.88", "brace": "WPB200X200X74.01",
        "steel_grade": "E250 B0", "brace_grade": "E250 B0", "column_lateral_support_both_flanges": True,
        "K_factors": {"lateral_col": {"Kz": 1.0, "Ky": 1.0}, "gravity_col": {"Kz": 1.0, "Ky": 1.0},
                      "brace": {"Kz": 1.0, "Ky": 1.0}, "basis": "IS 800 Table 11 (braced frame, both ends restrained)"},
        "LLT_sag_mm": {"floor": 600.0, "roof": 600.0}, "LLT_hog_mm": {"floor": 6000.0, "roof": 6000.0},
        "occupancy": {"use": "office", "area_m2": 216.0 * len(heights)}, "drift_limit": 0.004, "analyses": ["RSA"],
        "connections": {}, "section12_inputs": {},
        "seis": {"Z": Z, "I": I, "R": R, "zone": zone, "soil": soil},
        "load_plan": {"jurisdiction": "india", "retrieval": copy.deepcopy(EXAMPLE_RETRIEVAL),
                      "no_wind": ("EXAMPLE: seismic-governed EBF demonstration of frame_build ebf_bays; a real job "
                                  "retrieves IS 875 (Part 3) Vb / k1-k4 / Cp and applies the wind laterals"),
                      "notes": "EXAMPLE: illustrative loads, not retrieved (example_build_ebf.py)"},
        "notes": "EBF reference example (frame_build gold block with ebf_bays); illustrative loads.",
    }
    FB.attach_gold(cfg, gold)                     # N-mm geometry + cfg['custom_build'] = frame_build.frame_build
    E.activate_si_units()
    h = sum(cfg["heights"]) / 1000.0
    d = {"X": NX * bay, "Y": NY * bay}
    Ta = {k: 0.09 * h / math.sqrt(v) for k, v in d.items()}          # IS 1893 7.6.2(c) all other buildings
    r = E.esm_from_model(cfg, Ta, soil=soil)
    plan = cfg["load_plan"]
    ss = plan.setdefault("seismic_summary", {})
    ss.update(r["seismic_summary"])
    ss.update(system="EBF", zone=zone, Z=Z, I=I, R=R, soil=soil, Ta_x_s=Ta["X"], Ta_y_s=Ta["Y"],
              Ta_formula="0.09 h/sqrt(d) (IS 1893 7.6.2(c))", d_x_m=d["X"], d_y_m=d["Y"])
    plan["story_forces"] = {"EQ_" + k: r["story_forces"]["EQ_" + k] for k in ("X", "Y")}
    plan["story_forces_units"] = "N"
    plan["combinations"] = "auto"
    cfg["seis"].update(Ah=ss.get("Ah"), Ta=max(Ta.values()), Sa_g=ss.get("Sa_g"), VB_kN=ss.get("VB_kN"))
    return cfg
