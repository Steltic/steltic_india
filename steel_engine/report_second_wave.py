"""report_second_wave.py -- report-only fixes of the 2026-10 second wave (review items 9, 12, 13, 14, 16 and leftovers).

Nothing here changes a design: every function reads the cfg / calc package / job folder and returns text, a record
or an HTML fragment.

* headline, headline_html, write_headline  -- H1: the worst STRENGTH ratio is the headline; the slenderness ratio (with
  its limit) and the Section 12 / connection / drift ratios are printed beside it, never mixed into it.
  design/headline.json is written for the site build and the gold harness.
* base_shear_notes, base_shear_html        -- H2 (item 12): soil type and its basis with the next softer type's
  Sa/g and V_B; the facade assumption behind a bare-frame Ta and the infilled-frame Ta of the same clause.
* gust_factor_html                         -- H2: IS 875-3 10.2 gust factor and the dynamic-wind method.
* deck_layout, composite_scope_html, deck_span_warning -- H3 (item 9): bare-steel scope of composite-deck floors and
  the full-bay deck span point for the design engineer.
* FRAMING, framing_for, framing_html       -- H4 (item 14): capability-demonstration titles and intro text.
* compliance_html, strengthening_html      -- H5 (item 13): cost of compliance and the IN_Ex5 strengthening option.
* normalise_citations, CODE_ROWS           -- H6 (item 16): one citation style for the Indian Standards.
* ridge_restraint_html                     -- H7: what holds the ridge of a true-slope portal out of plane.
* assumptions_html, snow_html, s12_value, plain -- H8: leftovers of the review that only change what is printed.

Values quoted from the Indian Standards come from the engine's own transcriptions (india_seismic: IS 1893 6.4.2
Sa/g, 7.6.2 Ta, Table 7) or from records already in the job's load plan; nothing is added to them here.
"""
from __future__ import annotations

import html
import json
import math
import os
import re

# ---------------------------------------------------------------------------------------------------- helpers


def _e(x):
    return html.escape(str(x))


def _f(v, d=3, dash="—"):
    try:
        if isinstance(v, bool):
            return dash
        return ("{:,.%df}" % d).format(float(v))
    except (TypeError, ValueError):
        return dash if v is None else _e(v)


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def _tab(head, rows):
    h = "".join("<th>%s</th>" % c for c in head)
    b = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % c for c in r) for r in rows)
    return "<table class='t'><tr>%s</tr>%s</table>" % (h, b)


def _plan(cfg, pkg=None):
    p = (cfg or {}).get("load_plan")
    if not isinstance(p, dict) or not p:
        p = (pkg or {}).get("load_plan") if isinstance(pkg, dict) else None
    return p if isinstance(p, dict) else {}


def _combo_of(c):
    if c.get("combo"):
        return str(c["combo"])
    m = re.search(r"\((?:governing )?combination (.+)\)", str(c.get("name") or ""))
    return m.group(1) if m else ""


# ============================================================================================ H1 headline ratios
SLENDER_TAG = "slenderness"
S12_SLENDERNESS = {"brace_KL_r", "is18168_7_2_column_KL_r"}
S12_STRENGTH = {
    "12.11.2.3_panel_zone", "12.11.3.4_out_of_plane_12.2.3", "12.12_base", "7.4_base", "12.3.2.1_link_shear",
    "12.3.2.2_beam_axial", "12.3.2.2_brace_axial", "12.3.2.2_column_axial", "12.3.4.4_column_strength",
    "12.3.4.5_brace_tension", "12.5.1.1_column_compression", "12.5.1.1_column_tension", "brace_compression",
    "brace_conn_1p2Mp", "brace_conn_block_shear", "brace_conn_bolts", "brace_conn_net_rupture", "brace_conn_welds",
    "connection_moment", "connection_shear", "gusset_out_of_plane_buckling", "gusset_whitmore_yield"}
# everything else in Section 12 with a ratio is a width-thickness, proportioning, geometry or deformation limit


def member_ratios(m):
    """(strength, strength_check, slenderness, slenderness_check) of one calc-package member group.

    strength: the largest IS 800 member-resistance / 9.3 interaction ratio over the combinations; slenderness: the
    governing IS 800 Table 3 KL/r ratio (KL/r over its limit).  A member check that is neither is counted as strength
    (conservative for the headline).  A member without check records falls back to its DC as strength."""
    strength = slen = None
    s_chk = sl_chk = None
    for c in (m or {}).get("checks") or []:
        if not isinstance(c, dict) or not _num(c.get("dc")):
            continue
        nm = str(c.get("name") or "")
        dc = float(c["dc"])
        if SLENDER_TAG in nm.lower() and "KL/r" in nm:
            if slen is None or dc > slen:
                slen, sl_chk = dc, c
        elif strength is None or dc > strength:
            strength, s_chk = dc, c
    if strength is None and slen is None and _num((m or {}).get("DC")):
        strength = float(m["DC"])
    return strength, s_chk, slen, sl_chk


def _s12_class(cid):
    if cid in S12_SLENDERNESS:
        return "slenderness"
    if cid in S12_STRENGTH:
        return "strength"
    return "detailing"


