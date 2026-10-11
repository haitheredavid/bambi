---
name: print-orient
description: Decide how each part sits on the P1S bed and whether it needs supports. Rank orientations (support area, height, bed contact), weigh layer strength and the show face, pick a supports policy or a design fix (45° chamfers, gable roofs, teardrops), and fix adhesion with brims or chamfers. Use for "which way up", "does this need supports", "the ledge sagged", "it fell over / lifted", or when /bambi:print routes rows C, D or F here.
argument-hint: <workspace> [part]
---

# Orientation, supports, adhesion

Target: $ARGUMENTS

Read `${CLAUDE_PLUGIN_ROOT}/references/orientation-and-supports.md` and `${CLAUDE_PLUGIN_ROOT}/references/p1s-rules.md`.

1. **Ask what the score can't know**, unless it's already clear from the session's notes or spec `orientation.why`:
   - Where does the load go?
   - Which face is seen?
   - Which faces mate with other parts?
2. **Run `bambi orient <ws> [--part X]`**. Each candidate lists height, contact, the bed-projected support area, and its layer findings. Lower rank is better on geometry alone.
3. **Decide per part:**
   - If the top candidate respects load and show face, use it.
   - Otherwise take the best candidate that does, and design the remaining supports out:
     - 45° chamfer under ledges
     - gable roof over tunnels
     - teardrop holes
     - tabs instead of floating pegs
     - flat-cut features on the joint plane
   - Fall back to supports placed where the scars don't show:
     - packs: `supports = "build-plate"` in `[[print.part]]` upstream
     - sessions: `[slice.overrides]`
4. **Apply the decision:**
   - **Session:** run `bambi orient <s> --part X --apply N`. It rotates the part in `model.blend` and drops it on the bed. For design fixes, edit through blender-mcp and save.
   - **Pack:** change `[[print.part]]` (rotate, flat, supports) or the builder in the modelling repo and re-pack, or record it:
     `bambi log rec <ws> --target "model.toml:[[print.part]] match=X rotate" --value '[90,0,0]' --reason "..."`
5. **Adhesion.** Small contact or a tall, thin part needs either reorienting or bottom chamfers of 0.4–0.6 mm, plus a brim: `[slice.overrides] brim_type = "outer_only"`, `brim_width = 5`.
6. **Re-run `bambi plan <ws>`.** Rows C, D and F should be ok, or warn with a reason the user accepted.

Keep orientation out of Bambu's hands: `orient = false` (already the default for packs).
