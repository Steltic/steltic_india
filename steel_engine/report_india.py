"""India report mode (WP1.13 / WP2.10): the 13-chapter EOR report built from the India analysis
(engine3d.run_india), the generated combinations and the calc package -- IS 800:2007, IS 875 Parts 1-5
and IS 1893 (Part 1):2016 with Amendments 1 and 2 only.  Units: kN, kN-m, m, mm, MPa.

report.build_report dispatches here for India jobs.  Nothing in this module falls back to a foreign
code: a missing input is shown as "not evaluated" with the reason.
"""
from __future__ import annotations

import datetime
import json
import os
import re

import engine3d as E

CHAPTERS_IN = {
    1: ("Design basis & codes", [
        "Governing Indian Standards and editions stated: IS 800:2007, IS 875 Parts 1-5, IS 1893 (Part 1):2016 "
        "with Amendments 1 and 2, IS 808, IS 2062, IS 1161, IS 816 / IS 4000 where used.",
        "Importance factor (IS 1893 Table 8), zone and soil type, occupancy and imposed loads match the brief.",
        "Units (N, mm, MPa; kN/m2 for area loads) stated and consistent.",
        "Design status from india_seismic_gates.design_status stated with every open reason."]),
    2: ("Structural system & load path", [
        "Lateral system per direction with its IS 1893 Table 9 R and the IS 800 Section 12 detailing class.",
        "Rigid diaphragm; collector and chord forces from the diaphragm load path added to the beam checks.",
        "Plan and vertical irregularities screened (IS 1893 Tables 5 and 6, Amd 2) with their consequences."]),
    3: ("Loads", [
        "Dead (incl. member self-weight), imposed (IS 875 Part 2 by occupancy, partitions 3.1.2), roof imposed "
        "and snow.",
        "Wind (IS 875 Part 3): Vb, k1-k4, Kd, Ka, Kc, pz, pd, Cpe / Cpi; dynamic effects where 9.1 applies.",
        "Earthquake (IS 1893): Z, I, R, soil, Ta, Sa/g, Ah, seismic weight W, V_B and its distribution.",
        "Governing lateral load per direction."]),
    4: ("Load combinations", [
        "IS 800 Table 4 set with both signs; IS 1893 6.3 directional and vertical rules; 7.8.2 eccentricity; "
        "IS 800 12.2.3; IS 800 4.3.6 notional loads; crane and member-wind rows where applicable.",
        "Each combination analysed as one factored second-order case."]),
    5: ("Analysis model", [
        "Geometry, sections and orientation match the drawings; joints and bases as detailed.",
        "Modal properties: periods and at least 90 % participating mass (IS 1893 7.7.5.2).",
        "Response spectrum scaled to V-bar_B (7.7.3.1); displacements not scaled (7.7.3.2)."]),
    6: ("Member design (IS 800)", [
        "Every member group checked per combination with concurrent forces: IS 800 6 (tension), 7.1.2 "
        "(compression), 8.2 (bending incl. LTB), 8.4 (shear), 9.3 (interaction).",
        "Governing D/C <= 1.0; inputs (grades by thickness, LLT per moment sign, K) sourced."]),
    7: ("Stability & second-order", [
        "P-Delta included in every combination; IS 800 4.3.6 notional horizontal loads with the gravity "
        "combinations."]),
    8: ("Serviceability", [
        "IS 1893 7.11.1.1 storey drift <= 0.004 h at gamma 1.0 at the extreme column lines.",
        "IS 1893 7.11.2 deformation compatibility (R x drift) and 7.11.3 separation.",
        "IS 800 Table 6: wind drift / deflection, floor and roof deflection, crane sway where applicable."]),
    9: ("Earthquake detailing (IS 800 Section 12)", [
        "Section 12 checks for the declared system; capacity-design forces for columns and connections."]),
    10: ("Connections", [
        "Every connection type designed to IS 800 Section 10 (bolts 10.3 / 10.4, welds 10.5, block shear 6.4) "
        "and IS 800 7.4 (bases) at the Section 12 forces where required."]),
    11: ("Foundations interface", [
        "Column base reactions (compression, uplift, shear) for the foundation design."]),
    12: ("Drawings, specifications & documentation", [
        "Drawings and specifications consistent with this package (outside the analysis package)."]),
    13: ("QA / professional acceptance", [
        "Analysis gates, design status, grounding in the Indian Standards corpus, numerical self-consistency.",
        "Independent check and the EOR seal (outside the automated package)."]),
}


def _R():
    import report as R
    return R


def _t(headers, rows):
    return _R()._table(headers, rows)


