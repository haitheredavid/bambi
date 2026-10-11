# bambi

Sandbox for designing in Blender, slicing with Bambu Studio, and printing on a Bambu Lab P1S (LAN mode, or Bambu Cloud via the Studio GUI). It is also the **`bambi` Claude Code plugin** (`plugin/`, marketplace in `.claude-plugin/`). Other repos load the plugin to get models print-ready, chiefly the sibling `blender-sessions` (`models/<m>/print/` packs).

## Layout
- `src/bambi/`: the `bambi` CLI (typer). Host-side Python 3.13.
  - `printability.py`: layer analysis with manifold3d slices and shapely outlines. Finds ceilings, ledges, bridges, islands, thin walls and bed contact.
  - `orientation.py`: ranks orientations.
  - `colour.py`: estimates AMS swaps.
  - `readiness.py`: `bambi plan` triage.
  - `spec.py` / `results.py`: the cross-repo contract.
- `plugin/`: the Claude Code plugin.
  - `skills/`: `print` (router), `print-orient`, `print-fit`, `print-colour`, `print-run`, `print-log`, `new-session`.
  - `references/`: taxonomy, P1S rules, contract docs.
  - `bin/bambi`: launcher. It runs this checkout via `uv run --project`.
  - `hooks/`: forces a prompt on `printer send --start`.
- `src/bambi/blender_scripts/`: run **inside** Blender (`blender -b file.blend -P script.py -- --result out.json ...`). bpy/bmesh only; never import `bambi` here. Each script takes `--result` and writes JSON there.
- `profiles/{machine,process,filament}/*.json`: flattened Bambu Studio profiles. Regenerate with `bambi profiles sync --overwrite`; tune by editing the JSON (the slicer CLI needs fully resolved files, so no `inherits`).
- `assets/studio.blend`: render studio (P1S textured PEI plate on a cyclorama, lights, camera at a fixed printer-front angle in scene props `bambi_azimuth`/`bambi_elevation`). `bambi render` appends it and centres the models on the plate. Tweak the look by editing it in Blender; `bambi render-scene --overwrite` rebuilds it from `src/bambi/blender_scripts/build_studio.py`.
- `sessions/YYYY-MM-DD-<name>/`: one per modeling project. `model.blend` (source), `session.toml` (slice/print settings), `notes.md`, `exports/` (STL), `out/` (sliced `.gcode.3mf`, gitignored). `results.json` (check/slice/print/fit runs and recommendations), `thumb.png` (plate preview from the sliced 3mf, written on every slice) and `render.png` (`bambi render`) are committed; each slice/render turns the best one into a uniform card in `docs/gallery/<session>.png` and rewrites the README gallery grid (between `<!-- gallery:start/end -->`).

## Conventions
- **Units: 1 Blender unit = 1 mm.** `bambi new` creates `model.blend` with unit scale 0.001 / millimetres. Model at real size in mm; the STL exporter writes raw units.
- Z is up and the bed is z=0. `bambi blender orient <session>` drops objects onto the bed.
- P1S build volume: 256 x 256 x 256 mm.
- Build plate defaults to Textured PEI (`plate` in `session.toml` or `--plate`). Bambu rejects some filament/plate pairs, e.g. PETG on the Cool Plate.
- Only visible mesh objects are exported. Hide helper/reference geometry.
- Multi-colour (AMS) is per object: split a multi-colour part into separate objects, list `[[filaments]]` in `session.toml` and map exported STL names to filament numbers in `[objects]`. Multi-colour slices go through `--load-assemble-list` (Bambu ignores `--load-filament-ids`), so no auto-orient. Parts that don't touch the bed (inlays) need `[slice] assemble = true`, which merges every object into one. `[slice.overrides]` sets individual process keys (e.g. `wall_loops = 5`) without a new profile. `bambi printer ams <s> --write` fills `[[filaments]]` from what's loaded in the AMS (tray material codes resolve to Bambu Studio profiles, flattened into `profiles/filament/` on first use); `slice/build --ams` fills profile-less entries at slice time; `printer send` refuses when a tray's material doesn't match.

## Workspaces
A workspace is any folder with a `session.toml`. Commands take a session name, or a path to either kind:
- **session**: `sessions/YYYY-MM-DD-<name>/`, modelled here in `model.blend`.
- **pack**: a print pack written upstream by `blend print-pack`: `parts.blend`, `stl/`, and `manifest.json` (the print spec). `bambi init <pack>` adds `session.toml` with `[paths] kind = "pack"` and translates the spec's intent (supports policy, filaments, assemble) into `[slice]`. A blender-sessions model folder `models/<m>` resolves to `models/<m>/print`.

bambi never edits a pack's own files (`export` and `blender orient` refuse). Changes go upstream as recommendations: `bambi log rec`, `log fit`, `log print --rec`. The modelling side applies them, records the ids in `[print] feedback_applied/declined`, and re-packs. The contract is in `plugin/references/print-spec.md` and `print-results.md`.

## Starting a new print
- **New thing:** `/bambi:new-session <idea>`. Plan, create the session, model it via MCP, then `/bambi:print`.
- **Existing model or pack:** `/bambi:print <ws>`. Runs `bambi plan` (readiness rows A to J), routes each open row to a sub-skill, then slices with `build --strict`.

## Working live through blender-mcp
1. `uv run bambi blender open <session>` opens the session's `model.blend`; the add-on's MCP bridge auto-starts on port 9876.
2. Use the `mcp__blender__*` tools (call `get_scene_info` first). Save with `bpy.ops.wm.save_mainfile()` so the headless pipeline sees the changes.
3. `uv run bambi build <session>` = export, then check, then slice.

## CLI
`just` wraps the common commands (`just` lists them: `just new/build/slice/status/print ...`). The full CLI:
```
bambi new <name>            bambi ls               bambi init <pack|models/m> [--pack x] [--force]
bambi plan <s> [--json]     bambi check <s> [--json --no-layers]
bambi orient <s> [--part X] [--apply N]            bambi colour <s>
bambi export <s>            bambi slice <s> [--process --filament --ams]
bambi build <s> [--strict]  bambi studio <s>       bambi blender open|orient <s>
bambi log print|fit|rec|show <s>
bambi render <s> [--framing fit|wide] [--scene]   bambi render-scene [--overwrite]
bambi gallery
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
`just ci` (ruff, pytest, plugin validation), `just fmt`. Run the plugin from the checkout with `claude --plugin-dir plugin`. Repos that enable `bambi@bambi` get `bambi` on PATH through `plugin/bin/bambi`.

Binaries (`*.blend`, `*.stl`, `*.png`, `*.3mf`) are in Git LFS (`.gitattributes`); fresh clones need `git lfs install`.
