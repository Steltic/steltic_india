#!/usr/bin/env python3
"""Build steel_engine/is808_shapes.csv from IS 808:2021 pdftotext -layout extract.

Tables 1–5: I / column sections (MB, WB, JB, LB, HB, SC, NPB, WPB)
Tables 6–8: channels (MC, JC, LC, MPC) — extra Cy column before Izz
Tables 9–12: equal/unequal angles (ISA / ∠)
Table 13: bearing piles (PBP)

Units in CSV match the pipeline (kip+inch), converted from IS 808 SI tabulated
multipliers. SI source values retained in *_si columns for audit.
"""
from __future__ import annotations

import csv
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "is808_shapes.csv"
GAPS = HERE.parent / "is808_GAPS.md"
DEFAULT_TXT = Path("/tmp/is808/all_tables.txt")

MM = 1.0 / 25.4
MM2 = MM * MM
MM3 = MM2 * MM
MM4 = MM3 * MM
MM6 = MM4 * MM2


def A_in2(a_x1e2): return a_x1e2 * 1e2 * MM2
def I_in4(i_x1e4): return i_x1e4 * 1e4 * MM4
def Z_in3(z_x1e3): return z_x1e3 * 1e3 * MM3
def Iw_in6(iw_x1e6): return iw_x1e6 * 1e6 * MM6
def mm_to_in(v): return v * MM


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


TABLE_RE = re.compile(r"Table\s+(\d+)\b", re.I)
SIMPLE_RE = re.compile(r"^\s*(MB|WB|JB|LB|HB|SC)\s+(\d+)\*?\s+(.*)$", re.I)
PF_RE = re.compile(r"^\s*(NPB|WPB)\s+(\d+)\s*X\s*(\d+)\s*X\s+(.*)$", re.I)
CHAN_RE = re.compile(
    r"^\s*(MC|JC|LC|MPC)(?:\s*\(P\))?\s+(\d+)\*?\s+(.*)$", re.I
)
# Equal/unequal angles: ∠ 20 × 20 × 3   OR continuation   ×4
ANGLE_FULL_RE = re.compile(
    r"^\s*[∠∠]\s*(\d+)\s*[×xX]\s*(\d+)\s*[×xX]\s*(\d+)\s+(.*)$"
)
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
        d = parts[0]
        return f"PBP{int(d)}X{_mass_tag(mass)}".upper()
    if fam == "ISA":
        a, b, t = parts
        return f"ISA{int(a)}X{int(b)}X{_mass_tag(t)}".upper()
    d = parts[0]
    return f"{fam}{int(d)}".upper()


def _fix_ry(ry, B):
    """OCR sometimes drops a digit on ry (2.36 vs 23.6)."""
    if B and ry < max(5.0, 0.08 * B) and ry * 10 <= 0.55 * B + 5:
        return ry * 10.0
    return ry


