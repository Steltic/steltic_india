"""multi_unit.py -- several seismically separated units in one job (X04, HR-D-13, HR-C-06).

Each unit is its own structure (own diaphragms, ESM / RSA, drift) and runs as its own sub-job
<jobs root>/<name>/units/<unit>/ through pipeline.design_and_report (figure names are sanitised for the nested name,
H45).  The driver then computes the IS 1893 7.11.3 separation of every declared joint from the two units' 7.11.1
displacements (calc_package 'unit_displacements', the same governing drift run the unit's own drift check uses) and
writes ONE combined STATUS (worst unit status + the joint checks), a units index (report links) and a combined
summary json in <jobs root>/<name>/.  Units are NOT combined into one OpenSees domain (no shared diaphragm groups).

    import pipeline
    res = pipeline.design_units("IN_Ex11", {"A": cfg_a, "B": cfg_b, "C": cfg_c},
                                joints=[{"units": ["A", "B"], "direction": "X", "gap_mm": 100.0},
                                        {"units": ["B", "C"], "direction": "Y", "gap_mm": 75.0,
                                         "base_mm": {"C": 1200.0}}])

joint keys
  units            [unit_1, unit_2] (ids of cfg_units)
  direction        "X" | "Y": the direction normal to the joint (the units oscillate towards each other along it)
  gap_mm           the provided separation (a missing gap leaves the joint check open -> PARTIAL)
  same_floor_levels  None (default: decided from the level elevations) | True | False.  IS 1893 7.11.3 (Amd 1):
                   (R1 D1 + R2 D2)/2 only when the floor levels of the two units are at the same level -- every level of
                   the lower unit matches a level of the other within level_tol_mm; otherwise R1 D1 + R2 D2.  A declared
                   True whose levels do not match falls back to the full form (recorded).  False forces the full form.
  levels           optional {unit: level} (1-based): evaluate only this matching pair
  base_mm          optional {unit: elevation of the unit's base above a common datum} (stepped sites), default 0
  level_tol_mm     elevation tolerance for "the same level" (default 50 mm)
  id               optional joint name
With matching floor levels the required separation is evaluated at every matched level pair and the largest governs.
Otherwise D_i = the largest displacement of unit i over its levels up to and including the first level at or above the
top of the adjacent unit (the contact height; the levels above it cannot pound), R_i = that unit's R in the joint
direction.
"""
from __future__ import annotations

import json
import os
import re

CLAUSE = "IS 1893 7.11.3"
_UNIT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _level_elev(disp, base):
    return [float(base) + float(z) for z in disp.get("z_mm") or []]


