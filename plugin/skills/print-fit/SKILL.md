---
name: print-fit
description: Make parts fit the P1S bed and each other. Plan splits and seams, pick joints (filament dowels, keyed tabs, pegs, loose tenons, magnets, screws, glue faces) with clearances, design clearance coupons, and log which coupon won so the value flows back into the model. Use for "too big for the bed", "split this", "how do these join", "what clearance", "print a test coupon", "coupon 2 fits best", or when /bambi:print routes rows B or G here.
argument-hint: <workspace or model> [question]
---

# Fit: splitting, joinery, coupons

Target: $ARGUMENTS

Read `${CLAUDE_PLUGIN_ROOT}/references/joinery-and-coupons.md` and `${CLAUDE_PLUGIN_ROOT}/references/p1s-rules.md`.

## Too big for the bed (row B)
1. From `bambi plan <ws> --json`, get each oversized part's size.
2. Propose seams that land in thick sections, each piece ≤ 250 mm. Seams should also give a flat joint face to print on.
3. Pick a joint per seam from the catalogue. Before choosing a recessed joint, check the wall around it: it needs ≥ 2 mm.
4. **Geometry happens in the model:**
   - **blender-sessions:** follow `workflows/print-fit-and-sectioning.md`. Use `section_piece` for live sections and fitted loose tenons, and put the pieces in the Print collection. Record joints on each part as `obj["joints"] = json.dumps([...])` so the spec carries them.
   - **Native bambi session:** blender-mcp. Split into separately named objects and boolean the joint features (cutters offset 0.3–0.5 mm, then hidden).
5. Write the assembly order: in `[print] assembly` upstream, or in the session's `notes.md`.

## Clearances and coupons (row G)
- **Untested clearance on a long print:** propose a coupon of the worst joint at 2–3 clearances (for example 0.10, 0.15, 0.20 per side), notched 1, 2, 3.
  - **Upstream:** a `Coupon` collection, `[print.Coupon]`, and `[[print.coupon]]` with id, param, values, parts and rule. Then `blend print-pack <m> --collection Coupon`, `bambi init models/<m>/print/coupon`, and `/bambi:print-run`.
- **When the user reports which coupon won:**
  `bambi log fit <ws> --coupon <id> --value <v> --note "<what they felt>"`.
  This logs the fit and recommends `param = v` upstream. Then go to `/bambi:print-log` to apply it.
- **Without a coupon**, use the catalogue clearances and say they're untested.
