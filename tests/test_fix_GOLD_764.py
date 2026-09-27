"""GOLD-764 (IN_CFS_Ex9, lead decision 1): IS 1893 (Part 1):2016 7.6.4 is classified code-literally --
'flexible, if it deforms such that the maximum lateral displacement measured from the chord of the deformed shape at
any point of the diaphragm is more than 1.2 times the average displacement of the entire diaphragm (see Fig. 6)'.
The deviation / average storey drift is kept as an informative record and never classifies (X01 drift_and_764,
india_diaphragm.reconcile_7_6_4 / the AUD-3 warning)."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))

import india_diaphragm as D

CORPUS_764 = ("A floor diaphragm shall be considered to be flexible, if it deforms such that the maximum lateral "
              "displacement measured from the chord of the deformed shape at any point of the diaphragm is more than "
              "1.2 times the average displacement of the entire diaphragm")


def _FD():
    pytest.importorskip("openseespy.opensees")
    import india_flexible_diaphragm as FD
    return FD


def test_three_support_diaphragm_hand_numbers_rigid():
    """X load; three braced lines at y = 0, 6, 12 m (supports) with ux 10, 12, 14 mm (rigid-body translation +
    rotation); the deck mid-bays at y = 3 and 9 m move 17 and 19 mm; equal nodal masses.
    Chord (least squares through the supports): a = 12, th = -1/3000 -> chord 11 at y = 3, 13 at y = 9 -> deviation 6.
    Average displacement of the diaphragm (10 + 17 + 12 + 19 + 14) / 5 = 14.4 -> ratio 6 / 14.4 = 0.4167 <= 1.2:
    RIGID.  Informative: with the level below at 12.0 mm average the storey drift is 2.4 mm and 6 / 2.4 = 2.5 (the
    old reading would have called it flexible)."""
    FD = _FD()
    pts = [(10.0, 1.0, 0.0, 0.0), (17.0, 1.0, 0.0, 3000.0), (12.0, 1.0, 0.0, 6000.0), (19.0, 1.0, 0.0, 9000.0),
           (14.0, 1.0, 0.0, 12000.0)]
    sup = [(10.0, 0.0, 0.0), (12.0, 0.0, 6000.0), (14.0, 0.0, 12000.0)]
    ev = FD.chord_deviation_764(pts, sup, "X")
    assert ev["chord_a"] == pytest.approx(12.0) and ev["chord_theta"] == pytest.approx(-1.0 / 3000.0)
    assert ev["delta_max_from_chord_mm"] == pytest.approx(6.0)
    assert ev["delta_avg_diaphragm_mm"] == pytest.approx(14.4)
    assert ev["ratio"] == pytest.approx(6.0 / 14.4)
    cl = D.classify_7_6_4(delta_max_from_chord_mm=ev["delta_max_from_chord_mm"],
                          delta_avg_mm=ev["delta_avg_diaphragm_mm"])
    assert cl["classification"] == "rigid" and cl["flexible"] is False and "7.6.4 literal" in cl["ratio_basis"]
    assert 6.0 / (14.4 - 12.0) == pytest.approx(2.5)                   # informative drift ratio > 1.2


def test_three_support_diaphragm_hand_numbers_flexible_and_Y():
    """Same geometry, supports 2 mm, mid-bays 20 mm: deviation 18, average (2 + 20 + 2 + 20 + 2) / 5 = 9.2,
    ratio 1.957 > 1.2: FLEXIBLE.  The Y direction uses x as the chord coordinate (same numbers transposed); a heavier
    mid-bay mass weights the average: masses 1, 3, 1, 3, 1 -> average (2 + 60 + 2 + 60 + 2) / 9 = 14.0, ratio 1.286."""
    FD = _FD()
    ev = FD.chord_deviation_764([(2.0, 1.0, 0.0, 0.0), (20.0, 1.0, 0.0, 3000.0), (2.0, 1.0, 0.0, 6000.0),
                                 (20.0, 1.0, 0.0, 9000.0), (2.0, 1.0, 0.0, 12000.0)],
                                [(2.0, 0.0, 0.0), (2.0, 0.0, 6000.0), (2.0, 0.0, 12000.0)], "X")
    assert ev["delta_max_from_chord_mm"] == pytest.approx(18.0) and ev["ratio"] == pytest.approx(18.0 / 9.2)
    assert D.classify_7_6_4(delta_max_from_chord_mm=18.0, delta_avg_mm=9.2)["classification"] == "flexible"
    evy = FD.chord_deviation_764([(2.0, 1.0, 0.0, 0.0), (20.0, 3.0, 3000.0, 0.0), (2.0, 1.0, 6000.0, 0.0),
                                  (20.0, 3.0, 9000.0, 0.0), (2.0, 1.0, 12000.0, 0.0)],
                                 [(2.0, 0.0, 0.0), (2.0, 6000.0, 0.0), (2.0, 12000.0, 0.0)], "Y")
    assert evy["delta_avg_diaphragm_mm"] == pytest.approx(14.0) and evy["ratio"] == pytest.approx(18.0 / 14.0)


def test_reconcile_classifies_on_the_literal_ratio_not_the_drift_ratio():
    """CFS Ex9 level 6 Y: literal 0.37, drift-based 2.10 -> rigid; a declared rigid label is NOT contradicted; the
    drift ratio is kept as an informative record."""
    lv = {"X": [{"level": 6, "delta_max_from_chord_mm": 2.4, "delta_avg_diaphragm_mm": 10.0, "ratio": 0.24,
                 "ratio_vs_avg_displacement": 0.24, "avg_storey_drift_mm": 1.98, "ratio_vs_storey_drift": 1.21,
                 "ratio_basis": D.RATIO_BASIS_7_6_4, "limit": 1.2, "flexible": False, "classification": "rigid"}],
          "Y": [{"level": 6, "delta_max_from_chord_mm": 3.7, "delta_avg_diaphragm_mm": 10.0, "ratio": 0.37,
                 "ratio_vs_avg_displacement": 0.37, "avg_storey_drift_mm": 1.76, "ratio_vs_storey_drift": 2.10,
                 "ratio_basis": D.RATIO_BASIS_7_6_4, "limit": 1.2, "flexible": False, "classification": "rigid"}]}
    rec = D.reconcile_7_6_4(D.classify_7_6_4(declared="rigid"), lv, declared="rigid")
    assert rec["classification"] == "rigid" and rec["computed_classification"] == "rigid"
    assert rec["computed_ratio"] == pytest.approx(0.37) and rec["computed_at"]["dir"] == "Y"
    assert not rec.get("declared_contradicted") and "warning" not in rec
    assert "7.6.4 literal" in rec["ratio_basis"]
    inf = rec["informative_ratio_vs_storey_drift"]
    assert inf["value"] == pytest.approx(2.10) and inf["note"].startswith("informative (not the IS 1893 criterion)")
    # a flexible declaration on that deck is now the contradicted (conservative) label -> non-blocking warning
    fl = D.reconcile_7_6_4(D.classify_7_6_4(declared="flexible"), lv, declared="flexible")
    assert fl["declared_contradicted"] is True and "average displacement of the entire diaphragm" in fl["warning"]


def test_old_format_records_use_the_literal_field():
    """A record written before this fix ('ratio' = drift-based 3.5, 'ratio_vs_avg_displacement' = 0.37) classifies
    on the literal field; a literal ratio above 1.2 still gives the flexible label with its ratio."""
    old = {"Y": [{"level": 7, "ratio": 3.5, "ratio_vs_avg_displacement": 0.37, "avg_storey_drift_mm": 1.0,
                  "limit": 1.2, "flexible": True}]}
    assert D.literal_ratio_7_6_4(old["Y"][0]) == pytest.approx(0.37)
    rec = D.reconcile_7_6_4(D.classify_7_6_4(declared="rigid"), old, declared="rigid")
    assert rec["classification"] == "rigid" and not rec.get("declared_contradicted")
    hi = {"X": [{"level": 2, "ratio": 1.49, "ratio_basis": D.RATIO_BASIS_7_6_4, "avg_storey_drift_mm": 0.2,
                 "ratio_vs_storey_drift": 7.2}]}
    rec2 = D.reconcile_7_6_4(D.classify_7_6_4(declared="rigid"), hi, declared="rigid")
    assert rec2["classification"] == D.FLEXIBLE_FROM_ANALYSIS and rec2["ratio"] == pytest.approx(1.49)
    assert rec2["declared_contradicted"] is True


def test_cites_quote_the_corpus_text():
    FD = _FD()
    assert CORPUS_764 in FD.Q_7_6_4
    assert "average displacement of the entire diaphragm" in D.CITE_7_6_4
    assert "average displacement of the entire diaphragm" in FD.RATIO_BASIS and "Fig. 6" in FD.FIG6_NOTE
    root = os.environ.get("INDIA_CORPUS_ROOT") or "/home/claude/corpus_srv"
    pg = os.path.join(root, "documents", "standards", "IS_1893_Part_1_2016", "markdown", "pages_search", "page_025.md")
    if os.path.exists(pg):
        assert CORPUS_764 in open(pg, encoding="utf-8").read()