def joint_separation(joint, disp1, disp2):
    """IS 1893 7.11.3 required separation of one joint from the two units' displacement records
    ({disp_max_mm: [per level], z_mm: [level elevations above the unit base], R}).  Returns the check record
    {value, limit, dc, ok, clause, cite, source, ...}."""
    import india_seismic as IS
    u1, u2 = [str(u) for u in joint["units"]]
    d = str(joint.get("direction", "X")).upper()
    base = joint.get("base_mm") or {}
    tol = float(joint.get("level_tol_mm", 50.0))
    gap = joint.get("gap_mm")
    rec = {"id": joint.get("id") or "%s-%s" % (u1, u2), "units": [u1, u2], "direction": d, "limit": gap,
           "clause": CLAUSE, "source": "multi_unit.joint_separation (unit calc_package unit_displacements)"}
    missing = [u for u, dd in ((u1, disp1), (u2, disp2)) if not dd or not dd.get("disp_max_mm") or dd.get("R") is None]
    if missing:
        rec.update(value=None, dc=None, ok=None,
                   reason="7.11.1 displacements / R of unit(s) %s in direction %s not available" % (missing, d))
        return rec
    D1, D2 = [float(x) for x in disp1["disp_max_mm"]], [float(x) for x in disp2["disp_max_mm"]]
    z1, z2 = _level_elev(disp1, base.get(u1, 0.0)), _level_elev(disp2, base.get(u2, 0.0))
    R1, R2 = float(disp1["R"]), float(disp2["R"])
    rec["R"] = {u1: R1, u2: R2}
    # matched level pairs (same elevation within tol)
    pairs = []
    for a, za in enumerate(z1):
        for b, zb in enumerate(z2):
            if abs(za - zb) <= tol:
                pairs.append((a + 1, b + 1))
    lv = joint.get("levels")
    if lv:
        pin = (int(lv[u1]), int(lv[u2]))
        if not (1 <= pin[0] <= len(D1) and 1 <= pin[1] <= len(D2)):
            rec.update(value=None, dc=None, ok=None, reason="joint levels %s out of range" % lv)
            return rec
        cand = [pin]
        matched = pin in pairs
        match_basis = "declared levels %s: elevations %.0f / %.0f mm" % (lv, z1[pin[0] - 1], z2[pin[1] - 1])
    else:
        cand = pairs
        lower_is_1 = z1[-1] <= z2[-1]
        n_lower = len(z1) if lower_is_1 else len(z2)
        got = {p[0] if lower_is_1 else p[1] for p in pairs}
        matched = n_lower > 0 and len(got) == n_lower
        match_basis = ("%d of %d levels of the lower unit %s match a level of %s within %.0f mm"
                       % (len(got), n_lower, u1 if lower_is_1 else u2, u2 if lower_is_1 else u1, tol))
    decl = joint.get("same_floor_levels")
    if decl is False:
        same, basis = False, "declared False"
    elif decl is True:
        same = matched
        basis = "declared True; " + match_basis + ("" if matched else " -> NOT the same levels: full form R1 D1 + R2 D2")
    else:
        same, basis = matched, "from the level elevations: " + match_basis
    rec["same_floor_levels"] = same
    rec["same_floor_levels_basis"] = basis
    if same and cand:
        per = []
        for (a, b) in cand:
            r_ = IS.separation_required(R1, D1[a - 1], R2, D2[b - 1], True)
            per.append({"levels": {u1: a, u2: b}, "elev_mm": {u1: z1[a - 1], u2: z2[b - 1]},
                        "D_mm": {u1: D1[a - 1], u2: D2[b - 1]}, "required_mm": r_["required_mm"], "cite": r_["cite"]})
        g = max(per, key=lambda p: p["required_mm"])
        rec.update(value=g["required_mm"], cite=g["cite"], governing_levels=g["levels"], D_mm=g["D_mm"],
                   per_level=per, D_basis="displacement at the matching level (7.11.1, per unit)")
    else:
        def upto(D, z, top_other):
            k = next((i for i, zz in enumerate(z) if zz >= top_other - tol), len(z) - 1)
            return max(D[:k + 1]), k + 1
        a_, ka = upto(D1, z1, z2[-1])
        b_, kb = upto(D2, z2, z1[-1])
        r_ = IS.separation_required(R1, a_, R2, b_, False)
        rec.update(value=r_["required_mm"], cite=r_["cite"], D_mm={u1: a_, u2: b_},
                   governing_levels={u1: ka, u2: kb},
                   D_basis="largest displacement of each unit up to the first level at/above the top of the other unit "
                           "(contact height)")
    rec["dc"] = (rec["value"] / float(gap)) if gap else None
    rec["ok"] = (rec["value"] <= float(gap)) if gap is not None else None
    if gap is None:
        rec["reason"] = "joint gap_mm not declared (the provided separation is needed for the check)"
    return rec


def _unit_status(out, pkg):
    st = out.get("design_status") or (pkg or {}).get("design_status") or {}
    if out.get("blocked"):
        return "partial", ["unit blocked: %s" % (out.get("error") or "preflight ERRORs")]
    if out.get("unit_error"):
        return "partial", ["unit run failed: %s" % out["unit_error"]]
    if not pkg:
        return "partial", ["no calc_package.json"]
    return str(st.get("status") or "partial"), list(st.get("reasons") or [])