def headline(pkg):
    """The governing ratios of a calc package, kept apart (H1).  Returns a JSON-able record:
    strength (the headline: worst member strength ratio), slenderness (worst member KL/r against IS 800 Table 3),
    member_dc_max (the old single 'member D/C', the larger of the two), section12 {strength, slenderness, detailing},
    connections, secondary_members, drift."""
    pkg = pkg if isinstance(pkg, dict) else {}
    out = {"strength": None, "slenderness": None, "member_dc_max": None, "section12": {}, "connections": None,
           "secondary_members": None, "drift": None,
           "basis": ("strength = largest IS 800 member resistance / 9.3 interaction ratio of any member group; "
                     "slenderness = largest KL/r over its IS 800 Table 3 limit; Section 12 checks split into "
                     "strength, slenderness and detailing (width-thickness, proportioning, geometry, deformation) "
                     "limits; connections and storey drift as their own rows"),
           "source": "steltic_india report_second_wave.headline"}
    for m in pkg.get("members") or []:
        if not isinstance(m, dict):
            continue
        st, sc, sl, slc = member_ratios(m)
        mid, sec = m.get("id"), (m.get("inputs") or {}).get("section") or m.get("section")
        if st is not None and (out["strength"] is None or st > out["strength"]["dc"]):
            out["strength"] = {"dc": round(st, 4), "member": mid, "section": sec,
                               "check": re.sub(r"\s*\((?:governing )?combination .*$", "",
                                               str((sc or {}).get("name") or "member check")).strip(),
                               "combination": _combo_of(sc) if sc else (m.get("inputs") or {}).get("governing_combo"),
                               "clause": (sc or {}).get("clause") or "IS 800:2007 7.1.2, 8.2, 8.4, 9.3"}
        if sl is not None and (out["slenderness"] is None or sl > out["slenderness"]["ratio"]):
            out["slenderness"] = {"ratio": round(sl, 4), "KL_r": round(float(slc["value"]), 1) if _num(slc.get("value")) else None,
                                  "limit": slc.get("limit"), "member": mid, "section": sec,
                                  "combination": _combo_of(slc), "clause": slc.get("clause") or "IS 800:2007 3.8 / Table 3",
                                  "basis": slc.get("cite")}
        dc = m.get("DC")
        if _num(dc) and (out["member_dc_max"] is None or dc > out["member_dc_max"]["dc"]):
            out["member_dc_max"] = {"dc": round(float(dc), 4), "member": mid}
    s12 = (((pkg.get("capacity_design") or {}).get("section12") or {}).get("checks") or []) \
        if isinstance(pkg.get("capacity_design"), dict) else []
    for c in s12:
        if not isinstance(c, dict) or not _num(c.get("dc")):
            continue
        k = _s12_class(str(c.get("id")))
        cur = out["section12"].get(k)
        if cur is None or float(c["dc"]) > cur["dc"]:
            out["section12"][k] = {"dc": round(float(c["dc"]), 4), "check": c.get("id"), "member": c.get("member"),
                                   "value": c.get("value") if not isinstance(c.get("value"), dict) else None,
                                   "limit": c.get("limit") if not isinstance(c.get("limit"), dict) else None,
                                   "clause": c.get("clause")}
    for c in pkg.get("connections") or []:
        if isinstance(c, dict) and _num(c.get("DC")) and (out["connections"] is None or c["DC"] > out["connections"]["dc"]):
            out["connections"] = {"dc": round(float(c["DC"]), 4), "id": c.get("id"), "type": c.get("type")}
    for s_ in pkg.get("secondary_members") or []:
        if isinstance(s_, dict) and _num(s_.get("DC")) and (out["secondary_members"] is None
                                                          or s_["DC"] > out["secondary_members"]["dc"]):
            out["secondary_members"] = {"dc": round(float(s_["DC"]), 4), "id": s_.get("id"), "section": s_.get("section")}
    for r in pkg.get("drift_table") or []:
        if isinstance(r, dict) and _num(r.get("dc")) and (out["drift"] is None or r["dc"] > out["drift"]["dc"]):
            out["drift"] = {"dc": round(float(r["dc"]), 4), "storey": r.get("storey"), "dir": r.get("dir"),
                            "drift": r.get("drift"), "limit": r.get("limit")}
    return out


def headline_sentence(h):
    """One line for the status block and the site card: strength first, slenderness beside it with its limit."""
    st, sl = (h or {}).get("strength"), (h or {}).get("slenderness")
    parts = []
    if st:
        parts.append("worst member strength ratio %s (%s, %s%s)" % (
            _f(st["dc"]), st["member"], st.get("check") or "IS 800 member check",
            (", " + st["combination"]) if st.get("combination") else ""))
    if sl:
        parts.append("worst member slenderness KL/r %s against the IS 800 Table 3 limit of %s (ratio %s, %s)" % (
            _f(sl.get("KL_r"), 1), _f(sl.get("limit"), 0), _f(sl["ratio"]), sl["member"]))
    return "; ".join(parts)


def headline_html(pkg, h=None):
    h = h or headline(pkg)
    rows = []
    st, sl = h.get("strength"), h.get("slenderness")
    if st:
        rows.append(["<b>Strength, members (IS 800 9.3 interaction, Chapter 6): the headline</b>", "<b>%s</b>" % _f(st["dc"]),
                     "1.0", _e(st["member"]), _e(st.get("combination") or "")])
    if sl:
        rows.append(["Slenderness, members (IS 800 Table 3, Chapter 6)",
                     "KL/r %s / %s = %s" % (_f(sl.get("KL_r"), 1), _f(sl.get("limit"), 0), _f(sl["ratio"])),
                     "1.0", _e(sl["member"]), _e(sl.get("combination") or "")])
    lab = {"strength": "Section 12 strength checks (Chapter 9)",
           "slenderness": "Section 12 slenderness limits (Chapter 9)",
           "detailing": "Section 12 width-thickness, proportioning and deformation limits (Chapter 9)"}
    for k in ("strength", "slenderness", "detailing"):
        r = (h.get("section12") or {}).get(k)
        if r:
            val = _f(r["dc"])
            if k == "slenderness" and _num(r.get("value")) and _num(r.get("limit")):
                val = "KL/r %s / %s = %s" % (_f(r["value"], 1), _f(r["limit"], 0), _f(r["dc"]))
            rows.append([lab[k], val, "1.0", _e("%s%s" % (r.get("check"), (", " + str(r["member"])) if r.get("member") else "")),
                         _e(r.get("clause") or "")])
    if h.get("connections"):
        c = h["connections"]
        rows.append(["Connections (Chapter 10)", _f(c["dc"]), "1.0", _e(c["id"]), _e(c.get("type") or "")])
    if h.get("secondary_members"):
        c = h["secondary_members"]
        rows.append(["Secondary members (purlins, girts, joists)", _f(c["dc"]), "1.0", _e(c["id"]), _e(c.get("section") or "")])
    if h.get("drift"):
        c = h["drift"]
        rows.append(["Storey drift (IS 1893 7.11.1.1, Chapter 8)", _f(c["dc"]), "1.0",
                     _e("storey %s, %s" % (c.get("storey"), c.get("dir"))), ""])
    if not rows:
        return ""
    note = ("<p>The headline is the worst <b>strength</b> ratio of the members. Slenderness, width-thickness and "
            "proportioning ratios limit the proportions of a member, not the load it carries; they are shown beside the "
            "headline with their limits and each must also be at most 1.0.</p>")
    return ("<h3>Governing ratios</h3>" + note +
            _tab(["ratio", "value", "limit", "where", "combination / clause"], rows))


def write_headline(root, pkg, h=None):
    """design/headline.json (read by the site build and the gold harness)."""
    h = h or headline(pkg)
    try:
        os.makedirs(os.path.join(root, "design"), exist_ok=True)
        json.dump(h, open(os.path.join(root, "design", "headline.json"), "w"), indent=1, default=str)
    except Exception:
        pass
    return h


def member_cells(m):
    """Chapter 6 member table: [strength ratio, 'KL/r x / limit (ratio)'] for one member group."""
    st, _, sl, slc = member_ratios(m)
    s_txt = _f(st) if st is not None else "not evaluated"
    if sl is not None:
        kl = slc.get("value")
        l_txt = "%s / %s (%s)" % (_f(kl, 1), _f(slc.get("limit"), 0), _f(sl)) if _num(kl) else _f(sl)
    else:
        l_txt = "—"
    return [s_txt, l_txt]


def kl_cell(m):
    """Chapter 6: the effective lengths KLz / KLy (m) the governing element was checked with (IS 800 7.1.2)."""
    ax = ((((m or {}).get("governing_element_result") or {}).get("capacities") or {}).get("compression") or {}).get("axes") or {}
    z, y = (ax.get("z") or {}).get("KL_mm"), (ax.get("y") or {}).get("KL_mm")
    if not (_num(z) or _num(y)):
        return "—"
    return "%s / %s" % (_f(z / 1000.0 if _num(z) else None, 2), _f(y / 1000.0 if _num(y) else None, 2))


