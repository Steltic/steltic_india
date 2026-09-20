"""
Section properties for the design post-processor (steltic_india).

Source of truth (WP2.2, review HR800-04/13/21):
  1. IS 808:2021 rolled sections, `is808_shapes.csv` (validated by tools/build_is808_shapes.py; rows that
     fail the validator are in `is808_quarantine.csv` and are NOT selectable -> KeyError, found:false).
  2. IS 1161:2014 circular hollow sections, `is1161_tubes.csv`. Tube material is graded YSt 210/240/310/355
     and made HFS/CDS/ERW/HFIW; fy/fu come from IS 1161 Table 2 for the declared grade (never a default 250).
  3. AISC Shapes Database (`aisc_shapes.csv`) and the small built-in W table: legacy kip-in / USA twin ONLY.
     In an India (N-mm) job an AISC label raises unless `allow_aisc_shapes(eor_cite)` was called.

props(name) -> dict with keys A, Ix, Iy, J, Zx (plastic, z-z), Zy (plastic, y-y), Sx (elastic, z-z), Sy,
rx (= rz), ry, r_min, d, tw, bf, tf, Cw (= Iw; 0 for angles/CHS; None when the PDF has no value), Aw, ho,
plus for angles Iuu, Ivv, ru, rv. Units follow india_units.active_unit_system(): mm when N-mm (India).
brace_r(key) -> minimum radius of gyration min(rx, ry, rv) in the active length unit; raises when unknown.
"""
import os, csv, math

# tabulated extras for W-shapes used by the legacy USA twin: Zx (in^3), d, tw, bf, tf (in)
_GEOM = {
 "W14X90":(157,14.0,0.440,14.5,0.710), "W14X120":(212,14.5,0.590,14.7,0.940),
 "W14X132":(234,14.7,0.645,14.7,1.03), "W14X159":(287,15.0,0.745,15.6,1.19),
 "W14X193":(355,15.5,0.890,15.7,1.44), "W14X233":(436,16.0,1.07,15.9,1.72),
 "W14X311":(603,17.1,1.41,16.2,2.26),  "W14X370":(736,17.9,1.66,16.5,2.66),
 "W14X426":(869,18.7,1.88,16.7,3.04),  "W14X500":(1050,19.6,2.19,17.0,3.50),
 "W14X605":(1320,20.9,2.60,17.4,4.16), "W14X730":(1660,22.4,3.07,17.9,4.91),
 "W18X50":(101,18.0,0.355,7.50,0.570), "W21X62":(144,21.0,0.400,8.24,0.615),
 "W24X55":(134,23.6,0.395,7.01,0.505),
 "W24X76":(200,23.9,0.440,8.99,0.680), "W24X84":(224,24.1,0.470,9.02,0.770),
 "W27X94":(278,26.9,0.490,9.99,0.745), "W30X108":(346,29.8,0.545,10.5,0.760),
 "W30X116":(378,30.0,0.565,10.5,0.850),"W33X130":(467,33.1,0.580,11.5,0.855),
 "W36X150":(581,35.9,0.625,12.0,0.940),"W36X194":(767,36.5,0.765,12.1,1.26),
 "W40X199":(869,38.7,0.650,15.8,1.07),
}
# Legacy USA-twin square HSS radius of gyration (in). Never used for India (N-mm) jobs.
_HSS_R = {"H4":1.90,"H5":1.96,"H6":2.21,"H6b":2.30,"H7":2.62,"H8":3.02,
          "H8b":2.96,"H10":3.78,"H12":4.58,"H14":5.41}
