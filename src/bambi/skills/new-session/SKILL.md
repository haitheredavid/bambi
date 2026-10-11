---
name: new-session
description: Start a new 3D-print worksession in bambi. Plans the part first (intent, dimensions, material, printability), then on approval creates the session, models it in Blender via MCP, and gets it print-ready and sliced for the P1S. Use when the user says "new session", "new print", "let's make/print a <thing>", or asks for the `new-session` skill with an idea. For models that live in blender-sessions, use that repo's /model skill and then the `print` skill instead.
argument-hint: <what to make>
---

# New print session

The user wants to design and print something: $ARGUMENTS

Work in two stages: **plan** first, touching no files, then **build** once the plan is approved. The design rules are in `bambi docs p1s-rules`; read them before planning.

## Stage 1: Plan

1. Switch to plan mode if your harness has one; either way, touch no files until the plan is approved.
2. Look for related work. Run `bambi ls`, then read the `notes.md` of any session with a similar name. Reuse dimensions and lessons, such as a fit that was too tight last time.
3. Ask **one** round of questions. Only ask about what the request leaves open and what changes the design:
   - **Purpose and fit.** What does it attach to or hold? Get the critical dimensions in mm, or ask the user to measure them.
   - **Material.** PLA Basic is the default. Use PETG HF for heat, outdoor use or flex.
   - **Colours.** Single colour unless the user asks. For more than one, see `bambi docs colour-strategy`: inlays over a tall Z span cost hundreds of swaps, so glue-in may be better. `bambi printer ams` (read-only) shows what's loaded.
   - **Size and strength.** Is it load-bearing or cosmetic? Any size limit?
4. Write the plan with these sections:
   - **Session name.** A short kebab-case slug. The folder becomes `sessions/YYYY-MM-DD-<slug>/` in the bambi workspace (`bambi ls` shows where).
   - **Intent.** One or two sentences for `intent` in `session.toml`.
   - **Geometry.** Each object, its key dimensions in mm, and how it will be built in Blender. Name the objects; each visible mesh exports as its own STL.
   - **Printability.** Cover each need in `bambi docs readiness-taxonomy` that applies:
     - orientation and why (layers across the load, show face)
     - supports, or how the design avoids them
     - splits and joints with clearances
     - colour strategy
     - bottom chamfer
   - **Slice settings.** `process`, `filament`, `plate` (see `bambi profiles ls`), and any `[slice.overrides]`.
   - **Verification.** What `bambi plan` should show, and the rough print time and grams.
5. Present the plan and wait for the user to approve it.

## Stage 2: Build (after approval)

1. Create the session and open its model:
   - Run `bambi new <slug>`, then `bambi blender open <slug>`. The MCP bridge starts by itself; wait a few seconds for port 9876.
   - Check that `bpy.data.filepath` is the new session's `model.blend` before modelling. Only one Blender owns the port.
2. Fill in `session.toml` (`intent`, `[slice]`) and the Intent section of `notes.md`.
3. Model through the Blender MCP tools (`get_scene_info`, `execute_blender_code`, `look`):
   - Call `get_scene_info` first.
   - Build in small `execute_blender_code` steps. **1 Blender unit = 1 mm**, Z up, bed at z=0.
   - Model each part in its print orientation.
   - Name objects as planned. Hide cutters, or delete them once the boolean is applied.
   - Check progress with screenshots or `look`.
   - Save with `bpy.ops.wm.save_mainfile()` before any `bambi` command; they read the file from disk.
4. Hand off to the `print` skill with `<slug>`. It runs the readiness triage, routes the fixes, and slices with `bambi build --strict`.
5. Report back:
   - a screenshot
   - the dimensions
   - the readiness table
   - time and grams
   - the output file
6. Add a line under Iterations in `notes.md`: what was built, and any compromises.
7. Stop there. Offer to print via the `print-run` skill, but **never start a print without the user's explicit go-ahead in this conversation**.