def height_text(cfg, H_mm):
    """Building height for the description: eave and ridge when the roof is modelled at its true slope."""
    pls = [p for p in (cfg or {}).get("roof_planes") or [] if isinstance(p, dict)]
    rz = max([float(p["ridge_z_mm"]) for p in pls if _num(p.get("ridge_z_mm"))] or [0.0])
    ez = max([float(p["eave_z_mm"]) for p in pls if _num(p.get("eave_z_mm"))] or [0.0])
    if rz > ez > 0:
        return "%s m to the eave, %s m to the ridge" % (_f(ez / 1000.0, 2), _f(rz / 1000.0, 2))
    return "%s m" % _f(H_mm / 1000.0, 2)


# ============================================================================================ H2 base shear notes
_NEXT_SOFTER = {"I": "II", "II": "III"}
_SOIL_NAME = {"I": "rock or hard soil", "II": "medium stiff soil", "III": "soft soil"}
_MRF_COEF = re.compile(r"0\.0(75|80|85)\s*h")


def _formula_by_dir(formula):
    """{'X': part, 'Y': part} of a load-plan Ta_formula ('X: ...; Y: ...', 'Y (OMRF): ...', or one formula for both)."""
    out = {}
    parts = [p.strip() for p in re.split(r";", str(formula or "")) if p.strip()]
    common = None
    for p in parts:
        m = re.match(r"^([XY])\b\s*(?:\([^)]*\))?\s*:?", p)
        if m and re.search(r"h\s*\^|h/|h\s*/", p):
            out[m.group(1)] = p
        elif common is None and re.search(r"h\s*\^|h/|h\s*/|sqrt", p):
            common = p
    for d in ("X", "Y"):
        out.setdefault(d, common or "")
    return out


def _bare_frame(part):
    """(True, coefficient) when a Ta formula part is the bare-MRF 7.6.2(a) formula."""
    try:
        import india_seismic as IS
        mrf = IS._looks_like_mrf_formula(part)
    except Exception:
        mrf = bool(_MRF_COEF.search(part or ""))
    m = _MRF_COEF.search(part or "")
    coef = {"75": 0.075, "80": 0.080, "85": 0.085}[m.group(1)] if m else 0.085
    return bool(mrf), coef


def plan_dims_m(cfg):
    """Plan dimensions of the footprint along X and Y in m (IS 1893 7.6.2 d, base dimension at the plinth), from the
    engine grid over every level (a lean-to or podium level does not shrink it)."""
    try:
        import engine3d as E
        pts = [E._xy_in(cfg, i, j) for k in range(1, len(cfg["heights"]) + 1) for (i, j) in E.grid(cfg, k)]
        return {"X": (max(p[0] for p in pts) - min(p[0] for p in pts)) / 1000.0,
                "Y": (max(p[1] for p in pts) - min(p[1] for p in pts)) / 1000.0}
    except Exception:
        return {}


def _ah(Z, I, R, sa, rho):
    a = (float(Z) / 2.0) * (float(I) / float(R)) * float(sa)
    return max(a, rho or 0.0), a


def base_shear_notes(cfg, pkg=None, dims=None):
    """Item 12 records.  soil: type, basis and the next softer type's Sa/g and V_B ratio at the design Ta (ESM, with
    the Table 7 minimum).  ta: per direction where Ta is the bare-frame 7.6.2(a) formula: the facade basis and the
    7.6.2(c) Ta (the formula IS 1893 gives for a frame with masonry infill) with its Sa/g and V_B ratio."""
    import india_seismic as IS
    cfg = cfg or {}
    ss = _plan(cfg, pkg).get("seismic_summary") or {}
    out = {"soil": None, "ta": []}
    if not ss:
        return out
    try:
        soil = IS.soil_type(ss.get("soil") or (cfg.get("seis") or {}).get("soil") or "II")
    except Exception:
        soil = None
    Z, I = ss.get("Z"), ss.get("I")
    zone = str(ss.get("zone") or (cfg.get("seis") or {}).get("zone") or "").upper().replace("ZONE", "").strip()
    rho = ss.get("rho_min") if _num(ss.get("rho_min")) else IS.TABLE7_RHO.get(zone)
    dirs = []
    for d in ("X", "Y"):
        T = ss.get("Ta_%s_s" % d.lower(), ss.get("Ta_s"))
        R = ss.get("R_%s" % d.lower(), ss.get("R"))
        if _num(T) and _num(R) and _num(Z) and _num(I):
            dirs.append((d, float(T), float(R)))
    basis = (cfg.get("soil_basis") or ss.get("soil_basis")
             or ("%s (Type %s) as declared in the brief: %s assumed, not from a site investigation; confirm by site "
                 "investigation (geotechnical report)" % (_SOIL_NAME.get(soil, "soil"), soil,
                                                         "medium soil" if soil == "II" else "this soil type")))
    if soil:
        rec = {"type": soil, "name": _SOIL_NAME.get(soil), "basis": basis, "next": _NEXT_SOFTER.get(soil), "rows": []}
        if rec["next"]:
            for d, T, R in dirs:
                sa0, sa1 = IS.sa_over_g(T, soil, "ESM"), IS.sa_over_g(T, rec["next"], "ESM")
                a0, _ = _ah(Z, I, R, sa0, rho)
                a1, _ = _ah(Z, I, R, sa1, rho)
                rec["rows"].append({"dir": d, "Ta_s": round(T, 4), "Sa_g": round(sa0, 4), "Sa_g_next": round(sa1, 4),
                                    "VB_ratio": round(a1 / a0, 4) if a0 else None})
        out["soil"] = rec
    fby = _formula_by_dir(ss.get("Ta_formula"))
    dims = dims if dims is not None else plan_dims_m(cfg)
    facade = facade_basis(cfg)
    for d, T, R in dirs:
        bare, coef = _bare_frame(fby.get(d, ""))
        if not bare:
            continue
        h = (T / coef) ** (4.0 / 3.0)
        dd = (dims or {}).get(d)
        row = {"dir": d, "Ta_s": round(T, 4), "formula": "%.3f h^0.75 (7.6.2(a))" % coef, "h_m": round(h, 2),
               "d_m": round(dd, 2) if dd else None, "facade": facade}
        if dd and soil:
            ta_c = IS.approximate_Ta(h, dd, system="steel MRF", material="steel", infills=True)["Ta_s"]
            sa0, sa1 = IS.sa_over_g(T, soil, "ESM"), IS.sa_over_g(ta_c, soil, "ESM")
            a0, _ = _ah(Z, I, R, sa0, rho)
            a1, _ = _ah(Z, I, R, sa1, rho)
            row.update(Ta_infill_s=round(ta_c, 4), Sa_g=round(sa0, 4), Sa_g_infill=round(sa1, 4),
                       VB_ratio=round(a1 / a0, 4) if a0 else None)
        out["ta"].append(row)
    return out


