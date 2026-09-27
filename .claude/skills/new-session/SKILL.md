---
name: new-session
description: Start a new 3D-print worksession in bambi. Plans the part first (intent, dimensions, material, printability), then on approval creates the session, models it in Blender via MCP, and slices it for the P1S. Use when the user says "new session", "new print", "let's make/print a <thing>", or invokes /new-session <idea>.
argument-hint: <what to make>
---

# New print session

The user wants to design and print something: $ARGUMENTS

Work in two stages: **plan** (no files touched), then **build** once the plan is approved.

## Stage 1: Plan

1. Call `EnterPlanMode` straight away.
2. Look for related work: run `just ls` and read the `notes.md` of any sessions with a similar name. Reuse dimensions and lessons learned, such as a fit that was too tight last time.
3. Fill in what's missing with **one** `AskUserQuestion` round. Only ask about what the request leaves open and what changes the design:
   - **Purpose and fit.** What does it attach to or hold? Get critical dimensions in mm, or ask the user to measure them.
   - **Material.** PLA Basic is the default. Use PETG HF for heat, outdoor use or flex.
   - **Colours (AMS).** Single colour unless asked. For multi-colour, plan one Blender object per colour and fill `[[filaments]]` + `[objects]` in `session.toml`; each colour swap adds flush waste and time. Run `uv run bambi printer ams` (read-only) to see what's loaded, and `bambi printer ams <session> --write --slots ...` to fill `[[filaments]]` from it.
   - **Size and strength.** Load-bearing or cosmetic? Any size limit?
4. Write the plan with these sections:
   - **Session name.** A short kebab-case slug; the folder becomes `sessions/YYYY-MM-DD-<slug>/`.
   - **Intent.** One or two sentences for `session.toml` `intent`.
   - **Geometry.** Each object with its key dimensions in mm, and how it will be built in Blender (primitives, booleans, bevels, modifiers). Name the objects; each visible mesh exports as its own STL.
   - **Printability.** Print orientation and why (layer lines run across the load path), overhangs over 45°, supports yes/no, bridges, bottom-edge chamfer.
   - **Slice settings.** `process`, `filament`, `plate` (see `just profiles`). Say whether a new profile is needed.
   - **Verification.** The expected result of `just check` and the rough print time and grams.
5. Call `ExitPlanMode`.

### P1S design rules (0.4 mm nozzle)
- Build volume 256 × 256 × 256 mm; keep parts under about 250 mm.
- Walls at least 0.8 mm (2 perimeters). Prefer 1.2 to 1.6 mm, or thicker for load-bearing parts.
- Clearance for parts that fit together: 0.2 mm per side for a snug fit, 0.3 to 0.4 mm for a sliding fit. Holes print about 0.1 to 0.2 mm undersize.
- Overhangs up to 45° print without support. Bridges up to about 10 mm are fine. Use a teardrop shape or a flat top for horizontal holes over 5 mm.
- Chamfer bottom edges by about 0.4 to 0.6 mm to hide elephant's foot. Fillet stress corners.
- Parts are weakest between layers; orient so the load isn't pulling layers apart.
- Minimum feature size is about 0.4 mm. Minimum embossed or engraved text is about 0.6 mm deep and 5 mm tall.

## Stage 2: Build (after approval)

1. `just new <slug>` creates the session and opens `model.blend` in Blender. The MCP bridge starts on its own; wait a few seconds for port 9876.
2. Fill in `session.toml` (`intent`, and `[slice]` if not the defaults) and the Intent section of `notes.md`.
3. Model through the `mcp__blender__*` tools:
   - Call `get_scene_info` first.
   - Build in small `execute_blender_code` steps. **1 Blender unit = 1 mm**, Z up, bed at z=0.
   - Name objects as planned. Hide helper or cutter objects, or delete them after the boolean is applied.
   - Check progress with `get_viewport_screenshot`.
   - Save with `bpy.ops.wm.save_mainfile()` before any `just` command, which reads the file from disk.
4. Run `just build <slug>`: export, then check, then slice.
   - If the checks fail (non-manifold, below the bed, wrong scale), fix the model in Blender and run it again.
   - If slicing fails, read the error; for example, a filament/plate mismatch means changing `--plate` or `--filament`.
5. Report back: a screenshot, dimensions, the check results, print time and grams from the slice, and the output file.
6. Add a line under Iterations in `notes.md` covering what was built and any compromises.
7. Stop there. Offer `just upload <slug>` or `just print <slug>`, but **never start a print without the user's explicit go-ahead in this conversation**.