_HSS_R.update({
 "HSS4X4X1/4":1.51,"HSS4X4X3/8":1.46,"HSS5X5X1/4":1.90,"HSS5X5X3/8":1.85,"HSS5X5X1/2":1.80,
 "HSS6X6X1/4":2.34,"HSS6X6X5/16":2.31,"HSS6X6X3/8":2.28,"HSS6X6X1/2":2.21,
 "HSS7X7X3/8":2.70,"HSS7X7X1/2":2.62,"HSS8X8X1/4":3.15,"HSS8X8X3/8":3.10,"HSS8X8X1/2":3.02,"HSS8X8X5/8":2.94,
 "HSS10X10X3/8":3.90,"HSS10X10X1/2":3.84,"HSS10X10X5/8":3.78,
 "HSS12X12X3/8":4.72,"HSS12X12X1/2":4.66,"HSS12X12X5/8":4.60,
 "HSS14X14X1/2":5.49,"HSS14X14X5/8":5.43,"HSS16X16X1/2":6.31,"HSS16X16X5/8":6.25})

_INDIA_PREFIXES = ("MB", "WB", "JB", "LB", "HB", "SC", "NPB", "WPB", "PBP",
                   "MC", "LC", "JC", "MPC", "ISA", "CHS", "NB",
                   "ISMB", "ISWB", "ISLB", "ISJB", "ISMC", "ISLC", "ISHB", "ISSC")

# IS 1161:2014 Table 2 (pdf p.6) "Tensile Properties of Steel Tubes for Structural Purposes": Rm min, ReH min, A min
IS1161_TABLE2 = {
    "YST210": {"fu_MPa": 330.0, "fy_MPa": 210.0, "elongation_pct": 20.0},
    "YST240": {"fu_MPa": 410.0, "fy_MPa": 240.0, "elongation_pct": 17.0},
    "YST310": {"fu_MPa": 450.0, "fy_MPa": 310.0, "elongation_pct": 14.0},
    "YST355": {"fu_MPa": 490.0, "fy_MPa": 355.0, "elongation_pct": 10.0},
}
IS1161_CITE = "IS 1161:2014 Table 2 (Tensile Properties of Steel Tubes for Structural Purposes)"
# IS 1161:2014 cl. 5: HFS hot finished seamless; CDS cold finished seamless; ERW / HFIW welded.
# IS 800:2007 Table 10 hollow sections: "Hot rolled: a / Cold formed: b".
IS1161_PROCESS_BUCKLING_CLASS = {"HFS": "a", "CDS": "b", "ERW": "b", "HFIW": "b", "HFW": "b"}

_AISC_ALLOWED = {"allowed": False, "cite": None}


def allow_aisc_shapes(eor_cite=None, allowed=True):
    """India jobs: AISC W/HSS labels raise unless the EOR explicitly allows them with a cite (HR800-21)."""
    if allowed and not (eor_cite and str(eor_cite).strip()):
        raise ValueError("allow_aisc_shapes requires an EOR cite (name, basis, date)")
    _AISC_ALLOWED.update(allowed=bool(allowed), cite=eor_cite if allowed else None)


def _looks_india(name: str) -> bool:
    u = str(name).upper().replace(" ", "")
    return any(u.startswith(p) for p in _INDIA_PREFIXES)


def _here(fname):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)


def _is808_path():
    p = os.environ.get("IS808_CSV")
    if p and os.path.exists(p): return p
    here = _here("is808_shapes.csv")
    return here if os.path.exists(here) else None


def _is1161_path():
    p = os.environ.get("IS1161_CSV")
    if p and os.path.exists(p): return p
    here = _here("is1161_tubes.csv")
    return here if os.path.exists(here) else None


def _aisc_path():
    p = os.environ.get("AISC_CSV")
    if p and os.path.exists(p): return p
    here = _here("aisc_shapes.csv")
    return here if os.path.exists(here) else None


def _csv_path():
    """Back-compat: primary shapes file. India prefers IS 808 when present."""
    return _is808_path() or _aisc_path()


_CSV = None
_CSV_SRC = None
_QUAR = None

