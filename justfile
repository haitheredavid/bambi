set dotenv-load := false
# pass recipe args through as "$@" so quoted values (e.g. --plate "Cool Plate") stay intact
set positional-arguments

bambi := "uv run bambi"

# list recipes
default:
    @just --list --unsorted

# --- setup / dev -------------------------------------------------------------

# install deps, create .env if missing, flatten slicer profiles
setup:
    uv sync
    test -f .env || cp .env.example .env
    {{bambi}} profiles sync

# run tests
test *args:
    uv run pytest "$@"

# lint + format check
lint:
    uv run ruff check .
    uv run ruff format --check .

# auto-fix lint + format
fmt:
    uv run ruff check --fix .
    uv run ruff format .

# lint + tests
ci: lint test

# --- sessions ----------------------------------------------------------------

# create sessions/YYYY-MM-DD-<name>/ and open it in Blender
new name:
    {{bambi}} new {{name}}
    {{bambi}} blender open {{name}}

# list sessions
ls:
    {{bambi}} ls

# open a session's model.blend (MCP bridge auto-starts)
open session:
    {{bambi}} blender open {{session}}

# drop objects onto the bed and centre them
orient session:
    {{bambi}} blender orient {{session}}

# export STLs from model.blend
export session:
    {{bambi}} export {{session}}

# printability checks
check session:
    {{bambi}} check {{session}}

# slice with the session's profiles (extra flags pass through, e.g. --filament petg_hf)
slice session *flags:
    {{bambi}} slice "$@"

# export -> check -> slice
build session:
    {{bambi}} build {{session}}

# studio render of model.blend on the P1S plate -> sessions/<s>/render.png (--framing fit|wide)
render session *flags:
    {{bambi}} render "$@"

# build assets/studio.blend, the scene `render` uses (--overwrite discards hand edits)
render-scene *flags:
    {{bambi}} render-scene "$@"

# backfill thumb.png from sliced files and rewrite the README gallery
gallery:
    {{bambi}} gallery

# render a scene's animation to out/<session>-assembly.mp4 + .gif (save in Blender first)
anim session scene="Assembly Anim":
    #!/usr/bin/env bash
    set -euo pipefail
    read -r dir blender < <(uv run python -c 'import sys; from bambi.config import get_settings; from bambi.session import resolve; print(resolve(sys.argv[1]).path, get_settings().blender_bin)' "{{session}}")
    out="${dir:?}/out"; name="$(basename "$dir")-assembly"
    mkdir -p "$out/anim" && rm -f "$out"/anim/f*.png
    "$blender" -b "$dir/model.blend" -S "{{scene}}" -o "$out/anim/f####" -F PNG -a 2>&1 | grep -E "Error|Saved: .*f0001" || true
    ls "$out"/anim/f*.png >/dev/null
    fps=$("$blender" -b "$dir/model.blend" -S "{{scene}}" --python-expr 'import bpy; print("FPS", bpy.context.scene.render.fps)' 2>/dev/null | awk '/^FPS/{print $2}')
    ffmpeg -y -loglevel error -framerate "${fps:-24}" -i "$out/anim/f%04d.png" -c:v libx264 -pix_fmt yuv420p -crf 18 "$out/$name.mp4"
    ffmpeg -y -loglevel error -i "$out/$name.mp4" -vf "fps=15,scale=540:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse" "$out/$name.gif"
    echo "wrote $out/$name.mp4 and $name.gif ($(ls "$out"/anim/f*.png | wc -l | tr -d ' ') frames)"

# --- printer -----------------------------------------------------------------

# open the sliced file in Bambu Studio to send via Bambu Cloud
studio session:
    {{bambi}} studio {{session}}

# printer status (read-only, LAN)
status:
    {{bambi}} printer status

# what's loaded in the AMS; `just ams <session> --write` fills [[filaments]]
ams *args:
    {{bambi}} printer ams {{args}}

# upload the sliced file without starting
upload session:
    {{bambi}} printer send {{session}}

# upload and start printing (asks to confirm)
print session *flags:
    {{bambi}} printer send "$@" --start

# --- profiles ----------------------------------------------------------------

# list local profiles
profiles:
    {{bambi}} profiles ls

# re-flatten profiles from the installed Bambu Studio (overwrites local edits)
profiles-refresh:
    {{bambi}} profiles sync --overwrite

# search Bambu Studio system profiles: just profile-search filament "PLA Matte"
profile-search kind text:
    {{bambi}} profiles search "$@"