def _chapter(n, status=None):
    title, items = CHAPTERS_IN[n]
    li = "".join(f"<li>{t}</li>" for t in items)
    extra = f" &mdash; <span class='chk-status'>{status}</span>" if status else ""
    return (f"<h2>Chapter {n} &mdash; {title}</h2>"
            f"<div class='chk'><div class='chk-h'>Reviewer acceptance items{extra}</div><ul>{li}</ul></div>")


def _toc():
    rows = "".join(f"<li><b>Chapter {n}</b> &mdash; {CHAPTERS_IN[n][0]}</li>" for n in range(1, 14))
    return ("<h2>Report structure &mdash; EOR review checklist</h2><p>One chapter per checklist section. "
            "Appendix A: member checks by group; Appendix B: combinations; Appendix C: activity log.</p>"
            "<ol class='toc'>" + rows + "</ol>")


def _kN(v, d=1):
    try:
        return f"{float(v) / 1e3:,.{d}f}"
    except Exception:
        return "&mdash;"


def _kNm(v, d=1):
    try:
        return f"{float(v) / 1e6:,.{d}f}"
    except Exception:
        return "&mdash;"


def _m(v, d=2):
    try:
        return f"{float(v) / 1e3:,.{d}f}"
    except Exception:
        return "&mdash;"


def _num(v, d=3):
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int, float)):
        return f"{v:.{d}f}".rstrip("0").rstrip(".") if abs(v) < 1e6 else f"{v:,.0f}"
    return "&mdash;" if v is None else str(v)


def _ok(v):
    return "&mdash;" if v is None else ("OK" if v else "<b>NG</b>")


def _plan_fig(cfg):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    NX, NY = cfg["NX"], cfg["NY"]
    pres = set(tuple(p) for p in E.grid(cfg, 1))
    fig, ax = plt.subplots(figsize=(8, 6))
    for (i, j) in pres:
        x, y = E._xy_in(cfg, i, j)
        ax.plot([x / 1e3], [y / 1e3], "ks", ms=4)
        ax.annotate(f"({i},{j})", (x / 1e3, y / 1e3), textcoords="offset points", xytext=(3, 3), fontsize=7)
    for i in range(NX + 1):
        pts = sorted([E._xy_in(cfg, i, j) for j in range(NY + 1) if (i, j) in pres], key=lambda p: p[1])
        if len(pts) > 1:
            ax.plot([p[0] / 1e3 for p in pts], [p[1] / 1e3 for p in pts], color="#bbb", lw=0.8)
    for j in range(NY + 1):
        pts = sorted([E._xy_in(cfg, i, j) for i in range(NX + 1) if (i, j) in pres], key=lambda p: p[0])
        if len(pts) > 1:
            ax.plot([p[0] / 1e3 for p in pts], [p[1] / 1e3 for p in pts], color="#bbb", lw=0.8)
    ax.set_aspect("equal"); ax.set_xlabel("X (m)"); ax.set_ylabel("Y (m)")
    ax.set_title("Plan grid, level 1: column positions (i, j)")
    return _R()._b64(fig)


def _drift_fig(cfg, run):
    import matplotlib.pyplot as plt
    NF = len(cfg["heights"])
    fig, ax = plt.subplots(figsize=(8, 5))
    for d, mk in (("X", "-o"), ("Y", "-s")):
        dr = (run.get("drift") or {}).get(d)
        if dr:
            ax.plot([x * 100 for x in dr["drift"]], list(range(1, NF + 1)), mk, label=f"storey drift {d}")
    lim = run.get("drift_limits") or [0.004] * NF
    ax.plot([x * 100 for x in lim], list(range(1, NF + 1)), "r--", label="limit (IS 1893 7.11.1.1)")
    ax.set_xlabel("storey drift (% of storey height)"); ax.set_ylabel("storey")
    ax.set_title("Storey drift at the extreme column lines (gamma 1.0, 7.8.2 eccentricity)")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)
    return _R()._b64(fig)


def _codes_table(cfg, pkg):
    rows = [["IS 800:2007", "General construction in steel &mdash; limit state design"],
            ["IS 875 (Part 1):2026 / Part 2:1987", "Dead loads / imposed loads"],
            ["IS 875 (Part 3):2015", "Wind loads"],
            ["IS 875 (Part 4):1987 / Part 5:1987", "Snow loads / special loads and combinations"],
            ["IS 1893 (Part 1):2016 + Amd 1 (2017) + Amd 2 (2020)", "Earthquake resistant design"],
            ["IS 808:2021 / IS 2062:2025 / IS 1161:2014", "Rolled sections / structural steel / steel tubes"],
            ["IS 816 / IS 4000", "Welding / high-strength friction grip bolts (where used)"]]
    if str(cfg.get("system") or "").upper() in ("EBF",):
        rows.append(["IS 18168:2023", "Eccentrically braced frames (EOR basis)"])
    return _t(["Standard", "Scope"], rows)