_SI_KEYS = ("D_mm", "B_mm", "tw_mm", "tf_mm", "rz_mm", "ry_mm", "Zez_mm3", "Zey_mm3", "Zpz_mm3", "Zpy_mm3",
            "It_mm4", "Iw_mm6", "Iuu_mm4", "Ivv_mm4", "ru_mm", "rv_mm", "r_min_mm", "Cy_mm", "Cz_mm", "R1_mm",
            "flange_slope_deg", "t_mm", "r_mm", "Ze_mm3", "Zp_mm3")


def _load_one(path, origin):
    db = {}
    if not path: return db
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            lab = (row.get("AISC_Manual_Label") or row.get("Label") or row.get("Shape") or "").strip().upper()
            lab = lab.replace(" ", "")
            if not lab: continue
            def g(*keys):
                for k in keys:
                    v = row.get(k)
                    if v not in (None, "", "-", "–"):
                        try: return float(str(v).replace(",", ""))
                        except ValueError: pass
                return None
            rec = dict(A=g("A"), Ix=g("Ix"), Iy=g("Iy"), J=g("J"), Zx=g("Zx"), Zy=g("Zy"),
                       Sx=g("Sx"), Sy=g("Sy"), rx=g("rx"), ry=g("ry"), d=g("d"), tw=g("tw"),
                       bf=g("bf"), tf=g("tf"), Cw=g("Cw"), rts=g("rts"), ho=g("ho"),
                       A_si_mm2=g("A_si_mm2"), Izz_si_mm4=g("Izz_si_mm4"),
                       Iyy_si_mm4=g("Iyy_si_mm4"), Mass_kg_m=g("Mass_kg_m"),
                       _type=(row.get("Type") or "").strip().upper(), _origin=origin,
                       _source=row.get("Source") or path)
            for k in _SI_KEYS:
                rec[k] = g(k)
            db[lab] = rec
            des = (row.get("Designation_IS") or "").strip().upper().replace(" ", "")
            if des and des not in db:
                db[des] = rec
            for alt in ("NB_Label", "NB_label"):
                nb = (row.get(alt) or "").strip().upper().replace(" ", "")
                if nb and nb not in db:
                    db[nb] = rec
    return db


def _load_quarantine():
    global _QUAR
    if _QUAR is None:
        _QUAR = {}
        p = _here("is808_quarantine.csv")
        if os.path.exists(p):
            with open(p, newline="") as f:
                for row in csv.DictReader(f):
                    _QUAR[row["Label"].strip().upper()] = row.get("reasons", "")
    return _QUAR


def _load_csv():
    """Merged DB: IS 808 first, then IS 1161, then AISC (IS labels win on collision)."""
    global _CSV, _CSV_SRC
    if _CSV is not None: return _CSV
    is808 = _load_one(_is808_path(), "IS808")
    is1161 = _load_one(_is1161_path(), "IS1161")
    aisc = _load_one(_aisc_path(), "AISC")
    merged = dict(aisc)
    merged.update(is1161)
    merged.update(is808)
    _CSV = merged
    parts = [n for n, d in (("is808", is808), ("is1161", is1161), ("aisc", aisc)) if d]
    _CSV_SRC = "+".join(parts) if parts else "none"
    return _CSV


def normalize_label(name: str) -> str:
    return str(name).upper().replace(" ", "").strip()


def _active_us():
    try:
        from india_units import active_unit_system
        return active_unit_system()
    except Exception:
        return "N-mm"


def _fill_derived_legacy(d):
    """Legacy AISC (kip-in twin) derivations. NOT applied to IS 808 / IS 1161 rows."""
    d.setdefault("Aw", (d["d"]*d["tw"]) if d.get("d") and d.get("tw") else None)
    if not d.get("ho") and d.get("d") and d.get("tf"): d["ho"]=d["d"]-d["tf"]
    if not d.get("Cw") and d.get("Iy") and d.get("ho"): d["Cw"]=d["Iy"]*d["ho"]**2/4
    if not d.get("rts") and d.get("Iy") and d.get("Cw") and d.get("Sx"):
        d["rts"]=math.sqrt(math.sqrt(d["Iy"]*d["Cw"])/d["Sx"])
    if not d.get("Sx") and d.get("Ix") and d.get("d"): d["Sx"]=2*d["Ix"]/d["d"]
    if not d.get("Zy") and d.get("Sy"): d["Zy"]=1.55*d["Sy"]
    return d


