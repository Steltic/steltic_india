#!/usr/bin/env python3
"""Build steel_engine/is808_shapes.csv from the IS 808:2021 PDF text layer (pdftotext -layout).

Tables 1-5 : I / column sections (MB, WB, JB, LB, HB, SC, NPB, WPB)
Tables 6-8 : channels (MC, JC, LC, MPC) - extra Cy column before Izz
Tables 9-12: equal/unequal angles (ISA a x b x t) - Iuu, Ivv, ru, rv written (WP2.2)
Table 13   : bearing piles (PBP)

WP2.2 (review HR800-04): every row is validated after parsing.

  * r   : |r - sqrt(I/A)| <= 3 %   (rz, ry; angles also ru, rv)
  * M   : |M - 0.00785 A| <= 3 %   (kg/m vs mm2)
  * Ze  : |Zez - 2 Izz / D| <= 4 % (I sections and channels; z-z axis)
  * I/angle invariants and plate-area plausibility (see validate_row)

Corrections are applied ONLY when the PDF's own independent columns agree with each other
(e.g. A, Izz, Zez, M mutually consistent => a printed r that disagrees is a misprint and is
recomputed as sqrt(I/A)). Every correction is written to the `corrections` column and to
is808_GAPS.md with the PDF page. A row that still fails is QUARANTINED: it is not written to
is808_shapes.csv (so sections.props() raises, found:false) but to is808_quarantine.csv.

Units: the SI columns (*_mm, *_mm2, *_mm3, *_mm4, *_mm6) are the source of truth (IS 808 tabulated
values x their printed multipliers). The legacy inch columns (A, Ix, ... in inch units) are derived
from the corrected SI values for the kip-in USA twin only.

Usage:  pdftotext -layout IS_808_2021.pdf is808.txt ; python3 build_is808_shapes.py is808.txt
"""
from __future__ import annotations

import csv
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "is808_shapes.csv"
QUAR = HERE.parent / "is808_quarantine.csv"
GAPS = HERE.parent / "is808_GAPS.md"
DEFAULT_TXT = Path("/tmp/is808/all_tables.txt")

STEEL_DENSITY_KG_PER_M_PER_MM2 = 0.00785   # 7850 kg/m3
TOL_R, TOL_MASS, TOL_ZE = 0.03, 0.03, 0.04

MM = 1.0 / 25.4


def parse_nums(s: str) -> list[float]:
    """Parse numbers; join single-space thousands groups (1 260) only."""
    out = []
    for m in re.finditer(r"\d{1,3}(?: \d{3})+(?:\.\d+)?|\d+\.\d+|\d+", s):
        tok = m.group(0).replace(" ", "")
        try:
            out.append(float(tok))
        except ValueError:
            pass
    return out


# --------------------------------------------------------------------------------------------
# Line-level repairs of misprints that shift columns (verified against the PDF page images).
# --------------------------------------------------------------------------------------------
_DOUBLE_DOT = re.compile(r"(?<![\d.])(\d)\.(\d)\.(\d)(?![\d.])")

LINE_FIXES = [
    # (regex on the raw line, old token, new token, note)
    (re.compile(r"^\s*LB\s+600\b"), "2 04 0000", "2 040 000",
     "LB 600 Iw printed '2 04 0000' (IS 808:2021 Table 2, pdf p.10) -> 2 040 000 x10^6 mm6"),
    (re.compile(r"^\s*[∠∠]\s*35\s*×\s*35\s*×\s*3\b"), " .0.7 ", " 10.7 ",
     "ISA 35x35x3 rz printed '.0.7' (Table 9, pdf p.29); ry printed 10.7 and sqrt(Izz/A)=10.75 -> 10.7"),
]

# Cell-level overrides where the PDF cell wraps or is blank. Value = printed value read from the page image.
OVERRIDES = {
    "LC400": {"Izz": (13900.0, "Izz cell wraps '13 / 900' in IS 808:2021 Table 8 (pdf p.26, printed p.24)")},
}
# Rows whose Iw cell is blank in the PDF (Iw stays empty -> found:false for LTB).
ALLOW_MISSING_IW = {"WPB200X200X37.34": "Iw cell blank in IS 808:2021 Table 4 (pdf p.16, printed p.14)"}