def _status_block(pkg):
    st = (pkg or {}).get("design_status") or {}
    if not st:
        return "<p class='note'>Design status not recorded (run the pipeline).</p>"
    reasons = st.get("reasons") or []
    head = (f"<p><b>Design status: {st.get('status', '?').upper()}</b> "
            f"(authority: <code>{st.get('authority', 'india_seismic_gates.design_status')}</code>; "
            f"{st.get('n_reasons', len(reasons))} open reason(s)).</p>")
    if not reasons:
        return head
    rows = [[i + 1, r] for i, r in enumerate(reasons[:60])]
    more = f"<p class='note'>&hellip; {len(reasons) - 60} further reasons in calc_package.json.</p>" if len(reasons) > 60 else ""
    return head + _t(["#", "open reason"], rows) + more


def _systems(cfg, pkg):
    import india_seismic_gates as G
    ss = ((cfg.get("load_plan") or {}).get("seismic_summary") or {})
    rows = [["Seismic force-resisting system", str(cfg.get("system") or "&mdash;")],
            ["Response reduction factor R (IS 1893 Table 9)", _num(G.declared_R(cfg))],
            ["Importance factor I (IS 1893 Table 8)", _num(G.importance_of(cfg))],
            ["Zone / Z", "%s / %s" % (G.zone_of(cfg), _num(ss.get("Z")))],
            ["Soil type", str(ss.get("soil") or (cfg.get("seis") or {}).get("soil") or "&mdash;")],
            ["Brace configuration", str(cfg.get("brace_config") or "&mdash;")],
            ["Column bases / joints", "%s / %s" % ((cfg.get("model") or {}).get("bases", cfg.get("base")),
                                                   (cfg.get("model") or {}).get("joints", "&mdash;"))],
            ["Diaphragm", str(cfg.get("diaphragm") or "rigid")]]
    return _t(["Item", "Value"], rows)


def _collectors(pkg):
    c = (pkg or {}).get("collectors")
    if not isinstance(c, dict):
        return "<p class='note'>Collector / chord forces not recorded.</p>"
    if c.get("error"):
        return f"<p class='note'><b>Collector / chord forces NOT computed:</b> {c['error']}</p>"
    rows = [r for r in (c.get("rows") or []) if isinstance(r, dict) and "N_N" in r]
    best = {}
    for r in rows:
        k = (r.get("kind"), r.get("dir"), r.get("level"), r.get("role"))
        if k not in best or abs(r["N_N"]) > abs(best[k]["N_N"]):
            best[k] = r
    tab = [[k[0], k[1], k[2], k[3], _kN(abs(v["N_N"]))] for k, v in sorted(best.items(), key=lambda kv: str(kv[0]))]
    return ("<p>Axial forces in collectors (drag struts) and chords per unit lateral factor from the diaphragm "
            "load path (equilibrium of the analysed rigid-diaphragm model); they are multiplied by each "
            f"combination's f<sub>E</sub> / f<sub>W</sub> and added to the beam checks ({c.get('n_beams_with_axial', 0)} "
            "beams).</p>" + _t(["load", "dir", "level", "role", "max |N| (kN)"], tab[:40]))


def _irregularity(pkg):
    irr = (pkg or {}).get("irregularity") or {}
    if irr.get("error"):
        return f"<p class='note'>{irr['error']}</p>"
    rows = []
    for k, v in irr.items():
        if isinstance(v, dict):
            rows.append([k.replace("_", " "), _ok(not v.get("irregular")) if "irregular" in v else "&mdash;",
                         str(v.get("verdict") or "")[:220], str(v.get("clause") or "")])
    return _t(["screen", "regular?", "finding", "clause"], rows)


def _gravity_table(cfg):
    rows = [["Floor dead load D_floor", _num(cfg.get("D_floor")), "kN/m2"],
            ["Roof dead load D_roof", _num(cfg.get("D_roof")), "kN/m2"],
            ["Floor imposed load (IS 875 Part 2)", _num(cfg.get("L_floor")), "kN/m2"],
            ["Partition allowance (IS 875-2 3.1.2)", _num(cfg.get("partition_load_kNm2")), "kN/m2"],
            ["Roof imposed load Lr (IS 875-2 Table 2)", _num(cfg.get("Lr")), "kN/m2"],
            ["Snow (IS 875 Part 4)", _num(cfg.get("snow")), "kN/m2"],
            ["Cladding", _num(cfg.get("clad")), "kN/m2 of wall"],
            ["Member self-weight", "from the sections (78.5 kN/m3)", ""],
            ["Floor system", "%s%s" % (cfg.get("floor_system") or "one-way",
                                        (", deck spans " + str(cfg.get("deck_span"))) if cfg.get("deck_span") else ""), ""]]
    return _t(["Load", "Value", "Unit"], rows)


