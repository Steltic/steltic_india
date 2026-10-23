"""PEB-LEVERS, second wave (2026-10): the study runner's resumable time budget and the sizer's refusal of a proposal
that puts two resized constants on one section label."""
import argparse
import json
import os
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (os.path.join(ROOT, "steel_engine"), os.path.join(ROOT, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import peb_autosize as A        # noqa: E402


def test_shared_label_reason():
    assert A._shared_label({"G_COL": "WI300X180X8X5", "W_COL": "WI400X180X8X5"}) is None
    why = A._shared_label({"G_COL": "WI200X120X6X4", "W_COL": "WI200X120X6X4", "COL_T": "TI300-1000X250X14X6"})
    assert why and "G_COL" in why and "W_COL" in why and "WI200X120X6X4" in why


def test_evaluator_refuses_two_constants_on_one_label():
    """The next full run maps members back to constants by label (LocalModel), so a proposal with two constants on
    one label must be infeasible before any check is evaluated (IN_Ex1 strict: the gable corner and wind columns both
    went to the lightest plates and the next LocalModel stopped the study)."""
    lm = types.SimpleNamespace(res={})
    x_gold = {"G_COL": "WI300X180X8X5", "W_COL": "WI400X180X8X5"}
    ev = A.Evaluator(lm, {"members": {}}, {}, {}, x_gold)
    e = ev({"G_COL": "WI200X120X6X4", "W_COL": "WI200X120X6X4"})
    assert e["feasible"] is False and "share the label" in e["why"] and e.get("viol") is None
    # the local optimiser skips such a proposal (no 'viol'): a repair or descent move to it is never taken
    assert ev.n_eval == 1


def _args(tmp, **kw):
    a = argparse.Namespace(jobs_root=str(tmp / "jobs"), work=str(tmp / "study"), cfs_root=str(tmp / "cfs"),
                           published_root=str(tmp / "pub"), variants="", max_runs=1, resume=True, solar=False,
                           render=False, stop_after_min=0.0)
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def test_budget_spent():
    import peb_lever_study as L
    a = argparse.Namespace(stop_after_min=0.0)
    assert not L.budget_spent(a)
    a.stop_after_min = 30.0
    t0 = L.T_START
    try:
        L.T_START = time.time()
        assert not L.budget_spent(a)
        L.T_START = time.time() - 31 * 60.0
        assert L.budget_spent(a)
    finally:
        L.T_START = t0


def test_study_stops_between_variants_and_resumes(tmp_path):
    """With the budget spent the study starts no new variant: study.json records where it stopped and is not marked
    finished; the n/a levers before the stop are still recorded, so a resumed chunk continues from 'stopped_before'."""
    import peb_lever_study as L
    job = "IN_Ex1_PEB_factory_shed_tapered_Bengaluru"
    a = _args(tmp_path, stop_after_min=1.0)
    t0 = L.T_START
    try:
        L.T_START = time.time() - 120.0
        st = L.run_job(job, a, solar=True)
    finally:
        L.T_START = t0
    assert st["stopped_before"] == "strict" and "finished" not in st
    saved = json.load(open(os.path.join(a.work, job, "study.json")))
    assert saved["stopped_before"] == "strict" and "finished" not in saved
    assert os.path.exists(os.path.join(a.work, job, "study.html"))
    # resumed with every variant already done (here: marked done by hand), the chunk finishes and clears the stop
    for name, kw, status, note in L.variants_for(L.JOB_SPECS[job], solar=True):
        saved["rows"].setdefault(name, {"name": name, "label": L.label(name), "status": status, "note": note,
                                        "done": True})
    json.dump(saved, open(os.path.join(a.work, job, "study.json"), "w"))
    st2 = L.run_job(job, _args(tmp_path), solar=True)
    assert "stopped_before" not in st2 and st2.get("finished")
