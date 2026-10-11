# Splitting, joinery and coupons

## When to split
- **The part is bigger than the bed.** Cut it into sections, each ≤ 250 mm in XY and Z. Put the seams in thick sections; the mid-sides of a bowed frame are its thinnest point.
- **It removes supports.** Mirrored halves and a head cut on its centre plane each print cut-face down.
- **Colour.** Glue-in trim avoids hundreds of AMS swaps (see `colour-strategy.md`).
- **Orientation conflicts.** One region wants layers one way and another region wants them the other way.

Mark each seam as a thin plane in Work (blender-sessions) and assert that every piece's footprint fits the bed. `patterns.section_piece` keeps the pieces live against the source.

## Joint catalogue

| Joint | Geometry | Clearance | Good for | Seen in |
|---|---|---|---|---|
| Filament dowel | 1.75 mm filament in a Ø2.1 hole, 4–6 mm deep each side | built in | Alignment pins, many small parts | colossus (30), firebat |
| Keyed tab | Rectangular tab into a slot | 0.3 mm/side | Panels, directional fit | colossus |
| Peg | Round peg in a hole | Ø +0.2–0.4 | Heads and lids | anubis-head 4.9 mm pegs, saddle Ø5.2 holes |
| Loose tenon | Separate prism glued into mortises in both pieces, gable roof, edges chamfered 0.4 | 0.10–0.15 mm (coupon it) | Strong hidden seams in large frames | witch-frame |
| Magnet | Ø5.3 × 3.2 pocket for a 5 × 3 magnet | +0.3 Ø, +0.2 deep | Removable parts | — |
| Screw | Ø2.6 pilot for self-tapping M3, countersink, ≥ 3 mm skin | — | Clips, hardware | witch-frame turn clips |
| Glue face | Flat mating faces, optional pocket | — | Trim, inlays | anubis glue-in |

**Rules:**
- **Walls around a joint ≥ 2 mm (5 lines).** A recess in a narrow face leaves thin fins: butterfly keys in an 8 mm strip left 1.07 mm walls.
- **Horizontal tunnels get gable roofs,** not flat bridged roofs.
- **Chamfer the seam's back edge 0.4 mm** so first-layer squish can't hold the seam open.
- **Booleans:** keep cutter vertices off section planes, and use odd segment counts.
- **Document assembly order** in `[print] assembly`.

## Clearance coupons
Print the worst case before committing a long print: the thinnest tenon, the tightest hole. Do it in the real material and process.

1. Cut a short section of the worst seam, once per candidate clearance (for example 0.10, 0.15 and 0.20). Mark the pieces with 1, 2 or 3 notches.
2. Keep the coupons in their own collection and pack them separately:
   - Run `blend print-pack <m> --collection Coupon`.
   - Declare `[[print.coupon]] id/param/values/parts/rule` so bambi knows what the coupon decides.
3. Slice and print them. They take minutes, not hours.
4. Pick the winner by the rule, for example "the tightest that slides in by hand, with glue room".
5. Record it with `bambi log fit <ws> --coupon tenon-E --value 0.10`. This logs the fit and recommends `param = value` upstream.
6. Upstream, set the parameter (`TENON_CLEAR`), add the recommendation id to `[print] feedback_applied`, and re-pack.

Coupons also settle other questions:
- flat vs chamfered lip (witch-frame round 2)
- colour or geometry tests (flip-coupon)
- detail resolution (door-sampler)
