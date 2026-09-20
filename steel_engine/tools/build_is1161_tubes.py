#!/usr/bin/env python3
"""Build steel_engine/is1161_tubes.csv from IS 1161:2014 Table 1 (pdftotext -layout).

Circular hollow sections for structural purposes. Properties converted to kip+inch
pipeline units; SI retained for audit. Labels: CHS{OD}X{t} and NB{nb}X{t}.
"""
from __future__ import annotations

import csv
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "is1161_tubes.csv"
DEFAULT_TXT = Path("/tmp/is1161/t1.txt")

MM = 1 / 25.4
# Table 1 units: A cm², I cm⁴, Z cm³, r cm → inch
CM2_TO_IN2 = (10 * MM) ** 2
CM4_TO_IN4 = (10 * MM) ** 4
CM3_TO_IN3 = (10 * MM) ** 3
CM_TO_IN = 10 * MM


def parse_nums(s: str) -> list[float]:
    out = []
    for m in re.finditer(r"\d{1,3}(?: \d{3})+(?:\.\d+)?|\d+\.\d+|\d+", s):
        try:
            out.append(float(m.group(0).replace(" ", "")))
        except ValueError:
            pass
    return out


def geom_I_cm4(od_mm, t_mm) -> float:
    Do = od_mm / 10.0  # cm
    Di = (od_mm - 2 * t_mm) / 10.0
    if Di <= 0:
        return 0.0
    return (math.pi / 64.0) * (Do ** 4 - Di ** 4)


def geom_A_cm2(od_mm, t_mm) -> float:
    Do = od_mm / 10.0
    Di = (od_mm - 2 * t_mm) / 10.0
    if Di <= 0:
        return 0.0
    return (math.pi / 4.0) * (Do ** 2 - Di ** 2)


def parse(text: str):
    rows = []
    errors = []
    nb_cur = None
    for line in text.splitlines():
        # NB alone at start of a data block, or inline with OD
        # Patterns:
        # "  15    21.3   2.6    1.20     1.53 ..."
        # "        21.3     2   0.952     1.21 ..."  (NB carried)
        s = line.rstrip()
        if not s.strip() or "Table" in s or "NB" in s and "OD" in s:
            continue
        if re.match(r"^\s*\(\d+\)", s) or "cm²" in s or "kg/m" in s:
            continue
        nums = parse_nums(s)
        if len(nums) < 5:
            continue
        # Detect leading NB (integer 15..350 typical) when first token is NB-sized and second is OD
        # Line with NB: first int in {15,20,25,...,350}, then OD ~21..356
        m_nb = re.match(r"^\s*(\d{2,3})\s+(\d+\.?\d*)\s+(\d+\.?\d*)\s+(.*)$", s)
        m_od = re.match(r"^\s+(\d+\.?\d*)\s+(\d+\.?\d*)\s+(.*)$", s)
        nb = None
        od = thk = None
        rest_nums = []
        if m_nb:
            maybe_nb = int(m_nb.group(1))
            maybe_od = float(m_nb.group(2))
            maybe_t = float(m_nb.group(3))
            # NB is small int; OD is larger float typically
            if maybe_nb <= 350 and maybe_od > maybe_nb:
                nb = maybe_nb
                nb_cur = nb
                od = maybe_od
                thk = maybe_t
                rest_nums = parse_nums(m_nb.group(4))
            else:
                # first number was OD (no NB on line) — fall through
                m_nb = None
        if not m_nb and m_od:
            od = float(m_od.group(1))
            thk = float(m_od.group(2))
            rest_nums = parse_nums(m_od.group(3))
            nb = nb_cur
        if od is None or thk is None or not rest_nums:
            continue
        # rest: Mass, Area, InternalVol, SurfExt, SurfInt, I, Z, r, r2  (9) — some OCR merges
        if len(rest_nums) < 4:
            errors.append(f"short rest od={od} t={thk} n={len(rest_nums)}")
            continue
        mass = rest_nums[0]
        A_cm2 = rest_nums[1]
        # Find I, Z, r near the end — prefer last 4: I, Z, r, r²
        if len(rest_nums) >= 9:
            I_cm4, Z_cm3, r_cm, r2 = rest_nums[5], rest_nums[6], rest_nums[7], rest_nums[8]
        elif len(rest_nums) >= 6:
            I_cm4, Z_cm3, r_cm = rest_nums[-3], rest_nums[-2], rest_nums[-1]
            r2 = r_cm * r_cm
        else:
            errors.append(f"cant_split od={od} t={thk} rest={rest_nums}")
            continue

        # Sanity vs geometry — fix OCR-glitched I (e.g. 10221 vs 1221)
        Ig = geom_I_cm4(od, thk)
        Ag = geom_A_cm2(od, thk)
        if Ag > 0 and abs(A_cm2 - Ag) / Ag > 0.25:
            # bad A — skip rather than invent
            errors.append(f"A_mismatch od={od} t={thk} tab={A_cm2} geom={Ag:.3f}")
            continue
        if Ig > 0 and (I_cm4 <= 0 or abs(I_cm4 - Ig) / Ig > 0.35):
            # likely OCR; use geometry from tabulated OD/t (not inventing dims)
            I_cm4 = Ig
            Z_cm3 = Ig / (od / 20.0)  # Z = I / (D/2) with D in cm
            r_cm = math.sqrt(I_cm4 / A_cm2) if A_cm2 else 0.0

        if not (15 <= od <= 400) or not (1.5 <= thk <= 20) or A_cm2 <= 0 or I_cm4 <= 0:
            errors.append(f"sanity od={od} t={thk} A={A_cm2} I={I_cm4}")
            continue

        label = f"CHS{od:g}X{thk:g}".replace(" ", "")
        # also NB-based alias
        nb_label = f"NB{nb}X{thk:g}" if nb else ""

        A = A_cm2 * CM2_TO_IN2
        Ix = I_cm4 * CM4_TO_IN4
        Sx = Z_cm3 * CM3_TO_IN3
        rx = r_cm * CM_TO_IN
        d = od * MM
        t_in = thk * MM
        # thin-wall torsion J ≈ 2*I for CHS
        J = 2.0 * Ix
        Zx = Sx * 1.3  # plastic approx for CHS; elastic S retained — agent should RAG plastic factor
        # better: for CHS Z_plastic = (Do^3 - Di^3)/6 in cm3
        Do = od / 10.0
        Di = (od - 2 * thk) / 10.0
        Zp_cm3 = (Do ** 3 - Di ** 3) / 6.0 if Di > 0 else Sx / CM3_TO_IN3
        Zx = Zp_cm3 * CM3_TO_IN3

        row = {
            "AISC_Manual_Label": label,
            "Label": label,
            "Designation_IS": f"NB {nb} × {od:g} × {thk:g}" if nb else f"CHS {od:g} × {thk:g}",
            "Type": "CHS",
            "NB_mm": nb or "",
            "A": round(A, 4),
            "Ix": round(Ix, 4),
            "Iy": round(Ix, 4),
            "J": round(J, 4),
            "Zx": round(Zx, 4),
            "Zy": round(Zx, 4),
            "Sx": round(Sx, 4),
            "Sy": round(Sx, 4),
            "rx": round(rx, 4),
            "ry": round(rx, 4),
            "d": round(d, 4),
            "tw": round(t_in, 5),
            "bf": round(d, 4),
            "tf": round(t_in, 5),
            "Cw": 0.0,
            "rts": "",
            "ho": "",
            "Mass_kg_m": mass,
            "A_si_mm2": round(A_cm2 * 100, 2),
            "Izz_si_mm4": round(I_cm4 * 1e4, 2),
            "Iyy_si_mm4": round(I_cm4 * 1e4, 2),
            "Source": "IS_1161_2014",
            "Table": "1",
            "units": "inch_converted_from_IS1161_SI",
            "NB_Label": nb_label,
        }
        rows.append(row)
    return rows, errors


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TXT
    if not src.exists():
        print(f"missing {src}", file=sys.stderr)
        sys.exit(1)
    rows, errors = parse(src.read_text(errors="replace"))
    # de-dupe by Label
    seen = {}
    uniq = []
    for r in rows:
        if r["Label"] in seen:
            continue
        seen[r["Label"]] = 1
        uniq.append(r)
    rows = uniq
    fields = [
        "AISC_Manual_Label", "Label", "Designation_IS", "Type", "NB_mm", "NB_Label",
        "A", "Ix", "Iy", "J", "Zx", "Zy", "Sx", "Sy", "rx", "ry",
        "d", "tw", "bf", "tf", "Cw", "rts", "ho",
        "Mass_kg_m", "A_si_mm2", "Izz_si_mm4", "Iyy_si_mm4",
        "Source", "Table", "units",
    ]
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {OUT} rows={len(rows)} errors={len(errors)}")
    if errors[:10]:
        print("sample errors:", *errors[:10], sep="\n  ")
    annotate_materials(OUT)


