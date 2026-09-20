"""Legacy ASCE 7-22 §16.1.2 drift-relief helpers (USA artefact on steltic_india).

India analogue via IS RAG / NL module is DEFERRED. On this fork:
  - Table 12.12-1 drift ERRORs are not raised (IS 1893 cl.7.11.1.1 WARN path).
  - A present cfg['drift_relief_16_1_2'] is WARN'd as non-authoritative + validated.
  - RC IV still rejects the USA relief block (ERROR).
"""
import copy, io, json, os, sys, zipfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine")); sys.path.insert(0, ROOT)

import preflight as P  # noqa: E402

# Minimal RAG-shaped load_plan so India mandatory gate is not the only ERROR.
_LOAD_PLAN = {
    "jurisdiction": "india",
    "no_wind": "unit-test fixture — gravity/seismic drift-relief only (no wind laterals)",
    "retrieval": [
        {"stem": "IS_875_Part_2_1987", "query": "imposed", "found": True, "cite": "T1"},
        {"stem": "IS_1893_Part_1_2016", "query": "Z", "found": True, "cite": "T3"},
        {"stem": "IS_875_Part_3_2015", "query": "wind omitted for fixture", "found": False, "cite": "no_wind"},
        {"stem": "IS_800_2007", "query": "combinations", "found": True, "cite": "T4"},
    ],
    "combinations": [
        {"label": "1.5DL+1.5LL", "fD": 1.5, "fL": 1.5, "fLr": 0.0, "cite": "IS 800 T4"},
    ],
}

BASE = dict(heights=[192.0, 168.0, 168.0], SX=360.0, SY=360.0, NX=4, NY=3, system="SMF", rho=1.0,
            model={"bases": "fixed", "joints": "rigid", "gravity": "two-way"},
            seis=dict(SDS=1.0, SD1=0.6, S1=0.6, R=8.0, Cd=5.5, Ie=1.25), drift_limit=0.0112,
            load_plan=copy.deepcopy(_LOAD_PLAN))
RELIEF = dict(clause="ASCE 7-22 16.1.2", nlrha_job="Ex", nlrha_run="2026-09-14", nlrha_mean_drift=0.0146, nlrha_limit=0.03,
              nlrha_verdict="ACCEPTABLE", nlrha_records=11, linear_target=0.0112, risk_category="III")


def _cfg(**kw):
    c = copy.deepcopy(BASE); c.update(kw); return c


def _errors(cfg):
    return [m for s, m in P.check(cfg) if s == "ERROR"]


def _warns(cfg):
    return [m for s, m in P.check(cfg) if s == "WARN"]


def test_india_drift_limit_above_0p004_is_an_error():
    """WP1.9: IS 1893 7.11.1.1 -- a drift_limit above 0.004 is an ERROR on India jobs (was a WARN)."""
    assert any("7.11.1.1" in m and "0.004" in m for m in _errors(_cfg(units="mm", drift_limit=0.0168)))


def test_asce_16_1_2_relief_refused_on_india():
    """The ASCE 7-22 16.1.2 relief is a USA artefact: an India cfg carrying it is an ERROR (D3/D7)."""
    c = _cfg(units="mm", drift_limit=0.004, drift_relief_16_1_2=dict(RELIEF))
    assert any("16.1.2" in m for m in _errors(c))


def test_usa_relief_helpers_still_validate_usa_cfgs():
    usa = {k: v for k, v in _cfg(drift_relief_16_1_2={"clause": "x"}).items() if k != "load_plan"}
    assert any("missing" in m for s, m in P.relief_findings(usa) if s == "ERROR") and not P.relief_active(usa)


def test_consistency_mirrors_the_rules():
    import consistency as C
    src = open(os.path.join(ROOT, "steel_engine", "consistency.py"), encoding="utf-8").read()
    assert "relief_findings" in src and "_relief_on" in src


def test_restore_archives_and_keeps_the_viewer():
    import pytest
    pytest.importorskip("fastapi", reason="fastapi not installed in this interpreter")
    from fastapi.testclient import TestClient
    import steltic.main as M
    client = TestClient(M.app)
    def zip_of(building, extra=None):
        buf = io.BytesIO()
        files = {"cfg.py": "cfg = dict()\n", "conversation.json": "[]", "viewer_3d.html": "<html>viewer</html>", "report.html": "<html>r</html>",
                 "design/calc_package.json": "{}", "nlrha/nlrha_package.json": "{}"}
        files.update(extra or {})
        with zipfile.ZipFile(buf, "w") as z:
            for k, v in files.items():
                z.writestr("%s/%s" % (building, k), v)
        return buf.getvalue()
    b = "ReliefTestJob"
    r = client.post("/api/restore/%s" % b, content=zip_of(b)); assert r.status_code == 200 and r.json()["archived"] is None
    jd = M.JOBS_DIR / b
    assert (jd / "viewer_3d.html").exists() and not (jd / "nlrha").exists()               # viewer restored, analyses never
    r = client.post("/api/restore/%s?archive=1" % b, content=zip_of(b, {"cfg.py": "cfg = dict(v=2)\n"})); d = r.json()
    assert d["archived"] and d["archived"].startswith(b + "__") and (M.JOBS_DIR / d["archived"] / "cfg.py").exists()
    assert "v=2" in (jd / "cfg.py").read_text()
    r = client.post("/api/restore/%s" % b, content=zip_of(b)); assert r.json()["archived"] is None          # no flag, no archive
    import shutil
    shutil.rmtree(jd, ignore_errors=True); shutil.rmtree(M.JOBS_DIR / d["archived"], ignore_errors=True)
