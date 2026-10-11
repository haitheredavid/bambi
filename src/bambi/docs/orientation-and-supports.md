# Orientation and supports

## Choosing an orientation
`bambi orient <ws> [--part X]` ranks candidates for each part:
- as modelled
- the six axis rotations
- each large flat face laid on the bed

The score combines three things:
- the bed-projected area that would need support, minus the bridges the printer spans
- print height, as a proxy for time
- a penalty for too little bed contact

The best few candidates get the full layer analysis.

The score leaves out two things only you can judge. Weigh them first:
1. **Load path.** Layers should run across the load, never pulling apart along it. Examples: the cat mask prints upright for its strap, and the knife spine lies flat.
2. **The show face.** Supports and the bed both mark a face. Put marks on faces nobody sees:
   - anubis-gold trim prints with its glued face down;
   - the saddle prints upside down on its flat top.

Then use the ranking for the rest. Common good answers:
- **Joint face down.** Leg and head halves print with the cut face down; firebat arms print on the shoulder face.
- **Upside down when the top is the flat face.** The colossus Core and the saddle both do this.
- **Laid on the largest face.** For loose tenons, keys and clips, use `flat = [...]` in the model's `[print]`.

## Applying it
- **Native bambi session:** run `bambi orient <s> --part X --apply N`. It rotates the object in `model.blend` and drops it to z=0; then run `bambi build`.
- **Print pack:** the orientation belongs upstream. Run `bambi log rec <ws> --target 'model.toml:[[print.part]] match=X rotate' --value '[90,0,0]' --reason ...`. The model adds a `[[print.part]]` entry and re-packs.

## Supports
**Prefer to design them out:**

| Problem | Fix |
|---|---|
| Ledge or lip | 45° chamfer underneath (the witch-frame chamfered lip printed clean) |
| Tunnel or mortise | 45° gable roof |
| Horizontal hole | Teardrop shape, or a flat top |
| Underside of a jaw or belly | Slope it at 45° (anubis-head, firebat) |
| Hex emitter | Rotate it vertex-down (colossus) |
| Round peg that would float | Full-height tab (colossus) |
| Feature that would float | Flat-cut it on the joint plane |

**When supports stay,** set them per pack with intent: `supports = "build-plate"` in `[[print.part]]`, which bambi translates. For native sessions, use `[slice.overrides]`:
```toml
[slice.overrides]
enable_support = 1
support_type = "normal(auto)"        # tree(auto) for organic or hidden faces
support_on_build_plate_only = 1      # never land support on the part itself
support_top_z_distance = 0.2         # PETG: an easier release
```

When parts disagree, the strongest policy wins: one plate, one process. If one part needs supports everywhere and the rest need none, put it on its own plate or session.

**Bed adhesion:**
- Small contact or a tall, thin part needs a brim: `[slice.overrides] brim_type = "outer_only"` and `brim_width = 5`. `brim_type` is missing from the flattened profiles but allowlisted, and Bambu honours it.
- Chamfer bottom edges 0.4 to 0.6 mm.
