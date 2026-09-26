# bambi

Blender → Bambu Studio → Bambu Lab P1S sandbox.

## Setup
```sh
brew install --cask blender bambu-studio
uv sync
cp .env.example .env              # add printer IP, access code, serial (LAN mode)
uv run bambi profiles sync        # flatten Bambu Studio system profiles into profiles/
```
Blender needs the [blender-mcp](https://github.com/ahujasid/blender-mcp) add-on for live modeling with Claude.

## Workflow
```sh
uv run bambi new phone-stand          # sessions/2026-09-26-phone-stand/ with an mm-unit model.blend
uv run bambi blender open phone-stand # model it (by hand or via Claude + MCP), save
uv run bambi build phone-stand        # export STL, then run checks, then slice to out/*.gcode.3mf
uv run bambi printer status
uv run bambi printer send phone-stand --start
```
Per-session slice settings (process, filament, AMS slot) live in `session.toml`.