def fix_line(line: str, notes: list) -> str:
    for rx, old, new, note in LINE_FIXES:
        if rx.search(line) and old in line:
            line = line.replace(old, new)
            notes.append(note)
    def _dd(m):
        notes.append("printed '%s.%s.%s' (double decimal point) read as %s%s.%s" % (m.group(1), m.group(2), m.group(3),
                                                                                   m.group(1), m.group(2), m.group(3)))
        return "%s%s.%s" % (m.group(1), m.group(2), m.group(3))
    return _DOUBLE_DOT.sub(_dd, line)


TABLE_RE = re.compile(r"Table\s*(\d+)\b", re.I)
SIMPLE_RE = re.compile(r"^\s*(MB|WB|JB|LB|HB|SC)\s+(\d+)\*?\s+(.*)$", re.I)
PF_RE = re.compile(r"^\s*(NPB|WPB)\s+(\d+)\s*X\s*(\d+)\s*X\s+(.*)$", re.I)
CHAN_RE = re.compile(r"^\s*(MC|JC|LC|MPC)(\s*\(P\))?\s+(\d+)\*?\s+(.*)$", re.I)
ANGLE_FULL_RE = re.compile(r"^\s*[∠∠]\s*(\d+)\s*[×xX]\s*(\d+)\s*[×xX]\s*(\d+)\s+(.*)$")
ANGLE_CONT_RE = re.compile(r"^\s*[×xX]\s*(\d+)\s+(.*)$")
PBP_RE = re.compile(r"^\s*PBP\s+(\d+)\s*[×xX]\s+(.*)$", re.I)


def _mass_tag(mass: float) -> str:
    return f"{mass:.2f}".rstrip("0").rstrip(".")


def make_label(family, parts, mass) -> str:
    fam = family.upper()
    if fam in ("NPB", "WPB"):
        d, b = parts
        return f"{fam}{int(d)}X{int(b)}X{_mass_tag(mass)}".upper()
    if fam == "PBP":
        return f"PBP{int(parts[0])}X{_mass_tag(mass)}".upper()
    if fam == "ISA":
        a, b, t = parts
        return f"ISA{int(a)}X{int(b)}X{_mass_tag(t)}".upper()
    return f"{fam}{int(parts[0])}".upper()


def row_I_like(family, label_parts, nums, table_no, raw_desig, page, *, has_cy=False, notes=None):
    """I-beam / channel / pile row, SI values.

    I/column (no Cy): M A D B t T alpha R1 R2 Izz Iyy rz ry Zzz Zyy Zpz Zpy It Iw  (19)
    Channel (Cy):     M A D B t T alpha R1 R2 Cy Izz Iyy rz ry Zzz Zyy Zpz Zpy It Iw (20)
    """
    need = 20 if has_cy else 19
    M = nums[0] if nums else 0.0
    label = make_label(family, label_parts, M)
    missing_iw = False
    if len(nums) == need - 1 and label in ALLOW_MISSING_IW:
        nums = list(nums) + [None]
        missing_iw = True
    if len(nums) < need:
        return None, f"short_fields n={len(nums)} need={need} desig={raw_desig!r}"
    if has_cy:
        M, A, D, B, t, T, alpha, R1, R2, Cy, Izz, Iyy, rz, ry, Zzz, Zyy, Zpz, Zpy, It, Iw = nums[:20]
    else:
        M, A, D, B, t, T, alpha, R1, R2, Izz, Iyy, rz, ry, Zzz, Zyy, Zpz, Zpy, It, Iw = nums[:19]
        Cy = None
    if not (40 <= D <= 1500) or A <= 0 or Izz <= 0:
        return None, f"sanity_fail D={D} A={A} Izz={Izz} desig={raw_desig!r}"
    si = dict(Label=label, Designation_IS=raw_desig.strip(), Type=family.upper(), Table=table_no or "",
              pdf_page=page, Mass_printed_kg_m=M, Mass_kg_m=M,
              A_si_mm2=A * 1e2, D_mm=D, B_mm=B, tw_mm=t, tf_mm=T, flange_slope_deg=alpha, R1_mm=R1, R2_mm=R2,
              Izz_si_mm4=Izz * 1e4, Iyy_si_mm4=Iyy * 1e4, rz_mm=rz, ry_mm=ry,
              Zez_mm3=Zzz * 1e3, Zey_mm3=Zyy * 1e3, Zpz_mm3=Zpz * 1e3, Zpy_mm3=Zpy * 1e3,
              It_mm4=It * 1e4, Iw_mm6=(Iw * 1e6 if Iw is not None else None),
              Cy_mm=Cy, corrections=list(notes or []))
    if missing_iw:
        si["corrections"].append(ALLOW_MISSING_IW[label] + " -> Iw empty (found:false for LTB)")
    for fld, (val, why) in OVERRIDES.get(label, {}).items():
        key = {"Izz": "Izz_si_mm4"}[fld]
        si[key] = val * 1e4
        si["corrections"].append(why)
    return si, None


