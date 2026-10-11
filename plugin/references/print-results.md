# Print results (`print-results/1`)

`results.json` sits in every print workspace: a bambi session folder or a print pack. It is an append-only log. bambi writes it; the modelling side reads it, using `blend print-results <m>` in blender-sessions. Commit it, because it is the print history.

## Shape
```jsonc
{
  "schema": "print-results/1", "model": "witch-frame", "pack": "coupon",
  "runs": [
    {"id": "che-20261011-01", "kind": "check", "at": "...", "spec_hash": "...", "severity": "warn",
     "summary": {"block": 0, "warn": 6}, "report": "check.json"},
    {"id": "sli-20261011-01", "kind": "slice", "at": "...", "file": "out/witch-frame-coupon.gcode.3mf",
     "machine": "p1s_0.4", "process": "0.16mm_optimal", "filaments": ["insignia_petg"], "plate": "Textured PEI Plate",
     "overrides": {"enable_support": 1}, "seconds": 3240, "grams": 18.1, "grams_per_filament": [18.1],
     "filament_changes": 0, "spec_hash": "15f67528395c4ca7"},
    {"id": "pri-20261011-01", "kind": "print", "at": "...", "state": "started", "slice": "sli-20261011-01", "plate": 1},
    {"id": "pri-20261011-02", "kind": "print", "at": "...", "slice": "sli-20261011-01", "outcome": "failed",
     "failures": [{"part": "Coupon_C10_Flat_A", "kind": "sag", "z_mm": 9.0, "note": "flat 3.7 mm lip drooped"}],
     "note": "..."},
    {"id": "fit-20261011-01", "kind": "fit", "at": "...", "coupon": "tenon-E", "param": "builders/joinery.py:TENON_CLEAR",
     "value": 0.10, "material": "petg", "note": "all slide; 0.10 tightest with glue room"}
  ],
  "recommendations": [
    {"id": "rec-20261011-01", "at": "...", "from": "pri-20261011-02",
     "target": "model.toml:[[print.part]] match=Coupon_*_A supports", "value": "build-plate",
     "alt": "45 deg chamfer under the z9 lip in the frame builder", "reason": "flat ceiling sagged at z9"},
    {"id": "rec-20261011-02", "at": "...", "from": "fit-20261011-01",
     "target": "builders/joinery.py:TENON_CLEAR", "value": 0.10, "reason": "coupon pick (PETG)"}
  ]
}
```

- **Run kinds:**
  - `check`, from `bambi check`
  - `slice`, from `bambi slice` / `build`
  - `print`, from `printer send` (state) and `bambi log print` (outcome)
  - `fit`, from `bambi log fit`
- **Outcomes:** `ok`, `failed`, `partial`.
- **Failure kinds:** `sag`, `warp`, `adhesion`, `stringing`, `fit`, `layer-shift`, `snap`, `spaghetti`, `other`.

## The loop
1. **Print, then log.** Run `bambi log print <ws> --outcome failed --part X --kind sag --z 9 --note "..."`. Add `--rec "<target>=<value>"` to propose the fix right away.
2. **Coupon, then log.** Run `bambi log fit <ws> --coupon tenon-E --value 0.10`. If the coupon is in the spec, it proposes a recommendation for the coupon's `param` automatically.
3. **Other suggestions.** Run `bambi log rec <ws> --target ... --value ... --reason ...`.
4. **Modelling side.** `blend print-results <m>` lists the pending recommendations: those not in the spec's `feedback_applied` / `feedback_declined`. For each one, apply it (edit `model.toml` or the builder) or decline it, then record its id under `[print] feedback_applied` / `feedback_declined` and re-pack.
5. **bambi side.** `bambi plan <ws>` shows each recommendation as closed once the new spec lists it. It flags the last slice as **stale** when `spec_hash` changed.

bambi never edits the modelling repo's files. The recommendations are the only channel back.