def section_type(rec_or_name):
    """'I' (IS 808 rolled I/H/pile), 'channel', 'angle', 'CHS', 'AISC'."""
    rec = rec_or_name if isinstance(rec_or_name, dict) else _load_csv().get(normalize_label(rec_or_name), {})
    t = (rec.get("_type") or rec.get("Type") or "").upper()
    if t in ("MB", "WB", "JB", "LB", "HB", "SC", "NPB", "WPB", "PBP"):
        return "I"
    if t in ("MC", "JC", "LC", "MPC"):
        return "channel"
    if t == "ISA":
        return "angle"
    if t == "CHS":
        return "CHS"
    return "AISC"


def _is_si_row(src):
    return src.get("_origin") in ("IS808", "IS1161")


def _india_si_props(src):
    """mm-based properties from the authoritative SI columns of an IS 808 / IS 1161 row."""
    st = section_type(src)
    mm = 25.4
    d = {"_units": "mm", "section_type": st, "Type": src.get("_type"), "source": src.get("_source")}
    d["A"] = src["A_si_mm2"]
    d["Ix"] = src["Izz_si_mm4"]
    d["Iy"] = src["Iyy_si_mm4"]
    if st == "CHS":
        D, t = src.get("D_mm") or src["d"] * mm, src.get("t_mm") or src["tw"] * mm
        r = src.get("r_mm") or math.sqrt(d["Ix"] / d["A"])
        d.update(d=D, bf=D, tw=t, tf=t, rx=r, ry=r, r_min=r,
                 Sx=src.get("Ze_mm3") or 2 * d["Ix"] / D, Zx=src.get("Zp_mm3") or (D**3 - (D - 2*t)**3) / 6.0,
                 J=src.get("It_mm4") or 2 * d["Ix"], Cw=0.0)
        d["Sy"], d["Zy"] = d["Sx"], d["Zx"]
        d["Aw"] = 2 * d["A"] / math.pi          # IS 800 8.4.1.1: tubes Av = 2A/pi
        d["ho"] = None
    else:
        d.update(d=src["D_mm"], bf=src["B_mm"], tw=src["tw_mm"], tf=src["tf_mm"],
                 rx=src["rz_mm"], ry=src["ry_mm"], Sx=src["Zez_mm3"], Sy=src["Zey_mm3"],
                 Zx=src["Zpz_mm3"], Zy=src["Zpy_mm3"], J=src.get("It_mm4"),
                 Cw=(0.0 if st == "angle" else src.get("Iw_mm6")),
                 R1=src.get("R1_mm"), flange_slope_deg=src.get("flange_slope_deg"))
        d["ho"] = d["d"] - d["tf"]
        if st == "angle":
            d.update(Iuu=src.get("Iuu_mm4"), Ivv=src.get("Ivv_mm4"), ru=src.get("ru_mm"), rv=src.get("rv_mm"),
                     Cy=src.get("Cy_mm"), Cz=src.get("Cz_mm"))
            d["r_min"] = min(v for v in (d["rx"], d["ry"], d.get("rv")) if v)
            d["Aw"] = d["d"] * d["tw"]
        else:
            if st == "channel":
                d["Cy"] = src.get("Cy_mm")
            d["r_min"] = min(d["rx"], d["ry"])
            d["Aw"] = d["d"] * d["tw"]          # IS 800 8.4.1.1 hot-rolled I/channel, major axis: h*tw
    if src.get("Mass_kg_m") is not None:
        d["Mass_kg_m"] = src["Mass_kg_m"]
    return d