def row_angle(a, b, t, nums, table_no, raw_desig, page, notes=None):
    """Angle: M A a b t R1 R2 Cy Cz Izz Iyy alpha Iuu Ivv rz ry ru rv Zz Zy Zpz Zpy It (23)."""
    if len(nums) < 23:
        return None, f"angle_short n={len(nums)} desig={raw_desig!r}"
    M, A, a2, b2, t2, R1, R2, Cy, Cz, Izz, Iyy, tan_alpha, Iuu, Ivv, rz, ry, ru, rv, Zz, Zy, Zpz, Zpy, It = nums[:23]
    if a: a2 = a
    if b: b2 = b
    if t: t2 = t
    if not (15 <= a2 <= 400) or A <= 0 or Izz <= 0:
        return None, f"angle_sanity a={a2} A={A} Izz={Izz} desig={raw_desig!r}"
    label = make_label("ISA", (a2, b2, t2), t2)
    si = dict(Label=label, Designation_IS=raw_desig.strip(), Type="ISA", Table=table_no or "", pdf_page=page,
              Mass_printed_kg_m=M, Mass_kg_m=M, A_si_mm2=A * 1e2, D_mm=a2, B_mm=b2, tw_mm=t2, tf_mm=t2,
              R1_mm=R1, R2_mm=R2, Cy_mm=Cy, Cz_mm=Cz,
              Izz_si_mm4=Izz * 1e4, Iyy_si_mm4=Iyy * 1e4, tan_alpha=tan_alpha,
              Iuu_mm4=Iuu * 1e4, Ivv_mm4=Ivv * 1e4, rz_mm=rz, ry_mm=ry, ru_mm=ru, rv_mm=rv,
              Zez_mm3=Zz * 1e3, Zey_mm3=Zy * 1e3, Zpz_mm3=Zpz * 1e3, Zpy_mm3=Zpy * 1e3,
              It_mm4=It * 1e4, Iw_mm6=0.0,   # WP2.2: Cw = 0 for angles (no invented Iy*ho^2/4)
              corrections=list(notes or []))
    return si, None


# --------------------------------------------------------------------------------------------
# Validator (WP2.2)
# --------------------------------------------------------------------------------------------
def _rel(a, b):
    return abs(a / b - 1.0) if b else float("inf")


def _plate_area(si):
    """Approximate web+flange plate area of an I section (mm2) - root fillets add a few percent."""
    D, B, t, T = si.get("D_mm"), si.get("B_mm"), si.get("tw_mm"), si.get("tf_mm")
    if not all(v for v in (D, B, t, T)):
        return None
    return 2 * B * T + (D - 2 * T) * t


