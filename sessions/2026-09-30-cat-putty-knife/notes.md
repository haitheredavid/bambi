# Notes

## Intent
6" (150 mm) putty knife for spreading joint compound on medium apartment wall patches. Printed flat in PLA Basic: blade tapers 3 mm -> 1 mm edge, 100 mm handle, cat head with ears at the butt and blue silk eyes inlaid flush in the top face (2-colour AMS). Body orange PLA Basic (slot 3), eyes blue PLA Silk (slot 0).

## Iterations
- v1 (2026-09-30): `Knife` 236.5 x 150 x 16 mm (convex-hull parts unioned: blade 150->40 wide, 75 long, 3->1 mm top-side taper, R3 edge corners; neck ramp; 100 mm handle 28x16 w/ R5 top; Ø44 head w/ ears at ±40°, 14 thick; 0.4 bottom chamfer except blade; engraved nose 0.6 deep). `Eyes` 2x 6x9 mm ellipses, 1 mm inlay flush with head top. Floating eyes failed slicing as a separate object ("empty layer between 0 and 15.2"), so added `[slice] assemble = true` (assemble_index merges STLs into one object). Slice: 1h 15m, 47.5 g (46.3 white + 1.2 blue, 5 colour changes w/ prime tower), 0.20mm_standard, Textured PEI. Compromises: blade edge 1 mm PLA, no bottom chamfer on blade; slot 2 must hold white PLA Basic (currently Support for PLA).
- v1b (2026-09-30): body switched to orange PLA Basic (slot 3); slot 2 white is Bambu Support for PLA (GFS02 via RFID), unsuitable as body and PLA eyes would not bond to it.

## Print results
