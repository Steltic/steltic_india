#!/usr/bin/env python3
"""Build steel_engine/is808_shapes.csv from IS 808:2021 pdftotext -layout extract.

Source of truth: /workspace/INDIA_STEEL/pdfs/IS_808_2021.pdf (Tables 1–5 I/column sections).
Channels (Tables 6–8), angles (9–12), piles (13) are documented as GAPS — OCR/layout
differs enough that they are not auto-ingested in this pass.

Units in CSV match the existing pipeline (kip+inch), converted from IS 808 SI tabulated
multipliers. SI source values are retained in *_si columns for audit.
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
DEFAULT_TXT = Path("/tmp/is808/tables.txt")

# IS 808 tabulated multipliers → SI base, then → inch
MM = 1.0 / 25.4
MM2 = MM * MM
MM3 = MM2 * MM
MM4 = MM3 * MM
MM6 = MM4 * MM2

# A is ×10² mm²; Izz/Iyy/It ×10⁴ mm⁴; Z ×10³ mm³; Iw ×10⁶ mm⁶; rx/ry/d/bf/tw/tf in mm
def A_in2(a_x1e2): return a_x1e2 * 1e2 * MM2
def I_in4(i_x1e4): return i_x1e4 * 1e4 * MM4
def Z_in3(z_x1e3): return z_x1e3 * 1e3 * MM3
def Iw_in6(iw_x1e6): return iw_x1e6 * 1e6 * MM6
def mm_to_in(v): return v * MM

def parse_nums(s: str) -> list[float]:
    """Parse numbers; join single-space thousands groups (1 260, 1 550 000) only.
    Multi-space gaps are field separators and must NOT be joined."""
    out = []
    for m in re.finditer(r"\d{1,3}(?: \d{3})+(?:\.\d+)?|\d+\.\d+|\d+", s):
        tok = m.group(0).replace(" ", "")
        try:
            out.append(float(tok))
        except ValueError:
            pass
    return out

# Simple I-beam families: MB/WB/JB/LB/HB/SC (+ optional *)
SIMPLE_RE = re.compile(
    r"^\s*(MB|WB|JB|LB|HB|SC)\s+(\d+)\*?\s+(.*)$", re.I
)
# Parallel flange: NPB/WPB/PBP  D X B X   mass ...
PF_RE = re.compile(
    r"^\s*(NPB|WPB|PBP)\s+(\d+)\s*X\s*(\d+)\s*X\s+(.*)$", re.I
)

# Track which table we are in
TABLE_RE = re.compile(r"Table\s+(\d+)\b", re.I)

I_FAMILIES = {"MB", "WB", "JB", "LB", "HB", "SC", "NPB", "WPB"}  # I-sections for Tables 1-5
# Table 13 piles also I-like but deferred with NPB/WPB parser if we see them under T13

def make_label(family, parts, mass) -> str:
    fam = family.upper()
    if fam in ("NPB", "WPB", "PBP"):
        d, b = parts
        # mass to 2 decimals if needed
        m = f"{mass:.2f}".rstrip("0").rstrip(".") if abs(mass - round(mass)) > 1e-9 else str(int(round(mass))) if abs(mass - round(mass)) < 1e-9 and mass >= 10 else f"{mass:.2f}".rstrip("0").rstrip(".")
        # Prefer always 2-decimal-ish mass for uniqueness
        m = f"{mass:.2f}".rstrip("0").rstrip(".")
        return f"{fam}{int(d)}X{int(b)}X{m}".upper()
    d = parts[0]
    base = f"{fam}{int(d)}"
    return base.upper()


def row_from_nums(family, label_parts, nums, table_no, raw_desig):
    """nums: [M, A, D, B, t, T, alpha, R1, R2, Izz, Iyy, rz, ry, Zzz, Zyy, Zpz, Zpy, It, Iw]"""
    if len(nums) < 19:
        return None, f"short_fields n={len(nums)} desig={raw_desig!r}"
    M, A, D, B, t, T, alpha, R1, R2, Izz, Iyy, rz, ry, Zzz, Zyy, Zpz, Zpy, It, Iw = nums[:19]
    # Sanity: D should be ~depth in mm (50..1200), A positive
    if not (40 <= D <= 1500) or A <= 0 or Izz <= 0:
        return None, f"sanity_fail D={D} A={A} Izz={Izz} desig={raw_desig!r}"
    label = make_label(family, label_parts, M)
    # Disambiguate duplicate simple labels (e.g. two WB200) by appending mass
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
    ho = d - tf  # approx; IS uses more precise
    # rts ≈ sqrt(sqrt(Iy*Cw)/Sx) when Sx>0
    rts = math.sqrt(math.sqrt(Iy * Cw) / Sx) if Sx and Iy and Cw else ""
    typ = family.upper()
    row = {
        "AISC_Manual_Label": label,  # pipeline-compatible key name
        "Label": label,
        "Designation_IS": raw_desig.strip(),
        "Type": typ,
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
    return row, None


def parse(text: str):
    rows = []
    errors = []
    table_no = None
    seen = {}  # label -> count for disambiguation
    for line in text.splitlines():
        mt = TABLE_RE.search(line)
        if mt and "Concluded" not in line and "Continued" not in line:
            # Prefer the first Table N on a title line
            try:
                table_no = int(mt.group(1))
            except ValueError:
                pass
        # Only ingest Tables 1-5 (I / column) in this pass
        if table_no is not None and table_no > 5:
            continue

        m = PF_RE.match(line)
        if m:
            fam, d, b, rest = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
            nums = parse_nums(rest)
            raw = f"{fam} {d} X {b} X {nums[0] if nums else '?'}"
            row, err = row_from_nums(fam, (d, b), nums, table_no, raw)
            if err:
                errors.append(err)
                continue
            lab = row["Label"]
            if lab in seen:
                seen[lab] += 1
                # should be unique via mass; if collision, append suffix
                row["Label"] = f"{lab}_{seen[lab]}"
                row["AISC_Manual_Label"] = row["Label"]
            else:
                seen[lab] = 1
            rows.append(row)
            continue

        m = SIMPLE_RE.match(line)
        if m:
            fam, d, rest = m.group(1), int(m.group(2)), m.group(3)
            nums = parse_nums(rest)
            raw = f"{fam} {d}"
            row, err = row_from_nums(fam, (d,), nums, table_no, raw)
            if err:
                errors.append(err)
                continue
            lab = row["Label"]
            if lab in seen:
                # duplicate designation (e.g. WB200 twice) — append mass
                mkg = row["Mass_kg_m"]
                lab2 = f"{lab}X{mkg:.2f}".rstrip("0").rstrip(".")
                row["Label"] = lab2
                row["AISC_Manual_Label"] = lab2
                seen[lab2] = 1
            else:
                seen[lab] = 1
            rows.append(row)
            continue
    return rows, errors


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TXT
    if not src.exists():
        print(f"missing extract {src}; run pdftotext first", file=sys.stderr)
        sys.exit(1)
    text = src.read_text(errors="replace")
    rows, errors = parse(text)
    # Sort by Type, then depth-ish
    rows.sort(key=lambda r: (r["Type"], r["d"], r["Mass_kg_m"]))
    fields = [
        "AISC_Manual_Label", "Label", "Designation_IS", "Type",
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
    gaps = f"""# IS 808 shapes database — gaps