def check_row(si):
    """Return list of failure strings for the validated row (empty = pass)."""
    fails = []
    A = si["A_si_mm2"]
    pairs = [("rz_mm", "Izz_si_mm4"), ("ry_mm", "Iyy_si_mm4")]
    if si["Type"] == "ISA":
        pairs += [("ru_mm", "Iuu_mm4"), ("rv_mm", "Ivv_mm4")]
    for rk, ik in pairs:
        r, I = si.get(rk), si.get(ik)
        if r is None or I is None:
            fails.append(f"{rk} missing")
            continue
        rc = math.sqrt(I / A)
        if _rel(r, rc) > TOL_R:
            fails.append(f"{rk} {r:g} vs sqrt(I/A) {rc:.2f}")
    mc = STEEL_DENSITY_KG_PER_M_PER_MM2 * A
    if _rel(si["Mass_kg_m"], mc) > TOL_MASS:
        fails.append(f"mass {si['Mass_kg_m']:g} vs 0.00785A {mc:.2f}")
    if si["Type"] != "ISA":
        Zc = 2 * si["Izz_si_mm4"] / si["D_mm"]
        if _rel(si["Zez_mm3"], Zc) > TOL_ZE:
            fails.append(f"Zez {si['Zez_mm3']:.0f} vs 2I/D {Zc:.0f}")
        if si["Zpz_mm3"] < 0.99 * si["Zez_mm3"] or si["Zpz_mm3"] > 1.6 * si["Zez_mm3"]:
            fails.append("Zpz/Zez %.2f outside [0.99, 1.6]" % (si["Zpz_mm3"] / si["Zez_mm3"]))
        if si["Izz_si_mm4"] < si["Iyy_si_mm4"]:
            fails.append("Izz < Iyy")
    else:
        s1 = si["Izz_si_mm4"] + si["Iyy_si_mm4"]
        s2 = si["Iuu_mm4"] + si["Ivv_mm4"]
        if _rel(s2, s1) > 0.03:
            fails.append(f"Iuu+Ivv {s2:.0f} vs Izz+Iyy {s1:.0f}")
    if si["Type"] not in ("ISA", "MC", "JC", "LC", "MPC"):
        Ap = _plate_area(si)
        # plate area + root fillets; tapered-flange sections (MB/JB/LB/HB/SC/WB) use mean T so allow 12 %
        if Ap and not (0.88 <= A / Ap <= 1.15):
            fails.append(f"A {A:.0f} inconsistent with plate area 2BT+(D-2T)t {Ap:.0f}")
    return fails


def repair_row(si):
    """Apply consistency-backed corrections. Only corrects a column when the others agree."""
    A = si["A_si_mm2"]
    mass_ok = _rel(si["Mass_kg_m"], STEEL_DENSITY_KG_PER_M_PER_MM2 * A) <= TOL_MASS
    ze_ok = True
    if si["Type"] != "ISA":
        ze_ok = _rel(si["Zez_mm3"], 2 * si["Izz_si_mm4"] / si["D_mm"]) <= TOL_ZE
    pairs = [("rz_mm", "Izz_si_mm4"), ("ry_mm", "Iyy_si_mm4")]
    if si["Type"] == "ISA":
        pairs += [("ru_mm", "Iuu_mm4"), ("rv_mm", "Ivv_mm4")]
    # r misprints (decimal shifts, cm printed under a mm header, digit swaps): A and I are corroborated by
    # the mass column (and Ze for z-z), so r is recomputed = sqrt(I/A).
    for rk, ik in pairs:
        r, I = si.get(rk), si.get(ik)
        if r is None or I is None:
            continue
        rc = math.sqrt(I / A)
        if _rel(r, rc) > TOL_R and (mass_ok or (ze_ok and si["Type"] != "ISA")):
            si[rk] = round(rc, 1)
            si["corrections"].append(f"{rk} printed {r:g} disagrees with sqrt(I/A)={rc:.2f} "
                                     f"(A, I corroborated by mass/Ze) -> {si[rk]:g}")
    # mass misprint: A corroborated by I/r pairs (all r agree) and Ze => designation mass is a misprint
    if not mass_ok:
        r_ok = all(si.get(rk) and _rel(si[rk], math.sqrt(si[ik] / A)) <= TOL_R for rk, ik in pairs)
        if r_ok and ze_ok and not _plate_area_fail(si):
            mc = round(STEEL_DENSITY_KG_PER_M_PER_MM2 * A, 2)
            si["corrections"].append(
                f"printed mass {si['Mass_printed_kg_m']:g} kg/m disagrees with 0.00785A={mc:g}; A corroborated by "
                f"Izz/rz, Iyy/ry and Ze -> Mass_kg_m={mc:g} (designation label keeps the printed mass)")
            si["Mass_kg_m"] = mc
    return si