# ---------------------------------------------------------------------------------------------
# WP2.2 / HR800-13: IS 1161 material is NOT IS 2062. Tubes are graded YSt 210/240/310/355 and made
# HFS / CDS / ERW / HFIW (IS 1161:2014 cl. 3.1, 5 and Table 2, pdf p.6). The grade and process are
# job inputs (cfg), so each row carries empty `grade`/`process`/`fy_MPa`/`fu_MPa` columns that
# sections.props(..., grade=, process=) resolves from IS1161_TABLE2. There is NO default fy (never 250).
# ---------------------------------------------------------------------------------------------
MATERIAL_FIELDS = ["grade", "process", "fy_MPa", "fu_MPa", "D_mm", "t_mm", "r_mm", "Ze_mm3", "Zp_mm3",
                   "It_mm4", "Iw_mm6", "validated"]


def annotate_materials(path=OUT):
    rows = list(csv.DictReader(open(path, newline="")))
    fields = list(rows[0].keys())
    for k in MATERIAL_FIELDS:
        if k not in fields:
            fields.append(k)
    for r in rows:
        D = float(r["d"]) * 25.4
        t = float(r["tw"]) * 25.4
        A = float(r["A_si_mm2"])
        I = float(r["Izz_si_mm4"])
        Di = D - 2 * t
        r.update({"grade": "", "process": "", "fy_MPa": "", "fu_MPa": "",
                  "D_mm": round(D, 2), "t_mm": round(t, 2), "r_mm": round(math.sqrt(I / A), 2),
                  "Ze_mm3": round(2 * I / D, 1), "Zp_mm3": round((D ** 3 - Di ** 3) / 6.0, 1),
                  "It_mm4": round(2 * I, 1), "Iw_mm6": 0.0})
        ok = (abs(A / (math.pi / 4 * (D ** 2 - Di ** 2)) - 1) <= 0.03
              and abs(float(r["Mass_kg_m"]) / (0.00785 * A) - 1) <= 0.03)
        r["validated"] = "ok" if ok else "FAIL"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"annotated {path}: {sum(r['validated'] == 'ok' for r in rows)}/{len(rows)} rows validated")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--annotate":
        annotate_materials(OUT)
    else:
        main()
