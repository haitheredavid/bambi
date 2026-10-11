---
name: print-log
description: Close the loop after a print or coupon. Record outcomes and failures (sag, warp, adhesion, fit, snap) in results.json, log coupon picks, recommend model changes, and on the modelling side walk pending recommendations (apply or decline, record ids, re-pack). Use for "it printed", "it failed at", "the ledge sagged", "coupon 2 fits", "what did we learn", "apply the print feedback", or when the `print` skill shows row J.
argument-hint: <workspace or model> [what happened]
---

# Print results and feedback

Target: the workspace the user named ($ARGUMENTS)

Contract: `bambi docs print-results` (results) and `bambi docs print-spec` (spec).

## Recording (bambi side)
Ask for anything missing in one go:
- the outcome (ok / failed / partial)
- which part
- what kind of failure
- at what height
- what they'd change

Then record it:
- **Print:**
  `bambi log print <ws> --outcome failed --part X --kind sag --z 9 --note "..." --rec "<target>=<value>" --reason "..."`
  - Failure kinds: sag, warp, adhesion, stringing, fit, layer-shift, snap, spaghetti, other.
  - Turn each lesson into a recommendation aimed at where the fix lives:
    - `model.toml:[[print.part]] match=X supports`
    - `builders/<file>.py:<PARAM>`
    - a geometry note
  - Prefer design fixes (chamfer, gable, thicker wall) to support settings. Give the alternative with `--alt` on `bambi log rec`.
- **Coupon:** `bambi log fit <ws> --coupon <id> --value <v> --note "..."`. It auto-recommends the coupon's param.
- **Anything else:** `bambi log rec <ws> --target ... --value ... --reason ...`.
- **Native bambi session:** also add a dated line under "Print results" in its `notes.md`.

## Applying (modelling side, blender-sessions)
1. `blend print-results <m> [--pack coupon]` lists the pending recommendations.
2. For each, show the user the target, the value and the reason, and ask whether to apply or decline it.
   - **Apply:** edit `model.toml` or the builder parameter (with a comment naming the material and coupon), rebuild over MCP if it's geometry, then add the id to `[print] feedback_applied`.
   - **Decline:** add the id to `feedback_declined`, with the reason as a comment.
3. Re-pack with `blend print-pack <m> [--collection X]`, then `bambi init <pack> --force` if the intent changed.
4. `bambi plan <ws>`. Row J should show the recommendation closed and the old slice as stale until it's re-sliced.

bambi never edits the modelling repo by itself. Its recommendations reach the model only when you or the user apply them through this flow.
