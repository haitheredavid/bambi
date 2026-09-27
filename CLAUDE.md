# bambi

Sandbox for designing in Blender, slicing with Bambu Studio, and printing on a Bambu Lab P1S (LAN mode, or Bambu Cloud via the Studio GUI).

## Layout
- `src/bambi/`: the `bambi` CLI (typer). Host-side Python 3.13.
- `blender_scripts/`: run **inside** Blender (`blender -b file.blend -P script.py -- --result out.json ...`). bpy/bmesh only; never import `bambi` here. Each script takes `--result` and writes JSON there.
- `profiles/{machine,process,filament}/*.json`: flattened Bambu Studio profiles. Regenerate with `bambi profiles sync --overwrite`; tune by editing the JSON (the slicer CLI needs fully resolved files, so no `inherits`).
- `sessions/YYYY-MM-DD-<name>/`: one per modeling project. `model.blend` (source), `session.toml` (slice/print settings), `notes.md`, `exports/` (STL), `out/` (sliced `.gcode.3mf`, gitignored). `thumb.png` (plate preview from the sliced 3mf, written on every slice) and `render.png` (`bambi render`) are committed; each slice/render turns the best one into a uniform card in `docs/gallery/<session>.png` and rewrites the README gallery grid (between `<!-- gallery:start/end -->`).

## Conventions
- **Units: 1 Blender unit = 1 mm.** `bambi new` creates `model.blend` with unit scale 0.001 / millimetres. Model at real size in mm; the STL exporter writes raw units.
- Z is up and the bed is z=0. `bambi blender orient <session>` drops objects onto the bed.
- P1S build volume: 256 x 256 x 256 mm.
- Build plate defaults to Textured PEI (`plate` in `session.toml` or `--plate`). Bambu rejects some filament/plate pairs, e.g. PETG on the Cool Plate.
- Only visible mesh objects are exported. Hide helper/reference geometry.
- Multi-colour (AMS) is per object: split a multi-colour part into separate objects, list `[[filaments]]` in `session.toml` and map exported STL names to filament numbers in `[objects]`. Multi-colour slices go through `--load-assemble-list` (Bambu ignores `--load-filament-ids`), so no auto-orient. `bambi printer ams <s> --write` fills `[[filaments]]` from what's loaded in the AMS (tray material codes resolve to Bambu Studio profiles, flattened into `profiles/filament/` on first use); `slice/build --ams` fills profile-less entries at slice time; `printer send` refuses when a tray's material doesn't match.

## Starting a new print
Use the `/new-session <idea>` skill (`.claude/skills/new-session/`): plan first, then create the session, model it via MCP, and slice.

## Working live through blender-mcp
1. `uv run bambi blender open <session>` opens the session's `model.blend`; the add-on's MCP bridge auto-starts on port 9876.
2. Use the `mcp__blender__*` tools (call `get_scene_info` first). Save with `bpy.ops.wm.save_mainfile()` so the headless pipeline sees the changes.
3. `uv run bambi build <session>` = export, then check, then slice.

## CLI
`just` wraps the common commands (`just` lists them: `just new/build/slice/status/print ...`). The full CLI:
```
bambi new <name>            bambi ls
bambi export <s>            bambi check <s>        bambi slice <s> [--process --filament --ams]
bambi build <s>             bambi studio <s>       bambi blender open|orient <s>
bambi render <s> [--scene]  bambi gallery
bambi profiles sync|ls|search <kind> <text>
bambi printer status        bambi printer ams [<s> --write [--slots 2,0] [-y]]
bambi printer send <s> [--start] [--plate N] [--ams-slot N (single colour)] [--force] [-y]
```

## Printing: cloud vs LAN
- **Cloud (hybrid):** `bambi studio <s>` / `just studio <s>` opens the sliced `.gcode.3mf` in Bambu Studio; the user sends it with Print plate via Bambu Cloud. No `.env` needed.
- **LAN:** `bambi printer status|send` talk to the printer directly (MQTT/FTPS). Needs `.env`, and on newer firmware LAN-only mode + Developer Mode for `send --start`.

## Safety
- `printer send --start` starts a physical print. Always confirm with the user before running it, even with `-y`.
- `printer status` and `printer ams` (without `--write`) are read-only.
- `.env` holds the printer access code. Never commit it or print it.

## Dev
`just ci` (ruff + pytest), `just fmt`
