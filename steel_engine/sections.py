"""
Section properties for the design post-processor (steltic_india).

Source of truth, in priority order:
  1. IS 808:2021 rolled sections CSV (`is808_shapes.csv` next to this file, or IS808_CSV env).
     Indian designations: MB/WB/JB/LB/HB/SC/NPB/WPB/MC/JC/LC/MPC/ISA/PBP + IS 1161 CHS (see is808_GAPS.md, is1161_tubes.csv).
  2. AISC Shapes Database CSV (`aisc_shapes.csv` or AISC_CSV env) — retained for legacy
     W/HSS labels and USA twin parity; NOT the primary India path.
  3. Small built-in table for a few W-shapes used in library archetypes.

props(name) -> dict with keys: A, Ix, Iy, J, Zx, Zy, Sx, Sy, rx, ry, Aw, ho, Cw, rts,
d, tw, bf, tf. Units follow india_units.active_unit_system(): mm-based when N-mm (default
for India), inch-based when kip-in. IS 808 SI columns preferred; else inch×25.4^n.
brace_r(key) -> radius of gyration in active length unit.
"""
import os, csv, math

# tabulated extras for W-shapes used: Zx (in^3), d, tw, bf, tf (in)
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
# HSS brace radius of gyration (in), square HSS
_HSS_R = {"H4":1.90,"H5":1.96,"H6":2.21,"H6b":2.30,"H7":2.62,"H8":3.02,
          "H8b":2.96,"H10":3.78,"H12":4.58,"H14":5.41}
# Standard AISC square HSS radius of gyration (in), matching engine3d.HSS designation keys.
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

def _looks_india(name: str) -> bool:
    u = str(name).upper().replace(" ", "")
    return any(u.startswith(p) for p in _INDIA_PREFIXES)

def _is808_path():
    p = os.environ.get("IS808_CSV")
    if p and os.path.exists(p): return p
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "is808_shapes.csv")
    return here if os.path.exists(here) else None

def _is1161_path():
    p = os.environ.get("IS1161_CSV")
    if p and os.path.exists(p): return p
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "is1161_tubes.csv")
    return here if os.path.exists(here) else None

def _aisc_path():
    p = os.environ.get("AISC_CSV")
    if p and os.path.exists(p): return p
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aisc_shapes.csv")
    return here if os.path.exists(here) else None

def _csv_path():
    """Back-compat: primary shapes file. India prefers IS 808 when present."""
    return _is808_path() or _aisc_path()

_CSV = None
_CSV_SRC = None

def _load_one(path):
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
            db[lab] = dict(A=g("A"), Ix=g("Ix"), Iy=g("Iy"), J=g("J"), Zx=g("Zx"), Zy=g("Zy"),
                             Sx=g("Sx"), Sy=g("Sy"), rx=g("rx"), ry=g("ry"), d=g("d"), tw=g("tw"),
                             bf=g("bf"), tf=g("tf"), Cw=g("Cw"), rts=g("rts"), ho=g("ho"),
                             A_si_mm2=g("A_si_mm2"), Izz_si_mm4=g("Izz_si_mm4"),
                             Iyy_si_mm4=g("Iyy_si_mm4"), Mass_kg_m=g("Mass_kg_m"),
                             _source=row.get("Source") or path)
            # also index spaced Designation_IS if present
            des = (row.get("Designation_IS") or "").strip().upper().replace(" ", "")
            if des and des not in db:
                db[des] = db[lab]
            for alt in ("NB_Label", "NB_label"):
                nb = (row.get(alt) or "").strip().upper().replace(" ", "")
                if nb and nb not in db:
                    db[nb] = db[lab]
    return db

def _load_csv():
    """Merged DB: IS 808 first, then AISC (IS labels win on collision)."""
    global _CSV, _CSV_SRC
    if _CSV is not None: return _CSV
    is808 = _load_one(_is808_path())
    is1161 = _load_one(_is1161_path())
    aisc = _load_one(_aisc_path())
    merged = dict(aisc)
    merged.update(is1161)  # India CHS
    merged.update(is808)   # India rolled wins on collision
    _CSV = merged
    parts = []
    if is808: parts.append("is808")
    if is1161: parts.append("is1161")
    if aisc: parts.append("aisc")
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

def _fill_derived(d):
    d.setdefault("Aw", (d["d"]*d["tw"]) if d.get("d") and d.get("tw") else None)
    if not d.get("ho") and d.get("d") and d.get("tf"): d["ho"]=d["d"]-d["tf"]
    if not d.get("Cw") and d.get("Iy") and d.get("ho"): d["Cw"]=d["Iy"]*d["ho"]**2/4
    if not d.get("rts") and d.get("Iy") and d.get("Cw") and d.get("Sx"):
        d["rts"]=math.sqrt(math.sqrt(d["Iy"]*d["Cw"])/d["Sx"])
    if not d.get("Sx") and d.get("Ix") and d.get("d"): d["Sx"]=2*d["Ix"]/d["d"]
    if not d.get("Zy") and d.get("Sy"): d["Zy"]=1.55*d["Sy"]
    return d