def _seismic_table(cfg, pkg, run):
    plan = cfg.get("load_plan") or {}
    ss = plan.get("seismic_summary") or {}
    sc = (pkg or {}).get("seismic_calc") or {}
    keys = [("Z", "zone factor Z (Table 3 / Annex E)"), ("I", "importance factor I (Table 8)"),
            ("R", "response reduction factor R (Table 9)"), ("soil", "soil type"),
            ("Ta_x_s", "Ta X (s) (7.6.2)"), ("Ta_y_s", "Ta Y (s) (7.6.2)"), ("Ta_s", "Ta (s)"),
            ("Sa_g", "Sa/g"), ("Ah", "Ah = (Z/2)(I/R)(Sa/g) (6.4.2)"), ("W_kN", "seismic weight W (kN) (7.4)"),
            ("VB_x_kN", "V_B X (kN)"), ("VB_y_kN", "V_B Y (kN)"), ("VB_kN", "V_B (kN)")]
    rows = [[lab, _num(ss.get(k))] for k, lab in keys if ss.get(k) is not None]
    rows.append(["engine seismic weight (kN)", _num(sc.get("W_engine_kN"), 1)])
    sa = (pkg or {}).get("seismic_analysis") or {}
    rows.append(["analysis method (7.7.1)", str(sa.get("method") or run.get("method"))])
    out = _t(["Quantity", "Value"], rows)
    sf = (plan.get("story_forces") or {})
    import india_loads as IL
    try:
        scl = IL._story_force_scale(plan)
    except Exception:
        scl = None
    if scl and (sf.get("EQ_X") or sf.get("EQ_Y")):
        NF = len(cfg["heights"])
        tab = []
        for k in range(1, NF + 1):
            fx = (sf.get("EQ_X") or {}).get(str(k), (sf.get("EQ_X") or {}).get(k, [0]))
            fy = (sf.get("EQ_Y") or {}).get(str(k), (sf.get("EQ_Y") or {}).get(k, [0, 0]))
            fx = fx.get("fx", 0) if isinstance(fx, dict) else fx[0]
            fy = fy.get("fy", 0) if isinstance(fy, dict) else (fy[1] if len(fy) > 1 else 0)
            tab.append([k, _kN(float(fx) * scl), _kN(float(fy) * scl)])
        out += "<h4>ESM story forces Q<sub>i</sub> (7.6.3), unfactored</h4>" + _t(["level", "X (kN)", "Y (kN)"], tab)
    if sa.get("scale"):
        tab = [[d, _num(v.get("VB_rsa_kN"), 1), _num(v.get("VBbar_kN"), 1), _num(v.get("scale"), 3),
                _num(v.get("mass_participation"), 3)] for d, v in sa["scale"].items()]
        out += ("<h4>Response spectrum analysis (7.7)</h4><p>CQC with 5 % damping (7.7.5.3); base shear scaled up to "
                "V&#772;<sub>B</sub> from Ta (7.7.3.1); displacements are not scaled (7.7.3.2).</p>"
                + _t(["dir", "V_B RSA (kN)", "V&#772;_B (kN)", "scale", "mass participation"], tab))
    return out


def _wind_table(cfg):
    ws = (cfg.get("load_plan") or {}).get("wind_summary") or {}
    if not ws:
        return "<p class='cnote'>No wind summary in the load plan.</p>"
    keys = ["Vb_mps", "Vb_source", "terrain_category", "k1", "k2", "k3", "k4", "Kd", "Ka", "Ka_basis", "Kc",
            "Vz_mps", "pz_kNm2", "pd_kNm2", "Cpe_windward", "Cpe_leeward", "Cpi", "cyclone_belt", "VB_x_kN", "VB_y_kN"]
    rows = [[k, _num(ws.get(k))] for k in keys if ws.get(k) is not None]
    return ("<p>IS 875 (Part 3):2015: V<sub>z</sub> = V<sub>b</sub> k<sub>1</sub> k<sub>2</sub> k<sub>3</sub> "
            "k<sub>4</sub> (6.3); p<sub>z</sub> = 0.6 V<sub>z</sub><sup>2</sup> (7.2); p<sub>d</sub> = K<sub>d</sub> "
            "K<sub>a</sub> K<sub>c</sub> p<sub>z</sub> &ge; 0.7 p<sub>z</sub> (7.2).</p>"
            + _t(["Quantity", "Value"], rows))