def facade_basis(cfg):
    """What the bare-frame Ta assumes about the walls (an assumption the report states, item 12)."""
    cfg = cfg or {}
    if cfg.get("facade_basis"):
        return str(cfg["facade_basis"])
    blob = json.dumps(cfg.get("delegated_design") or [], default=str).lower() + " " + str(cfg.get("notes") or "").lower()
    if "dado" in blob:
        return ("the brick dado is self-supporting on the plinth beam and tied to the columns out of plane only (as "
                "declared); it and the sheeting above it are taken as not stiffening the frame in its plane")
    return ("the facade (cladding %s kN/m² of wall) and the partitions are taken as not stiffening the frame: no masonry "
            "infill built in contact with the frame" % _f(cfg.get("clad"), 2))


def base_shear_html(cfg, pkg=None, dims=None):
    n = base_shear_notes(cfg, pkg, dims)
    out = []
    s = n.get("soil")
    if s:
        txt = "<p><b>Soil:</b> Type %s, %s. Basis: %s.</p>" % (_e(s["type"]), _e(s["name"]), _e(s["basis"]))
        if s.get("next") and s["rows"]:
            rsa = str((((pkg or {}).get("seismic_analysis") or {}).get("method")) or "").upper() == "RSA"
            if all(abs((r["VB_ratio"] or 1.0) - 1.0) < 0.005 for r in s["rows"]):
                txt += ("<p>Note (not a design case): on Type %s soil, Sa/g at the design Ta (%s s) would be the same "
                        "(IS 1893 6.4.2), so V_B would not change.</p>"
                        % (_e(s["next"]), " / ".join(_f(r["Ta_s"]) for r in s["rows"])))
            else:
                rows = [[r["dir"], _f(r["Ta_s"]), _f(r["Sa_g"]), _f(r["Sa_g_next"]), _f(r["VB_ratio"], 2)] for r in s["rows"]]
                txt += ("<p>Note (not a design case): on Type %s soil the design acceleration at the same Ta would be as "
                        "below (IS 1893 6.4.2, with the 7.2.2 Table 7 minimum). The design here is for Type %s.</p>"
                        % (_e(s["next"]), _e(s["type"])) +
                        _tab(["dir", "design Ta (s)", "Sa/g Type %s" % _e(s["type"]), "Sa/g Type %s" % _e(s["next"]),
                              "V_B ratio"], rows))
            if rsa:
                txt += ("<p>In the response-spectrum analysis, modes with periods above the Type %s corner period would "
                        "also see the higher Type %s ordinates (IS 1893 6.4.2).</p>" % (_e(s["type"]), _e(s["next"])))
        out.append(txt)
    ta = list(n.get("ta") or [])
    if len(ta) == 2 and all(ta[0].get(k) == ta[1].get(k) for k in ("formula", "h_m", "d_m", "Ta_infill_s", "VB_ratio")):
        ta = [dict(ta[0], dir="X and Y")]                  # one note when both directions are the same
    for r in ta:
        t = ("<p><b>Ta, %s direction:</b> %s with h = %s m, the formula for a bare moment frame without masonry infill. "
             "Assumption: %s.</p>" % (r["dir"], _e(r["formula"]), _f(r["h_m"], 2), _e(r["facade"])))
        if r.get("Ta_infill_s") is not None:
            same = abs((r.get("VB_ratio") or 1.0) - 1.0) < 0.005
            t += ("<p>Note (not a design case): if masonry infill were built in contact with the frame, IS 1893 7.6.2(c) "
                  "would apply: Ta = 0.09 h/&radic;d = 0.09 &times; %s / &radic;%s = %s s, Sa/g %s against %s, %s</p>"
                  % (_f(r["h_m"], 2), _f(r["d_m"], 2), _f(r["Ta_infill_s"]), _f(r["Sa_g_infill"], 3), _f(r["Sa_g"], 3),
                     "so V_B would not change." if same else
                     "and V_B &times; %s. The frame would then have to be re-designed for that base shear."
                     % _f(r["VB_ratio"], 2)))
        out.append(t)
    if not out:
        return ""
    return "<h4>Statements that move the base shear (assumptions to confirm)</h4>" + "".join(out)


# ============================================================================================ H2 dynamic wind
_GF_LABELS = [
    ("G", "gust factor G (10.2)"), ("G_x", "G, wind along X"), ("G_X", "G, wind along X"), ("G_y", "G, wind along Y"),
    ("G_Y", "G, wind along Y"), ("fa_hz", "first-mode frequency f<sub>a</sub> (Hz)"),
    ("fa_x_hz", "f<sub>a</sub>, X (Hz)"), ("fa_y_hz", "f<sub>a</sub>, Y (Hz)"), ("T1_s", "first-mode period T1 (s)"),
    ("beta", "damping coefficient &beta; (Table 36)"), ("beta_basis", "&beta; basis"),
    ("Cf", "force coefficient C<sub>f</sub>"), ("Cf_basis", "C<sub>f</sub> basis"), ("terrain", "terrain category"),
    ("h_m", "h (m)"), ("b_m", "b (m)"), ("Ih", "turbulence intensity I<sub>h</sub> (6.5)"),
    ("Bs", "background factor B<sub>s</sub>"), ("S", "size reduction factor S"), ("E", "E (10.2)"),
    ("Vh_d", "design hourly mean speed at h, V&#772;<sub>h,d</sub> (m/s)"),
    ("Vh_d_mps", "design hourly mean speed at h, V&#772;<sub>h,d</sub> (m/s)"),
    ("VB_x_kN", "along-wind base shear X, gust factor (kN)"), ("VB_y_kN", "along-wind base shear Y, gust factor (kN)"),
    ("static_VB_x_kN", "base shear X, static 7.2 (kN)"), ("static_VB_y_kN", "base shear Y, static 7.2 (kN)"),
    ("VB_applied_kN", "base shear applied (kN)"), ("method", "method"), ("note", "note"), ("cite", "reference")]


_GF_DIGITS = {"terrain": 0, "h_m": 1, "b_m": 1, "Vh_d": 2, "Vh_d_mps": 2, "E": 4}


def _gf_val(v, key=""):
    d = 1 if str(key).startswith(("VB", "static_VB")) else _GF_DIGITS.get(key, 3)
    if isinstance(v, dict):
        if all(_num(x) for x in v.values()) and v:
            return " / ".join("%s %s" % (_e(k), _f(x, d)) for k, x in v.items())
        return None
    if isinstance(v, (list, tuple)):
        return None
    return _f(v, d) if _num(v) else _e(v)


def gust_factor_html(cfg, pkg=None):
    ws = _plan(cfg, pkg).get("wind_summary") or {}
    gf = ws.get("gust_factor")
    lines = []
    for k, lab in (("method", "dynamic-wind route"), ("dynamic_required", "dynamic wind required (9.1)"),
                   ("f1_hz", "first-mode frequency used for 9.1 (Hz)")):
        if ws.get(k) is not None:
            v = ws[k]
            lines.append([lab, ("yes" if v else "no") if isinstance(v, bool) else _gf_val(v)])
    if not isinstance(gf, dict) or not gf:
        if not lines:
            return ""
        return "<h4>Dynamic wind (IS 875 (Part 3):2015 9.1 / 10.2)</h4>" + _tab(["item", "value"], lines)
    seen = set()
    for k, lab in _GF_LABELS:
        if k in gf and k not in seen:
            v = _gf_val(gf[k], k)
            if v not in (None, ""):
                lines.append([lab, v])
            seen.add(k)
    return ("<h4>Dynamic wind: gust factor (IS 875 (Part 3):2015 10.2)</h4><p>The along-wind storey forces use the "
            "design hourly mean wind pressure multiplied by the gust factor G (10.2); the values used are below.</p>"
            + _tab(["item", "value"], lines))


