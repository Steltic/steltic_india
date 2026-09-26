"""IS 800:2007 Section 12 system checks (WP2.4) + IS 18168:2023 EBF links (D2).

Entry point: section12_checks(system, model_data, cfg) -> {system, supported, ok, checks[...], advisories[...]}.

Every check is {id, member, value, limit, dc, ok, clause, cite, source}; ok=None means "not evaluated" (an input is
missing) and blocks COMPLETE exactly like ok=False. Units N, mm, MPa.

Supported systems (decision D3/WP2.8): OCBF (12.7), SCBF (12.8), EBF (IS 18168:2023 cl. 11 / 12.3 - IS 800 12.9 only
refers to specialist literature), OMF (12.10), SMF (12.11). Any other system (BRBF, SPSW, dual, IMF, ...) returns
ok=None with reason "no Indian basis".

Clause text was read from the IS 800:2007 PDF (pp. 87-91) and the IS 18168:2023 PDF (cl. 1.3, 5.2, 5.5, 11, 12.3).

model_data (built by design_pipeline from the analysis model; see the hook list in the WP2.4 report):
  members:  [{id, role: 'brace'|'column'|'beam'|'link', section, grade, process (CHS), L_mm, Kz, Ky,
              node_i, node_j, sfrs: bool, cos_h (horizontal direction cosine, braces), line (brace line id),
              major_axis_plane: 'X'|'Y' (columns), frame_dir: 'X'|'Y' (beams/braces), An_mm2 (braces, net area)}]
  forces:   {member_id: [{combo, family ('table4'|'12.2.3'|...), P_N (+compression), Mz_i_Nmm, Mz_j_Nmm,
                           My_i_Nmm, My_j_Nmm, Vy_N, Vz_N}]}
  joints:   [{id, level, frame_dir, columns: [{member_id, position: 'above'|'below'}],
              beams: [{member_id, L_clear_mm, V_gravity_N (1.2DL+0.5LL end shear)}],
              continuity_plates: bool, doubler_t_mm, connection: {moment_capacity_Nmm, shear_capacity_N, cite,
              type: 'end_plate'|'welded', weld_type, bolt_type}}]   (joints_from_model builds these)
  connections: [{id, member_id, kind: 'brace_end'|'beam_column'|'splice'|'base', weld_type, bolt_type,
              bolts_and_welds_share, system_max_force_N, moment_capacity_Nmm, bolts: {n_bolts, d_mm, grade, t_mm,
              fu_plate_MPa, e_mm, p_mm, d0_mm, lj_mm}, welds: {size_mm, length_mm, fu_MPa, n_sides, site},
              gusset: {t_mm, fy_MPa, w_start_mm, L_conn_mm, L_unbraced_mm, K, Avg_mm2, Avn_mm2, Atg_mm2, Atn_mm2}}]
  bases:    [{id, column_member_id, fixed: bool, plate/anchor geometry for india_connections.base_plate_design}]
  brace_lines: [{id, braces: [member ids], combos: {'+': combo, '-': combo}}]
  links:    [{id, member_id, section, grade, e_mm, bay_L_mm, Vu_N, Pu_N, rotation_rad (or
              drift_ratio_inelastic), end_stiffeners: {both_sides, width_mm, t_mm}, intermediate_stiffener_spacing_mm,
              braced_both_flanges, connected_to_column, doubler}]
  combos_12_2_3_present: bool
cfg: {zone ('II'..'V' or Z), I, brace_config ('X'|'diagonal'|'chevron'|'V'|'K'), height_m, eor_weld_exception}
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import india_is800 as I8
import india_connections as C
import india_is18168 as I18

SRC = "steel_engine/india_is800_s12.py"
SUPPORTED_SYSTEMS = ("OCBF", "SCBF", "EBF", "OMF", "SMF")
_ALIASES = {"OBF": "OCBF", "OCBF": "OCBF", "SCBF": "SCBF", "EBF": "EBF", "OMF": "OMF", "OMRF": "OMF",
            "SMF": "SMF", "SMRF": "SMF"}
NO_BASIS = "no Indian basis"


def normalize_system(system):
    s = str(system or "").upper().replace("-", "").replace("_", "").replace(" ", "")
    if "+" in s:
        s = s.split("+", 1)[0]                     # mixed per-direction system 'OMF+OCBF': the primary (first) one
    return _ALIASES.get(s)


def system_components(system):
    """Canonical components of a system string: 'OMF+OCBF' -> ['OMF', 'OCBF'] (WP6-fix: a transverse moment frame
    with longitudinal braced bays is checked under BOTH Section 12 branches)."""
    out = []
    for part in str(system or "").upper().replace("-", "").replace("_", "").replace(" ", "").split("+"):
        c = _ALIASES.get(part)
        if c and c not in out:
            out.append(c)
    return out


_AUTO = object()


def _chk(id_, value, limit, *, clause, cite, member=None, dc=None, ok=_AUTO, **extra):
    """Structured check. ok defaults to dc <= 1.0 when a dc can be formed; pass ok explicitly (incl. None)."""
    if dc is None and value is not None and limit not in (None, 0):
        try:
            dc = abs(float(value)) / float(limit)
        except (TypeError, ValueError):
            dc = None
    if ok is _AUTO:
        ok = (dc <= 1.0) if dc is not None else None
    out = {"id": id_, "member": member, "value": value, "limit": limit, "dc": dc, "ok": ok, "clause": clause,
           "cite": cite, "source": SRC}
    out.update(extra)
    return out


def _na(id_, *, clause, cite, member=None, reason):
    return _chk(id_, None, None, clause=clause, cite=cite, member=member, ok=None, reason=reason)


def is18168_status(system, cfg):
    """IS 18168:2023 applicability for this job (mandatory Zones III-V for SMRF/SCBF/EBF; Zone II opt-in)."""
    cfg = cfg or {}
    return I18.applies(system, cfg.get("zone") or cfg.get("Z"), opt_in=bool(cfg.get("apply_is18168")))


def _ry(member, p):
    """IS 18168 Table 1 Ry for the member grade (B0/C); IS 1161 tubes / other steels -> 1.4 per 5.2.1 (flagged)."""
    grade = str(member.get("grade") or "")
    key, q = I8.parse_is2062_grade(grade)
    ry = I18.ry_for_grade(key, q) if key else None
    if ry is None:
        return 1.4, "Ry 1.4 (IS 18168:2023 5.2.1 'other steels'; grade %r not an IS 2062 B0/C grade)" % grade
    return ry, "Ry %.1f (IS 18168:2023 Table 1, %s)" % (ry, key)


# ------------------------------------------------------------------------------------------ zone / material
def _zone_roman(z):
    if z is None:
        return None
    s = str(z).upper().strip().replace("ZONE", "").strip()
    if s in ("II", "III", "IV", "V"):
        return s
    try:
        v = float(s)
        return {0.10: "II", 0.16: "III", 0.24: "IV", 0.36: "V"}.get(round(v, 2))
    except ValueError:
        return None


def zone_gate(system, cfg):
    """OCBF / OMF bans: IS 800 12.7.1.1 / 12.10.1.1 (Zones IV-V; Zone III with I > 1) and IS 1893 (Part 1):2016
    Table 9 Note 1 as amended (Amd 2): steel OMRF and OBF not permitted in Zones III-V (decision D4 - block)."""
    sysn = normalize_system(system)
    zone = _zone_roman((cfg or {}).get("zone") or (cfg or {}).get("Z"))
    I = (cfg or {}).get("I")
    clause = {"OCBF": "IS 800:2007 12.7.1.1; IS 1893 (Part 1):2016 Table 9 Note 1 (Amd 2)",
              "OMF": "IS 800:2007 12.10.1.1; IS 1893 (Part 1):2016 Table 9 Note 1 (Amd 2)"}.get(sysn)
    if clause is None:
        return None
    cite = "ordinary braced / moment frames not permitted in Zones III-V (IS 1893 Note 1, D4)"
    if zone is None:
        return _na("zone_gate", clause=clause, cite=cite, reason="seismic zone not given")
    banned = zone in ("III", "IV", "V")
    return _chk("zone_gate", zone, "II only", clause=clause, cite=cite, ok=not banned, I=I,
                is800_only_ban=(zone in ("IV", "V") or (zone == "III" and (I or 1.0) > 1.0)))


def material_gate(member, *, clause, props=None):
    """IS 2062 E250B requirement (12.8.2.1 SCBF braces; 12.11.1 SMF). E250B of IS 800:2007 maps to IS 2062:2025
    E250 with an impact-tested quality (B0 or C; BR only when the RT impact test is specified - Table 3 Note 3).
    IS 1161 YSt tubes are not IS 2062 and fail; IS 18168:2023 5.2 (which governs where applicable) also admits
    E250-E350 (B0 or C) or steels with elongation >= 22 % - IS 1161 Table 2 gives 10-20 %, so tubes still fail."""
    cite = "IS 800:2007 %s 'E250B steel of IS 2062'; IS 2062:2025 Table 3 qualities" % clause
    grade = member.get("grade")
    p = props or {}
    if p.get("section_type") == "CHS" or str(grade or "").upper().replace(" ", "").startswith("YST"):
        return _chk("material_E250B", grade, "IS 2062 E250B", clause="IS 800:2007 " + clause, cite=cite,
                    member=member.get("id"), ok=False,
                    reason="IS 1161 YSt tube is not IS 2062 E250B; IS 18168:2023 5.2(b) needs elongation >= 22 % "
                           "(IS 1161 Table 2: YSt 210 20 %, YSt 240 17 %, YSt 310 14 %, YSt 355 10 %)")
    if not grade:
        return _na("material_E250B", clause="IS 800:2007 " + clause, cite=cite, member=member.get("id"),
                   reason="grade not declared")
    key, q = I8.parse_is2062_grade(grade)
    if key != "E250":
        return _chk("material_E250B", grade, "IS 2062 E250B", clause="IS 800:2007 " + clause, cite=cite,
                    member=member.get("id"), ok=False,
                    reason="IS 800 requires E250B (IS 18168:2023 5.2 would admit E250-E350 B0/C where it governs)")
    if q in ("B0", "C", "B"):
        return _chk("material_E250B", grade, "IS 2062 E250B", clause="IS 800:2007 " + clause, cite=cite,
                    member=member.get("id"), ok=True)
    if q == "BR":
        ok = True if member.get("impact_test_specified") else None
        return _chk("material_E250B", grade, "IS 2062 E250B", clause="IS 800:2007 " + clause, cite=cite,
                    member=member.get("id"), ok=ok,
                    reason=None if ok else "E250 BR: impact test optional (Table 3 Note 3) - specify it for E250B")
    return _chk("material_E250B", grade, "IS 2062 E250B", clause="IS 800:2007 " + clause, cite=cite,
                member=member.get("id"), ok=False, reason="quality %s is not E250B" % (q or "unspecified"))


# ------------------------------------------------------------------------------------------ helpers
def _props(member):
    import sections as S
    sec = member["section"]
    if str(sec).upper().startswith(("CHS", "NB")):
        return S.props(sec, grade=member.get("grade"), process=member.get("process"))
    return S.props(sec)


def _fy(member, p):
    if member.get("fy_MPa"):
        return float(member["fy_MPa"]), float(member.get("fu_MPa") or 0) or None
    m = I8.material_for_section(p, member.get("grade"), process=member.get("process"))
    return m.get("fy_MPa"), m.get("fu_MPa")


def _forces(model_data, mid):
    return (model_data.get("forces") or {}).get(mid) or []


def _members(model_data, role=None):
    return [m for m in (model_data.get("members") or []) if (role is None or m.get("role") == role)
            and m.get("sfrs", True)]


def _member(model_data, mid):
    for m in model_data.get("members") or []:
        if m.get("id") == mid:
            return m
    return None


def _brace_compression(model_data, m):
    fs = _forces(model_data, m["id"])
    return max([f.get("P_N", 0.0) for f in fs] + [0.0]) if fs else None


# ------------------------------------------------------------------------------------------ braces
def brace_member_checks(system, m, model_data, cfg):
    """12.7.2 (OCBF) / 12.8.2 (SCBF) member rules for one brace."""
    sysn = normalize_system(system)
    out = []
    try:
        p = _props(m)
    except KeyError as e:
        return [_na("brace_section", clause="IS 800:2007 12.7/12.8", cite="section", member=m.get("id"), reason=str(e))]
    fy, fu = _fy(m, p)
    sec_cl = "12.7" if sysn == "OCBF" else "12.8"
    if sysn == "SCBF":
        out.append(material_gate(m, clause="12.8.2.1", props=p))
    if not fy:
        out.append(_na("brace_fy", clause="IS 800:2007 " + sec_cl, cite="fy from grade", member=m["id"],
                       reason="grade not resolved (no default fy)"))
        return out
    L = m.get("L_mm")
    K = max(m.get("Kz") or 1.0, m.get("Ky") or 1.0)
    rmin = p.get("r_min") or min(p["rx"], p["ry"])
    klr = K * L / rmin if L else None
    lim = 120 if sysn == "OCBF" else 160
    klr_clause = "IS 800:2007 12.7.2.1" if sysn == "OCBF" else "IS 800:2007 12.8.2.2"
    klr_cite = "slenderness of bracing members shall not exceed %d%s" % (
        lim, "" if sysn == "OCBF" else " (printed '(only hangers)'; applied to braces)")
    a18 = is18168_status(sysn, cfg)
    strict = False
    if sysn == "SCBF" and a18["applies"]:
        # IS 18168 10.2 '< 160' vs IS 800 12.8.2.2 '<= 160': same number, the strict inequality governs; both cited
        klr_clause += " + IS 18168:2023 10.2"
        klr_cite += "; " + I18.CITE_10_2 + " (" + I18.PRECEDENCE + ")"
        strict = True
    out.append(_chk("brace_KL_r", klr, lim, clause=klr_clause, member=m["id"], cite=klr_cite,
                    ok=(klr < lim) if strict else (klr <= lim), K=K, L_mm=L, r_min_mm=rmin) if klr else
               _na("brace_KL_r", clause=klr_clause, cite="KL/r", member=m["id"], reason="L_mm missing"))
    comp = I8.compression_capacity(p, fy, KLz_mm=K * L, KLy_mm=K * L, process=m.get("process")) if L else {"found": False}
    Pc = _brace_compression(model_data, m)
    fac = 0.8 if sysn == "OCBF" else 1.0
    cl = "IS 800:2007 12.7.2.2" if sysn == "OCBF" else "IS 800:2007 12.8.2.3"
    if comp.get("found") and Pc is not None:
        out.append(_chk("brace_compression", Pc, fac * comp["Pd_N"], clause=cl, member=m["id"],
                        cite="required compressive strength <= %s Pd (7.1.2)" % ("0.8" if fac < 1 else "1.0"),
                        Pd_N=comp["Pd_N"]))
    else:
        out.append(_na("brace_compression", clause=cl, cite="P <= %.1f Pd" % fac, member=m["id"],
                       reason="Pd or brace forces missing (%s)" % (comp.get("note") or "")))
    sc = I8.section_class_table2(p, fy, loading="axial" if p.get("section_type") in ("CHS", "angle") else "bending")
    sc_m = I8.section_class_table2(p, fy)
    if sysn == "OCBF":
        out.append(_chk("brace_not_slender", sc["section_class"], "not slender", clause="IS 800:2007 12.7.2.4",
                        cite="plastic, compact or semi-compact, not slender", member=m["id"],
                        ok=sc["section_class"] != "slender"))
    else:
        out.append(_chk("brace_plastic", sc_m["section_class"], "plastic", clause="IS 800:2007 12.8.2.5",
                        cite="braced cross-section shall be plastic (3.7.2)", member=m["id"],
                        ok=sc_m["section_class"] == "plastic"))
    An = m.get("An_mm2")
    gy_cl = "IS 800:2007 12.7.2.6" if sysn == "OCBF" else "IS 800:2007 12.8.2.7"
    if An and fu:
        Tdg = p["A"] * fy / I8.GAMMA_M0_DEFAULT
        Tdn = 0.9 * An * fu / I8.GAMMA_M1_DEFAULT
        out.append(_chk("brace_gross_yield_governs", Tdg, Tdn, clause=gy_cl, member=m["id"],
                        cite="gross area yielding (6.2), not net rupture (6.3), governs"))
    else:
        out.append(_na("brace_gross_yield_governs", clause=gy_cl, cite="6.2 governs over 6.3", member=m["id"],
                       reason="net area An_mm2 / fu not declared"))
    return out


def brace_connection_force(system, m, model_data, *, conn=None, cfg=None):
    """12.8.3.1 SCBF: min(1.1 fy Ag, system max); 12.7.3.1 OCBF: min(1.2 fy Ag, 12.2.3 force, system max).
    IS 18168:2023 10.4.1 (Zones III-V SCBF): expected yield max(1.1 Ry fy Ag, Ru fu An) replaces 1.1 fy Ag (stricter)."""
    sysn = normalize_system(system)
    p = _props(m)
    fy, _ = _fy(m, p)
    if not fy:
        return {"found": False, "demand_N": None, "reason": "grade/fy not resolved"}
    Ag = p["A"]
    sys_max = (conn or {}).get("system_max_force_N")
    a18 = is18168_status(sysn, cfg)
    if sysn == "SCBF":
        base = 1.1 * fy * Ag
        cands = {"1.1 fy Ag (12.8.3.1a)": base}
        clause = "IS 800:2007 12.8.3.1"
        if a18["applies"]:
            # IS 18168 10.4.1(a): max(1.1 Ry fy Ag, Ru fu An) -- stricter than IS 800's 1.1 fy Ag; both cited
            ry, ry_note = _ry(m, p)
            ru = I18.RU.get(I8.parse_is2062_grade(str(m.get("grade") or ""))[0] or "", 1.2)
            _, fu = _fy(m, p)
            An = m.get("An_mm2") or Ag
            exp_ = max(1.1 * ry * fy * Ag, (ru * fu * An) if fu else 0.0)
            cands["max(1.1 Ry fy Ag, Ru fu An) (IS 18168 10.4.1a; %s)" % ry_note] = exp_
            # precedence: the stricter of the two 'expected yield' terms is the (a) term
            cands = {k: v for k, v in cands.items() if v == max(base, exp_)}
            clause += " + IS 18168:2023 10.4.1"
        if sys_max:
            cands["system maximum (12.8.3.1b / IS 18168 10.4.1b)"] = float(sys_max)
    elif sysn == "EBF":
        # IS 18168:2023 12.3.2.2: connections are capacity-protected for the link overstrength 1.1 Ry Sh Vd; 5.5(d):
        # all connections for the Omega 2.5 combinations; 10.4.1 tension (expected brace yield) as the upper bound
        # (the brace cannot deliver more than its own expected strength). IS 800 12.9 refers to specialist literature.
        cands = {}
        f55 = [abs(f.get("P_N", 0.0)) for f in _forces(model_data, m["id"]) if f.get("family") == "12.2.3"]
        if f55:
            cands["IS 18168 5.5 overstrength combination (Omega 2.5)"] = max(f55)
        over = _link_overstrength_for_brace(model_data, m["id"])
        if over:
            fs = [f for f in _forces(model_data, m["id"]) if f.get("P_EL_N") is not None]
            if fs:
                cands["IS 18168 12.3.2.2 link overstrength 1.1 Ry Sh Vd (amplification %.2f)" % over["amp"]] = \
                    max(abs(f.get("P_N", 0.0) - f["P_EL_N"] + over["amp"] * f["P_EL_N"]) for f in fs)
        if not cands:
            return {"found": False, "demand_N": None, "reason": "no 5.5 / link-overstrength brace forces"}
        gov = max(cands, key=cands.get)
        ry, ry_note = _ry(m, p)
        cap = 1.1 * ry * fy * Ag
        D = min(cands[gov], cap)
        return {"found": True, "demand_N": D, "basis": gov if D < cap else "expected brace yield 1.1 Ry fy Ag (IS 18168 10.4.1a) "
                "caps the capacity-design force", "candidates": dict(cands, **{"1.1 Ry fy Ag cap (10.4.1a)": cap}),
                "clause": "IS 18168:2023 12.3.2.2 / 5.5(d) / 10.4.1", "Ag_mm2": Ag, "fy_MPa": fy,
                "cite": "EBF brace connections: larger of the 5.5 overstrength and 12.3.2.2 link-overstrength forces, "
                        "not more than the expected brace strength"}
    else:
        base = 1.2 * fy * Ag
        cands = {"1.2 fy Ag (12.7.3.1a)": base}
        f1223 = [abs(f.get("P_N", 0.0)) for f in _forces(model_data, m["id"]) if f.get("family") == "12.2.3"]
        if f1223:
            cands["12.2.3 force (12.7.3.1b)"] = max(f1223)
        if sys_max:
            cands["system maximum (12.7.3.1c)"] = float(sys_max)
        clause = "IS 800:2007 12.7.3.1"
    gov = min(cands, key=cands.get)
    return {"found": True, "demand_N": cands[gov], "basis": gov, "candidates": cands, "clause": clause,
            "Ag_mm2": Ag, "fy_MPa": fy, "cite": "bracing end connections designed for the minimum of the listed forces"}


def _link_overstrength_for_brace(model_data, brace_id):
    """{amp, link_id} of the link this brace frames into (set by section12_checks after ebf_link_checks)."""
    for ln in model_data.get("links") or []:
        ov = ln.get("_overstrength")
        if ov and brace_id in (ln.get("brace_ids") or []) and ov.get("amplification_braces") is not None:
            return {"amp": max(ov["amplification_braces"], ov.get("amplification_capacity_protected") or 0.0),
                    "link_id": ln.get("id")}
    return None


def ebf_brace_checks(m, model_data, cfg):
    """IS 18168:2023 EBF braces: 5.2 material (Ry), Table 2 (iii) width-thickness (12.3.4.1), 12.3.4.5 tension yield /
    compression buckling at the 1.2 Ry Vd link shear (the axial check itself is ebf_capacity_protected_checks) and
    brace slenderness (IS 800 Table 3 / IS 18168 10.2 as the stricter braced-frame limit, both cited)."""
    out = []
    try:
        p = _props(m)
    except KeyError as e:
        return [_na("brace_section", clause="IS 18168:2023 12.3.4", cite="section", member=m.get("id"), reason=str(e))]
    out.append(material_gate(m, clause="IS 18168:2023 5.2", props=p))
    fy, fu = _fy(m, p)
    if not fy:
        return out + [_na("brace_fy", clause="IS 18168:2023 12.3.4.5", cite="fy from grade", member=m["id"],
                          reason="grade not resolved")]
    ry, _ = _ry(m, p)
    if p.get("section_type") == "I":
        out.append(dict(I18.table2_check("brace", p, fy, ry, member=m["id"]),
                        cite="12.3.4.1: braces satisfy the Table 2 (iii) width-to-thickness limits"))
    L = m.get("L_mm")
    K = max(m.get("Kz") or 1.0, m.get("Ky") or 1.0)
    rmin = p.get("r_min") or min(p["rx"], p["ry"])
    klr = K * L / rmin if L else None
    out.append(_chk("brace_KL_r", klr, I18.BRACE_KLR_LIMIT, clause="IS 18168:2023 10.2 (braced frames) / IS 800:2007 Table 3",
                    member=m["id"], cite=I18.CITE_10_2 + " (applied to EBF braces as the braced-frame limit; IS 800 "
                    "Table 3 gives 180)", ok=(klr < I18.BRACE_KLR_LIMIT) if klr else None, K=K, L_mm=L, r_min_mm=rmin))
    over = _link_overstrength_for_brace(model_data, m["id"])
    fs = [f for f in _forces(model_data, m["id"]) if f.get("P_EL_N") is not None]
    if over and fs:
        Tmax = max(-(f.get("P_N", 0.0) - f["P_EL_N"] + over["amp"] * f["P_EL_N"]) for f in fs)
        Tmin2 = max(-(f.get("P_N", 0.0) - f["P_EL_N"] - over["amp"] * f["P_EL_N"]) for f in fs)
        T = max(Tmax, Tmin2, 0.0)
        Td = I8.tension_capacity(p["A"], fy, None)
        out.append(_chk("12.3.4.5_brace_tension", T, Td["Td_N"], clause="IS 18168:2023 12.3.4.5", member=m["id"],
                        cite="braces shall not yield in tension at 1.2 Ry x the link design strength (6.2 yield)"))
    else:
        out.append(_na("12.3.4.5_brace_tension", clause="IS 18168:2023 12.3.4.5", member=m["id"],
                       cite="tension at 1.2 Ry Vd", reason="link overstrength / EL split unavailable"))
    return out


def brace_connection_checks(system, m, conn, model_data, cfg):
    sysn = normalize_system(system)
    out = []
    pre = "12.7.3" if sysn == "OCBF" else "12.8.3"
    if sysn == "EBF":
        # IS 800 12.9 -> specialist literature; the connection limit states are IS 800 Section 10 / 6.4.1 at the
        # IS 18168 12.3.2.2 / 5.5(d) force (brace_connection_force), gusset rules as for SCBF (engineering practice)
        pre = "12.8.3 (as EBF practice; IS 18168 12.3.4.6)"
    if conn is None:
        return [_na("brace_connection", clause="IS 800:2007 " + pre, cite="brace end connection", member=m["id"],
                    reason="no connection data for brace")]
    dem = brace_connection_force(system, m, model_data, conn=conn, cfg=cfg)
    if not dem["found"]:
        return [_na("brace_connection_force", clause="IS 800:2007 %s.1" % pre, cite="connection force",
                    member=m["id"], reason=dem["reason"])]
    D = dem["demand_N"]
    out.append(_chk("brace_connection_force", D, None, clause=dem["clause"], cite=dem["cite"], member=m["id"],
                    ok=True, basis=dem["basis"], candidates=dem["candidates"]))
    b = conn.get("bolts")
    if b:
        g = C.bolt_group_capacity_is800(b.get("n_bolts"), b.get("d_mm"), b.get("grade", "8.8"),
                                        **{k: v for k, v in b.items() if k not in ("n_bolts", "d_mm", "grade")})
        out.append(_chk("brace_conn_bolts", D, g.get("capacity_N"), clause="IS 800:2007 10.3 at %s.1 force" % pre,
                        cite="n x min(Vdsb, Vdpb)", member=m["id"]) if g.get("found") else
                   _na("brace_conn_bolts", clause="IS 800:2007 10.3", cite="bolts", member=m["id"],
                       reason=str(g.get("required_inputs"))))
    w = conn.get("welds")
    wcj = conn.get("welds_cjp")
    if wcj:
        wc = C.cjp_weld_capacity_N(**wcj)
        out.append(_chk("brace_conn_welds", D, wc.get("capacity_N"), clause="IS 800:2007 10.5.7.1.2 at %s.1 force" % pre,
                        cite="CJP butt weld = parent metal in shear (throat = thinner part)", member=m["id"])
                   if wc.get("found") else
                   _na("brace_conn_welds", clause="IS 800:2007 10.5.7.1.2", cite="CJP welds", member=m["id"],
                       reason=str(wc.get("required_inputs"))))
        w = w or wcj
    elif w:
        wc = C.fillet_weld_capacity_is800_N(**w)
        out.append(_chk("brace_conn_welds", D, wc.get("capacity_N"), clause="IS 800:2007 10.5.7 at %s.1 force" % pre,
                        cite="fillet weld K s fu/(sqrt3 gamma_mw)", member=m["id"]) if wc.get("found") else
                   _na("brace_conn_welds", clause="IS 800:2007 10.5.7", cite="welds", member=m["id"],
                       reason=str(wc.get("required_inputs"))))
    if not b and not w:
        out.append(_na("brace_conn_fasteners", clause="IS 800:2007 10.3/10.5", cite="bolts/welds", member=m["id"],
                       reason="no bolts or welds declared"))
    gus = conn.get("gusset") or {}
    fyg = gus.get("fy_MPa")
    fug = gus.get("fu_MPa")
    bs = C.block_shear(Avg_mm2=gus.get("Avg_mm2"), Avn_mm2=gus.get("Avn_mm2"), Atg_mm2=gus.get("Atg_mm2"),
                       Atn_mm2=gus.get("Atn_mm2"), fy_MPa=fyg, fu_MPa=fug)
    out.append(_chk("brace_conn_block_shear", D, bs.get("Tdb_N"), clause="IS 800:2007 %s.2 / 6.4.1" % pre,
                    cite="tension rupture and block shear under the %s.1 load" % pre, member=m["id"])
               if bs.get("found") else
               _na("brace_conn_block_shear", clause="IS 800:2007 %s.2 / 6.4.1" % pre, cite="block shear",
                   member=m["id"], reason="gusset areas Avg/Avn/Atg/Atn or fy/fu missing"))
    if conn.get("An_conn_mm2") and fug:
        Tdn = 0.9 * conn["An_conn_mm2"] * fug / I8.GAMMA_M1_DEFAULT
        out.append(_chk("brace_conn_net_rupture", D, Tdn, clause="IS 800:2007 %s.2 / 6.3" % pre,
                        cite="tension rupture of the connected section", member=m["id"]))
    wm = C.whitmore_section(t_gusset_mm=gus.get("t_mm"), fy_MPa=fyg, w_start_mm=gus.get("w_start_mm"),
                            L_conn_mm=gus.get("L_conn_mm"), whitmore_width_mm=gus.get("whitmore_width_mm"))
    out.append(_chk("gusset_whitmore_yield", D, wm.get("capacity_N"), clause="engineering practice (Whitmore) + 6.2",
                    cite=C.WHITMORE_CITE, member=m["id"]) if wm.get("found") else
               _na("gusset_whitmore_yield", clause="engineering practice (Whitmore) + 6.2", cite=C.WHITMORE_CITE,
                   member=m["id"], reason="gusset t / Whitmore geometry missing"))
    # 12.x.3.4 gusset out-of-plane buckling: compression = brace buckling strength (IS 18168:2023 10.4.2 wording)
    p = _props(m)
    fy, _ = _fy(m, p)
    K = max(m.get("Kz") or 1.0, m.get("Ky") or 1.0)
    comp = I8.compression_capacity(p, fy, KLz_mm=K * m["L_mm"], KLy_mm=K * m["L_mm"], process=m.get("process")) \
        if (fy and m.get("L_mm")) else {"found": False}
    if wm.get("found") and comp.get("found"):
        gb = C.whitmore_buckling(whitmore_width_mm=wm["whitmore_width_mm"], t_gusset_mm=gus.get("t_mm"),
                                 fy_MPa=fyg, L_unbraced_mm=gus.get("L_unbraced_mm"), K=gus.get("K"))
        out.append(_chk("gusset_out_of_plane_buckling", comp["Pd_N"], gb.get("Pd_N"),
                        clause="IS 800:2007 %s.4" % pre, member=m["id"],
                        cite="gusset plates checked for buckling out of their plane; demand = brace buckling "
                             "strength (IS 18168:2023 10.4.2)") if gb.get("found") else
                   _na("gusset_out_of_plane_buckling", clause="IS 800:2007 %s.4" % pre, cite="gusset buckling",
                       member=m["id"], reason=str(gb.get("required_inputs"))))
    else:
        out.append(_na("gusset_out_of_plane_buckling", clause="IS 800:2007 %s.4" % pre, cite="gusset buckling",
                       member=m["id"], reason="Whitmore geometry or brace Pd missing"))
    # 12.x.3.3 1.2 Mp about the (critical) buckling axis (SCBF/OCBF; EBF braces pinned to the link -- 12.3.4.6 needs a
    # fully restrained connection only where the brace resists part of the link end moment)
    if fy and sysn == "EBF":
        out.append(_chk("brace_conn_pinned_12.3.4.6", bool(conn.get("resists_link_end_moment")), False,
                        clause="IS 18168:2023 12.3.4.6", member=m["id"], dc=None, gate=True,
                        ok=not conn.get("resists_link_end_moment"),
                        cite="brace connection declared pinned (no share of the link end moment); a moment-sharing "
                             "brace connection must be fully restrained"))
    elif fy:
        axis = "y" if (p.get("ry") or 1e9) <= (p.get("rx") or 1e9) else "z"
        Zp = p["Zy"] if axis == "y" else p["Zx"]
        Mdem = 1.2 * Zp * fy
        cap = conn.get("moment_capacity_Nmm")
        cl = "IS 800:2007 %s.3" % pre
        out.append(_chk("brace_conn_1p2Mp", Mdem, cap, clause=cl, member=m["id"],
                        cite="connection moment of 1.2 x full plastic moment of the brace about the buckling axis",
                        axis=axis, capacity_cite=conn.get("moment_capacity_cite")) if cap else
                   _chk("brace_conn_1p2Mp", Mdem, None, clause=cl, member=m["id"], ok=None,
                        cite="1.2 Mp brace-end moment", reason="connection moment capacity not declared"))
    # 12.4.x gates
    out.append(dict(C.cjp_weld_gate(conn.get("weld_type"), location=conn.get("kind", "brace_end"),
                                    eor_exception=(cfg or {}).get("eor_weld_exception")), id="12.4.2_weld_type",
                    member=m["id"]))
    if b:
        out.append(dict(C.hsfg_gate(conn.get("bolt_type")), id="12.4.1_bolt_type", member=m["id"]))
    if b and w:
        out.append(dict(C.no_load_sharing_gate(conn.get("bolts_and_welds_share")), id="12.4.3_no_load_sharing",
                        member=m["id"]))
    return out


def tension_share_checks(system, model_data):
    """12.7.2.3 / 12.8.2.4: along any line of bracing the tension braces resist 30-70 % of the lateral load in each
    direction (horizontal components from the per-combination brace forces)."""
    sysn = normalize_system(system)
    cl = "IS 800:2007 12.7.2.3" if sysn == "OCBF" else "IS 800:2007 12.8.2.4"
    cite = "tension braces resist between 30 and 70 percent of the lateral load along any line of bracing"
    out = []
    lines = model_data.get("brace_lines") or []
    if not lines:
        return [_na("brace_tension_share", clause=cl, cite=cite, reason="brace_lines not supplied")]
    for ln in lines:
        for d, combo in (ln.get("combos") or {}).items():
            t = c = 0.0
            ok_inputs = True
            for bid in ln.get("braces") or []:
                m = _member(model_data, bid)
                f = [x for x in _forces(model_data, bid) if x.get("combo") == combo]
                if not m or not f or m.get("cos_h") is None:
                    ok_inputs = False
                    break
                h = abs(f[0].get("P_N", 0.0)) * abs(m["cos_h"])
                if f[0].get("P_N", 0.0) < 0:
                    t += h
                else:
                    c += h
            if not ok_inputs or (t + c) == 0:
                out.append(_na("brace_tension_share", clause=cl, cite=cite, member=ln.get("id"),
                               reason="brace forces / cos_h missing for combo %s" % combo))
                continue
            frac = t / (t + c)
            out.append(_chk("brace_tension_share", frac, "0.30-0.70", clause=cl, cite=cite, member=ln.get("id"),
                            ok=0.30 <= frac <= 0.70, direction=d, combo=combo, dc=None))
    return out


# ------------------------------------------------------------------------------------------ columns / 12.5
def column_checks(system, model_data, cfg):
    sysn = normalize_system(system)
    out = []
    for m in _members(model_data, "column"):
        try:
            p = _props(m)
        except KeyError as e:
            out.append(_na("column_section", clause="IS 800:2007 12.5", cite="section", member=m.get("id"),
                           reason=str(e)))
            continue
        fy, _ = _fy(m, p)
        if sysn == "SCBF":
            sc = I8.section_class_table2(p, fy) if fy else {"section_class": None}
            out.append(_chk("scbf_column_plastic", sc["section_class"], "plastic", clause="IS 800:2007 12.8.4.1",
                            cite="column sections used in SCBF shall be plastic (3.7.2)", member=m["id"],
                            ok=(sc["section_class"] == "plastic") if sc["section_class"] else None))
        if sysn == "SMF":
            out.append(material_gate(m, clause="12.11.1", props=p))
            sc = I8.section_class_table2(p, fy) if fy else {"section_class": None}
            out.append(_chk("smf_column_class", sc["section_class"], "plastic or compact",
                            clause="IS 800:2007 12.11.3.1", member=m["id"],
                            cite="beam and column sections plastic or compact (plastic at hinge locations)",
                            ok=(sc["section_class"] in ("plastic", "compact")) if sc["section_class"] else None))
        if sysn == "SMF":
            f1223_all = [f for f in _forces(model_data, m["id"]) if f.get("family") == "12.2.3"]
            if f1223_all and fy and m.get("L_mm"):
                mc = I8.member_check_is800(dict(m), f1223_all)
                out.append(_chk("12.11.3.4_out_of_plane_12.2.3", mc.get("dc"), 1.0, clause="IS 800:2007 12.11.3.4",
                                member=m["id"], ok=mc.get("ok"), dc=mc.get("dc"),
                                cite="plane frame non-sway out of plane: buckling check under 12.2.3 (9.3.2.2)",
                                governing_combo=mc.get("governing_combo")))
            else:
                out.append(_na("12.11.3.4_out_of_plane_12.2.3", clause="IS 800:2007 12.11.3.4", member=m["id"],
                               cite="buckling under 12.2.3", reason="no 12.2.3 forces / fy / L"))
            ls = m.get("lateral_support_both_flanges")
            out.append(_chk("12.11.3.3_column_lateral_support", ls, True, clause="IS 800:2007 12.11.3.3",
                            member=m["id"], dc=None, ok=None if ls is None else bool(ls),
                            cite="lateral support at top and bottom beam flange levels for 2 % of flange strength"))
        if not fy or not m.get("L_mm"):
            out.append(_na("12.5.1_column", clause="IS 800:2007 12.5.1", cite="P/Pd > 0.4 -> 12.2.3",
                           member=m["id"], reason="fy or L_mm missing"))
            continue
        comp = I8.compression_capacity(p, fy, KLz_mm=(m.get("Kz") or 1.0) * m["L_mm"],
                                       KLy_mm=(m.get("Ky") or 1.0) * m["L_mm"], process=m.get("process"))
        a18 = is18168_status(sysn, cfg)
        if a18["applies"] and comp.get("found"):
            # IS 18168 7.2 (alone: IS 800 Table 3 gives 180 for the same member) -> cite IS 18168
            klr = comp.get("KL_over_r_max")
            out.append(_chk("is18168_7_2_column_KL_r", klr, I18.COLUMN_KLR_LIMIT, clause="IS 18168:2023 7.2",
                            member=m["id"], cite=I18.CITE_7_2, ok=(klr < I18.COLUMN_KLR_LIMIT) if klr is not None else None,
                            note="IS 800:2007 Table 3 (180) is less strict; IS 18168 governs (Foreword)"))
        fs = _forces(model_data, m["id"])
        t4 = [f.get("P_N", 0.0) for f in fs if f.get("family", "table4") != "12.2.3"]
        if not comp.get("found") or not t4:
            out.append(_na("12.5.1_column", clause="IS 800:2007 12.5.1", cite="P/Pd > 0.4 -> 12.2.3",
                           member=m["id"], reason="Pd or Table 4 forces missing"))
            continue
        ratio = max(t4) / comp["Pd_N"]
        if ratio <= 0.4:
            out.append(_chk("12.5.1_trigger", ratio, 0.4, clause="IS 800:2007 12.5.1", member=m["id"],
                            cite="P/Pd <= 0.4: 12.5.1.1 not triggered", ok=True, dc=None))
            continue
        f1223 = [f.get("P_N", 0.0) for f in fs if f.get("family") == "12.2.3"]
        if not f1223:
            out.append(_na("12.5.1.1_column_12.2.3", clause="IS 800:2007 12.5.1.1", member=m["id"],
                           cite="axial strength from 12.2.3 combinations", reason="P/Pd = %.2f > 0.4 but no "
                           "12.2.3 (1.2DL+0.5LL+/-2.5EL, 0.9DL+/-2.5EL) forces" % ratio))
            continue
        Pc = max(f1223)
        Pt = -min(f1223)
        cap = m.get("P_cap_12_5_1_2_N")
        if cap:
            Pc, Pt = min(Pc, cap), min(Pt, cap)
        out.append(_chk("12.5.1.1_column_compression", Pc, comp["Pd_N"], clause="IS 800:2007 12.5.1.1 / 12.5.1.2",
                        cite="required axial strength from 12.2.3 (capped per 12.5.1.2 when declared)",
                        member=m["id"], P_over_Pd_table4=ratio))
        if Pt > 0:
            Td = I8.tension_capacity(p["A"], fy, None)
            out.append(_chk("12.5.1.1_column_tension", Pt, Td["Td_N"], clause="IS 800:2007 12.5.1.1",
                            cite="axial tension from 12.2.3 vs 6.2 yield (rupture per splice detail)",
                            member=m["id"]))
    return out


def base_checks(system, model_data, cfg):
    """12.12: fixed bases for 1.2 Mp of the column (+ anchors for shear+tension+prying); all bases for
    max(full shear, 1.2 x column shear capacity)."""
    out = []
    sysn = normalize_system(system)
    cols = {m["id"]: m for m in (model_data.get("members") or []) if m.get("role") == "column"}
    bases = model_data.get("bases") or []
    if not bases:
        return [_na("12.12_bases", clause="IS 800:2007 12.12", cite="column bases 1.2 Mp / 1.2 Vd",
                    reason="no base data")]
    for b in bases:
        m = cols.get(b.get("column_member_id"))
        if not m:
            continue
        sfrs = bool(m.get("sfrs", True))
        p = _props(m)
        fy, _ = _fy(m, p)
        ax = b.get("axis", "z")
        Zp = p["Zx"] if ax == "z" else p["Zy"]
        Vd = I8.shear_capacity(p, fy, axis=ax).get("Vd_N") if fy else None
        import inspect as _insp
        _allowed = set(_insp.signature(C.base_plate_design).parameters) | {"load_cases", "Hc_mm"}
        geo = {k: v for k, v in b.items() if k in _allowed and k not in ("sfrs_fixed_base", "col_Zp_mm3", "col_fy_MPa",
                                                                       "col_Vd_N", "sfrs_moment_factor")}
        need = ("B_mm", "L_mm", "t_plate_mm", "fy_plate_MPa", "fck_MPa") + (() if geo.get("load_cases") else ("P_N",))
        if not all(geo.get(k) is not None for k in need):
            out.append(_na("12.12_base", clause="IS 800:2007 12.12 / 7.4", cite="base plate + anchors",
                           member=b.get("id"), reason="base geometry/forces missing: %s" %
                           [k for k in need if geo.get(k) is None]))
            continue
        geo.setdefault("col_d_mm", p["d"]); geo.setdefault("col_bf_mm", p["bf"]); geo.setdefault("col_tf_mm", p["tf"])
        Hc = geo.pop("Hc_mm", None) or m.get("L_mm")
        if not sfrs:
            # gravity column base: IS 800 7.4 / 10.3 under its own (P, M, V); no 12.12 / IS 18168 9 demands
            mfac, vmin, cl, ct = 1.2, None, "IS 800:2007 7.4 / 10.3", "gravity column base: bearing 0.6 fck, anchors, plate (7.4)"
            b = dict(b, fixed=False)
            Vd = None
        else:
            mfac, vmin, cl, ct = 1.2, None, "IS 800:2007 12.12 / 7.4 / 10.3", "fixed base 1.2 Mp (12.12.1); shear max(full, 1.2 Vd) (12.12.2)"
        a18 = is18168_status(sysn, cfg)
        if sfrs and a18["applies"] and fy:
            ry, ry_note = _ry(m, p)
            if b.get("fixed"):
                # IS 18168 9.3: M = 1.1 Ry Mpc (1.54 Mpc for E250 > IS 800's 1.2 Mp -> governs), V = 2.2 Ry Mpc/Hc
                mfac = max(1.2, 1.1 * ry)
                vmin = (2.2 * ry * Zp * fy / Hc) if Hc else None
                cl += " + IS 18168:2023 9.3"
                ct += "; IS 18168:2023 9.3 (pdf p. 13): fixed base 1.1 Ry Mpc, shear 2.2 Ry Mpc/Hc (%s; stricter governs)" % ry_note
            else:
                vmin = (1.1 * ry * Zp * fy / Hc) if Hc else None
                cl += " + IS 18168:2023 9.4"
                ct += "; IS 18168:2023 9.4 (pdf p. 13): pinned base min moment 0.5 Ry Myc, shear 1.1 Ry Mpc/Hc (%s)" % ry_note
                geo["M_Nmm"] = max(float(geo.get("M_Nmm") or 0.0), 0.5 * ry * p["Sx"] * fy)
        cases = geo.pop("load_cases", None) or [{"combo": "declared", "P_N": geo.get("P_N"), "M_Nmm": geo.get("M_Nmm", 0.0),
                                                 "V_N": geo.get("V_N", 0.0)}]
        worst, per_case = None, []
        for lc in cases:
            g2 = dict(geo, P_N=float(lc.get("P_N") or 0.0), M_Nmm=abs(float(lc.get("M_Nmm") or 0.0)),
                      V_N=abs(float(lc.get("V_N") or 0.0)))
            if vmin:
                g2["V_N"] = max(g2["V_N"], vmin)
            r = C.base_plate_design(sfrs_fixed_base=bool(b.get("fixed")), col_Zp_mm3=Zp, col_fy_MPa=fy, col_Vd_N=Vd,
                                    sfrs_moment_factor=mfac, **g2)
            if not b.get("fixed") and Vd:
                r["demands"]["V_N"] = max(r["demands"]["V_N"], 1.2 * Vd)
            r["combo"] = lc.get("combo")
            per_case.append({"combo": lc.get("combo"), "dc": r.get("dc"), "ok": r.get("ok"), "P_N": g2["P_N"],
                             "M_Nmm": g2["M_Nmm"], "V_N": g2["V_N"]})
            key = (r.get("ok") is None, r.get("dc") if r.get("dc") is not None else -1)
            if worst is None or key > worst[0]:
                worst = (key, r)
        r = worst[1]
        out.append(_chk("12.12_base" if sfrs else "7.4_base", r.get("dc"), 1.0, clause=cl, member=b.get("id"), cite=ct,
                        ok=r.get("ok"), dc=r.get("dc"), detail=r, governing_combo=r.get("combo"), n_cases=len(per_case),
                        per_case=per_case, sfrs=sfrs))
    return out


# ------------------------------------------------------------------------------------------ SMF / OMF
def panel_zone_design_shear(Mp_beams_Nmm, d_beam_mm, tf_beam_mm, V_col_N=0.0, factor=1.2):
    """Panel shear at the 12.11.2.2 connection design moments: sum(1.2 Mp_b/(d_b - tf_b)) - V_column
    (standard free-body; EOR-documented form of 12.11.2.2 / 12.11.2.3, HR800-17). IS 18168:2023 8.3.1 uses
    Vpzd = sum(1.1 Ry fy Zpb/0.95 db) where IS 18168 governs."""
    arm = float(d_beam_mm) - float(tf_beam_mm)
    return max(sum(factor * float(M) for M in Mp_beams_Nmm) / arm - abs(float(V_col_N or 0.0)), 0.0)


def _mpc_reduced(p, fy, P, axis):
    """Column plastic moment reduced for axial load (IS 800 9.3.1.2(c) form with Mp = Zp fy; n = P/(A fy))."""
    n = max(float(P or 0.0), 0.0) / (p["A"] * fy)
    if axis == "z":
        Mp = p["Zx"] * fy
        return min(1.11 * Mp * (1 - n), Mp), n
    Mp = p["Zy"] * fy
    return (Mp if n <= 0.2 else 1.56 * Mp * (1 - n) * (n + 0.6)), n


def scwb_joint(joint, model_data):
    """12.11.3.2 sum(Mpc)/sum(Mpb) >= 1.2 at one joint, columns above/below with the axis in the frame plane and
    Mpc reduced for the joint column axial load (12.2.3 family when present, else the Table 4 maximum)."""
    cols, beams = joint.get("columns") or [], joint.get("beams") or []
    if not cols or not beams:
        return _na("12.11.3.2_SCWB", clause="IS 800:2007 12.11.3.2", cite="sum Mpc / sum Mpb >= 1.2",
                   member=joint.get("id"), reason="joint has no columns or beams")
    sMpc, terms_c = 0.0, []
    for c in cols:
        m = _member(model_data, c["member_id"]) or c
        p = _props(m)
        fy, _ = _fy(m, p)
        if not fy:
            return _na("12.11.3.2_SCWB", clause="IS 800:2007 12.11.3.2", cite="SCWB", member=joint.get("id"),
                       reason="column grade not resolved")
        axis = "z" if (m.get("major_axis_plane") in (None, joint.get("frame_dir"))) else "y"
        fs = _forces(model_data, m["id"])
        f1223 = [f.get("P_N", 0.0) for f in fs if f.get("family") == "12.2.3"]
        P = c.get("P_N") if c.get("P_N") is not None else (max(f1223) if f1223 else max([f.get("P_N", 0.0) for f in fs] + [0.0]))
        Mpc, n = _mpc_reduced(p, fy, P, axis)
        sMpc += Mpc
        terms_c.append({"member": m["id"], "section": m["section"], "axis": axis, "P_N": P, "n": n, "Mpc_Nmm": Mpc})
    sMpb, terms_b = 0.0, []
    for b in beams:
        m = _member(model_data, b["member_id"]) or b
        p = _props(m)
        fy, _ = _fy(m, p)
        Mpb = p["Zx"] * fy
        sMpb += Mpb
        terms_b.append({"member": m["id"], "section": m["section"], "Mpb_Nmm": Mpb})
    ratio = sMpc / sMpb
    return _chk("12.11.3.2_SCWB", ratio, 1.2, clause="IS 800:2007 12.11.3.2", member=joint.get("id"),
                cite="sum Mpc (above + below, axial-reduced per 9.3.1.2) / sum Mpb >= 1.2", dc=1.2 / ratio,
                ok=ratio >= 1.2, level=joint.get("level"), columns=terms_c, beams=terms_b)


def scwb_joint_is18168(joint, model_data, cfg=None):
    """IS 18168:2023 8.2: sum Zpc fyc (1 - Pu/Pd) / sum 1.1 Ry Zpb fyb > 1.4 (Pu = max factored axial compression,
    Pd = 7.1.2 design compressive strength of the column); 8.2.1: not required at the roof level.  Stricter than
    IS 800 12.11.3.2 (1.2, no Ry) -> governs where IS 18168 applies (both records kept)."""
    cols, beams = joint.get("columns") or [], joint.get("beams") or []
    cid = "is18168_8_2_SCWB"
    if joint.get("roof") or not any(c.get("position") == "above" for c in cols):
        return _chk(cid, None, None, clause="IS 18168:2023 8.2.1", cite="need not be satisfied at the roof level",
                    member=joint.get("id"), ok=True, dc=None, note="roof joint")
    if not cols or not beams:
        return _na(cid, clause="IS 18168:2023 8.2", cite=I18.CITE_8_2, member=joint.get("id"),
                   reason="joint has no columns or beams")
    sMpc, terms_c = 0.0, []
    for c in cols:
        m = _member(model_data, c["member_id"]) or c
        p = _props(m)
        fy, _ = _fy(m, p)
        if not fy or not m.get("L_mm"):
            return _na(cid, clause="IS 18168:2023 8.2", cite=I18.CITE_8_2, member=joint.get("id"),
                       reason="column grade / L_mm not resolved")
        axis = "z" if (m.get("major_axis_plane") in (None, joint.get("frame_dir"))) else "y"
        fs = _forces(model_data, m["id"])
        Pu = max([f.get("P_N", 0.0) for f in fs] + [0.0])
        comp = I8.compression_capacity(p, fy, KLz_mm=(m.get("Kz") or 1.0) * m["L_mm"],
                                       KLy_mm=(m.get("Ky") or 1.0) * m["L_mm"], process=m.get("process"))
        if not comp.get("found"):
            return _na(cid, clause="IS 18168:2023 8.2", cite=I18.CITE_8_2, member=joint.get("id"),
                       reason="column Pd (7.1.2) not computed")
        Zp = p["Zx"] if axis == "z" else p["Zy"]
        Mpc = Zp * fy * max(1.0 - Pu / comp["Pd_N"], 0.0)
        sMpc += Mpc
        terms_c.append({"member": m["id"], "section": m["section"], "axis": axis, "Pu_N": Pu, "Pd_N": comp["Pd_N"],
                        "Mpc_Nmm": Mpc})
    sMbo, terms_b = 0.0, []
    for b in beams:
        m = _member(model_data, b["member_id"]) or b
        p = _props(m)
        fy, _ = _fy(m, p)
        if not fy:
            return _na(cid, clause="IS 18168:2023 8.2", cite=I18.CITE_8_2, member=joint.get("id"),
                       reason="beam grade not resolved")
        ry, ry_note = _ry(m, p)
        Mbo = 1.1 * ry * p["Zx"] * fy
        sMbo += Mbo
        terms_b.append({"member": m["id"], "section": m["section"], "Ry": ry, "Ry_basis": ry_note, "Mbo_Nmm": Mbo})
    ratio = sMpc / sMbo
    return _chk(cid, ratio, I18.SCWB_MIN, clause="IS 18168:2023 8.2", member=joint.get("id"),
                cite=I18.CITE_8_2 + " (" + I18.PRECEDENCE + "; IS 800 12.11.3.2 gives 1.2 without Ry)",
                dc=I18.SCWB_MIN / ratio if ratio else None, ok=ratio > I18.SCWB_MIN, level=joint.get("level"),
                columns=terms_c, beams=terms_b)


def smf_joint_checks(joint, model_data, cfg, *, system="SMF"):
    """Per-joint 12.11.2.1 (1.2 Mp), 12.11.2.2 (shear), 12.11.2.3/.4 (panel zone), 12.11.2.5 (continuity plates)
    for SMF; 12.10.2.1/12.10.2.4/12.10.2.5 for OMF."""
    sysn = normalize_system(system)
    out = []
    conn = joint.get("connection") or {}
    beams = joint.get("beams") or []
    Mp_list = []
    for b in beams:
        m = _member(model_data, b["member_id"]) or b
        p = _props(m)
        fy, _ = _fy(m, p)
        if not fy:
            out.append(_na("beam_Mp", clause="IS 800:2007 12.11.2.1", cite="1.2 Mp", member=m.get("id"),
                           reason="beam grade not resolved"))
            continue
        Mp = p["Zx"] * fy
        Mp_list.append((b, m, p, fy, Mp))
        if sysn == "SMF":
            out.append(material_gate(m, clause="12.11.1", props=p))
            sc = I8.section_class_table2(p, fy)
            out.append(_chk("smf_beam_class", sc["section_class"], "plastic (hinge) / compact",
                            clause="IS 800:2007 12.11.3.1", cite="plastic or compact; plastic at hinge locations",
                            member=m["id"], ok=sc["section_class"] in ("plastic", "compact")))
        Mdem = 1.2 * Mp
        cl = "IS 800:2007 12.11.2.1" if sysn == "SMF" else "IS 800:2007 12.10.2.1"
        if sysn == "OMF" and conn.get("max_deliverable_moment_Nmm"):
            Mdem = min(Mdem, float(conn["max_deliverable_moment_Nmm"]))
        if sysn == "SMF" and b.get("rbs"):
            Mdem = max(Mdem, 0.8 * Mp)
        cap = conn.get("moment_capacity_Nmm")
        out.append(_chk("connection_moment", Mdem, cap, clause=cl, member=m["id"],
                        cite="beam-to-column connection for 1.2 x full plastic moment of the beam",
                        capacity_cite=conn.get("cite")) if cap else
                   _chk("connection_moment", Mdem, None, clause=cl, member=m["id"], ok=None,
                        cite="1.2 Mp beam", reason="connection moment capacity not declared"))
        Lc = b.get("L_clear_mm")
        Vg = b.get("V_gravity_N")
        vcl = "IS 800:2007 12.11.2.2" if sysn == "SMF" else "IS 800:2007 12.10.2.4"
        if Lc and Vg is not None:
            Vdem = abs(Vg) + 2 * Mdem / Lc
            if sysn == "SMF" and b.get("V_12_2_3_N") is not None:
                Vdem = min(Vdem, abs(b["V_12_2_3_N"]))
            vcap = conn.get("shear_capacity_N")
            out.append(_chk("connection_shear", Vdem, vcap, clause=vcl, member=m["id"],
                            cite="shear from 1.2DL+0.5LL plus 2 x (1.2 Mp)/L'") if vcap else
                       _chk("connection_shear", Vdem, None, clause=vcl, member=m["id"], ok=None,
                            cite="connection shear", reason="connection shear capacity not declared"))
        else:
            out.append(_na("connection_shear", clause=vcl, cite="1.2DL+0.5LL + 2 Mconn/L'", member=m["id"],
                           reason="L_clear_mm / V_gravity_N missing"))
    # panel zone (strong-axis joints)
    cols = joint.get("columns") or []
    below = next((c for c in cols if c.get("position") == "below"), cols[0] if cols else None)
    if sysn == "SMF" and below and Mp_list:
        cm = _member(model_data, below["member_id"]) or below
        cp = _props(cm)
        fyc, _ = _fy(cm, cp)
        strong = cm.get("major_axis_plane") in (None, joint.get("frame_dir"))
        if strong and fyc:
            bp0 = Mp_list[0][2]
            Vcol = below.get("V_N") or 0.0
            Vpz = panel_zone_design_shear([x[4] for x in Mp_list], bp0["d"], bp0["tf"], Vcol)
            pz = I8.panel_zone_check(d_col_mm=cp["d"], tw_mm=cp["tw"], bf_mm=cp["bf"], tf_mm=cp["tf"],
                                     d_beam_mm=bp0["d"], tf_beam_mm=None, V_design_N=Vpz, fy_MPa=fyc,
                                     doubler_t_mm=joint.get("doubler_t_mm") or 0.0,
                                     continuity_plates=bool(joint.get("continuity_plates")))
            out.append(_chk("12.11.2.3_panel_zone", pz.get("dc"), 1.0, clause="IS 800:2007 12.11.2.3 / 12.11.2.4",
                            member=joint.get("id"), ok=pz.get("pass"), dc=pz.get("dc"),
                            cite="panel zone shear buckling (8.4.2) at the 12.11.2.2 shear; individual t >= (dp+bp)/90",
                            detail=pz))
        elif not strong:
            out.append(_chk("12.11.2.3_panel_zone", None, None, clause="IS 800:2007 12.11.2.3", member=joint.get("id"),
                            cite="column strong-axis connections only", ok=True, note="weak-axis joint"))
    if sysn == "SMF":
        typ = str(conn.get("type") or "").lower()
        if "end_plate" in typ or "end plate" in typ:
            out.append(_chk("12.11.2.5_continuity_plates", None, None, clause="IS 800:2007 12.11.2.5",
                            member=joint.get("id"), cite="continuity plates except in end plate connection", ok=True))
        else:
            cp_ = joint.get("continuity_plates")
            out.append(_chk("12.11.2.5_continuity_plates", cp_, True, clause="IS 800:2007 12.11.2.5",
                            member=joint.get("id"), cite="continuity plates in all strong-axis welded connections",
                            ok=None if cp_ is None else bool(cp_), dc=None))
        out.append(scwb_joint(joint, model_data))
        if is18168_status(sysn, cfg)["applies"]:
            out.append(scwb_joint_is18168(joint, model_data, cfg))
    else:
        typ = str(conn.get("type") or "").lower()
        if "weld" in typ:
            tcp, tfb = joint.get("continuity_plate_t_mm"), (Mp_list[0][2]["tf"] if Mp_list else None)
            # provided-vs-required row: D/C = required / provided (dc=None would form provided / required, WP6-fix)
            dc_cp = (float(tfb) / float(tcp)) if (tcp and tfb) else None
            out.append(_chk("12.10.2.5_continuity_plates", tcp, tfb, clause="IS 800:2007 12.10.2.5",
                            member=joint.get("id"), cite="continuity plates t >= beam flange t (rigid welded)",
                            ok=None if (tcp is None or tfb is None) else tcp >= tfb, dc=dc_cp))
    if conn:
        out.append(dict(C.cjp_weld_gate(conn.get("weld_type"), location="beam_column",
                                        eor_exception=(cfg or {}).get("eor_weld_exception")),
                        id="12.4.2_weld_type", member=joint.get("id")))
        if conn.get("bolt_type") is not None or conn.get("bolts"):
            out.append(dict(C.hsfg_gate(conn.get("bolt_type")), id="12.4.1_bolt_type", member=joint.get("id")))
    else:
        out.append(_na("beam_column_connection", clause="IS 800:2007 12.11.2 / 12.10.2", cite="connection data",
                       member=joint.get("id"), reason="no connection declared at joint"))
    return out


def joints_from_model(nodes, elements, *, frame_members=None):
    """Build SMF/OMF joints from model connectivity (never a 'representative joint').

    nodes: {id: (x, y, z)}; elements: [{id, role 'beam'|'column', node_i, node_j, section, ...}].
    frame_members: optional set of element ids that belong to the moment frames (others are gravity).
    A joint is every node where >= 1 frame beam meets >= 1 frame column; beams are grouped by frame direction
    (X or Y from their plan orientation) so each (node, direction) is one joint."""
    fm = set(frame_members) if frame_members is not None else None
    by_node = {}
    for e in elements:
        if fm is not None and e["id"] not in fm:
            continue
        for end in ("node_i", "node_j"):
            by_node.setdefault(e[end], []).append(e)
    joints = []
    for nid, els in by_node.items():
        x0, y0, z0 = nodes[nid]
        cols, beams = [], {"X": [], "Y": []}
        for e in els:
            other = e["node_j"] if e["node_i"] == nid else e["node_i"]
            x1, y1, z1 = nodes[other]
            if e.get("role") == "column":
                cols.append({"member_id": e["id"], "position": "above" if z1 > z0 else "below"})
            elif e.get("role") == "beam":
                rel = e.get("release_major") or "none"
                if rel == "both" or (rel == "I" and e["node_i"] == nid) or (rel == "J" and e["node_j"] == nid):
                    continue          # pinned at this end: delivers no moment to the joint (WP6-fix)
                d = "X" if abs(x1 - x0) >= abs(y1 - y0) else "Y"
                beams[d].append({"member_id": e["id"], "L_clear_mm": e.get("L_clear_mm"),
                                 "V_gravity_N": e.get("V_gravity_N")})
        for d, bl in beams.items():
            if bl and cols:
                joints.append({"id": "J%s-%s" % (nid, d), "node": nid, "level": z0, "frame_dir": d,
                               "columns": cols, "beams": bl})
    return joints


# ------------------------------------------------------------------------------------------ EBF (IS 18168)
IS18168_RY = {"E250": 1.4, "E275": 1.4, "E300": 1.3, "E350": 1.2}      # Table 1 (B0 or C)
IS18168_SH = {"I": 1.25, "box": 1.4}                                   # cl. 4 / 12.3.2.2
IS18168_LINK_ROTATION_LIMIT = 0.08                                     # 12.3.3.1


def ebf_link_checks(link, model_data=None, cfg=None):
    """IS 18168:2023 shear links (EBF): 11.1 section, 11.2 design shear strength, 11.3 length, 12.3.2.1 demand,
    12.3.3.1 rotation <= 0.08 rad, 11.4 stiffeners, 12.3.1 no link-to-column, 12.3.3.2 bracing, and the
    capacity-design forces of 12.3.2.2 (1.1 Ry Sh Vd_link) / 12.3.4.5 (braces 1.2 Ry Vd_link)."""
    out = []
    lid = link.get("id")
    import sections as S
    try:
        p = S.props(link["section"])
    except KeyError as e:
        return [_na("link_section", clause="IS 18168:2023 11.1", cite="link section", member=lid, reason=str(e))]
    st = p.get("section_type")
    out.append(_chk("11.1_link_section", st, "I-shaped (rolled/built-up) or built-up box; no HSS",
                    clause="IS 18168:2023 11.1", cite="HSS sections shall not be used as links", member=lid,
                    ok=st == "I", dc=None))
    if link.get("doubler"):
        out.append(_chk("11.1a_no_doubler", True, False, clause="IS 18168:2023 11.1(a)", member=lid,
                        cite="single-thickness web; doubler plates and web penetrations not permitted", ok=False,
                        dc=None))
    key, q = I8.parse_is2062_grade(link.get("grade"))
    fy = link.get("fy_MPa") or (I8.fy_is2062(link["grade"], I8.governing_thickness_mm(p)) if key in I8.IS2062_TABLE3
                                 else None)
    Ry = IS18168_RY.get(key) if q in ("B0", "C") else (1.4 if link.get("other_steel_5_2b") else None)
    if not fy:
        out.append(_na("link_material", clause="IS 18168:2023 5.2", cite="IS 2062 E250-E350 (B0 or C)", member=lid,
                       reason="link grade not resolved"))
        return out
    if Ry is None:
        out.append(_chk("5.2_material", link.get("grade"), "IS 2062 E250/E275/E300/E350 (B0 or C)",
                        clause="IS 18168:2023 5.2 / Table 1", cite="material grades; Ry from Table 1",
                        member=lid, ok=False, dc=None))
        Ry = None
    Sh = IS18168_SH["I"] if st == "I" else IS18168_SH["box"]
    gm0 = 1.1
    d, tf, tw = p["d"], p["tf"], p["tw"]
    if Ry and st == "I":
        out.append(dict(I18.table2_check("link", p, fy, Ry, member=lid),
                        cite="11.1: flange and web width-to-thickness less than Table 2 (iv) links"))
    AwL = (d - 2 * tf) * tw
    Py = fy * p["A"]
    Pu = abs(float(link.get("Pu_N") or 0.0))
    r = Pu / Py
    VpL = fy * AwL / math.sqrt(3.0) * (1.0 if r <= 0.15 else math.sqrt(max(1 - r ** 2, 0.0)))
    MpL = fy * p["Zx"] * (1.0 if r <= 0.15 else (1 - r))
    e = link.get("e_mm")
    if not e:
        out.append(_na("11.3_link_length", clause="IS 18168:2023 11.3", cite="e < 1.6 MpL/VpL", member=lid,
                       reason="link length e_mm missing"))
        return out
    Vd = min(VpL / gm0, 2 * MpL / (e * gm0))
    out.append({"id": "11.2_link_design_shear", "member": lid, "value": Vd, "VpL_N": VpL, "MpL_Nmm": MpL,
                "Pu_over_Py": r, "clause": "IS 18168:2023 11.2", "ok": True, "dc": None, "limit": None,
                "cite": "lower of VpL/gamma_m0 and 2 MpL/(e gamma_m0), gamma_m0 = 1.1", "source": SRC})
    elim = 1.6 * MpL / VpL
    Vu = link.get("Vu_N")
    if r > 0.15 and Vu:
        Vy = fy * AwL / math.sqrt(3.0)
        rho = r / (abs(Vu) / Vy)
        if rho > 0.5:
            elim = 1.6 * MpL * (1.15 - 0.3 * rho) / VpL
    out.append(_chk("11.3_link_length", e, elim, clause="IS 18168:2023 11.3", member=lid,
                    cite="e < 1.6 MpL/VpL (shear links only; reduced for Pu/Py > 0.15)", ok=e < elim))
    if Vu is not None:
        out.append(_chk("12.3.2.1_link_shear", abs(Vu), Vd, clause="IS 18168:2023 12.3.2.1 / 11.2", member=lid,
                        cite="link shear demand from IS 1893 analysis <= link design shear strength"))
    else:
        out.append(_na("12.3.2.1_link_shear", clause="IS 18168:2023 12.3.2.1", cite="link shear", member=lid,
                       reason="Vu_N missing"))
    rot = link.get("rotation_rad")
    basis = "declared"
    if rot is None and link.get("drift_ratio_inelastic") is not None and link.get("bay_L_mm"):
        rot = link["bay_L_mm"] / e * link["drift_ratio_inelastic"]
        basis = "gamma = (L/e) theta_p (rigid-plastic mechanism, engineering practice)"
    out.append(_chk("12.3.3.1_link_rotation", rot, IS18168_LINK_ROTATION_LIMIT, clause="IS 18168:2023 12.3.3.1",
                    member=lid, cite="link rotation angle shall not exceed 0.08 rad", basis=basis) if rot is not None else
               _na("12.3.3.1_link_rotation", clause="IS 18168:2023 12.3.3.1", cite="<= 0.08 rad", member=lid,
                   reason="link rotation (or inelastic drift ratio + bay length) missing"))
    es = link.get("end_stiffeners") or {}
    if st == "I":
        need_w = p["bf"] - 2 * tw
        need_t = max(0.75 * tw, 10.0)
        ok_es = (bool(es.get("both_sides")) and (es.get("width_mm") or 0) >= need_w and (es.get("t_mm") or 0) >= need_t) \
            if es else None
        out.append(_chk("11.4.1_end_stiffeners", es or None, {"both_sides": True, "combined_width_mm": need_w,
                                                               "t_min_mm": need_t},
                        clause="IS 18168:2023 11.4.1", member=lid, ok=ok_es, dc=None,
                        cite="full-depth both sides; combined width >= bf - 2tw; t >= max(0.75tw, 10 mm)"))
        smax = 30 * tw - 0.2 * d
        s = link.get("intermediate_stiffener_spacing_mm")
        out.append(_chk("11.4.2_intermediate_stiffeners", s, smax, clause="IS 18168:2023 11.4.2", member=lid,
                        cite="intermediate web stiffeners at spacing <= (30 tw - 0.2 d)") if s is not None else
                   _na("11.4.2_intermediate_stiffeners", clause="IS 18168:2023 11.4.2", cite="<= 30tw - 0.2d",
                       member=lid, reason="stiffener spacing not declared"))
    ctc = link.get("connected_to_column")
    out.append(_chk("12.3.1_link_not_at_column", ctc, False, clause="IS 18168:2023 12.3.1", member=lid,
                    cite="links shall not be connected directly to columns", ok=None if ctc is None else not ctc,
                    dc=None))
    br = link.get("braced_both_flanges")
    out.append(_chk("12.3.3.2_link_bracing", br, True, clause="IS 18168:2023 12.3.3.2 / 6.3.3", member=lid,
                    cite="bracing at top and bottom flanges at link ends", ok=None if br is None else bool(br), dc=None))
    if Ry:
        out.append({"id": "12.3.2.2_link_overstrength", "member": lid, "value": 1.1 * Ry * Sh * Vd, "Ry": Ry, "Sh": Sh,
                    "clause": "IS 18168:2023 12.3.2.2 / 12.3.4.5", "ok": True, "dc": None, "limit": None,
                    "brace_design_shear_N": 1.2 * Ry * Vd,
                    "cite": "capacity-protected elements for 1.1 Ry Sh x link design strength; braces 1.2 Ry",
                    "source": SRC,
                    "amplification_capacity_protected": (1.1 * Ry * Sh * Vd / abs(Vu)) if Vu else None,
                    "amplification_braces": (1.2 * Ry * Vd / abs(Vu)) if Vu else None})
    return out


def ebf_capacity_protected_checks(link_result, model_data, link):
    """Apply the 12.3.2.2 / 12.3.4.5 amplification to the EL part of the forces of the braces/columns/beam
    associated with a link ({brace_ids, column_ids, beam_ids} on the link) - axial check P <= Pd."""
    over = next((c for c in link_result if c["id"] == "12.3.2.2_link_overstrength"), None)
    out = []
    if not over or over.get("amplification_capacity_protected") is None:
        return [_na("12.3.2.2_capacity_protected", clause="IS 18168:2023 12.3.2.2", cite="link overstrength",
                    member=link.get("id"), reason="link overstrength / Vu unavailable")]
    for role, ids, amp in (("brace", link.get("brace_ids") or [], over["amplification_braces"]),
                           ("column", link.get("column_ids") or [], over["amplification_capacity_protected"]),
                           ("beam", link.get("beam_ids") or [], over["amplification_capacity_protected"] *
                            (0.9 if link.get("continuous_link_beam") else 1.0))):
        for mid in ids:
            m = _member(model_data, mid)
            if not m:
                continue
            p = _props(m)
            fy, _ = _fy(m, p)
            fs = [f for f in _forces(model_data, mid) if f.get("P_EL_N") is not None]
            if not fs or not fy or not m.get("L_mm"):
                out.append(_na("12.3.2.2_%s_axial" % role, clause="IS 18168:2023 12.3.2.2", member=mid,
                               cite="capacity-protected axial", reason="P_EL_N split / fy / L missing"))
                continue
            Preq = max(f.get("P_N", 0.0) - f["P_EL_N"] + amp * f["P_EL_N"] for f in fs)
            comp = I8.compression_capacity(p, fy, KLz_mm=(m.get("Kz") or 1.0) * m["L_mm"],
                                           KLy_mm=(m.get("Ky") or 1.0) * m["L_mm"], process=m.get("process"))
            out.append(_chk("12.3.2.2_%s_axial" % role, Preq, comp.get("Pd_N"),
                            clause="IS 18168:2023 %s" % ("12.3.4.5" if role == "brace" else "12.3.2.2"), member=mid,
                            cite="axial with EL amplified to link overstrength (%.2f)" % amp)
                       if comp.get("found") else
                       _na("12.3.2.2_%s_axial" % role, clause="IS 18168:2023 12.3.2.2", member=mid, cite="Pd",
                           reason="Pd not computed"))
    return out


def ebf_beam_column_checks(links, model_data, cfg):
    """IS 18168:2023 12.3.4.4: where a brace / gusset connects to both members at a beam-to-column connection, the
    connection assembly resists the beam moment 1.1 Ry fyb Zpb (a fully restrained CJP-welded connection, whose
    welds are parent metal per IS 800 10.5.7.1.2, develops the beam at its expected strength) and the sum of the
    expected column flexural strengths at the joint exceeds 1.1 Ry fyb Zpb.  Joints are read from model_data
    ['joints'] (joints_from_model) for the beams outside the links; the expected column flexural strength is
    Ry Zpc fyc (the clause names no axial reduction; Pu/Py of the columns is recorded for information)."""
    out = []
    beam_ids = set()
    for ln in links:
        beam_ids.update(ln.get("beam_ids") or [])
    if not beam_ids:
        return out
    joints = [j for j in (model_data.get("joints") or []) if any(b["member_id"] in beam_ids for b in j.get("beams") or [])]
    if not joints:
        return [_na("12.3.4.4_beam_column", clause="IS 18168:2023 12.3.4.4", cite="brace-gusset beam-column joints",
                    reason="no beam-column joints found for the beams outside the links (rigid joints expected)")]
    for j in joints:
        bl = [b for b in j.get("beams") or [] if b["member_id"] in beam_ids]
        mb = _member(model_data, bl[0]["member_id"])
        pb = _props(mb); fyb, _ = _fy(mb, pb)
        ryb, _ = _ry(mb, pb)
        Mdem = 1.1 * ryb * fyb * pb["Zx"]
        cn = j.get("connection") or {}
        typ = str(cn.get("type") or "").lower()
        wt = str(cn.get("weld_type") or "").lower()
        cap = cn.get("moment_capacity_Nmm")
        develops = typ in ("welded", "cjp") and wt == "cjp"
        if develops:
            out.append(_chk("12.3.4.4_connection_moment", Mdem, Mdem, clause="IS 18168:2023 12.3.4.4", member=j.get("id"),
                            ok=True, dc=None, connection=typ,
                            cite="fully restrained CJP flange + web welds: parent metal (IS 800 10.5.7.1.2) develops the "
                                 "beam at 1.1 Ry fyb Zpb"))
        elif cap:
            out.append(_chk("12.3.4.4_connection_moment", Mdem, cap, clause="IS 18168:2023 12.3.4.4", member=j.get("id"),
                            cite="connection assembly moment capacity vs 1.1 Ry fyb Zpb", connection=typ))
        else:
            out.append(_na("12.3.4.4_connection_moment", clause="IS 18168:2023 12.3.4.4", member=j.get("id"),
                           cite="1.1 Ry fyb Zpb", reason="no beam_column connection declared for %s" % mb["section"]))
        Ssum = 0.0
        pupy = []
        for c in j.get("columns") or []:
            mc = _member(model_data, c["member_id"])
            if not mc:
                continue
            pc = _props(mc); fyc, _ = _fy(mc, pc); ryc, _ = _ry(mc, pc)
            Pu = max([abs(f.get("P_N", 0.0)) for f in _forces(model_data, mc["id"]) if f.get("family") == "table4"] + [0.0])
            Py = fyc * pc["A"]
            pupy.append(round(Pu / Py, 3))
            Zpc = pc["Zx"] if (mc.get("major_axis_plane") in (None, j.get("frame_dir"))) else pc["Zy"]
            Ssum += ryc * fyc * Zpc
        out.append(_chk("12.3.4.4_column_strength", Mdem, Ssum, clause="IS 18168:2023 12.3.4.4", member=j.get("id"),
                        Pu_over_Py=pupy,
                        cite="sum of the expected column flexural strengths Ry fyc Zpc (about the frame axis) exceeds "
                             "1.1 Ry fyb Zpb of the beam outside the link (no axial reduction in the clause; Pu/Py recorded)") if Ssum > 0 else
                   _na("12.3.4.4_column_strength", clause="IS 18168:2023 12.3.4.4", member=j.get("id"),
                       cite="expected column strengths", reason="no columns at the joint"))
    return out


# ------------------------------------------------------------------------------------------ entry point
def section12_checks(system, model_data, cfg=None):
    """IS 800:2007 Section 12 (and IS 18168:2023 for EBF) system checks. See module docstring for inputs."""
    cfg = cfg or {}
    model_data = model_data or {}
    sysn = normalize_system(system)
    if sysn is None:
        return {"system": system, "supported": False, "ok": None, "reason": NO_BASIS,
                "checks": [_na("system_basis", clause="IS 800:2007 12 / IS 1893 Table 9 / IS 18168:2023 1.3",
                               cite="supported: OCBF, SCBF, EBF (IS 18168), OMF, SMF", reason=NO_BASIS)],
                "note": "Decision D3: BRBF, SPSW, dual, IMF and other systems have no Indian design basis."}
    checks: List[Dict[str, Any]] = []
    advisories: List[Dict[str, Any]] = []
    comps = system_components(system) or [sysn]
    for cs_ in comps:
        zg = zone_gate(cs_, cfg)
        if zg:
            checks.append(zg)
    has_braces = any(c in ("OCBF", "SCBF") for c in comps)
    has_joints = any(c in ("OMF", "SMF") for c in comps)
    sys_br = next((c for c in comps if c in ("OCBF", "SCBF")), None)
    sys_mf = next((c for c in comps if c in ("OMF", "SMF")), None)
    if len(comps) > 1:
        advisories.append({"clause": "IS 800:2007 12 / IS 1893 Table 9", "applies": True,
                           "note": "mixed per-direction system %s: brace rules (12.7 / 12.8) for the braced bays and "
                                   "moment-frame joint rules (12.10 / 12.11) for the portal joints; column / base rules of "
                                   "the primary system %s; R = min over the components" % (" + ".join(comps), sysn)})
    a18 = is18168_status(sysn, cfg)
    if a18["applies"]:
        g = I18.system_gate(sysn, cfg.get("zone") or cfg.get("Z"), cfg.get("height_m"))
        g["source"] = SRC
        checks.append(g)
        p55 = model_data.get("combos_is18168_5_5_present")
        checks.append(_chk("is18168_5_5_combinations", bool(p55), True, clause="IS 18168:2023 5.5", cite=I18.CITE_5_5,
                           ok=bool(p55), dc=None, Omega=I18.omega(sysn)["Omega"]) if p55 is not None else
                      _na("is18168_5_5_combinations", clause="IS 18168:2023 5.5", cite=I18.CITE_5_5,
                          reason="not reported by the load plan"))
    # all Section 12 systems
    if model_data.get("combos_12_2_3_present") is None:
        checks.append(_na("12.2.3_combinations", clause="IS 800:2007 12.2.3",
                          cite="1.2DL+0.5LL+/-2.5EL and 0.9DL+/-2.5EL", reason="not reported by the load plan"))
    else:
        checks.append(_chk("12.2.3_combinations", bool(model_data["combos_12_2_3_present"]), True,
                           clause="IS 800:2007 12.2.3", cite="1.2DL+0.5LL+/-2.5EL; 0.9DL+/-2.5EL",
                           ok=bool(model_data["combos_12_2_3_present"]), dc=None))
    checks += column_checks(sysn, model_data, cfg)
    checks += base_checks(sysn, model_data, cfg)
    conns = {c.get("member_id"): c for c in (model_data.get("connections") or []) if c.get("kind") == "brace_end"}
    if a18["applies"] and sysn in ("SCBF", "SMF") and not cfg.get("is18168_table2"):
        advisories.append({"clause": "IS 18168:2023 5.3 / Table 2", "applies": True, "live": False,
                           "note": "width-to-thickness limits of the SFRS sections (Table 2 x eps/sqrt(Ry): beams 9.0/44.5, columns "
                                   "9.0/72.7(1-1.04Ca), braces 11.3/44.4) are NOT enforced on this job -- set cfg['is18168_table2'] = "
                                   "True to run them as live checks (rolled NPB webs d/tw > ~38 and WPB flanges b/tf > ~7.8 fail; WP6)"})
    if a18["applies"] and sysn in ("SCBF", "SMF") and cfg.get("is18168_table2"):
        # IS 18168:2023 5.3 / Table 2: width-to-thickness limits of the lateral load resisting system's sections
        # (braces (iii), columns (ii) with Ca, SFRS beams (i)); EBF members are checked in their own branch (WP6).
        # Opt-in on SCBF / SMF jobs (cfg['is18168_table2']) so the wave-2 fixtures keep their status; EBF always.
        for m in _members(model_data):
            if m.get("role") not in ("brace", "column", "beam") or (m.get("role") == "beam" and not m.get("sfrs")):
                continue
            try:
                pm = _props(m)
            except KeyError:
                continue
            fym, _ = _fy(m, pm)
            if not fym or pm.get("section_type") != "I":
                continue
            comp = {"brace": "brace", "column": "column", "beam": "beam"}[m["role"]]
            Ca = None
            if comp == "column":
                Py = fym * pm["A"] / I8.GAMMA_M0_DEFAULT
                Ca = max([abs(f.get("P_N", 0.0)) for f in _forces(model_data, m["id"])] + [0.0]) / Py
            checks.append(dict(I18.table2_check(comp, pm, fym, _ry(m, pm)[0], Ca=Ca, member=m["id"]),
                               cite="IS 18168:2023 5.3: sections of the lateral load resisting system within Table 2 (%s)"
                                    % {"brace": "iii", "column": "ii", "beam": "i"}[comp]))
    if has_braces:
        sysn_b = sys_br
        cfgb = str(cfg.get("brace_config") or "").lower()
        cl = "IS 800:2007 12.7.1.2" if sysn_b == "OCBF" else "IS 800:2007 12.8.1.2"
        if not cfgb:
            checks.append(_na("brace_configuration", clause=cl, cite="diagonal and X-bracing only",
                              reason="brace_config not declared"))
        else:
            okc = cfgb in ("x", "diagonal", "single_diagonal", "x-bracing")
            checks.append(_chk("brace_configuration", cfgb, "diagonal or X", clause=cl, dc=None,
                               cite="provisions apply to diagonal and X-bracing only; K-bracing not permitted; "
                                    "V/inverted-V -> specialist literature (no Indian basis, D3)", ok=okc))
        braces = _members(model_data, "brace")
        if not braces:
            checks.append(_na("braces", clause=cl, cite="brace members", reason="no brace members in model_data"))
        for m in braces:
            checks += brace_member_checks(sysn_b, m, model_data, cfg)
            checks += brace_connection_checks(sysn_b, m, conns.get(m["id"]), model_data, cfg)
        checks += tension_share_checks(sysn_b, model_data)
    if "EBF" in comps:                         # H06 (E2): the EBF link chain runs whenever EBF is any component
        links = model_data.get("links") or []
        if not links:
            checks.append(_na("ebf_links", clause="IS 18168:2023 11 / 12.3", cite="links modelled and designed",
                              reason="no links in model_data (an EBF analysed without links is not an EBF)"))
        for ln in links:
            lr = ebf_link_checks(ln, model_data, cfg)
            ln["_overstrength"] = next((c for c in lr if c["id"] == "12.3.2.2_link_overstrength"), None)
            checks += lr
            checks += ebf_capacity_protected_checks(lr, model_data, ln)
        # 12.3.4.1 width-thickness (Table 2) of the beams outside the links and the SFRS columns
        seen = set()
        for ln in links:
            for bid in ln.get("beam_ids") or []:
                if bid in seen:
                    continue
                seen.add(bid)
                mb = _member(model_data, bid)
                if not mb:
                    continue
                pb = _props(mb); fyb, _ = _fy(mb, pb)
                if fyb and pb.get("section_type") == "I":
                    checks.append(dict(I18.table2_check("beam", pb, fyb, _ry(mb, pb)[0], member=bid),
                                       cite="12.3.4.1: beams outside the links satisfy Table 2 (i)"))
        for mc in _members(model_data, "column"):
            pc = _props(mc); fyc, _ = _fy(mc, pc)
            if fyc and pc.get("section_type") == "I":
                Py = fyc * pc["A"] / I8.GAMMA_M0_DEFAULT
                Pu = max([abs(f.get("P_N", 0.0)) for f in _forces(model_data, mc["id"])] + [0.0])
                checks.append(dict(I18.table2_check("column", pc, fyc, _ry(mc, pc)[0], Ca=Pu / Py, member=mc["id"]),
                                   cite="12.3.4.1: columns satisfy Table 2 (ii), Ca = Pu/(Py/gamma_m0)"))
        for m in _members(model_data, "brace"):
            checks += ebf_brace_checks(m, model_data, cfg)
            checks += brace_connection_checks("EBF", m, conns.get(m["id"]), model_data, cfg)
        checks += ebf_beam_column_checks(links, model_data, cfg)
        advisories.append({"note": "IS 800:2007 12.9 refers EBF to specialist literature; IS 18168:2023 cl. 11/12.3 "
                                   "applied (decision D2)."})
    if has_joints:
        joints = model_data.get("joints") or []
        if not joints:
            checks.append(_na("moment_frame_joints", clause="IS 800:2007 12.11 / 12.10",
                              cite="every frame joint from model connectivity", reason="no joints in model_data"))
        for j in joints:
            checks += smf_joint_checks(j, model_data, cfg, system=sys_mf)
    # IS 18168:2023 advisories (governs over IS 800 Section 12 where applicable - lead/EOR decision)
    zone = _zone_roman(cfg.get("zone") or cfg.get("Z"))
    if a18["applies"]:
        advisories.append({"clause": "IS 18168:2023 1.2 / Foreword", "applies": True, "mandatory": a18["mandatory"],
                           "note": I18.PRECEDENCE, "live_checks": ["is18168_1_3_system", "is18168_5_5_combinations",
                           "is18168_7_2_column_KL_r", "brace_KL_r (10.2)", "brace_connection_force (10.4.1)",
                           "is18168_8_2_SCWB", "12.12_base (9.3/9.4)", "EBF links (11, 12.3)"]})
    elif sysn in ("SCBF", "SMF", "EBF") and zone == "II":
        advisories.append({"clause": "IS 18168:2023 1.2", "applies": False,
                           "note": "Zone II: IS 18168 optional (set cfg['apply_is18168'] to apply it); Omega "
                                   "2.5 SCBF/EBF, 3.0 SMRF (5.5) - see india_omega_is18168.resolve_omega"})
    oks = [c.get("ok") for c in checks]
    ok = False if any(o is False for o in oks) else (None if any(o is None for o in oks) else True)
    failing = [c for c in checks if c.get("ok") is False]
    missing = [c for c in checks if c.get("ok") is None]
    dcs = [c["dc"] for c in checks if isinstance(c.get("dc"), (int, float))]
    return {"system": sysn, "supported": True, "ok": ok, "dc_max": max(dcs) if dcs else None,
            "n_checks": len(checks), "n_fail": len(failing), "n_not_evaluated": len(missing),
            "checks": checks, "advisories": advisories,
            "blocks_complete": ok is not True,
            "cite": "IS 800:2007 Section 12" + (" + IS 18168:2023 (EBF links)" if "EBF" in comps else "")}