def _to_si_props(csvd):
    """Build mm-based property dict from CSV row (prefer SI columns)."""
    mm = 25.4
    d = {}
    src = dict(csvd)
    src.pop("_source", None)
    if src.get("A_si_mm2"):
        d["A"] = src["A_si_mm2"]
    elif src.get("A") is not None:
        d["A"] = src["A"] * mm**2
    if src.get("Izz_si_mm4") is not None:
        d["Ix"] = src["Izz_si_mm4"]
    elif src.get("Ix") is not None:
        d["Ix"] = src["Ix"] * mm**4
    if src.get("Iyy_si_mm4") is not None:
        d["Iy"] = src["Iyy_si_mm4"]
    elif src.get("Iy") is not None:
        d["Iy"] = src["Iy"] * mm**4
    for key, power in (("J", 4), ("Zx", 3), ("Zy", 3), ("Sx", 3), ("Sy", 3),
                       ("Cw", 6), ("rx", 1), ("ry", 1), ("d", 1), ("tw", 1),
                       ("bf", 1), ("tf", 1), ("ho", 1), ("rts", 1)):
        if src.get(key) is not None:
            d[key] = src[key] * (mm ** power)
    if src.get("Mass_kg_m") is not None:
        d["Mass_kg_m"] = src["Mass_kg_m"]
    d["_units"] = "mm"
    return _fill_derived(d)

def props(name, SEC=None, unit_system=None):
    """Section properties in active (or requested) unit system."""
    name_u = normalize_label(name)
    us = unit_system or _active_us()
    csvd = _load_csv().get(name_u)
    if csvd and (csvd.get("A") or csvd.get("A_si_mm2")):
        if us == "N-mm":
            return _to_si_props(csvd)
        d = dict(csvd)
        d.pop("_source", None)
        d.pop("A_si_mm2", None); d.pop("Izz_si_mm4", None); d.pop("Iyy_si_mm4", None)
        d.pop("Mass_kg_m", None)
        d["_units"] = "in"
        return _fill_derived(d)
    if _looks_india(name_u):
        raise KeyError(
            "section %r looks like an IS 808 designation but was not found in is808_shapes.csv "
            "(see is808_GAPS.md / is1161_tubes.csv). Do not substitute an AISC W-shape."
            % (name,)
        )
    if SEC is None:
        from engine3d import SEC as _S; SEC=_S
    key = name.upper()
    A,Ix,Iy,J = SEC[key]
    Zx,dd,tw,bf,tf = _GEOM[key]
    Sx = 2*Ix/dd; Sy = 2*Iy/bf
    rx = math.sqrt(Ix/A); ry = math.sqrt(Iy/A)
    Aw = dd*tw; ho = dd-tf; Cw = Iy*ho**2/4.0
    rts = math.sqrt(math.sqrt(Iy*Cw)/Sx)
    Zy = 1.55*Sy
    d = dict(A=A,Ix=Ix,Iy=Iy,J=J,Zx=Zx,Zy=Zy,Sx=Sx,Sy=Sy,rx=rx,ry=ry,
             Aw=Aw,ho=ho,Cw=Cw,rts=rts,d=dd,tw=tw,bf=bf,tf=tf, _units="in")
    if us == "N-mm":
        return _to_si_props(d)
    return d

def brace_r(key):
    r = _HSS_R.get(key)
    us = _active_us()
    if r is not None:
        return r * 25.4 if us == "N-mm" else r
    d = props(key) if _load_csv().get(normalize_label(key)) else None
    if d and d.get("rx"):
        return d["rx"]
    return 2.5 * 25.4 if us == "N-mm" else 2.5

def hss_b_over_t(name, spec="A1085"):
    """Flat-width / design-wall ratio b/t for a SQUARE/RECT HSS (legacy AISC path).
    India hollow sections: prefer IS 1161 labels (CHS… / NB…) from is1161_tubes.csv; legacy AISC HSS keys remain for twin parity."""
    import re as _re
    m = _re.match(r"HSS(\\d+(?:\\.\\d+)?)X(\\d+(?:\\.\\d+)?)X(\\d+)(?:/(\\d+))?", str(name).upper())
    if not m:
        return None, None
    B = float(m.group(1))
    tnom = (float(m.group(3))/float(m.group(4))) if m.group(4) else float(m.group(3))
    tdes = tnom if str(spec).upper() == "A1085" else 0.93*tnom
    b = B - 3.0*tdes
    return b/tdes, tdes

def list_is808(prefix=None):
    """Return sorted IS 808 labels (optionally filtered by Type/prefix)."""
    db = _load_one(_is808_path())
    labs = sorted(set(db.keys()))
    if prefix:
        p = prefix.upper().replace(" ", "")
        labs = [L for L in labs if L.startswith(p)]
    return labs


def list_chs(prefix=None):
    """Return sorted IS 1161 CHS labels (optionally filtered by prefix)."""
    db = _load_one(_is1161_path())
    labs = sorted(set(db.keys()))
    if prefix:
        p = prefix.upper().replace(" ", "")
        labs = [L for L in labs if L.startswith(p)]
    return labs