def across_wind_text(ws, reason):
    """Across-wind row text when the 10.3 patterns are not evaluated: 'not required' with the 9.1 basis when the load
    plan records it, else the engine's reason."""
    aw = (ws or {}).get("across_wind")
    if isinstance(aw, dict) and aw.get("required") is False:
        res = str(aw.get("result") or "IS 875-3 9.1 does not require it")
        res = re.sub(r"^\s*NOT REQUIRED\s*[-:—]*\s*", "", res)
        return "not required: " + res
    return "NOT EVALUATED: %s" % reason


# ============================================================================================ H3 composite deck
_SEC_RE = (re.compile(r"(?:secondar(?:y|ies)|filler)(?:\s+beams?)?(?:\s+lines?)?\s*(?:at|@|\(|,)?\s*(\d+(?:\.\d+)?)\s*m\b", re.I),
           re.compile(r"(\d+(?:\.\d+)?)\s*m\s+(?:secondar(?:y|ies)|filler)", re.I))


def _texts(cfg):
    t = []
    cs = cfg.get("construction_stage")
    if isinstance(cs, dict):
        t.append(str(cs.get("cite") or ""))
    for d in cfg.get("delegated_design") or []:
        if isinstance(d, dict):
            t += [str(d.get("item") or ""), json.dumps(d.get("criteria"), default=str),
                  json.dumps(d.get("interface_forces"), default=str)]
    t.append(str(cfg.get("notes") or ""))
    return t


def deck_layout(cfg):
    """Composite-deck floor layout (item 9): composite?, deck span direction, secondary-beam spacing (declared in
    cfg['deck'] or read from the construction-stage / delegated-design text), the deck span in m and its basis."""
    cfg = cfg or {}
    fs = str(cfg.get("floor_system") or "").lower()
    composite = "composite" in fs or str(cfg.get("composite_scope") or "").lower() in ("bare_steel", "bare-steel")
    rec = {"composite": composite, "deck_span_dir": str(cfg.get("deck_span") or "").upper() or None,
           "secondary_spacing_m": None, "span_m": None, "full_bay": None, "basis": None}
    if not composite:
        return rec
    dk = cfg.get("deck") if isinstance(cfg.get("deck"), dict) else {}
    sp = dk.get("secondary_spacing_mm")
    if _num(sp):
        rec["secondary_spacing_m"], rec["basis"] = float(sp) / 1000.0, "cfg['deck'] secondary_spacing_mm"
    else:
        for t in _texts(cfg):
            for rx in _SEC_RE:
                m = rx.search(t)
                if m and 0.5 <= float(m.group(1)) <= 6.0:
                    rec["secondary_spacing_m"], rec["basis"] = float(m.group(1)), "secondary / filler beams declared at %s m" % m.group(1)
                    break
            if rec["secondary_spacing_m"]:
                break
    if _num(dk.get("span_mm")):
        rec["span_m"] = float(dk["span_mm"]) / 1000.0
        rec["basis"] = rec["basis"] or "cfg['deck'] span_mm"
    elif rec["secondary_spacing_m"]:
        rec["span_m"] = rec["secondary_spacing_m"]
    else:
        d = rec["deck_span_dir"] or "X"
        co = cfg.get("xcoords" if d == "X" else "ycoords")
        if co and len(co) > 1:
            rec["span_m"] = max(b - a for a, b in zip(co[:-1], co[1:])) / 1000.0
        elif _num(cfg.get("SX" if d == "X" else "SY")):
            rec["span_m"] = float(cfg["SX" if d == "X" else "SY"]) / 1000.0
        rec["basis"] = "no secondary beams declared: the deck spans the full bay between the girders"
    rec["full_bay"] = rec["secondary_spacing_m"] is None and not _num(dk.get("span_mm"))
    return rec


def deck_span_warning(cfg):
    """Non-blocking point for the design engineer (design_status warnings) when a composite deck spans a full bay."""
    try:
        d = deck_layout(cfg)
    except Exception:
        return None
    if not d["composite"] or not d["full_bay"] or not d["span_m"]:
        return None
    return ("deck span: the composite metal deck spans the full %.1f m bay between the girders (deck span %s) with no "
            "secondary beams. The deck profile is not designed here: the deck supplier must confirm the profile for this "
            "span (with propping during concreting if needed), or secondary beams must be added."
            % (d["span_m"], d["deck_span_dir"] or "X"))


def composite_scope_html(cfg, pkg):
    d = deck_layout(cfg)
    if not d["composite"]:
        return ""
    out = ["<h3>Floor system scope: composite metal deck designed as bare steel</h3>",
           "<p>The floor beams are designed as <b>bare steel</b> to IS 800 (8.2, 8.4, 9.3) and rely on no composite action, "
           "which is conservative for their strength. <b>Not designed here:</b> composite action and the shear connectors "
           "(IS 11384); the profiled deck itself (as formwork under wet concrete, propping, and as the floor slab: spans, "
           "reinforcement, crack control); the construction stage of the deck; and fire protection of the steel (period "
           "of fire resistance, intumescent or board protection), which is for the design engineer and the fire "
           "consultant.</p>"]
    cs = None
    cd = (pkg or {}).get("composite_design") or {}
    for s_ in ((cd.get("chI_worksheet") or {}).get("slots") or []):
        if s_.get("component") == "construction_stage" and _num(s_.get("DC")):
            cs = s_
    if cs:
        det = cs.get("detail") or {}
        out.append("<p>Checked here: the steel beams at the wet-concrete stage, unpropped, with the compression flange "
                   "restrained only at %s mm (IS 800 8.2.2): worst ratio %s (%s, %s).</p>"
                   % (_f(det.get("LLT_mm"), 0), _f(cs["DC"]), _e(det.get("section") or ""), _e(det.get("combo") or "")))
    if d["span_m"]:
        if d["full_bay"]:
            out.append("<p><b>Deck span %s m</b> (%s, deck span %s). The deck profile must be checked for this span by "
                       "the deck supplier, with propping during concreting if needed, or secondary beams added. This is "
                       "listed as a point for the checking engineer in the design status.</p>"
                       % (_f(d["span_m"], 2), _e(d["basis"]), _e(d["deck_span_dir"] or "X")))
        else:
            out.append("<p>Deck span %s m (%s). The secondary beams are a load path for the girders: they are sized by "
                       "hand in the job and not designed or counted in this package.</p>" % (_f(d["span_m"], 2), _e(d["basis"])))
    return "".join(out)