def _plate_area_fail(si):
    if si["Type"] in ("ISA", "MC", "JC", "LC", "MPC"):
        return False
    Ap = _plate_area(si)
    return bool(Ap) and not (0.88 <= si["A_si_mm2"] / Ap <= 1.15)


def validate_csv(path) -> list:
    """Validate an existing is808_shapes.csv (SI columns). Returns [(label, [fails])] for failing rows."""
    bad = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            si = {}
            for k, v in row.items():
                if v in (None, ""):
                    si[k] = None
                    continue
                try:
                    si[k] = float(v)
                except ValueError:
                    si[k] = v
            si["Type"] = row["Type"]
            fails = check_row(si)
            if fails:
                bad.append((row["Label"], fails))
    return bad


# --------------------------------------------------------------------------------------------
def _disambiguate(row, seen):
    lab = row["Label"]
    if lab in seen:
        lab2 = f"{lab}X{_mass_tag(row['Mass_printed_kg_m'])}"
        if lab2 in seen:
            seen[lab2] = seen.get(lab2, 1) + 1
            lab2 = f"{lab2}_{seen[lab2]}"
        row["Label"] = lab2
        seen[lab2] = 1
        seen[lab] = seen.get(lab, 1) + 1
    else:
        seen[lab] = 1
    return row


def parse(text: str):
    rows, errors = [], []
    table_no = None
    seen = {}
    angle_ab = None
    page = 1
    for raw in text.split("\n"):
        page += raw.count("\f")
        raw = raw.replace("\f", "")
        mt = TABLE_RE.search(raw)
        if mt and "Concluded" not in raw and "Continued" not in raw:
            try:
                n = int(mt.group(1))
                if 1 <= n <= 13:
                    table_no = n
                elif n > 13:
                    table_no = 99
            except ValueError:
                pass
        notes = []
        line = fix_line(raw, notes)

        if table_no is not None and 9 <= table_no <= 12:
            m = ANGLE_FULL_RE.match(line)
            if m:
                a, b, t = int(m.group(1)), int(m.group(2)), float(m.group(3))
                angle_ab = (a, b)
                raw_d = f"ISA {a} x {b} x {t:g}"
                row, err = row_angle(a, b, t, parse_nums(m.group(4)), table_no, raw_d, page, notes)
            else:
                m = ANGLE_CONT_RE.match(line)
                if not (m and angle_ab):
                    continue
                t = float(m.group(1))
                a, b = angle_ab
                raw_d = f"ISA {a} x {b} x {t:g}"
                row, err = row_angle(a, b, t, parse_nums(m.group(2)), table_no, raw_d, page, notes)
            if err:
                errors.append(err)
            else:
                rows.append(_disambiguate(row, seen))
            continue

        if table_no is not None and 6 <= table_no <= 8:
            m = CHAN_RE.match(line)
            if m:
                fam, prov, d, rest = m.group(1), m.group(2), int(m.group(3)), m.group(4)
                raw_d = f"{fam}{' (P)' if prov else ''} {d}"
                row, err = row_I_like(fam, (d,), parse_nums(rest), table_no, raw_d, page, has_cy=True, notes=notes)
                if err:
                    errors.append(err)
                else:
                    rows.append(_disambiguate(row, seen))
            continue

        if table_no == 13:
            m = PBP_RE.match(line)
            if m:
                d = int(m.group(1))
                nums = parse_nums(m.group(2))
                raw_d = f"PBP {d} x {nums[0] if nums else '?'}"
                row, err = row_I_like("PBP", (d,), nums, table_no, raw_d, page, notes=notes)
                if err:
                    errors.append(err)
                else:
                    rows.append(_disambiguate(row, seen))
            continue

        if table_no is None or table_no > 5:
            continue

        m = PF_RE.match(line)
        if m:
            fam, d, b, rest = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
            nums = parse_nums(rest)
            raw_d = f"{fam} {d} X {b} X {nums[0] if nums else '?'}"
            row, err = row_I_like(fam, (d, b), nums, table_no, raw_d, page, notes=notes)
            if err:
                errors.append(err)
            else:
                rows.append(_disambiguate(row, seen))
            continue
        m = SIMPLE_RE.match(line)
        if m:
            fam, d, rest = m.group(1), int(m.group(2)), m.group(3)
            row, err = row_I_like(fam, (d,), parse_nums(rest), table_no, f"{fam} {d}", page, notes=notes)
            if err:
                errors.append(err)
            else:
                rows.append(_disambiguate(row, seen))
    return rows, errors


