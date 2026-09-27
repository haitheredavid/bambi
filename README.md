# bambi

Blender → Bambu Studio → Bambu Lab P1S sandbox.

## Setup
```sh
brew install --cask blender bambu-studio
brew install just
just setup                        # uv sync, create .env, flatten Bambu Studio profiles into profiles/
$EDITOR .env                      # printer IP, access code, serial (LAN mode only)
```
Blender needs the [blender-mcp](https://github.com/ahujasid/blender-mcp) add-on for live modeling with Claude.

## Workflow
```sh
just new phone-stand       # sessions/2026-09-26-phone-stand/ with an mm-unit model.blend, opened in Blender
just build phone-stand     # export STL, then run checks, then slice to out/*.gcode.3mf
just slice phone-stand --filament petg_hf --plate "Engineering Plate"
just studio phone-stand    # open in Bambu Studio -> Print plate sends via Bambu Cloud
just status                # printer status (LAN)
just print phone-stand     # LAN: upload and start (asks first)
```
`just` lists every recipe; each wraps `uv run bambi ...`, which you can call directly for anything not covered.
Per-session slice settings (process, filament, build plate, AMS slot) live in `session.toml`.