# ============================================================================================ H4 framing
FRAMING = {
    "IN_Ex9_Gable_warehouse_SMF_SCBF_snow_Shimla": {
        "title": "Ex 9 · capability demonstration: snow and drift on a Zone IV SMRF + SCBF gable shed · Shimla",
        "blurb": ("Shows IS 875 (Part 4):2021 snow with the lean-to drift, true-slope gable portals and IS 18168 SMRF / "
                  "SCBF detailing in Zone IV. In Indian practice a shed like this is usually a pre-engineered "
                  "(PEB) building with tapered portals and rod or angle bracing."),
        "what": "snow with the lean-to drift (IS 875 (Part 4):2021), true-slope gable portals, SMRF across and SCBF along "
                "the building in Zone IV with IS 18168 detailing",
        "practice": "a warehouse like this is usually a pre-engineered (PEB) shed with tapered portals and rod or angle "
                    "bracing, sited on the plains rather than in a hill town"},
    "IN_Ex10_SCBF_bigbox_flexdiaphragm_Indore": {
        "title": "Ex 10 · capability demonstration: flexible roof diaphragm on a braced single-storey store · Indore",
        "blurb": ("Shows a flexible bare-deck roof diaphragm compared line by line with the rigid model (IS 1893 7.6.4) "
                  "and perimeter SCBF in Zone III. Large single-storey stores in India are usually PEB sheds or RC "
                  "frames; the 15 m joist-and-deck roof is a North American form."),
        "what": "a flexible bare metal deck roof diaphragm (IS 1893 7.6.4) compared line by line with the rigid model, "
                "with perimeter SCBF in Zone III",
        "practice": "a large single-storey store is usually a PEB shed or an RC frame; the 15 m joist-and-deck roof is a "
                    "North American form"},
    "IN_Ex12_SMF_3levels_Zplan_school_Chandigarh": {
        "title": "Ex 12 · capability demonstration: Zone IV steel SMRF with I = 1.5 and IS 18168, three units · Chandigarh",
        "blurb": ("Shows an I = 1.5 educational building in Zone IV designed as a steel SMRF to IS 18168, split into "
                  "three units with seismic joints (IS 1893 7.11.3). Indian schools are almost always RC frames; this is "
                  "not a typical school."),
        "what": "an I = 1.5 building in Zone IV as a steel SMRF to IS 18168, in three units separated by seismic joints "
                "(IS 1893 7.11.3)",
        "practice": "schools are almost always RC frames; this is not a typical school"},
    "IN_Ex12_SMF_3levels_Zplan_school_Chandigarh/unitB_link": {
        "title": "Ex 12 · unit B (link block) of the Zone IV SMRF capability demonstration · Chandigarh",
        "blurb": ("The two-storey link block of Ex 12, a separate unit across a seismic joint, designed as a steel SMRF "
                  "to IS 18168 with I = 1.5. Indian schools are almost always RC frames."),
        "what": "the link block of Ex 12 as its own unit across a seismic joint, a steel SMRF to IS 18168 with I = 1.5",
        "practice": "schools are almost always RC frames; this is not a typical school"},
    "IN_Ex12_SMF_3levels_Zplan_school_Chandigarh/unitC_gym": {
        "title": "Ex 12 · unit C (gym) of the Zone IV SMRF capability demonstration · Chandigarh",
        "blurb": ("The long-span gym of Ex 12, a separate unit across a seismic joint, designed as a steel SMRF to "
                  "IS 18168 with I = 1.5. Indian schools are almost always RC frames; this is not a typical school."),
        "what": "the gym of Ex 12 as its own unit across a seismic joint, a steel SMRF to IS 18168 with I = 1.5",
        "practice": "schools are almost always RC frames; this is not a typical school"},
    "IN_Ex19_EBF_12levels_Tplan_Guwahati": {
        "title": "Ex 19 · capability demonstration: 12-storey steel EBF in Zone V, T-plan · Guwahati",
        "blurb": ("Shows a 12-storey eccentrically braced frame in Zone V, where IS 18168 1.3 requires an EBF for a "
                  "steel building of this height, with link checks, vertical earthquake and a seismic joint to the stem "
                  "unit. Residential towers in India are built in RC; a steel EBF residential tower is rare."),
        "what": "a 12-storey eccentrically braced frame in Zone V (IS 18168 1.3: steel buildings in Zone V are EBF; an "
                "SMRF only below 15 m), with link checks, vertical earthquake and a seismic joint to the stem unit",
        "practice": "residential towers are built in RC; a steel EBF residential tower is rare"},
    "IN_Ex19_EBF_12levels_Tplan_Guwahati/units/stem": {
        "title": "Ex 19 · stem unit of the Zone V steel EBF capability demonstration · Guwahati",
        "blurb": ("The stem of the Ex 19 T-plan, a separate 12-storey EBF unit across a seismic joint in Zone V. "
                  "Residential towers in India are built in RC; a steel EBF residential tower is rare."),
        "what": "the stem of the Ex 19 T-plan as its own 12-storey EBF unit across a seismic joint in Zone V",
        "practice": "residential towers are built in RC; a steel EBF residential tower is rare"},
}


def _job_key(name):
    n = str(name or "").replace("\\", "/").strip("/")
    m = re.search(r"(IN_Ex\d+_[^/]+(?:/(?:units/)?[^/]+)?)$", n)
    return m.group(1) if m else n


def framing_for(name, cfg=None):
    """The capability-demonstration framing of a job (cfg['report_framing'] overrides), or None."""
    fr = (cfg or {}).get("report_framing")
    if isinstance(fr, dict) and fr.get("title"):
        return fr
    key = _job_key(name)
    if key in FRAMING:
        return FRAMING[key]
    for k, v in FRAMING.items():
        if key.endswith(k):
            return v
    return None


def framing_html(name, cfg=None):
    fr = framing_for(name, cfg)
    if not fr:
        return ""
    return ("<p><b>%s</b></p><div class='chk'><div class='chk-h'>Capability demonstration</div><p>This example shows "
            "what the engine can do: %s. It is not typical Indian practice: %s. The job ID and folder name are "
            "unchanged.</p></div>" % (_e(fr["title"]), _e(fr.get("what") or fr.get("blurb")), _e(fr.get("practice") or "")))


def titles():
    """{job_id: {title, blurb}} for the site build (briefs/titles_wave2.json)."""
    return {k: {"title": v["title"], "blurb": v["blurb"]} for k, v in FRAMING.items()}


# ============================================================================================ H5 item 13 hooks
def _load(root, fn):
    p = os.path.join(root or "", fn)
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception as ex:
        return {"_error": "%s could not be read: %s" % (fn, ex)}