def _to_si_props_legacy(csvd):
    """AISC (inch) row -> mm (legacy USA-twin rows only)."""
    mm = 25.4
    d = {}
    src = dict(csvd)
    if src.get("A_si_mm2"):
        d["A"] = src["A_si_mm2"]
    elif src.get("A") is not None:
        d["A"] = src["A"] * mm**2
    d["Ix"] = src["Izz_si_mm4"] if src.get("Izz_si_mm4") is not None else (src["Ix"] * mm**4 if src.get("Ix") else None)
    d["Iy"] = src["Iyy_si_mm4"] if src.get("Iyy_si_mm4") is not None else (src["Iy"] * mm**4 if src.get("Iy") else None)
    for key, power in (("J", 4), ("Zx", 3), ("Zy", 3), ("Sx", 3), ("Sy", 3),
                       ("Cw", 6), ("rx", 1), ("ry", 1), ("d", 1), ("tw", 1),
                       ("bf", 1), ("tf", 1), ("ho", 1), ("rts", 1)):
        if src.get(key) is not None:
            d[key] = src[key] * (mm ** power)
    d["_units"] = "mm"
    d["section_type"] = "AISC"
    d = _fill_derived_legacy(d)
    if d.get("rx") and d.get("ry"):
        d["r_min"] = min(d["rx"], d["ry"])
    return d


def _check_aisc_allowed(name_u):
    if _active_us() == "N-mm" and not _AISC_ALLOWED["allowed"]:
        raise KeyError(
            "section %r is an AISC label; India (N-mm) jobs use IS 808 / IS 1161 sections only. "
            "An AISC shape needs sections.allow_aisc_shapes(eor_cite) (HR800-21)." % (name_u,))


# ---------------------------------------------------------------------------------------------------------------
# WP6-fix: built-up welded BOX sections from IS 2062 plates (L6: 'built-up box columns ... built-up from plates').
# Registered per job by the agent (cfg['custom_sections'] -> register_box); properties are computed from the four
# plates, never read from a catalogue.  section_type 'box' is handled by india_is800 (Table 2 internal elements,
# Table 10 welded box class, 8.2.2(b) no LTB, 8.4.1.1 shear area of the two webs).
# ---------------------------------------------------------------------------------------------------------------
CUSTOM = {}


def register_box(name, B_mm, D_mm, tf_mm, tw_mm, *, source="built-up welded box from IS 2062 plates (declared in cfg)"):
    """Welded box: two flange plates B x tf (outside) and two web plates (D - 2 tf) x tw at the outer faces.
    Returns the mm property dict (also stored in CUSTOM under the normalised label)."""
    B, D, tf, tw = float(B_mm), float(D_mm), float(tf_mm), float(tw_mm)
    d = D - 2.0 * tf
    A = 2.0 * B * tf + 2.0 * d * tw
    Ix = 2.0 * (B * tf ** 3 / 12.0 + B * tf * ((D - tf) / 2.0) ** 2) + 2.0 * tw * d ** 3 / 12.0
    Iy = 2.0 * (tf * B ** 3 / 12.0) + 2.0 * (d * tw ** 3 / 12.0 + d * tw * ((B - tw) / 2.0) ** 2)
    Sx, Sy = 2.0 * Ix / D, 2.0 * Iy / B
    Zx = B * tf * (D - tf) + 2.0 * tw * (d / 2.0) ** 2            # plastic: flanges + webs
    Zy = d * tw * (B - tw) + 2.0 * tf * (B / 2.0) ** 2
    Am = (B - tw) * (D - tf)                                       # enclosed area to the mid-lines
    J = 4.0 * Am ** 2 / (2.0 * (B - tw) / tf + 2.0 * (D - tf) / tw)   # thin-walled closed section
    props_ = {"_units": "mm", "section_type": "box", "Type": "BOX", "source": source, "A": A, "Ix": Ix, "Iy": Iy,
              "Zx": Zx, "Zy": Zy, "Sx": Sx, "Sy": Sy, "rx": math.sqrt(Ix / A), "ry": math.sqrt(Iy / A),
              "r_min": math.sqrt(min(Ix, Iy) / A), "d": D, "bf": B, "tf": tf, "tw": tw, "J": J, "Cw": 0.0,
              "ho": D - tf, "Aw": 2.0 * d * tw, "R1": 0.0, "Mass_kg_m": A * 7850.0 / 1e6, "welded": True,
              "plates": {"flange_mm": [B, tf], "web_mm": [d, tw]}}
    CUSTOM[normalize_label(name)] = props_
    return props_