def design_units(name, cfg_units, joints=None, do_report=True):
    """Run each unit as its own sub-job <name>/units/<unit>, then the 7.11.3 joints; write the combined STATUS,
    units index and units_summary.json in <jobs root>/<name>.  Returns the combined summary dict."""
    import pipeline as P
    import package_finalize as PF
    joints = list(joints or [])
    if not cfg_units:
        raise ValueError("design_units: cfg_units is empty")
    for u in cfg_units:
        if not _UNIT_RE.match(str(u)):
            raise ValueError("design_units: unit id %r must be a plain name ([A-Za-z0-9_.-], no '/')" % (u,))
    for jt in joints:
        us = jt.get("units") or []
        if len(us) != 2 or any(u not in cfg_units for u in us) or us[0] == us[1]:
            raise ValueError("design_units: joint %r must name two different declared units" % (jt,))
        if str(jt.get("direction", "X")).upper() not in ("X", "Y"):
            raise ValueError("design_units: joint %r direction must be 'X' or 'Y'" % (jt,))
    root = P._root(name)
    os.makedirs(os.path.join(root, "units"), exist_ok=True)
    units = {}
    for u, cfg in cfg_units.items():
        sub = "%s/units/%s" % (name, u)
        try:
            out = P.design_and_report(sub, cfg, do_report=do_report)
        except Exception as ex:                       # one unit failing must not hide the others
            out = {"root": P._root(sub), "unit_error": "%s: %s" % (type(ex).__name__, ex)}
        uroot = out.get("root") or P._root(sub)
        cp = os.path.join(uroot, "design", "calc_package.json")
        pkg = json.load(open(cp)) if os.path.exists(cp) and not out.get("blocked") and not out.get("unit_error") else None
        status, reasons = _unit_status(out, pkg)
        rep = os.path.join(uroot, "report.html")
        units[u] = {"job": sub, "root": uroot, "status": status, "reasons": reasons,
                    "report_html": rep if os.path.exists(rep) else None,
                    "displacements": (pkg or {}).get("unit_displacements") or {},
                    "model_valid": out.get("model_valid")}
    jrecs = []
    for jt in joints:
        u1, u2 = jt["units"]
        d = str(jt.get("direction", "X")).upper()
        jrecs.append(joint_separation(jt, units[u1]["displacements"].get(d), units[u2]["displacements"].get(d)))
    reasons = []
    for u, r in units.items():
        reasons += ["unit %s: %s" % (u, x) for x in r["reasons"]]
    joint_status = "complete"
    for j in jrecs:
        if j.get("ok") is not True:
            joint_status = "partial"
            if j.get("ok") is False:
                reasons.append("joint %s (%s): %s required separation %.1f mm > provided gap %.1f mm"
                               % (j["id"], j["direction"], CLAUSE, j["value"], float(j["limit"])))
            else:
                reasons.append("joint %s (%s): %s not evaluated -- %s" % (j["id"], j["direction"], CLAUSE,
                                                                        j.get("reason") or "?"))
    status = PF.worst_status([r["status"] for r in units.values()] + [joint_status])
    authority = ("multi_unit.design_units: worst of the unit statuses (india_seismic_gates.design_status per unit) "
                 "and the IS 1893 7.11.3 joint checks")
    unit_lines = ["%s: %s (units/%s/STATUS.engine.md, units/%s/report.html)" % (u, r["status"].upper(), u, u)
                  for u, r in units.items()]
    joint_lines = [("%s %s-%s dir %s: required %s mm vs gap %s mm -> %s (%s)" %
                    (j["id"], j["units"][0], j["units"][1], j["direction"],
                     "%.1f" % j["value"] if j.get("value") is not None else "n/a", j.get("limit"),
                     {True: "OK", False: "FAIL", None: "NOT EVALUATED"}[j.get("ok")], j.get("cite") or CLAUSE))
                   for j in jrecs]
    files = PF.write_status(root, name, status, authority, reasons,
                            sections=[("Units", unit_lines), ("Joints (IS 1893 7.11.3)", joint_lines or ["none declared"])])
    summary = {"name": name, "root": root, "status": status, "authority": authority, "n_reasons": len(reasons),
               "reasons": reasons, "units": {u: {k: v for k, v in r.items()} for u, r in units.items()},
               "joints": jrecs, "status_files": files}
    summary["units_index"] = os.path.join(root, "units_index.html")
    summary["summary_json"] = os.path.join(root, "units_summary.json")
    rows = []
    for u, r in units.items():
        link = ("html", "<a href='units/%s/report.html'>units/%s/report.html</a>" % (u, u)) if r["report_html"] \
            else "not rendered"
        rows.append([u, r["status"].upper(), link, len(r["reasons"])])
    jrows = [[j["id"], "%s / %s" % tuple(j["units"]), j["direction"],
              "%.1f" % j["value"] if j.get("value") is not None else "n/a", j.get("limit"),
              "%.3f" % j["dc"] if j.get("dc") is not None else "n/a",
              {True: "OK", False: "FAIL", None: "NOT EVALUATED"}[j.get("ok")],
              j.get("same_floor_levels_basis") or j.get("reason") or "", j.get("cite") or CLAUSE] for j in jrecs]
    page = PF.html_index("%s -- units" % name,
                         "Combined design status: %s. Each unit is a separate structure (own model, analysis and "
                         "report); joints are checked to IS 1893 7.11.3 from the units' 7.11.1 displacements." % status.upper(),
                         [("Units", ["unit", "status", "report", "open reasons"], rows),
                          ("Joints (IS 1893 7.11.3)", ["joint", "units", "dir", "required mm", "gap mm", "D/C", "result",
                                                       "basis", "cite"], jrows)])
    with open(summary["units_index"], "w", encoding="utf-8") as f:
        f.write(page)
    with open(summary["summary_json"], "w") as f:
        json.dump(summary, f, indent=1, default=str)
    return summary