def _governing(cfg):
    plan = cfg.get("load_plan") or {}
    ss = plan.get("seismic_summary") or {}
    ws = plan.get("wind_summary") or {}
    rows = []
    for d in ("X", "Y"):
        eq = ss.get("VB_%s_kN" % d.lower(), ss.get("VB_kN"))
        w = ws.get("VB_%s_kN" % d.lower())
        gov = "&mdash;"
        if eq is not None and w is not None:
            gov = "earthquake (1.5 EL)" if 1.5 * float(eq) >= 1.5 * float(w) else "wind (1.5 WL)"
        rows.append([d, _num(eq, 1), _num(w, 1), gov])
    return ("<p>Characteristic base shears; both are carried through every combination, so the governing "
            "effect is taken member by member.</p>" + _t(["dir", "V_B earthquake (kN)", "V_B wind (kN)",
                                                           "larger lateral"], rows))


def _modal_table(run):
    modes = run.get("modes") or []
    rows = []
    for i, m in enumerate(modes[:9]):
        T = m.get("T") if isinstance(m, dict) else None
        rows.append([i + 1, _num(T, 3), _num(m.get("mass_x"), 3), _num(m.get("mass_y"), 3), _num(m.get("rot"), 3)])
    if not rows and run.get("T"):
        rows = [[i + 1, _num(t, 3), "", "", ""] for i, t in enumerate(run["T"][:9])]
    return _t(["mode", "T (s)", "mass X", "mass Y", "rotation"], rows)


def _members(pkg):
    mem = (pkg or {}).get("members") or []
    if not mem:
        return "<p class='note'>No members in the calc package.</p>"
    rows = []
    for m in mem:
        i = m.get("inputs") or {}
        rows.append([m.get("id"), i.get("section"), i.get("n_elements", ""), i.get("governing_combo", ""),
                     _kN(i.get("P_comp_N")), _kN(i.get("P_tens_N")), _kNm(i.get("Mz_Nmm")), _kNm(i.get("My_Nmm")),
                     _kN(i.get("V_N")), _num(m.get("DC")) if isinstance(m.get("DC"), (int, float)) else "not evaluated"])
    return _t(["group", "section", "n", "governing combination", "P<sub>c</sub> (kN)", "P<sub>t</sub> (kN)",
               "M<sub>z</sub> (kN-m)", "M<sub>y</sub> (kN-m)", "V (kN)", "D/C"], rows)


def _checks_table(checks, max_rows=400):
    rows = []
    for c in (checks or [])[:max_rows]:
        if not isinstance(c, dict):
            continue
        rows.append([c.get("name") or c.get("id") or "", str(c.get("member") or ""), _num(c.get("value")),
                     _num(c.get("limit")), _num(c.get("dc")), _ok(c.get("ok")), c.get("clause") or "",
                     c.get("source") or ""])
    return _t(["check", "member", "value", "limit", "D/C", "status", "Ref. (IS 800)", "source"], rows)


def _is800_s12_detailing(cfg, pkg):
    """Chapter 9 from calc_package.capacity_design (india_is800_s12.section12_checks)."""
    cap = (pkg or {}).get("capacity_design") or {}
    if cap.get("error"):
        return f"<p class='note'><b>Section 12 checks not evaluated:</b> {cap['error']}</p>"
    s12 = cap.get("section12") or {}
    checks = s12.get("checks") or []
    if not checks:
        return "<p class='note'>No Section 12 checks recorded.</p>"
    fails = [c for c in checks if c.get("ok") is False]
    notev = [c for c in checks if c.get("ok") is None]
    summ = (f"<p>System <b>{cap.get('system')}</b>, R = {_num(cap.get('R'))}: {len(checks)} checks, "
            f"{len(fails)} failing, {len(notev)} not evaluated (missing inputs block COMPLETE).</p>")
    by = {}
    for c in checks:
        by.setdefault(c.get("id"), []).append(c)
    rows = []
    for cid, cs in by.items():
        worst = max(cs, key=lambda c: (c.get("ok") is False, c.get("ok") is None,
                                        c.get("dc") if isinstance(c.get("dc"), (int, float)) else -1))
        nf = sum(1 for c in cs if c.get("ok") is False); nn = sum(1 for c in cs if c.get("ok") is None)
        rows.append([cid, len(cs), nf, nn, _num(worst.get("value")), _num(worst.get("limit")), _num(worst.get("dc")),
                     worst.get("clause") or ""])
    return summ + _t(["check", "n", "failing", "not evaluated", "worst value", "limit", "worst D/C",
                      "Ref. (IS 800)"], rows)


def _connections(pkg):
    con = (pkg or {}).get("connections") or []
    rows = []
    for c in con:
        dem = c.get("demand") or {}
        dtxt = "; ".join(f"{k.replace('_N', '').replace('_Nmm', '')} = "
                         + (_kNm(v) + " kN-m" if k.endswith("_Nmm") else _kN(v) + " kN")
                         for k, v in dem.items() if isinstance(v, (int, float)))
        n_ok = sum(1 for x in (c.get("checks") or []) if isinstance(x, dict) and x.get("ok") is True)
        rows.append([c.get("id"), c.get("type"), dtxt, len(c.get("checks") or []), n_ok,
                     _num(c.get("DC")) if isinstance(c.get("DC"), (int, float)) else "not designed"])
    return _t(["connection", "type", "demand (incl. IS 800 12.2.3 where tagged)", "checks", "passing", "D/C"], rows)


