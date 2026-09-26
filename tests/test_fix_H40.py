"""H40 (HR-C-05, HR-D-06, NEW): construction-stage (wet concrete) check per floor-beam element and direction (not
per section), half-bay tributary on edge beams, and the element's own grade."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))

import india_connection_design as CD

CFG = {"SX": 8500.0, "SY": 8500.0, "deck_span": "X", "composite_scope": "bare_steel", "steel_grade": "E250 B0",
       "construction_stage": {"D_wet_kNm2": 3.0, "L_const_kNm2": 0.75, "LLT_mm": 2833.0}}
SEC = "NPB300X165X45.76"


def test_section_used_as_floor_x_and_roof_y_is_not_skipped_by_the_roof_y():
    # floor-X parallel to the deck span (X): no wet load; the roof-Y use of the same section must not make it checked
    els = [{"tag": 1, "section": SEC, "role": "floor", "dir": "X", "L_mm": 8500.0, "nb": 2},
           {"tag": 2, "section": SEC, "role": "roof", "dir": "Y", "L_mm": 8500.0, "nb": 2}]
    assert CD.construction_stage_elements(CFG, els) is None
    # the per-section path (old) checked it: the section had {'X','Y'} directions
    els.append({"tag": 3, "section": SEC, "role": "floor", "dir": "Y", "L_mm": 8500.0, "nb": 2})
    w = CD.construction_stage_elements(CFG, els)
    assert w["element"] == 3 and w["dir"] == "Y"


def test_edge_beam_half_bay_and_grade():
    inner = CD.construction_stage_elements(CFG, [{"tag": 1, "section": SEC, "role": "floor", "dir": "Y", "L_mm": 8500.0,
                                                  "nb": 2}])
    edge = CD.construction_stage_elements(CFG, [{"tag": 2, "section": SEC, "role": "floor", "dir": "Y", "L_mm": 8500.0,
                                                 "nb": 1}])
    assert inner["trib_mm"] == pytest.approx(8500.0) and edge["trib_mm"] == pytest.approx(4250.0)
    assert edge["M_Nmm"] == pytest.approx(inner["M_Nmm"] / 2.0)
    e350 = CD.construction_stage_elements(CFG, [{"tag": 2, "section": SEC, "role": "floor", "dir": "Y", "L_mm": 8500.0,
                                                 "nb": 2, "grade": "E350 B0"}])
    assert e350["grade"] == "E350 B0" and e350["DC"] < inner["DC"]


def test_record_uses_elements():
    els = [{"tag": 3, "section": SEC, "role": "floor", "dir": "Y", "L_mm": 8500.0, "nb": 1}]
    rec = CD.composite_design_record(CFG, [], beam_elems=els)
    cs = next(s for s in rec["slots"] if s["component"] == "construction_stage")
    assert cs["found"] is True and cs["detail"]["element"] == 3 and cs["detail"]["trib_mm"] == pytest.approx(4250.0)