def register_custom_sections(cfg):
    """cfg['custom_sections'] = {name: {'type': 'box', 'B_mm', 'D_mm', 'tf_mm', 'tw_mm', 'source'}} -> CUSTOM."""
    for nm, spec in (cfg.get("custom_sections") or {}).items():
        if str(spec.get("type", "box")).lower() != "box":
            raise KeyError("custom section %r: only built-up welded 'box' sections are supported" % nm)
        register_box(nm, spec["B_mm"], spec["D_mm"], spec["tf_mm"], spec["tw_mm"],
                     source=spec.get("source") or "built-up welded box from IS 2062 plates (declared in cfg)")


def props(name, SEC=None, unit_system=None, *, grade=None, process=None):
    """Section properties in the active (or requested) unit system.

    For IS 1161 tubes pass grade ('YSt 240' ...) and process ('HFS'/'ERW'/...) to get fy_MPa/fu_MPa and the
    IS 800 Table 10 buckling class; without them fy/fu are None (no default 250).
    """
    name_u = normalize_label(name)
    us = unit_system or _active_us()
    if name_u in CUSTOM:
        if us != "N-mm":
            raise KeyError("custom built-up section %r is defined in mm only" % (name,))
        return dict(CUSTOM[name_u])
    q = _load_quarantine()
    if name_u in q:
        raise KeyError("section %r is quarantined (found:false): IS 808:2021 row fails the WP2.2 validator (%s); "
                       "see is808_GAPS.md" % (name, q[name_u]))
    csvd = _load_csv().get(name_u)
    if csvd and (csvd.get("A") or csvd.get("A_si_mm2")):
        if csvd.get("_origin") == "AISC":
            _check_aisc_allowed(name_u) if us == "N-mm" else None
        if us == "N-mm":
            d = _india_si_props(csvd) if _is_si_row(csvd) else _to_si_props_legacy(csvd)
            if d.get("section_type") == "CHS":
                d.update(chs_material(grade, process) if (grade or process) else
                         {"fy_MPa": None, "fu_MPa": None, "grade": None, "process": None,
                          "material_found": False,
                          "material_note": "IS 1161 grade/process not declared (cfg) - no default fy"})
            return d
        d = dict(csvd)
        for k in ("_source", "_origin", "_type", "A_si_mm2", "Izz_si_mm4", "Iyy_si_mm4", "Mass_kg_m") + _SI_KEYS:
            d.pop(k, None)
        d["_units"] = "in"
        if not _is_si_row(csvd):
            return _fill_derived_legacy(d)
        st = section_type(csvd)
        if st in ("angle", "CHS"):
            d["Cw"] = 0.0
        return d
    if _looks_india(name_u):
        raise KeyError(
            "section %r looks like an IS 808/IS 1161 designation but was not found in is808_shapes.csv / "
            "is1161_tubes.csv (see is808_GAPS.md). Do not substitute an AISC W-shape." % (name,))
    if us == "N-mm":
        _check_aisc_allowed(name_u)
    if SEC is None:
        from engine3d import SEC as _S; SEC = _S
    key = name.upper()
    A, Ix, Iy, J = SEC[key]
    Zx, dd, tw, bf, tf = _GEOM[key]
    Sx = 2*Ix/dd; Sy = 2*Iy/bf
    rx = math.sqrt(Ix/A); ry = math.sqrt(Iy/A)
    Aw = dd*tw; ho = dd-tf; Cw = Iy*ho**2/4.0
    rts = math.sqrt(math.sqrt(Iy*Cw)/Sx)
    Zy = 1.55*Sy
    d = dict(A=A, Ix=Ix, Iy=Iy, J=J, Zx=Zx, Zy=Zy, Sx=Sx, Sy=Sy, rx=rx, ry=ry,
             Aw=Aw, ho=ho, Cw=Cw, rts=rts, d=dd, tw=tw, bf=bf, tf=tf, _units="in")
    if us == "N-mm":
        return _to_si_props_legacy(d)
    return d


