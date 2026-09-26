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

# --- printer -----------------------------------------------------------------

# printer status (read-only)
status:
    {{bambi}} printer status

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
