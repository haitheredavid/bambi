# P1S design rules (0.4 mm nozzle)

- **Build volume:** 256 × 256 × 256 mm. Keep parts under about 250 mm.
- **Walls:** at least 0.8 mm (2 perimeters). Prefer 1.2 to 1.6 mm, or thicker for load-bearing parts.
- **Fits:** the clearance per side depends on the fit:

  | Fit | Clearance per side |
  |---|---|
  | Snug | 0.2 mm |
  | Sliding | 0.3 to 0.4 mm |
  | Glued loose tenon, PETG | 0.10 mm (witch-frame coupon) |

  Holes print about 0.1 to 0.2 mm undersize.
- **Overhangs and bridges:**
  - Overhangs up to 45° print without support. Bridges up to about 10 mm are fine.
  - Ledges anchored on one side sag past about 1 mm. Chamfer them at 45°.
  - Horizontal holes over 5 mm need a teardrop shape or a flat top.
  - Tunnels need a 45° gable roof, because a bridged roof droops 0.1 to 0.2 mm into the clearance.
- **Edges:** chamfer bottom edges 0.4 to 0.6 mm against elephant's foot; skip blade edges. Fillet stress corners.
- **Layer strength:** parts are weakest between layers, so orient them so the load isn't pulling layers apart.
  - The knife snapped at its neck. v2 got a tapered spine, fillets, 5 walls and 40% gyroid.
  - The cat mask prints upright so the strap tension runs along the layers.
- **Detail:**
  - Minimum feature about 0.4 mm. Raised detail at 0.4 mm or more and recesses at 0.5 to 0.6 mm read well; anything at the nozzle limit is "soft".
  - Text at least 0.6 mm deep and 5 mm tall.
- **Booleans:** EXACT booleans on coplanar faces leave non-manifold edges. Offset cutters 0.3 to 0.5 mm and triangulate with BEAUTY.
- **Infill:** large closed blocks print fine with few walls and low infill (half-step: 3 walls, 10%, 6 top layers). Lightning infill at 8% lets closed tops print without support (anubis-head).