def chs_material(grade, process):
    """IS 1161 tube material: fy/fu from Table 2 for the declared grade; Table 10 class from the process."""
    g = normalize_label(grade or "").replace(".", "")
    p = normalize_label(process or "")
    rec = IS1161_TABLE2.get(g)
    out = {"grade": grade, "process": process, "fy_MPa": None, "fu_MPa": None, "elongation_pct": None,
           "buckling_class": IS1161_PROCESS_BUCKLING_CLASS.get(p), "material_found": False,
           "material_cite": IS1161_CITE}
    if rec:
        out.update(fy_MPa=rec["fy_MPa"], fu_MPa=rec["fu_MPa"], elongation_pct=rec["elongation_pct"],
                   material_found=True)
    else:
        out["material_note"] = "grade %r is not an IS 1161 grade (YSt 210/240/310/355)" % (grade,)
    if p and p not in IS1161_PROCESS_BUCKLING_CLASS:
        out["material_note"] = "process %r is not an IS 1161 process (HFS/CDS/ERW/HFIW)" % (process,)
        out["material_found"] = False
    if not p:
        out["material_found"] = False
        out["material_note"] = "IS 1161 manufacturing process not declared (HFS/CDS/ERW/HFIW)"
    return out


def r_min(key):
    return brace_r(key)


def brace_r(key):
    """Minimum radius of gyration min(rx, ry, rv) (HR800-04/21). Raises for unknown sections (no default)."""
    us = _active_us()
    if us != "N-mm" and key in _HSS_R:
        return _HSS_R[key]
    d = props(key)
    vals = [v for v in (d.get("rx"), d.get("ry"), d.get("rv")) if v]
    if not vals:
        raise KeyError("no radius of gyration for section %r (found:false)" % (key,))
    return min(vals)


def brace_area(key):
    """Gross area of a brace section in the active unit (replaces the AISC-only engine3d.HSS[...] lookup)."""
    return props(key)["A"]


def hss_b_over_t(name, spec="A1085"):
    """Flat-width / design-wall ratio b/t for a SQUARE/RECT AISC HSS (legacy USA twin path only)."""
    import re as _re
    m = _re.match(r"HSS(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)X(\d+)(?:/(\d+))?", str(name).upper())
    if not m:
        return None, None
    B = float(m.group(1))
    tnom = (float(m.group(3))/float(m.group(4))) if m.group(4) else float(m.group(3))
    tdes = tnom if str(spec).upper() == "A1085" else 0.93*tnom
    b = B - 3.0*tdes
    return b/tdes, tdes


def list_is808(prefix=None):
    """Return sorted IS 808 labels (optionally filtered by Type/prefix)."""
    db = _load_one(_is808_path(), "IS808")
    labs = sorted(set(db.keys()))
    if prefix:
        p = prefix.upper().replace(" ", "")
        labs = [L for L in labs if L.startswith(p)]
    return labs


def list_chs(prefix=None):
    """Return sorted IS 1161 CHS labels (optionally filtered by prefix)."""
    db = _load_one(_is1161_path(), "IS1161")
    labs = sorted(set(db.keys()))
    if prefix:
        p = prefix.upper().replace(" ", "")
        labs = [L for L in labs if L.startswith(p)]
    return labs
