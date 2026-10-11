set dotenv-load := false
# pass recipe args through as "$@" so quoted values (e.g. --plate "Cool Plate") stay intact
set positional-arguments

bambi := "uv run bambi"

# list recipes
default:
    @just --list --unsorted

# --- setup / dev -------------------------------------------------------------

# install deps, create .env if missing, check the toolchain
setup:
    uv sync
    test -f .env || cp .env.example .env
    {{bambi}} doctor || true

# run tests
test *args:
    uv run pytest "$@"

# lint + format check
lint:
    uv run ruff check src tests scripts
    uv run ruff format --check src tests scripts

# auto-fix lint + format
fmt:
    uv run ruff check --fix src tests scripts
    uv run ruff format src tests scripts

# validate the Claude Code plugin and marketplace manifests
plugin-check:
    claude plugin validate . --strict

# lint + tests + plugin manifests
ci: lint test plugin-check
    uv run python scripts/sync_version.py --check

# symlink the skills into a harness for dev: just skills-link codex
skills-link target="codex":
    {{bambi}} skills install --target {{target}} --link

# copy skills into npm/ and dry-run the package
npm-pack:
    cd npm && npm run prepack && npm pack --dry-run

# copy the pyproject version into plugin.json and npm/package.json
sync-version:
    uv run python scripts/sync_version.py

# bump (patch|minor|major, or X.Y.Z), sync manifests, commit and tag vX.Y.Z; push to publish
release bump="patch":
    #!/usr/bin/env bash
    set -euo pipefail
    test -z "$(git status --porcelain)" || { echo "commit or stash first"; exit 1; }
    case "{{bump}}" in patch|minor|major) uv version --bump "{{bump}}" ;; *) uv version "{{bump}}" ;; esac
    v=$(uv run python scripts/sync_version.py)
    just ci
    git add pyproject.toml uv.lock .claude-plugin/plugin.json npm/package.json
    git commit -m "chore: release v$v"
    git tag -a "v$v" -m "v$v"
    echo "push with: git push --follow-tags  (the release workflow publishes v$v)"

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

# printability checks (mesh + layer analysis)
check session:
    {{bambi}} check {{session}}

# readiness triage: what's left before slicing (rows A-J)
plan session *flags:
    {{bambi}} plan "$@"

# rank print orientations per part (--part X, --apply N)
orient-rank session *flags:
    {{bambi}} orient "$@"

# colour strategies: AMS swaps vs glue-in, paint, engrave
colour session:
    {{bambi}} colour {{session}}

# make a print pack sliceable (writes its session.toml)
init pack *flags:
    {{bambi}} init "$@"

# runs and recommendations in results.json
log session:
    {{bambi}} log show {{session}}

# slice with the session's profiles (extra flags pass through, e.g. --filament petg_hf)
slice session *flags:
    {{bambi}} slice "$@"

# export -> check -> slice (--strict stops on blocking checks)
build session *flags:
    {{bambi}} build "$@"

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

# re-flatten the bundled profiles from the installed Bambu Studio (dev; overwrites edits)
profiles-refresh:
    {{bambi}} profiles sync --bundled --overwrite

# search Bambu Studio system profiles: just profile-search filament "PLA Matte"
profile-search kind text:
    {{bambi}} profiles search "$@"