def _serviceability(cfg, pkg, run):
    out = []
    dt = (pkg or {}).get("drift_table") or []
    if dt:
        rows = [[r["storey"], r["dir"], _num(r["drift"], 5), _num(r["limit"], 4), _num(r.get("dc"), 3), _ok(r.get("ok"))]
                for r in dt]
        out.append("<h3>Storey drift (IS 1893 7.11.1.1)</h3><p>Under V<sub>B</sub> with &gamma; = 1.0, measured at every "
                   "column line with the 7.8.2 design eccentricity, P-&Delta; with 1.0 DL + 1.0 LL. Limit 0.004 h "
                   "(soft storeys per Table 6(i) as screened).</p>"
                   + _t(["storey", "dir", "drift / h", "limit", "D/C", "status"], rows))
        try:
            out.append(_R()._img(_drift_fig(cfg, run), "Storey drift profile"))
        except Exception as ex:
            out.append(f"<p class='note'>[drift figure failed: {ex}]</p>")
    dc = (pkg or {}).get("deformation_compatibility")
    if isinstance(dc, dict):
        rows = [[c.get("element"), c.get("section"), _num(c.get("value")), _num(c.get("limit")), _ok(c.get("ok")),
                 c.get("cite") or ""] for c in (dc.get("checks") or [])[:30]]
        out.append("<h3>Deformation compatibility (IS 1893 7.11.2)</h3>" +
                   (_t(["element", "section", "value", "limit", "status", "basis"], rows) if rows else
                    "<p>No non-SFRS member requires the check in this zone.</p>"))
        sep = dc.get("separation") or []
        if sep:
            out.append("<h4>Separation between adjacent units (7.11.3)</h4>" + _checks_table(sep))
    out.append(_R()._india_wind_serviceability_html(cfg))
    bd = (pkg or {}).get("beam_deflection") or []
    if bd:
        rows = [[r["section"], _m(r["span_mm"]), "roof" if r["roof"] else "floor", _num(r["delta_mm"], 2),
                 _num(r["limit_mm"], 2), _num(r["ratio"], 3)] for r in bd]
        out.append("<h3>Imposed-load deflection (IS 800 Table 6)</h3><p>%s</p>" % bd[0].get("cite", "")
                   + _t(["section", "span (m)", "level", "&delta; (mm)", "limit (mm)", "ratio"], rows))
    cs = (pkg or {}).get("crane_sway")
    if isinstance(cs, dict):
        out.append("<h3>Crane frame sway (IS 800 Table 6)</h3>" + _t(
            ["sway (mm)", "limit (mm)", "ratio", "basis"],
            [[_num(cs.get("sway_mm"), 2), _num(cs.get("limit_mm"), 2), _num(cs.get("ratio"), 3), cs.get("cite")]]))
    return "".join(out)