def row_I_like(family, label_parts, nums, table_no, raw_desig, *, has_cy=False):
    """I-beam / channel / pile row.

    I/column (no Cy): M A D B t T α R1 R2 Izz Iyy rz ry Zzz Zyy Zpz Zpy It Iw  (19)
    Channel (Cy):     M A D B t T α R1 R2 Cy Izz Iyy rz ry Zzz Zyy Zpz Zpy It Iw (20)
    """
    need = 20 if has_cy else 19
    if len(nums) < need:
        return None, f"short_fields n={len(nums)} need={need} desig={raw_desig!r}"
    if has_cy:
        M, A, D, B, t, T, alpha, R1, R2, Cy, Izz, Iyy, rz, ry, Zzz, Zyy, Zpz, Zpy, It, Iw = nums[:20]
    else:
        M, A, D, B, t, T, alpha, R1, R2, Izz, Iyy, rz, ry, Zzz, Zyy, Zpz, Zpy, It, Iw = nums[:19]
        Cy = None
    ry = _fix_ry(ry, B)
    if not (40 <= D <= 1500) or A <= 0 or Izz <= 0:
        return None, f"sanity_fail D={D} A={A} Izz={Izz} desig={raw_desig!r}"
    label = make_label(family, label_parts, M)
    A_i = A_in2(A)
    Ix = I_in4(Izz)
    Iy = I_in4(Iyy)
    J = I_in4(It)
    Sx = Z_in3(Zzz)
    Sy = Z_in3(Zyy)
    Zx = Z_in3(Zpz)
    Zy = Z_in3(Zpy)
    d = mm_to_in(D)
    bf = mm_to_in(B)
    tw = mm_to_in(t)
    tf = mm_to_in(T)
    rx = mm_to_in(rz)
    ry_in = mm_to_in(ry)
    Cw = Iw_in6(Iw)
    ho = d - tf
    rts = math.sqrt(math.sqrt(Iy * Cw) / Sx) if Sx and Iy and Cw else ""
    row = {
        "AISC_Manual_Label": label,
        "Label": label,
        "Designation_IS": raw_desig.strip(),
        "Type": family.upper(),
        "A": round(A_i, 4),
        "Ix": round(Ix, 4),
        "Iy": round(Iy, 4),
        "J": round(J, 6),
        "Zx": round(Zx, 4),
        "Zy": round(Zy, 4),
        "Sx": round(Sx, 4),
        "Sy": round(Sy, 4),
        "rx": round(rx, 4),
        "ry": round(ry_in, 4),
        "d": round(d, 4),
        "tw": round(tw, 5),
        "bf": round(bf, 4),
        "tf": round(tf, 5),
        "Cw": round(Cw, 4) if Cw else "",
        "rts": round(rts, 4) if rts != "" else "",
        "ho": round(ho, 4),
        "Mass_kg_m": M,
        "A_si_mm2": A * 1e2,
        "Izz_si_mm4": Izz * 1e4,
        "Iyy_si_mm4": Iyy * 1e4,
        "Source": "IS_808_2021",
        "Table": table_no or "",
        "units": "inch_converted_from_IS808_SI",
    }
    if Cy is not None:
        row["Cy_si_mm"] = Cy
    return row, None


def row_angle(a, b, t, nums, table_no, raw_desig):
    """Angle: M A a b t R1 R2 Cy Cz Izz Iyy α Iuu Ivv rz ry ru rv Zz Zy Zpz Zpy It (23)."""
    if len(nums) < 23:
        return None, f"angle_short n={len(nums)} desig={raw_desig!r}"
    M, A, a2, b2, t2, R1, R2, Cy, Cz, Izz, Iyy, alpha, Iuu, Ivv, rz, ry, ru, rv, Zz, Zy, Zpz, Zpy, It = nums[:23]
    # Prefer dims from designation when present
    if a: a2 = a
    if b: b2 = b
    if t: t2 = t
    ry = _fix_ry(ry, min(a2, b2))
    rv = _fix_ry(rv, min(a2, b2) * 0.6)
    if not (15 <= a2 <= 400) or A <= 0 or Izz <= 0:
        return None, f"angle_sanity a={a2} A={A} Izz={Izz} desig={raw_desig!r}"
    label = make_label("ISA", (a2, b2, t2), t2)
    # For angles Ix about zz (parallel to axis through heel along longer leg convention in IS tables)
    A_i = A_in2(A)
    Ix = I_in4(Izz)
    Iy = I_in4(Iyy)
    J = I_in4(It)
    Sx = Z_in3(Zz)
    Sy = Z_in3(Zy)
    Zx = Z_in3(Zpz)
    Zy_pl = Z_in3(Zpy)
    d = mm_to_in(a2)
    bf = mm_to_in(b2)
    tw = mm_to_in(t2)
    tf = mm_to_in(t2)
    rx = mm_to_in(rz)
    ry_in = mm_to_in(ry)
    row = {
        "AISC_Manual_Label": label,
        "Label": label,
        "Designation_IS": raw_desig.strip(),
        "Type": "ISA",
        "A": round(A_i, 4),
        "Ix": round(Ix, 4),
        "Iy": round(Iy, 4),
        "J": round(J, 6),
        "Zx": round(Zx, 4),
        "Zy": round(Zy_pl, 4),
        "Sx": round(Sx, 4),
        "Sy": round(Sy, 4),
        "rx": round(rx, 4),
        "ry": round(ry_in, 4),
        "d": round(d, 4),
        "tw": round(tw, 5),
        "bf": round(bf, 4),
        "tf": round(tf, 5),
        "Cw": "",  # warping ≈ 0 for angles in this pipeline
        "rts": "",
        "ho": round(d - tf, 4),
        "Mass_kg_m": M,
        "A_si_mm2": A * 1e2,
        "Izz_si_mm4": Izz * 1e4,
        "Iyy_si_mm4": Iyy * 1e4,
        "Source": "IS_808_2021",
        "Table": table_no or "",
        "units": "inch_converted_from_IS808_SI",
    }
    return row, None


