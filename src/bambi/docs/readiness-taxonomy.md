# What makes a model ready to print

`bambi plan <ws>` gives one row per need below:
- a status: `ok`, `info`, `todo`, `warn` or `block`
- the next step

**Block** rows stop `bambi build --strict`. Each need cites the session that taught it, so the reasoning stays checkable.

| | Need | Detected by | Usual fix | Skill |
|---|---|---|---|---|
| A | **Valid meshes**: watertight, consistent winding, no degenerate faces, mm scale, no overlapping shells | `bambi check` (Blender scene plus trimesh) | Offset boolean cutters 0.3–0.5 mm off coplanar faces. Triangulate with BEAUTY, not EAR_CLIP (colossus). Union overlapping shells. | model |
| B | **Fits the bed**: 256 × 256 × 256, under 250 mm to be safe | check | Split into sections with joints | print-fit |
| C | **Orientation**: layers across the load, show face up or on the plate, joint faces flat, low height | `bambi orient` | Model the part in print orientation. Keep `orient = false`: Bambu's auto-orient stood the half-step on end. | print-orient |
| D | **Support**: overhangs over 45°, flat ceilings and ledges, bridges over 10 mm, islands that start in mid-air | `bambi check` (layer analysis) | A 45° chamfer under ledges (witch-frame lip), gable roofs over tunnels (witch-frame mortise), teardrop holes, tabs instead of pegs (colossus). Otherwise supports via `[slice.overrides]`: build-plate only, scars on hidden faces (anubis-gold). | print-orient |
| E | **Printable detail**: walls ≥ 0.8 mm, features ≥ 0.4 mm, text ≥ 0.6 deep and 5 tall | check (thin bands) | Thicken, or leave it to paint (colossus engraving). Tapers to a top edge print rounded, which is cosmetic. | model |
| F | **Bed adhesion**: first-layer contact, height ÷ √contact | check | Brim (mask: 5 mm), reorient, chamfer the bottom edges 0.4–0.6 mm to stop elephant's foot | print-orient |
| G | **Assembly**: seams, joint type, clearance, hardware, coupons | spec joints/coupons, results | Pick joints from `joinery-and-coupons.md`. Print a clearance coupon in the real material first (witch-frame: 0.10 won in PETG). | print-fit |
| H | **Colour**: single, AMS bands, AMS inlay, glue-in, paint, engrave | `bambi colour` | Inlays over a tall Z span cost hundreds of swaps (anubis-head: 690 swaps, 18h30 vs 3h06 as glue-in). Floating colour parts need `assemble = true` (putty knife). | print-colour |
| I | **Material + process**: plate pairing, profile, overrides | plan, slice | PETG not on the Cool Plate. `brim_type` is missing from the flattened profiles but allowlisted as an override. Strength comes from walls and infill (knife: 5 walls, 40% gyroid after it snapped). | print-run |
| J | **Provenance**: stale slice, unapplied recommendations, print results logged | results.json vs spec | Re-pack and re-slice. Log every print, because most sessions have empty "Print results". | print-log |

## Reading the layer analysis
- **flat ceiling**: unsupported area in one layer.
  - **ledge** (cantilever): anchored on one side. It sags past about 1 mm; the witch-frame 3.7 mm PETG lip drooped.
  - **bridge**: anchored on two or more sides. Up to 10 mm is fine.
- **shallow overhang**: the part steps out more than a line width per layer over several layers. It needs support, or a steeper angle.
- **overhang band**: a slope just past 45°. Usually prints with some droop. It's a warning, not a block.
- **island**: a region that starts in mid-air. It always needs support or a redesign.

Supports on (`enable_support` in the process or overrides) downgrade ceilings, ledges and islands to warnings. The question then becomes where the scars land.

## Order of attack
1. A and B (the geometry is wrong or too big).
2. C, D, E and F together (orientation decides support, adhesion and often strength).
3. G (fit before committing a long print: coupon first).
4. H (colour can change the parts list).
5. I, then slice.
6. J after every print.