def compliance_html(root):
    cc = _load(root, "compliance_comparison.json")
    if not cc:
        return ""
    if cc.get("_error"):
        return "<p class='note'>%s</p>" % _e(cc["_error"])
    rows = [[_e(r.get("variant")), _f(r.get("R"), 1), _f(r.get("steel_t"), 1), _f(r.get("kg_m2"), 1),
             _f(r.get("worst_strength_dc"), 3), _e(r.get("governing") or ""), _e(r.get("status") or ""),
             _e(r.get("code_status") or "")] for r in cc.get("rows") or [] if isinstance(r, dict)]
    df = cc.get("difference") or {}
    out = ["<h3>%s</h3>" % _e(cc.get("title") or "Cost of compliance"),
           "<p>%s</p>" % _e(cc.get("basis") or ""),
           _tab(["design", "R", "steel (t)", "kg/m²", "worst strength ratio", "governing", "status", "code status"], rows)]
    if df:
        out.append("<p><b>Difference:</b> %s kg/m² (%s %%) for the code-compliant design.</p>"
                   % (_f(df.get("kg_m2"), 1), _f(df.get("percent"), 1)))
    if cc.get("source"):
        out.append("<p class='note'>Source: %s</p>" % _e(cc["source"]))
    return "".join(out)


def strengthening_html(root):
    so = _load(root, "strengthening_option.json")
    if not so:
        return ""
    if so.get("_error"):
        return "<p class='note'>%s</p>" % _e(so["_error"])
    out = ["<h3>%s</h3>" % _e(so.get("title") or "Strengthening option"),
           "<p>%s</p>" % _e(so.get("basis") or ""),
           _tab(["result", "value"], [
               ["PV load carried", "%s kN/m²" % _f(so.get("pv_kNm2"), 2)],
               ["status", _e(so.get("status") or "")],
               ["worst strength ratio after strengthening", _f(so.get("worst_strength_dc"), 3)],
               ["steel added", "%s t (%s kg/m²)" % (_f(so.get("added_steel_t"), 2), _f(so.get("added_kg_m2"), 2))]])]
    ch = [[_e(c.get("item")), _e(c.get("from")), _e(c.get("to")), _f(c.get("added_kg"), 0)]
          for c in so.get("changes") or [] if isinstance(c, dict)]
    if ch:
        out.append(_tab(["item", "from", "to", "added (kg)"], ch))
    if so.get("source"):
        out.append("<p class='note'>Source: %s</p>" % _e(so["source"]))
    return "".join(out)


# ============================================================================================ H6 citations
CODE_ROWS = [["IS 800:2007", "General construction in steel &mdash; limit state design"],
             ["IS 875 (Part 1):1987 / (Part 2):1987", "Dead loads / imposed loads"],
             ["IS 875 (Part 3):2015", "Wind loads"],
             ["IS 875 (Part 4):2021 / (Part 5):1987", "Snow loads / special loads and combinations"],
             ["IS 1893 (Part 1):2016 + Amd 1 (2017) + Amd 2 (2020)", "Earthquake resistant design (in force: BIS withdrew "
              "the 2025 revision in March 2026)"],
             ["IS 808:2021 / IS 2062 (Part 1):2025 / IS 1161:2014", "Rolled sections / structural steel / steel tubes"],
             ["IS 816 / IS 4000", "Welding / high-strength friction grip bolts (where used)"]]

_CITE_SUBS = [
    (re.compile(r"IS\s*875\s*\(Part\s*1\)\s*:\s*2026"), "IS 875 (Part 1):1987"),
    (re.compile(r"IS\s*875\s*\(Part\s*4\)\s*:\s*1987"), "IS 875 (Part 4):2021"),
    (re.compile(r"IS\s*2062\s*:\s*(\d{4})"), r"IS 2062 (Part 1):\1"),
    (re.compile(r"IS\s*875\s+Parts\s+1\s*-\s*5"), "IS 875 (Parts 1 to 5)"),
    (re.compile(r"IS\s*875\s+Parts\s+(\d)\s+and\s+(\d)"), r"IS 875 (Parts \1 and \2)"),
    (re.compile(r"IS\s*875\s+Part\s+(\d)(?=\s*[:)\s,;.]|$)"), r"IS 875 (Part \1)"),
    (re.compile(r"IS\s*875-(\d)\b"), r"IS 875 (Part \1)"),
    (re.compile(r"IS\s*1893\s+Part\s+1\b"), "IS 1893 (Part 1)"),
    (re.compile(r"(?<![(\w])Part\s+([25]):1987"), r"(Part \1):1987"),
]

_EOR_SUBS = [
    (re.compile(r"\bEOR's\b"), "design engineer's"),
    (re.compile(r"\bEOR-labelled\b"), "design engineer's"),
    (re.compile(r"\bEOR Cfs\b"), "Cfs read by the design engineer"),
    (re.compile(r"\bEOR\s+(\{value)"), r"design-engineer record \1"),
    (re.compile(r"\bEOR (record|input|reading|assumption|bound)\b"), r"design-engineer \1"),
    (re.compile(r"\bEORs\b"), "design engineers"),
    (re.compile(r"\bEOR\b"), "design engineer"),
]


def normalise_citations(text):
    """One citation style for the Indian Standards in printed text (item 16)."""
    for rx, rep in _CITE_SUBS:
        text = rx.sub(rep, text)
    return text


def plain(text):
    """Indian usage in printed text: 'design engineer', not 'EOR' (item 7 / item 16 leftovers)."""
    for rx, rep in _EOR_SUBS:
        text = rx.sub(rep, text)
    return text


def tidy_html(html_text):
    """Citation style and 'design engineer' wording in the text of an HTML fragment (tags and attributes untouched)."""
    parts = re.split(r"(<[^>]+>)", html_text)
    return "".join(p if p.startswith("<") else plain(normalise_citations(p)) for p in parts)


def uses_is18168(cfg, pkg):
    if (cfg or {}).get("apply_is18168") or str((cfg or {}).get("system") or "").upper() in ("EBF",):
        return True
    s12 = (((pkg or {}).get("capacity_design") or {}).get("section12") or {}).get("checks") or []
    return any(str(c.get("id") or "").startswith(("is18168_", "11.", "12.3.")) and c.get("ok") is not None
               for c in s12 if isinstance(c, dict))


# ============================================================================================ H7 ridge restraint
def ridge_restraint_html(cfg, pkg):
    """True-slope portals (cfg['roof_planes']) outside the PEB path: the apex is tied to the diaphragm along the span
    only.  Say so and say what holds the ridge out of plane."""
    if (pkg or {}).get("peb"):
        return ""
    pls = [p for p in (cfg or {}).get("roof_planes") or [] if isinstance(p, dict)]
    if not pls:
        return ""
    ax = str(pls[0].get("axis") or "X").upper()
    other = "Y" if ax == "X" else "X"
    ridge = pls[0].get("ridge_sec")
    pur = next((s_ for s_ in (cfg or {}).get("secondary_members") or [] if isinstance(s_, dict)
                and "purlin" in str(s_.get("id") or "").lower()), None)
    return ("<p><b>Ridge restraint in the frame model:</b> the apex (ridge) nodes are tied to the roof diaphragm along the "
            "span (%s) only, so the eaves spread freely; there is no tie across the span (%s) at the ridge. Out of the "
            "portal plane the ridge is held in the model only by the rafters bending about their minor axis from the "
            "eaves, which are tied across the span, and by the pinned ridge members%s linking the apexes of adjacent "
            "portals. In the building it is held by the roof-plane bracing and the purlins tied into it%s, the same "
            "restraint the rafters' out-of-plane length assumes; both are to be shown on the drawings.</p>"
            % (ax, other, (" (%s)" % _e(ridge)) if ridge else "",
               (" (%s at %s m)" % (_e(pur.get("section")), _f((pur.get("spacing_mm") or 0) / 1000.0, 1))) if pur else ""))


