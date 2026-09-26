"""H47 (HR-C-10, ruling R5): one site-proxy policy -- preflight wind_findings and
india_loads.resolve_site_annex_proxy agree; free-text proxy / nearest stays an ERROR."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "steel_engine"))
import india_loads as IL  # noqa: E402
import india_wind_tables as W  # noqa: E402

REC = {"cyclone_belt": False, "Vb_mps": 47.0, "Vb_source": "site_proxy", "proxy_town": "Delhi",
       "distance_km": 25.0, "basis": "Annex A has no Noida row; Delhi isotach 47 m/s", "verify": True,
       "annex_found": False}


def _f(ws, sev="ERROR", ss=None):
    plan = {"wind_summary": dict(ws), "member_wind": {"patterns": []}}
    if ss is not None:
        plan["seismic_summary"] = ss
    return [m for s, m in W.wind_findings({"load_plan": plan}) if s == sev]


def test_site_proxy_record_accepted_by_preflight_and_helper():
    assert not _f(REC)
    assert any("VERIFY" in m for m in _f(REC, "WARN"))
    r = IL.resolve_site_annex_proxy({}, quantity="Vb", record=REC)
    assert r["found"] is True and r["site_proxy"] is True and r["value"] == 47.0 and r["distance_km"] == 25.0


def test_site_proxy_incomplete_record_refused_by_both():
    for drop in ("proxy_town", "distance_km", "basis", "verify", "annex_found"):
        rec = {k: v for k, v in REC.items() if k != drop}
        e = _f(rec)
        assert any("site_proxy" in m and "refused" in m for m in e), drop
        assert IL.resolve_site_annex_proxy({}, quantity="Vb", record=rec)["found"] is False, drop


def test_free_text_proxy_still_error():
    rec = dict(REC, Vb_source="nearest listed city (Delhi)")
    assert any("proxy city is not permitted" in m for m in _f(rec))


def test_zone_source_same_policy():
    ss = {"zone": "IV", "zone_source": "site_proxy", "proxy_town": "Delhi", "distance_km": 25.0,
          "basis": "Annex E has no Noida row", "verify": True, "annex_found": False}
    assert not _f({"cyclone_belt": False}, ss=ss)
    assert any("site_proxy" in m for m in _f({"cyclone_belt": False}, ss=dict(ss, verify=False)))
    assert any("proxy / nearest" in m for m in _f({"cyclone_belt": False}, ss=dict(ss, zone_source="nearest town")))
