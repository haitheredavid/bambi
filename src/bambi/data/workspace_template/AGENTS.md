# {{name}}

A bambi print workspace. Each `sessions/YYYY-MM-DD-<name>/` has `model.blend` (source, 1 unit = 1 mm, Z up, bed z=0), `session.toml` (slice/print settings), `notes.md`, `exports/` (STL), `out/` (sliced, gitignored) and `results.json`.

- Use the bambi skills: `new-session` to design something new, `print` to get a session or print pack ready, `print-run` to slice and send.
- `bambi docs` lists the reference docs (P1S rules, readiness taxonomy, print contract).
- Starting a print (`bambi printer send --start`) is physical: always get the user's explicit go-ahead first.
- `.env` holds the printer access code. Never commit or print it.