# ============================================================================================ H8 leftovers
def assumptions_html(cfg, pkg=None):
    """The design engineer's assumptions recorded in the job (cfg['eor_assumptions'] and found:false retrieval rows
    carrying {value, source, verify}): printed for the checking engineer to confirm."""
    rows = []
    for a in (cfg or {}).get("eor_assumptions") or []:
        if not isinstance(a, dict):
            continue
        item = a.get("item") or a.get("query") or ""
        val = a.get("value")
        rows.append([_e(plain(str(item))), _e(plain(json.dumps(val) if isinstance(val, (dict, list)) else str(val))),
                     _e(plain(str(a.get("source") or ""))), _e(normalise_citations(str(a.get("cite") or ""))),
                     "yes" if a.get("verify") else "&mdash;"])
    for r in _plan(cfg, pkg).get("retrieval") or []:
        if isinstance(r, dict) and r.get("found") is False and r.get("verify") and r.get("value") is not None:
            rows.append([_e("look-up not in the corpus: %s" % (r.get("query") or r.get("stem") or "")), _e(plain(str(r.get("value")))),
                         _e(plain(str(r.get("source") or ""))), _e(normalise_citations(str(r.get("cite") or ""))), "yes"])
    if not rows:
        return ""
    return ("<h3>Assumptions for the design engineer to confirm</h3><p>Inputs the job takes as assumptions (no survey, "
            "site investigation or code value behind them); each is to be confirmed before the design is used.</p>"
            + _tab(["item", "value", "basis", "reference", "confirm"], rows[:40]))


def snow_html(cfg, pkg=None):
    sn = _plan(cfg, pkg).get("snow_summary") or {}
    if not sn:
        return ""
    rows = []
    for k, lab, d in (("zone_Z", "snow zone Z (IS 875 (Part 4):2021 Fig. 1)", 1), ("zone_source", "zone basis", None),
                      ("altitude_m", "site altitude (m)", 0), ("s0_kNm2", "ground snow load s<sub>0</sub> (kN/m²) (Annex A-3)", 3),
                      ("mu_roof", "shape coefficient &mu; (roof)", 2), ("s_roof_kNm2", "roof snow load s (kN/m²)", 3),
                      ("partial", "unbalanced load (4.3)", None)):
        if sn.get(k) is not None:
            rows.append([lab, _f(sn[k], d) if d is not None else _e(sn[k])])
    dr = sn.get("drift") if isinstance(sn.get("drift"), dict) else {}
    if dr:
        rows.append(["drift at the lean-to (5.2.4): &mu;<sub>1</sub> / &mu;<sub>2</sub> / l<sub>3</sub> (m)",
                     "%s / %s / %s" % (_f(dr.get("mu1"), 2), _f(dr.get("mu2"), 2), _f(dr.get("l3_m"), 1))])
        if dr.get("s_wall_kNm2") is not None:
            rows.append(["drift load at the step / uniform (kN/m²)", "%s / %s" % (_f(dr.get("s_wall_kNm2"), 2),
                                                                                  _f(dr.get("s_uniform_kNm2"), 2))])
    if sn.get("cite"):
        rows.append(["reference", _e(normalise_citations(str(sn["cite"])))])
    return "<h3>Snow (IS 875 (Part 4):2021)</h3>" + _tab(["quantity", "value"], rows) if rows else ""


S12_UNITS = {
    "N": {"11.2_link_design_shear", "12.3.2.1_link_shear", "12.3.2.2_beam_axial", "12.3.2.2_brace_axial",
          "12.3.2.2_column_axial", "12.3.2.2_link_overstrength", "12.3.4.5_brace_tension", "12.5.1.1_column_compression",
          "12.5.1.1_column_tension", "brace_compression", "brace_conn_block_shear", "brace_conn_bolts",
          "brace_conn_net_rupture", "brace_conn_welds", "brace_connection_force", "brace_gross_yield_governs",
          "connection_shear", "gusset_out_of_plane_buckling", "gusset_whitmore_yield"},
    "Nmm": {"12.3.4.4_column_strength", "12.3.4.4_connection_moment", "brace_conn_1p2Mp", "connection_moment"},
    "mm": {"11.3_link_length", "11.4.2_intermediate_stiffeners", "12.10.2.5_continuity_plates"},
    "rad": {"12.3.3.1_link_rotation"}}


def s12_value(cid, v):
    """A Section 12 value or limit in report units: forces in kN, moments in kN·m, lengths in mm, width-thickness
    records as 'b/tf 6.67, d/tw 18.89'."""
    if isinstance(v, dict):
        return ", ".join("%s %s" % (_e(k), _f(x, 2) if _num(x) else _e(x)) for k, x in v.items())
    if isinstance(v, bool) or not _num(v):
        return "&mdash;" if v is None else ("yes" if v is True else "no" if v is False else _e(v))
    if cid in S12_UNITS["N"]:
        return "%s kN" % _f(float(v) / 1e3, 1)
    if cid in S12_UNITS["Nmm"]:
        return "%s kN·m" % _f(float(v) / 1e6, 1)
    if cid in S12_UNITS["mm"]:
        return "%s mm" % _f(v, 0)
    if cid in S12_UNITS["rad"]:
        return "%s rad" % _f(v, 3)
    return _f(v, 3).rstrip("0").rstrip(".") if abs(float(v)) < 1e6 else _f(v, 0)


_SYS_NAMES = {
    "SMRF": "SMRF, steel special moment resisting frame (IS 1893 Table 9 (i)(d)) = SMF (IS 800 12.11)",
    "OMRF": "OMRF, steel ordinary moment resisting frame (IS 1893 Table 9 (i)(c)) = OMF (IS 800 12.10)",
    "SCBF": "SBF with concentric braces (IS 1893 Table 9 (ii)(b)) = SCBF (IS 800 12.8)",
    "OCBF": "OBF with concentric braces (IS 1893 Table 9 (ii)(a)) = OCBF (IS 800 12.7)",
    "EBF": "SBF with eccentric braces (IS 1893 Table 9 (ii)(c)) = EBF (IS 800 12.9, links to IS 18168)"}
_SYS_ALIAS = {"SMF": "SMRF", "OMF": "OMRF", "SBF": "SCBF", "OBF": "OCBF"}


def system_names(system):
    """The IS 1893 Table 9 and IS 800 Section 12 names of a declared system ('SMRF+SCBF', 'SMF', ...)."""
    out = []
    for tok in re.split(r"[+/,&]| and ", str(system or "")):
        t = tok.strip().upper()
        t = _SYS_ALIAS.get(t, t)
        if t in _SYS_NAMES and _SYS_NAMES[t] not in out:
            out.append(_SYS_NAMES[t])
    return "; ".join(out)
