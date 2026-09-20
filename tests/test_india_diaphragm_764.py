"""IS 1893 7.6.4 diaphragm classification and the flexible-diaphragm tributary distribution (HR-INTEGRATE)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "steel_engine"))

import india_diaphragm as D  # noqa: E402


def test_classification_deflection_ratio():
    r = D.classify_7_6_4(delta_max_from_chord_mm=13.0, delta_avg_mm=10.0)
    assert r["flexible"] is True and r["ratio"] == pytest.approx(1.3) and r["limit"] == 1.2
    assert D.classify_7_6_4(delta_max_from_chord_mm=11.0, delta_avg_mm=10.0)["classification"] == "rigid"


def test_classification_rules_and_declaration():
    assert D.classify_7_6_4(rc_slab=True, plan_aspect_ratio=2.0)["classification"] == "rigid"
    assert D.classify_7_6_4(screed_mm=75, roof=True, plan_aspect_ratio=3.5)["flexible"] is True
    assert D.classify_7_6_4(screed_mm=50, roof=True)["ok"] is None          # 75 mm needed on a roof
    assert D.classify_7_6_4(declared="flexible")["flexible"] is True
    assert D.classify_7_6_4()["ok"] is None                                  # blocks COMPLETE


def test_tributary_distribution_and_eccentricity():
    v = D.tributary_line_shears(1000.0, [0, 30000, 60000, 90000], (0, 90000))
    assert [round(x, 3) for x in v.values()] == [166.667, 333.333, 333.333, 166.667]
    assert sum(v.values()) == pytest.approx(1000.0)
    v2 = D.tributary_line_shears(1000.0, [0, 90000], (0, 90000), eccentricity_mm=0.05 * 90000)
    assert v2[90000.0] == pytest.approx(550.0) and v2[0.0] == pytest.approx(450.0)
