"""H21 (E7, HR-A-12): inside the IS 875-3 6.3.4 cyclone belt the wind structure class is an explicit input
(no silent 'other' -> k4 1.00); a hospital declaring k1 = 1.0 gets a Table 1 iv) warning."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "steel_engine"))
import india_wind_tables as W  # noqa: E402


def _cfg(occ=None, **ws):
    c = {"load_plan": {"wind_summary": dict(ws), "member_wind": {"patterns": []}}}
    if occ is not None:
        c["occupancy"] = occ
    return c


def _f(cfg, sev):
    return [m for s, m in W.wind_findings(cfg) if s == sev]


def test_cyclone_belt_without_class_is_error():
    e = _f(_cfg(cyclone_belt=True, Kd=1.0, k4=1.0), "ERROR")
    assert any("wind_structure_class" in m and "post_cyclone" in m for m in e)
    assert W.k4_required(True, None)["k4"] is None


def test_cyclone_belt_class_must_be_one_of_three():
    e = _f(_cfg(cyclone_belt=True, Kd=1.0, k4=1.0, structure_class="warehouse"), "ERROR")
    assert any("must be one of" in m for m in e)


def test_cyclone_belt_industrial_requires_115():
    e = _f(_cfg(cyclone_belt=True, Kd=1.0, k4=1.0, structure_class="industrial"), "ERROR")
    assert any("6.3.4 gives 1.15" in m for m in e)
    assert not _f(_cfg(cyclone_belt=True, Kd=1.0, k4=1.15, structure_class="industrial"), "ERROR")
    cfg = _cfg(cyclone_belt=True, Kd=1.0, k4=1.30)
    cfg["wind_structure_class"] = "post_cyclone"
    assert not _f(cfg, "ERROR")


def test_outside_belt_needs_no_class():
    assert not _f(_cfg(cyclone_belt=False, k4=1.0), "ERROR")


def test_hospital_k1_10_warns_table1_iv():
    w = _f(_cfg({"use": "hospital", "persons": 400}, cyclone_belt=False, k1=1.0), "WARN")
    assert any("Table 1 iv)" in m for m in w)
    w = _f(_cfg({"use": "office", "hospital": True}, cyclone_belt=False, k1=1.0), "WARN")
    assert any("Table 1 iv)" in m for m in w)
    assert not any("Table 1 iv)" in m for m in _f(_cfg({"use": "hospital"}, cyclone_belt=False, k1=1.08), "WARN"))
    assert not any("Table 1 iv)" in m for m in _f(_cfg({"use": "office"}, cyclone_belt=False, k1=1.0), "WARN"))
