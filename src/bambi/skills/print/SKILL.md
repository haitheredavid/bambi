---
name: print
description: Get a model ready to print on the Bambu Lab P1S and route each open issue to the right fix. Triage a bambi session, a blender-sessions model (models/<m>/) or a print pack, show a readiness table (validity, bed fit, orientation, supports, detail, adhesion, assembly, colour, material, provenance), and refuse to slice while anything blocks. Use when the user says "get X ready to print", "is this printable", "print models/<m>", "prep this for the P1S", or invokes the `print` skill.
argument-hint: <session | models/<m> | path to a print pack>
---

# Print readiness

Target: the workspace the user named ($ARGUMENTS)

This needs the `bambi` CLI on PATH (the Claude plugin adds it; otherwise `uv tool install git+https://github.com/haitheredavid/bambi` or `npx @notrealarchitecture/bambi`). Run `bambi doctor` if a command is missing. It does the measuring; you do the judging.

## 1. Find the workspace
- **A bambi session name** (`witch-frame-coupon`): use it as-is.
- **A blender-sessions model folder** (`models/<m>`): `bambi` reads `models/<m>/print/`. For another pack, use its path (`models/<m>/print/coupon`).
  - If there's no pack yet, the model needs `blend print-pack <m>` first. Run it only if the user is in blender-sessions and the model has a Print collection; otherwise ask.
  - If the pack has no `session.toml`, run `bambi init <pack>`. Use `--process 0.16mm_optimal` for fine detail and the default `0.20mm_standard` otherwise.
  - When the spec changed, run `bambi init --force`. It rewrites `session.toml` but keeps `results.json`.

## 2. Triage
Run `bambi plan <ws> --json`. For each `needs[]` row, read its `status` and `next`. `check` holds the full per-part report.

Show the user one compact table: need, status, and one line of detail. Then group what's open:

| Status | Meaning | Handling |
|---|---|---|
| block | The print would fail or slicing would refuse | Resolve before slicing |
| todo | Not done yet (coupon not fitted, not sliced) | Usually do now |
| warn | Prints, with a cost or risk | Explain it and let the user decide |

Run `bambi docs readiness-taxonomy` and read it the first time, and whenever a row is unclear.

## 3. Route

| Row | Go to |
|---|---|
| A valid meshes | Fix the model (blender-mcp, or the modelling repo); cutters/triangulation hints are in the row |
| B fit, G assembly | the `print-fit` skill |
| C orientation, D supports, F adhesion | the `print-orient` skill |
| E detail | Thicken in the model, or accept tapers (they print rounded) |
| H colour | the `print-colour` skill |
| I material/process | Edit `[slice]` in `session.toml` (packs: bambi owns it) |
| J provenance | the `print-log` skill |

**Where fixes go:**
- **Packs** (`kind = "pack"`): the geometry and intent belong to the modelling repo. Either make the change there yourself (in blender-sessions: edit `model.toml` `[[print.part]]` or the builder, re-pack, then `bambi init --force`), or record it with `bambi log rec`. Never edit `stl/`, `parts.blend` or `manifest.json`.
- **Native sessions:** fix `model.blend` through blender-mcp, save, and run `bambi build`.

## 4. Slice
- When nothing blocks, hand off to the `print-run` skill, which runs `bambi build <ws> --strict`.
- Warnings are fine to slice with once the user knows about them.
- If the user insists on slicing over a block (for example to inspect it in Bambu Studio), use `bambi slice` and say clearly that it will likely fail.

## Rules
- Units are mm and Z is up. The bed is z=0, 256³.
- Never start a print. Printing is the `print-run` skill, and it needs the user's explicit go-ahead in this conversation.
