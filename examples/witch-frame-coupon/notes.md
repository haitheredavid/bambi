# Notes

## Intent
Tenon clearance coupon for blender-sessions' witch-frame (print pack `models/witch-frame/print/coupon`,
manifest 2026-10-11T09:43:22-04:00). Three coupons of the E seam, the thinnest tenon:
1 notch = 0.10 mm clearance per side, 2 = 0.15, 3 = 0.20. Each is two rail offcuts (A, B) and a tenon.

Same settings the frame will use: Insignia PETG (black, AMS slot 3), 0.16mm_optimal, Textured PEI.
`orient = false` keeps the pack's orientation (offcuts back face down so the gable-roofed mortise
prints without bridging; tenons on a side face).

`model.blend` is the pack's `parts.blend`, copied in unchanged.

## Iterations
1. **First print (supports off):** the offcuts' flat 3.7 mm ledge at z = 9 mm has nothing under it
   with the back face down, so it printed as sagging, blobbed strands. The mortise's gable roof (45°)
   was fine; only that flat ceiling failed.
2. **Fix: supports on, build plate only.** `[slice.overrides]` sets `enable_support = 1`,
   `support_type = "normal(auto)"`, `support_on_build_plate_only = 1`, `support_top_z_distance = 0.2`
   (0.2 rather than the profile's 0.16 so PETG releases). Resliced: 54 min / 18.1 g (was 49 min / 15.8 g).
   The gcode has supports on all 6 offcuts from z 0.2 to 8.84 (the ledge at 9 minus the 0.2 gap) and
   none on the tenons. Confirmed in Bambu Studio: supports sit under the ledge.
   - **The frame needs the same:** each corner piece in the frame pack has about 970 mm² of this flat
     ceiling at z = 9, plus about 375 mm² at z = 4, so the frame's bambi session needs these overrides. The other fix is a 45° chamfer under the ledge in
     blender-sessions' witch-frame builder, which makes it self-supporting.
3. **Round 2: flat vs chamfered lip, at 0.10 only.** 0.10 (1 notch) had the best fit, so the pack now
   has two 0.10 coupons (pack manifest 2026-10-11T12:20:21-04:00; `model.blend` replaced by its
   `parts.blend`). `C10_Flat` has the lip as the frame has it. `C10_Chamfer` fills the rabbet corner
   under the 3.675 mm lip with a 45° wedge, so it has no flat ceiling. Same support overrides.
   Sliced: 39 min / 11.4 g. Supports only under Flat_A/B (z 0.2-8.8); none on Chamfer_A/B or the
   tenons. Compare the two lip undersides. The full wedge also takes the glazing's seat, so if
   Chamfer wins, the frame needs a deeper rabbet or a narrower wedge.
   **Result (2026-10-11):** both printed fine. User picked **Flat + supports** for the frame; no chamfer.

## Print results
Dry-fit each tenon into both offcuts of its coupon. Pick the tightest that slides in by hand with no
force (it needs glue room), then set `TENON_CLEAR` in blender-sessions'
`models/witch-frame/builders/joinery.py` and rebuild before packing the frame.
