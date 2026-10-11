# bambi

Toolchain for getting Blender models printed on a Bambu Lab P1S: printability checks, orientation, splitting, colour, Bambu Studio slicing, and printing (LAN, or Bambu Cloud via the Studio GUI). It ships as the `bambi` CLI plus a set of agent skills for Claude Code (plugin + marketplace in `.claude-plugin/`), Codex and opencode. Other repos load the skills to get models print-ready, chiefly the sibling `blender-sessions` (`models/<m>/print/` packs). Without blender-sessions, bambi still runs the whole loop itself: `new-session` models in Blender over MCP, then slices and prints.

## Layout
- `src/bambi/`: the `bambi` CLI (typer). Host-side Python 3.13.
  - `printability.py`: layer analysis with manifold3d slices and shapely outlines. Finds ceilings, ledges, bridges, islands, thin walls and bed contact.
  - `orientation.py`: ranks orientations.
  - `colour.py`: estimates AMS swaps.
  - `readiness.py`: `bambi plan` triage.
  - `spec.py` / `results.py`: the cross-repo contract.
  - `skills/`: **the canonical skills** (Agent Skills format): `print` (router), `print-orient`, `print-fit`, `print-colour`, `print-run`, `print-log`, `new-session`. Keep them harness-neutral: no `${CLAUDE_PLUGIN_ROOT}`, `/bambi:` names or Claude tool ids (`tests/test_skills.py` enforces it). Point at reference docs with `bambi docs <topic>`.
  - `docs/`: reference docs (taxonomy, P1S rules, contract), printed by `bambi docs`.
  - `skills_install.py`: `bambi skills install --target claude|codex|opencode|agents`.
  - `workspace.py`, `doctor.py`: `bambi workspace init`, `bambi doctor`.
  - `data/profiles/{machine,process,filament}/*.json`: bundled flattened Bambu Studio profiles. A workspace's `profiles/` overrides them. Refresh with `just profiles-refresh` (`profiles sync --bundled --overwrite`); tune by editing the JSON (the slicer CLI needs fully resolved files, so no `inherits`).
  - `data/session_template/`, `data/workspace_template/` (dotfiles stored without the dot).
- `src/bambi/blender_scripts/`: run **inside** Blender (`blender -b file.blend -P script.py -- --result out.json ...`). bpy/bmesh only; never import `bambi` here. Each script takes `--result` and writes JSON there.
- Claude plugin = repo root: `.claude-plugin/plugin.json` (skills path points into `src/bambi/skills/`), `bin/bambi` (launcher: this checkout via `uv run --project`, else `uvx` at the tag matching the plugin version), `hooks/` (forces a prompt on `printer send --start`).
- `npm/`: the `@notrealarchitecture/bambi` package. `npx @notrealarchitecture/bambi install --target X` copies the skills; other args run the CLI via `uvx`. `npm/skills/` is copied at pack time (gitignored).
- Versions: `pyproject.toml` is the source (`uv version`); `scripts/sync_version.py` copies it into `.claude-plugin/plugin.json` and `npm/package.json` (`just ci` checks they match). Release: Actions → release → Run workflow (patch/minor/major), or `just release [patch|minor|major|X.Y.Z]` then `git push --follow-tags`. The release workflow builds with `uv build`, creates the GitHub release with the wheel and sdist, and publishes npm (needs the `NPM_TOKEN` secret).
- `examples/witch-frame-coupon/`: one real session, a demo and the fixture for `tests/test_example.py`.

## Workspace (the data home)
Print work lives outside the tool, in a workspace: `BAMBI_HOME`, else `home` in `~/.config/bambi/config.toml`, else this checkout while it still has `sessions/` (legacy), else `~/bambi`. `bambi workspace init <dir>` scaffolds one; `bambi workspace where` prints it.
- `sessions/YYYY-MM-DD-<name>/`: one per modeling project. `model.blend` (source), `session.toml` (slice/print settings), `notes.md`, `exports/` (STL), `out/` (sliced `.gcode.3mf`, gitignored). `results.json` (check/slice/print/fit runs and recommendations), `thumb.png` (plate preview from the sliced 3mf, written on every slice) and `render.png` (`bambi render`) are committed; each slice/render turns the best one into a uniform card in `docs/gallery/<session>.png` and rewrites the workspace README gallery grid (between `<!-- gallery:start/end -->`).
- `assets/studio.blend`: render studio (P1S textured PEI plate on a cyclorama, lights, camera at a fixed printer-front angle in scene props `bambi_azimuth`/`bambi_elevation`). Built on first `bambi render`; `bambi render` appends it and centres the models on the plate. Tweak the look by editing it in Blender; `bambi render-scene --overwrite` rebuilds it from `src/bambi/blender_scripts/build_studio.py`.

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

bambi never edits a pack's own files (`export` and `blender orient` refuse). Changes go upstream as recommendations: `bambi log rec`, `log fit`, `log print --rec`. The modelling side applies them, records the ids in `[print] feedback_applied/declined`, and re-packs. The contract is `bambi docs print-spec` and `bambi docs print-results`.

## Starting a new print
- **New thing:** the `new-session` skill (`/bambi:new-session <idea>` in Claude Code). Plan, create the session, model it via MCP, then `/bambi:print`.
- **Existing model or pack:** the `print` skill (`/bambi:print <ws>`). Runs `bambi plan` (readiness rows A to J), routes each open row to a sub-skill, then slices with `build --strict`.

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
bambi gallery               bambi docs [topic]     bambi doctor
bambi workspace init <dir> [--default]    bambi workspace where
bambi skills install --target claude|codex|opencode|agents [--project DIR] [--link]
bambi skills ls|uninstall
bambi profiles sync [--bundled]|ls|search <kind> <text>
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
`just ci` (ruff, pytest, plugin validation), `just fmt`. Run the plugin from the checkout with `claude --plugin-dir .`; for Codex/opencode, `just skills-link codex` symlinks the skills. Repos that enable `bambi@bambi` get `bambi` on PATH through `bin/bambi`. `just npm-pack` dry-runs the npm package.

Binaries (`*.blend`, `*.stl`, `*.png`, `*.3mf`) are in Git LFS (`.gitattributes`); fresh clones need `git lfs install`.