# --------------------------------------------------------------------------------------------
SI_FIELDS = ["D_mm", "B_mm", "tw_mm", "tf_mm", "flange_slope_deg", "R1_mm", "R2_mm", "rz_mm", "ry_mm",
             "Zez_mm3", "Zey_mm3", "Zpz_mm3", "Zpy_mm3", "It_mm4", "Iw_mm6", "Cy_mm", "Cz_mm", "tan_alpha",
             "Iuu_mm4", "Ivv_mm4", "ru_mm", "rv_mm", "r_min_mm"]
FIELDS = ["AISC_Manual_Label", "Label", "Designation_IS", "Type",
          "A", "Ix", "Iy", "J", "Zx", "Zy", "Sx", "Sy", "rx", "ry", "d", "tw", "bf", "tf", "Cw", "rts", "ho",
          "Mass_kg_m", "Mass_printed_kg_m", "A_si_mm2", "Izz_si_mm4", "Iyy_si_mm4"] + SI_FIELDS + \
         ["Source", "Table", "pdf_page", "units", "validated", "corrections"]


def to_csv_row(si):
    """Derive legacy inch columns from the (corrected) SI values."""
    A, Izz, Iyy = si["A_si_mm2"], si["Izz_si_mm4"], si["Iyy_si_mm4"]
    It, Iw = si.get("It_mm4") or 0.0, si.get("Iw_mm6")
    rmin = min(v for v in (si.get("rz_mm"), si.get("ry_mm"), si.get("rv_mm")) if v)
    si["r_min_mm"] = rmin
    d_in, tf_in = si["D_mm"] * MM, si["tf_mm"] * MM
    Sx_in = si["Zez_mm3"] * MM ** 3
    Iy_in, Cw_in = Iyy * MM ** 4, (Iw * MM ** 6 if Iw else None)
    rts = math.sqrt(math.sqrt(Iy_in * Cw_in) / Sx_in) if (Cw_in and Sx_in) else ""
    row = {
        "AISC_Manual_Label": si["Label"], "Label": si["Label"], "Designation_IS": si["Designation_IS"],
        "Type": si["Type"],
        "A": round(A * MM ** 2, 4), "Ix": round(Izz * MM ** 4, 4), "Iy": round(Iy_in, 4),
        "J": round(It * MM ** 4, 6), "Zx": round(si["Zpz_mm3"] * MM ** 3, 4), "Zy": round(si["Zpy_mm3"] * MM ** 3, 4),
        "Sx": round(Sx_in, 4), "Sy": round(si["Zey_mm3"] * MM ** 3, 4),
        "rx": round(si["rz_mm"] * MM, 4), "ry": round(si["ry_mm"] * MM, 4),
        "d": round(d_in, 4), "tw": round(si["tw_mm"] * MM, 5), "bf": round(si["B_mm"] * MM, 4), "tf": round(tf_in, 5),
        "Cw": (round(Cw_in, 4) if Cw_in else (0.0 if si["Type"] == "ISA" else "")),
        "rts": (round(rts, 4) if rts != "" else ""), "ho": round(d_in - tf_in, 4),
        "Mass_kg_m": si["Mass_kg_m"], "Mass_printed_kg_m": si["Mass_printed_kg_m"],
        "A_si_mm2": A, "Izz_si_mm4": Izz, "Iyy_si_mm4": Iyy,
        "Source": "IS_808_2021", "Table": si["Table"], "pdf_page": si["pdf_page"],
        "units": "SI columns authoritative (mm, mm2, mm3, mm4, mm6); inch columns derived",
        "validated": "ok", "corrections": " | ".join(si["corrections"]),
    }
    for k in SI_FIELDS:
        v = si.get(k)
        row[k] = "" if v is None else (round(v, 4) if isinstance(v, float) else v)
    return row