def _disambiguate(row, seen):
    lab = row["Label"]
    if lab in seen:
        mkg = row["Mass_kg_m"]
        lab2 = f"{lab}X{_mass_tag(mkg)}"
        # if still colliding (same mass), append count
        if lab2 in seen:
            seen[lab2] = seen.get(lab2, 1) + 1
            lab2 = f"{lab2}_{seen[lab2]}"
        row["Label"] = lab2
        row["AISC_Manual_Label"] = lab2
        seen[lab2] = 1
        seen[lab] = seen.get(lab, 1) + 1
    else:
        seen[lab] = 1
    return row


def parse(text: str):
    rows = []
    errors = []
    table_no = None
    seen = {}
    angle_ab = None  # (a,b) for continuation ×t rows

    for line in text.splitlines():
        mt = TABLE_RE.search(line)
        if mt and "Concluded" not in line and "Continued" not in line and "Continued" not in line:
            try:
                table_no = int(mt.group(1))
            except ValueError:
                pass

        # --- angles (T9–12) ---
        if table_no is not None and 9 <= table_no <= 12:
            m = ANGLE_FULL_RE.match(line)
            if m:
                a, b, t = int(m.group(1)), int(m.group(2)), float(m.group(3))
                angle_ab = (a, b)
                nums = parse_nums(m.group(4))
                raw = f"ISA {a} x {b} x {t:g}"
                row, err = row_angle(a, b, t, nums, table_no, raw)
                if err:
                    errors.append(err)
                    continue
                rows.append(_disambiguate(row, seen))
                continue
            m = ANGLE_CONT_RE.match(line)
            if m and angle_ab:
                t = float(m.group(1))
                a, b = angle_ab
                nums = parse_nums(m.group(2))
                raw = f"ISA {a} x {b} x {t:g}"
                row, err = row_angle(a, b, t, nums, table_no, raw)
                if err:
                    errors.append(err)
                    continue
                rows.append(_disambiguate(row, seen))
                continue
            continue  # don't fall through to I-parsers on angle pages

        # --- channels (T6–8) ---
        if table_no is not None and 6 <= table_no <= 8:
            m = CHAN_RE.match(line)
            if m:
                fam, d, rest = m.group(1), int(m.group(2)), m.group(3)
                nums = parse_nums(rest)
                raw = f"{fam} {d}"
                row, err = row_I_like(fam, (d,), nums, table_no, raw, has_cy=True)
                if err:
                    errors.append(err)
                    continue
                rows.append(_disambiguate(row, seen))
            continue

        # --- piles (T13) ---
        if table_no is not None and table_no == 13:
            m = PBP_RE.match(line)
            if m:
                d = int(m.group(1))
                nums = parse_nums(m.group(2))
                raw = f"PBP {d} x {nums[0] if nums else '?'}"
                row, err = row_I_like("PBP", (d,), nums, table_no, raw, has_cy=False)
                if err:
                    errors.append(err)
                    continue
                rows.append(_disambiguate(row, seen))
            continue

        # --- I / columns (T1–5) ---
        if table_no is not None and table_no > 5:
            continue

        m = PF_RE.match(line)
        if m:
            fam, d, b, rest = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
            nums = parse_nums(rest)
            raw = f"{fam} {d} X {b} X {nums[0] if nums else '?'}"
            row, err = row_I_like(fam, (d, b), nums, table_no, raw, has_cy=False)
            if err:
                errors.append(err)
                continue
            rows.append(_disambiguate(row, seen))
            continue

        m = SIMPLE_RE.match(line)
        if m:
            fam, d, rest = m.group(1), int(m.group(2)), m.group(3)
            nums = parse_nums(rest)
            raw = f"{fam} {d}"
            row, err = row_I_like(fam, (d,), nums, table_no, raw, has_cy=False)
            if err:
                errors.append(err)
                continue
            rows.append(_disambiguate(row, seen))
            continue

    return rows, errors


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TXT
    if not src.exists():
        print(f"missing extract {src}; run pdftotext first", file=sys.stderr)
        sys.exit(1)
    text = src.read_text(errors="replace")
    rows, errors = parse(text)
    rows.sort(key=lambda r: (r["Type"], r["d"], r["Mass_kg_m"]))
    fields = [
        "AISC_Manual_Label", "Label", "Designation_IS", "Type",
        "A", "Ix", "Iy", "J", "Zx", "Zy", "Sx", "Sy", "rx", "ry",
        "d", "tw", "bf", "tf", "Cw", "rts", "ho",
        "Mass_kg_m", "A_si_mm2", "Izz_si_mm4", "Iyy_si_mm4",
        "Source", "Table", "units",
    ]
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    by = {}
    for r in rows:
        by[r["Type"]] = by.get(r["Type"], 0) + 1
    gaps = f"""# IS 808 shapes database — gaps

**Built:** from IS 808:2021 Tables 1–13 via `pdftotext -layout` → `build_is808_shapes.py`
**Output:** `steel_engine/is808_shapes.csv` ({len(rows)} rows)
**Parse errors/skipped lines:** {len(errors)}

## Ingested
- Table 1: Medium / Wide flange beams (MB, WB)
- Table 2: Junior / Light beams (JB, LB)
- Table 3: Narrow parallel flange beams (NPB …×…×mass)
- Table 4: Wide parallel flange beams (WPB …×…×mass)
- Table 5: Column / heavy beam sections (SC, HB)
- Tables 6–8: channels (MC, JC, LC, MPC) — Cy column handled
- Tables 9–12: equal / unequal angles (ISA a×b×t)
- Table 13: bearing piles (PBP …×mass)

## Counts by Type
{chr(10).join(f'- {k}: {v}' for k,v in sorted(by.items()))}

## Remaining / out of scope
- Annex A/B formula-only custom sections — agent must compute via RAG, not invent
- OCR digit-drop on a few ry values: auto-corrected when ry ≪ 0.08·B (documented heuristic)

## Units
Pipeline still kip+inch. CSV properties converted from IS 808 SI multipliers;
`A_si_mm2` / `Izz_si_mm4` / `Iyy_si_mm4` retain SI for audit.

## Lookup labels
- Beams/cols: `MB200`, `LB150`, `SC250`, `NPB100X55X8.1`, …
- Channels: `MC200`, `JC150`, `LC300`, `MPC250`
- Angles: `ISA50X50X6`, `ISA100X75X10` (also Designation_IS spaced form)
- Piles: `PBP200X43.85`
- Duplicates append mass suffix (`WB200X28.8`)
"""
    GAPS.write_text(gaps)
    print(f"wrote {OUT} rows={len(rows)} errors={len(errors)}")
    print("by type:", by)
    if errors[:12]:
        print("sample errors:", *errors[:12], sep="\n  ")


if __name__ == "__main__":
    main()