**Built:** from IS 808:2021 Tables 1–5 via `pdftotext -layout` → `build_is808_shapes.py`
**Output:** `steel_engine/is808_shapes.csv` ({len(rows)} rows)
**Parse errors/skipped lines:** {len(errors)}

## Ingested
- Table 1: Medium / Wide flange beams (MB, WB)
- Table 2: Junior / Light beams (JB, LB)
- Table 3: Narrow parallel flange beams (NPB …×…×mass)
- Table 4: Wide parallel flange beams (WPB …×…×mass)
- Table 5: Column / heavy beam sections (SC, HB)

## NOT ingested this pass (found:false for auto-CSV)
- Tables 6–8: channels (JC, LC, MC, MPC) — layout/column count differs; TODO
- Tables 9–12: equal/unequal angles (ISA / ∠) — different property columns; TODO
- Table 13: bearing piles (PBP) — deferred with channels/angles
- Annex A/B formula-only custom sections — agent must compute via RAG, not invent

## Units
Pipeline still kip+inch. CSV properties are converted from IS 808 SI multipliers;
`A_si_mm2` / `Izz_si_mm4` / `Iyy_si_mm4` retain SI for audit. Full SI engine is a separate deferred item.

## Lookup labels
- `MB200`, `LB150`, `SC250`, …
- Duplicate designations (two `WB200`) become `WB200X28.8` / `WB200X52.09` (mass suffix)
- Parallel flange: `NPB100X55X8.1`, `WPB600X300X128.79`
"""
    GAPS.write_text(gaps)
    print(f"wrote {OUT} rows={len(rows)} errors={len(errors)}")
    by = {}
    for r in rows:
        by[r["Type"]] = by.get(r["Type"], 0) + 1
    print("by type:", by)
    if errors[:8]:
        print("sample errors:", *errors[:8], sep="\n  ")


if __name__ == "__main__":
    main()
