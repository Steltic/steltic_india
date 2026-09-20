# COMPOSITE_INDIA.md - composite floors on India (IS) jobs (WP2.9, review HR800-14)

**Basis.** IS 800:2007 has **no composite chapter** (Sections 1-17 and Annexes A-G; "composite" appears only
in the 4.x tie provisions and the Annex C vibration note). Composite steel-concrete beams in India are designed
to **IS 11384** (composite construction in structural steel and concrete). IS 11384 is **not in the India
corpus**, so every composite capacity is `found:false`. IS 800 has no composite chapter to cite, and the AISC 360
composite provisions are not an Indian design basis (decision D3) - do not use them.

## Allowed scopes (declare one in `cfg["composite_scope"]`)
1. **`bare_steel`** - design every floor beam as a **bare steel** member to IS 800:2007:
   - strength: 8.2.1.2 (laterally supported, deck fastened to the top flange for sagging) and 8.2.2 LTB with
     the real unbraced length of the compression flange for each moment sign (`india_is800.ltb_moment_capacity`);
   - **construction stage**: wet concrete + deck + construction load on the unshored bare beam, checked with
     8.2.2 using the pre-hardening restraint (bridging / deck fastening as actually provided), plus the
     wet-concrete deflection (camber decision recorded, even "none");
   - serviceability: IS 800:2007 Table 6 limits on the bare-steel second moment of area.
   The composite action is then an unclaimed reserve; the report states that composite action is not relied on.
2. **`delegated`** - the composite design is delegated to a named designer working to IS 11384; the package
   records the delegation, the loads handed over and the interface forces. Status stays `PARTIAL` until the
   delegated design is attached.

Without a declared scope the composite worksheet stays `found:false` and blocks COMPLETE
(`india_is800.h6_h7_residual_status`, `india_is800.composite_is11384_worksheet_stubs`).

## Never
- invent stud counts, stud strengths, effective widths, degree of shear connection or camber;
- cite "IS 800 Ch. I", "I3.1a", "I3.2a", "I8.2a" or AISC design examples on an India job;
- use psf / kip / inch values.
