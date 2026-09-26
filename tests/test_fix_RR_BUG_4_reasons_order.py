"""RR-BUG-4: design_status reasons were cut at 200 with the per-element rows first, so the Table 5(ii) flexible-diaphragm
blocker and the H30 evidence reasons disappeared from the package (and from the CFS STATUS built from it).  Reasons
are now ordered by class (analysis / irregularity / gates / evidence / system first), the per-check element rows are
grouped, the full count is kept and a cap never drops a class."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "steel_engine"))
import india_seismic_gates as G  # noqa: E402

T5 = ("Amd 2 Table 5(ii): re-entrant plan requires a flexible-diaphragm 3D dynamic analysis in addition to the "
      "rigid case -- not performed")
EV = ("consistency: load_plan.retrieval[12] (Noida): found:false without EOR assumption -- record the value used "
      "with {value, source, cite, verify: True} on the row or in cfg['eor_assumptions']")


def _synthetic_400():
    rs = ["capacity_design.checks.is18168_table2_column@e%d fails (pass/ok false)" % i for i in range(1, 221)]
    rs += ["capacity_design.checks.is18168_table2_beam@e%d fails (pass/ok false)" % i for i in range(300, 470)]
    rs += ["member 'lateral_col-WPB300X300X100.85' / IS 800 9.3 interaction: D/C = 1.183 > 1.0 (demand 1.183 / "
           "capacity 1)",
           "capacity_design.checks.12.12_base@base-e1 not evaluated",
           "capacity_design.checks.12.12_base@base-e3 not evaluated",
           "I = 1.00 is below the Table 8 value 1.50 (Table 8 (i) via food storage)",
           "analysis gate dynamic_wind FAILS (engine3d.run_india)",
           EV,
           "IS 1893 7.7.1: linear dynamic analysis required (Zone IV, h > 15 m) but scaled RSA forces were not used",
           T5]
    assert len(rs) == 398
    return rs + ["capacity_design.checks.is18168_table2_column@e999 fails (pass/ok false)",
                 "member 'brace-X' / IS 800 Table 3 slenderness KL/r: D/C = 1.200 > 1.0 (demand 216 / capacity 180)"]


def test_blockers_first_and_elements_grouped():
    rs = _synthetic_400()
    sm = G.summarize_reasons(rs)
    out = sm["reasons"]
    assert sm["n_reasons"] == 400 and not sm["truncated"]
    assert T5 in out and EV in out
    # blocking classes come before any element row
    first_elem = min(i for i, r in enumerate(out) if G.reason_class(r) == "elements" or r.startswith("check "))
    for r in (T5, EV, "analysis gate dynamic_wind FAILS (engine3d.run_india)",
              "I = 1.00 is below the Table 8 value 1.50 (Table 8 (i) via food storage)"):
        assert out.index(r) < first_elem
    assert G.reason_class(T5) == "irregularity" and G.reason_class(EV) == "evidence"
    # grouped per check, with a full element count
    col = [r for r in out if "is18168_table2_column" in r]
    assert col == ["check capacity_design.checks.is18168_table2_column fails (pass/ok false) on 221 elements "
                   "(e.g. e1, e2, e3, ...)"]
    assert any("is18168_table2_beam fails (pass/ok false) on 170 elements" in r for r in out)
    assert any("12.12_base not evaluated on 2 elements (e.g. base-e1, base-e3)" in r for r in out)
    # single member rows stay verbatim
    assert "member 'brace-X' / IS 800 Table 3 slenderness KL/r: D/C = 1.200 > 1.0 (demand 216 / capacity 180)" in out
    assert len(out) < 20
    assert set(sm["classes"]) >= {"analysis", "irregularity", "gates", "evidence", "system", "elements"}
    assert sum(sm["classes_raw"].values()) == 400


def test_cap_never_drops_a_class():
    rs = ["member 'm%d' / chk%d: ok:false" % (i, i) for i in range(400)] + [EV, T5]
    sm = G.summarize_reasons(rs, limit=50)
    out = sm["reasons"]
    assert sm["truncated"] and sm["n_reasons"] == 402 and len(out) == 51
    assert out[0] == T5 and out[1] == EV
    assert out[-1].startswith("... 352 more reason rows")


def test_status_record_for_the_package():
    st = {"status": "partial", "reasons": _synthetic_400(), "authority": "x"}
    rec = G.status_record(st)
    assert rec["n_reasons"] == 400 and T5 in rec["reasons"] and EV in rec["reasons"]
    assert rec["reason_classes"]["elements"] == 395 and rec["reason_classes"]["irregularity"] == 1
    assert rec["status"] == "partial" and rec["authority"] == "x"


def test_already_grouped_rows_are_elements_and_idempotent():
    sm = G.summarize_reasons(_synthetic_400())
    again = G.summarize_reasons(sm["reasons"])
    assert again["reasons"] == sm["reasons"]
    assert G.reason_class(next(r for r in sm["reasons"] if r.startswith("check "))) == "elements"