def _base_reactions(cfg, root):
    try:
        d = json.load(open(os.path.join(root, "design", "member_combo_forces.json")))
    except Exception:
        return "<p class='note'>Member combination forces not available.</p>"
    info = E.build(cfg, "Linear")
    base = {str(t) for (t, k, s, n1, n2) in info["ele"] if k == "col" and min(n1, n2) // 100000 == 0}
    Pc = Pt = V = 0.0
    for t, e in d.get("elements", {}).items():
        if t not in base:
            continue
        for lab, r in (e.get("records") or {}).items():
            if lab.startswith("SLS"):
                continue
            Pc = max(Pc, -r[0]); Pt = max(Pt, r[0]); V = max(V, abs(r[3]))
    return _t(["quantity (factored, all strength combinations)", "value"],
              [["max column compression at the base", _kN(Pc) + " kN"],
               ["max column tension (uplift) at the base", _kN(Pt) + " kN" + (" &mdash; <b>net uplift</b>" if Pt > 0 else "")],
               ["max column shear at the base", _kN(V) + " kN"]])


def _PM_stem(name):
    """H45: figure file stem of a (possibly 'units/<unit>') job name -- plot_model.fig_stem."""
    return str(name).replace("\\", "/").strip("/").replace("/", "__")


def _title_name(name):
    """H45: report title uses the basename of a 'units/<unit>' job name."""
    return os.path.basename(str(name).replace("\\", "/").rstrip("/")) or str(name)


def _grounding(cfg, name, pkg):
    R = _R()
    recs, _ = R._load_activity(name)
    cols = {}
    for r in recs:
        if r.get("tool") == "search_engineering_standards":
            mm = re.search(r"\[([A-Za-z0-9_]+)\]", r.get("detail", ""))
            if mm:
                cols[mm.group(1)] = cols.get(mm.group(1), 0) + 1
    retr = ((cfg.get("load_plan") or {}).get("retrieval") or [])
    stems = " ".join(str(x.get("stem") or x.get("collection") or x.get("cite") or "") for x in retr if isinstance(x, dict))
    cited = json.dumps(pkg or {})

    def n(prefix):
        return sum(v for k, v in cols.items() if k.upper().startswith(prefix.upper()))
    items = [("IS 800:2007 (members, connections, Section 12)", n("engineering_standards_IS800"),
              "IS 800" in cited),
             ("IS 875 (loads)", n("engineering_standards_IS875"), "875" in stems),
             ("IS 1893 (earthquake)", n("engineering_standards_IS1893"), "1893" in stems)]
    rows = [[lab, q, "yes" if c else "no", "grounded" if (q or c) else "<b>MISSING</b>"] for lab, q, c in items]
    return "<h3>Grounding verification</h3>" + _t(["standard", "RAG queries (activity log)",
                                                   "cited in load plan / package", "status"], rows)


def _consistency(name, root, pkg):
    import html as _html
    try:
        import consistency
        issues = consistency.check(name, root=root, pkg=pkg, verbose=False)
    except Exception as ex:
        return f"<h3>Numerical self-consistency check</h3><p class='note'>[consistency check unavailable: {ex}]</p>"
    if not issues:
        return "<h3>Numerical self-consistency check</h3><p class='cnote'><b>PASS</b></p>"
    rows = []
    for i, iss in enumerate(issues):
        txt = _html.escape(str(iss))
        if "residue" in txt.lower():
            txt = "<span class='residue-quote'>%s</span>" % txt
        rows.append([str(i + 1), txt])
    return ("<h3>Numerical self-consistency check</h3>"
            f"<p class='note'><b>{len(issues)} item(s) to reconcile</b> before the report is final.</p>"
            + _t(["#", "issue"], rows))


def build_report_india(name, root):
    R = _R()
    cfg = E.CFG[name]
    NF = len(cfg["heights"])
    pkg, pkgsrc = R._load_pkg(name, root)
    figdir = os.path.join(root, "figs"); os.makedirs(figdir, exist_ok=True)
    R._FIGDIR = figdir; R._FIGSEQ[0] = 0
    run = E.india_run_cached(cfg, name)
    parts = [f"<h1>{_title_name(name)} &mdash; structural analysis &amp; design report (IS 800 / IS 875 / IS 1893)</h1>",
             f"<p><b>{cfg.get('arch', '')}</b> &middot; generated {datetime.date.today()} &middot; units: kN, kN-m, "
             "m, mm, MPa (engine N-mm)</p>", _toc()]
    try:
        import plot_model as PM
        PM.figures(name, figdir, deformed_fig=bool(cfg.get("deformed_shape_figure")))
    except Exception as ex:
        parts.append(f"<p class='note'>[model figures failed: {ex}]</p>")

    # 1
    parts.append(_chapter(1))
    parts.append(_status_block(pkg))
    parts.append("<h3>Codes</h3>" + _codes_table(cfg, pkg))
    Lx = max(E._xy_in(cfg, i, j)[0] for (i, j) in E.grid(cfg, 1))
    Ly = max(E._xy_in(cfg, i, j)[1] for (i, j) in E.grid(cfg, 1))
    parts.append("<h3>Building description</h3>" + _t(["Item", "Value"], [
        ["Archetype", cfg.get("arch", "")], ["Storeys", NF],
        ["Plan extents", f"{_m(Lx)} m (X) &times; {_m(Ly)} m (Y)"],
        ["Grid", f"{cfg['NX']} &times; {cfg['NY']} bays @ {_m(cfg['SX'])} m / {_m(cfg['SY'])} m"],
        ["Storey heights (m)", ", ".join(_m(h) for h in cfg["heights"])],
        ["Height", f"{_m(sum(cfg['heights']))} m"],
        ["Occupancy", json.dumps(cfg.get("occupancy") or {})]]))
    parts.append("<h3>Materials</h3>" + _t(["Item", "Value"], [
        ["Rolled sections", "IS 2062 %s (fy by thickness per IS 2062 Table 3)" % (cfg.get("steel_grade") or "&mdash;")],
        ["Braces", "%s %s" % (cfg.get("brace_grade") or cfg.get("steel_grade") or "&mdash;", cfg.get("brace_process") or "")],
        ["E", "200 000 MPa"]]))
    try:
        parts.append(R._img(_plan_fig(cfg), "Plan grid (level 1)"))
    except Exception as ex:
        parts.append(f"<p class='note'>[plan figure failed: {ex}]</p>")
    parts.append(R._img(R._png_file_b64(os.path.join(figdir, "%s_orientation.png" % _PM_stem(name))),
                        "Section orientation (web/depth ticks; beam strong axis vertical)"))
    # 2
    parts.append(_chapter(2))
    parts.append(_systems(cfg, pkg))
    parts.append("<h3>Collectors and chords</h3>" + _collectors(pkg))
    parts.append("<h3>Irregularity screens (IS 1893 Tables 5 and 6, Amd 2)</h3>" + _irregularity(pkg))
    try:
        import viewer3d
        viewer3d.report_section(cfg, name, root)
    except Exception as ex:
        print(f"[report] viewer_3d.html generation failed: {ex}")
    # 3
    parts.append(_chapter(3))
    parts.append("<h3>Gravity loads</h3>" + _gravity_table(cfg))
    parts.append("<h3>Earthquake (IS 1893 Part 1)</h3>" + _seismic_table(cfg, pkg, run))
    parts.append("<h3>Wind (IS 875 Part 3)</h3>" + _wind_table(cfg))
    parts.append("<h3>Governing lateral load</h3>" + _governing(cfg))
    # 4
    parts.append(_chapter(4))
    try:
        cases = R.load_cases(cfg)
        parts.append(R._combo_notes(cfg, cases))
        parts.append(R._combo_legend(cfg))
        parts.append("<p>The full list of %d combinations with their factors is in Appendix B.</p>" % len(cases))
    except Exception as ex:
        cases = []
        parts.append(f"<p class='note'><b>Combinations could not be generated:</b> {ex}</p>")
    # 5
    parts.append(_chapter(5))
    parts.append(_t(["Assumption", "As modelled"], [
        ["Column bases", str((cfg.get("model") or {}).get("bases", cfg.get("base")))],
        ["Joints", str((cfg.get("model") or {}).get("joints", "&mdash;"))],
        ["Diaphragm", "rigid in-plane, master node per level"],
        ["Second order", "P-&Delta; on every gravity state (Newton), laterals as linear increments"],
        ["Floor load distribution", str(cfg.get("floor_system") or "one-way")]]))
    try:
        parts.append(R._img(R._joint_figure(cfg), "Modelled joint and base fixity", full=True))
    except Exception as ex:
        parts.append(f"<p class='note'>[joint figure failed: {ex}]</p>")
    parts.append("<h3>Modal properties</h3>" + _modal_table(run))
    parts.append("<h3>Analysis gates</h3>" + _t(["gate", "status"], [[k, _ok(v)] for k, v in (run.get("chk") or {}).items()]))
    # 6
    parts.append(_chapter(6))
    parts.append(_members(pkg))
    # 7
    parts.append(_chapter(7))
    n_not = sum(1 for c in cases if (getattr(c, "meta", {}) or {}).get("notional"))
    parts.append(f"<p>Every strength combination is solved second-order (P-&Delta;). IS 800 4.3.6 notional horizontal "
                 f"loads (0.5 % of the factored gravity per level) are applied in {n_not} gravity combinations in both "
                 "directions and signs. Effective lengths per IS 800 7.2 / Annex D as recorded in the member inputs.</p>")
    # 8
    parts.append(_chapter(8))
    parts.append(_serviceability(cfg, pkg, run))
    # 9
    parts.append(_chapter(9))
    parts.append(_is800_s12_detailing(cfg, pkg))
    # 10
    parts.append(_chapter(10))
    parts.append(_connections(pkg))
    # 11
    parts.append(_chapter(11))
    parts.append(_base_reactions(cfg, root))
    # 12
    parts.append(_chapter(12, status="outside the analysis package"))
    # 13
    parts.append(_chapter(13))
    parts.append(_grounding(cfg, name, pkg))
    parts.append(_consistency(name, root, pkg))
    # appendices
    parts.append("<h2>Appendix A &mdash; IS 800 checks by member group</h2>")
    for m in (pkg or {}).get("members") or []:
        parts.append(f"<h4>{m.get('id')}</h4>" + _checks_table(m.get("checks")))
    parts.append("<h2>Appendix B &mdash; Combinations analysed</h2>")
    if cases:
        parts.append(R._combo_table(cases))
    parts.append(R._activity_section(name))
    html = (f"<!doctype html><html><head><meta charset='utf-8'><title>{_title_name(name)} report</title>"
            f"<style>{R.CSS}{R.CHK_CSS}</style>{R.MATHJAX}</head><body>" + "".join(parts) + "</body></html>")
    fc = [0]

    def _fignum(_m):
        fc[0] += 1
        return f"<b>Figure {fc[0]}.</b>"
    html = re.sub("@@FIGNUM@@", _fignum, html)
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, "report.html")
    open(path, "w", encoding="utf-8").write(html)
    print(f"[{name}] wrote {path}")
    return path