def build(text):
    rows, errors = parse(text)
    good, quarantined = [], []
    for si in rows:
        repair_row(si)
        fails = check_row(si)
        if fails:
            quarantined.append((si, fails))
        else:
            good.append(si)
    good.sort(key=lambda r: (r["Type"], r["D_mm"], r["Mass_printed_kg_m"]))
    return good, quarantined, errors


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TXT
    if not src.exists():
        print(f"missing extract {src}; run pdftotext -layout IS_808_2021.pdf first", file=sys.stderr)
        sys.exit(1)
    good, quar, errors = build(src.read_text(errors="replace"))
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for si in good:
            w.writerow(to_csv_row(si))
    with QUAR.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["Label", "Designation_IS", "Type", "pdf_page", "found", "reasons"])
        w.writeheader()
        for si, fails in quar:
            w.writerow({"Label": si["Label"], "Designation_IS": si["Designation_IS"], "Type": si["Type"],
                        "pdf_page": si["pdf_page"], "found": "false", "reasons": " | ".join(fails)})
    post = validate_csv(OUT)
    corrected = [si for si in good if si["corrections"]]
    by = {}
    for r in good:
        by[r["Type"]] = by.get(r["Type"], 0) + 1
    lines = [
        "# IS 808 shapes database - gaps and corrections",
        "",
        "**Built:** from IS 808:2021 Tables 1-13 via `pdftotext -layout` -> `tools/build_is808_shapes.py` (WP2.2).",
        f"**Output:** `steel_engine/is808_shapes.csv` ({len(good)} validated rows); "
        f"`steel_engine/is808_quarantine.csv` ({len(quar)} rows, found:false).",
        f"**Parse errors / skipped lines:** {len(errors)}",
        f"**Validator after build:** {len(post)} failing rows "
        "(|r - sqrt(I/A)| <= 3 %, |M - 0.00785A| <= 3 %, |Ze - 2I/D| <= 4 %, Zp/Ze in [0.99, 1.6], "
        "angle Iuu+Ivv = Izz+Iyy within 3 %, I-section A vs plate area 0.88-1.15).",
        "",
        "## Units",
        "N-mm. The SI columns (`*_mm`, `*_mm2`, `*_mm3`, `*_mm4`, `*_mm6`, `A_si_mm2`, `Izz_si_mm4`, `Iyy_si_mm4`) are",
        "authoritative. Inch columns (`A`, `Ix`, `rx`, ...) are derived from them for the kip-in twin only.",
        "Angles carry `Iuu_mm4, Ivv_mm4, ru_mm, rv_mm` (principal axes) and `r_min_mm = rv`; `Iw_mm6 = 0` for angles.",
        "",
        "## Counts by type (validated)",
        *[f"- {k}: {v}" for k, v in sorted(by.items())],
        "",
        f"## Quarantined rows ({len(quar)}) - not selectable; `sections.props()` raises (found:false)",
        *[f"- `{si['Label']}` (pdf p.{si['pdf_page']}): " + "; ".join(f) for si, f in quar],
        "",
        f"## Corrected rows ({len(corrected)}) - PDF misprints corrected from the PDF's own corroborating columns",
        *[f"- `{si['Label']}` (pdf p.{si['pdf_page']}): " + " | ".join(si["corrections"]) for si in corrected],
        "",
        "## Parse errors",
        *([f"- {e}" for e in errors] or ["- none"]),
        "",
        "## Out of scope",
        "- Annex A/B formula-only custom sections: compute from the Annex formulae with a cite; never invent.",
        "- Rectangular/square hollow sections (IS 4923) are not in the corpus: no path (found:false).",
        "- IS 1161 circular hollow sections live in `is1161_tubes.csv` (grade/process resolved from cfg; no default fy).",
        "",
        "## Lookup labels",
        "- Beams/cols: `MB200`, `LB150`, `SC250`, `NPB100X55X8.1`; channels `MC200`, `LC300`; angles `ISA100X75X10`;",
        "  piles `PBP200X43.85`; duplicates append the printed mass (`WB200X52.09`).",
    ]
    GAPS.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT} rows={len(good)} quarantined={len(quar)} errors={len(errors)} post-validate-fail={len(post)}")
    for si, f in quar:
        print("  Q", si["Label"], f)
    for e in errors:
        print("  E", e)


if __name__ == "__main__":
    main()
