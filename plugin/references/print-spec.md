# Print spec (`print-spec/1`)

The contract from a modelling repo to bambi. The modelling repo (blender-sessions) writes it, and bambi only reads it.

- **Location:** `manifest.json` in a print pack, next to `parts.blend` and `stl/`.
- **Writer:** in blender-sessions, `blend print-pack <m> [--collection X]`, which writes `models/<m>/print/` (or `print/<x>/`).
- **What it carries:** intent, never Bambu Studio keys. bambi turns intent into slice settings:

| Intent | bambi does |
|---|---|
| `supports.policy = "none"` | `enable_support = 0` |
| `"auto"` | keeps the process profile's choice |
| `"build-plate"` | normal(auto) supports on the build plate only |
| `"everywhere"` | tree(auto) supports |
| `filament` per part, plus `filaments[]` | `[[filaments]]` and `[objects]` in session.toml |
| `colour.method = "ams"` with `into` | `assemble = true`, so floating inlays slice as one object |

When parts disagree on supports, the strongest policy wins, because one plate is sliced with one process.

## Shape
```jsonc
{
  "schema": "print-spec/1",
  "model": "witch-frame",            // model name upstream
  "pack": "coupon",                  // "print" for the main pack
  "intent": "E-seam clearance coupon",
  "created": "2026-10-11T12:20:21-04:00",
  "source": {"repo": "blender-sessions", "commit": "abc123", "blend": "models/witch-frame/model.blend"},
  "units": "mm",
  "printer": "Bambu Lab P1S", "bed_mm": 256,
  "material": "PETG (Insignia, black)",          // free text; also the single-filament fallback
  "filaments": [                                  // optional; omit for single material
    {"id": 1, "role": "body", "material": "petg", "color": "#111111", "profile_hint": "insignia_petg"}
  ],
  "parts": [{
    "name": "Piece_TR", "stl": "stl/Piece_TR.stl",
    "size": [139.7, 177.8, 40.0], "volume_cm3": 86.0, "manifold": true, "fits_bed": true, "flat": false,
    "orientation": {"mode": "as-modelled", "rotate_deg": [0, 0, 0], "why": "back face down; gable mortise self-supports"},
    "filament": 1,
    "colour": {"method": "single"},              // single | ams | glue-in | paint | engrave; "into": host part
    "supports": {"policy": "none", "why": "z9 ledge chamfered"},
    "joints": [{"id": "seam-E", "kind": "loose-tenon", "mate": "Tenon_E",
                "clearance_mm": 0.10, "param": "builders/joinery.py:TENON_CLEAR", "coupon": "tenon-E"}]
  }],
  "coupons": [{"id": "tenon-E", "param": "builders/joinery.py:TENON_CLEAR", "values": [0.10, 0.15, 0.20],
               "parts": {"0.10": ["Coupon_C10_A", "Coupon_C10_B", "Coupon_C10_Tenon"]},
               "rule": "tightest that slides in by hand, with glue room"}],
  "feedback_applied": ["rec-20261011-01"],        // results.json recommendation ids the model took
  "feedback_declined": [],                        // ...or chose not to
  "orientation": "...", "hardware": ["..."], "assembly": ["..."],
  "plates_suggested": [["..."]], "total_volume_cm3": 363.7
}
```

All per-part intent keys are optional. A v0 manifest, which has no `schema`, loads as "intent unknown".

`joints[].kind` is one of:
- `loose-tenon`
- `dowel` (1.75 mm filament in a Ø2.1 hole)
- `peg`
- `key`
- `magnet`
- `screw`
- `glue-face`
- `snap`

## Where it comes from (blender-sessions `model.toml`)
```toml
[print]
collection = "Print"
material = "PETG (Insignia, black)"
feedback_applied = ["rec-20261011-01"]
feedback_declined = []

[[print.part]]                # fnmatch on part names; later entries win, key by key
match = "Piece_*"             # a glob or a list of globs
# flat = true                 # lay on the largest face (beats rotate)
# orientation_why = "back face down: gable mortises self-support"
supports = "none"             # none | auto | build-plate | everywhere
supports_why = "z9 ledge chamfered"
filament = 1
colour = "single"             # single | ams | glue-in | paint | engrave
# into = "Body"               # colour host for ams inlays / glue-in pockets
# rotate = [90, 0, 0]         # degrees, applied by print-pack before laying on the bed

[[print.filament]]
id = 1
role = "body"
material = "petg"
color = "#111111"
profile_hint = "insignia_petg"

[[print.coupon]]
id = "tenon-E"
param = "builders/joinery.py:TENON_CLEAR"
values = [0.10, 0.15, 0.20]
parts = { "0.10" = ["Coupon_C10_*"], "0.15" = ["Coupon_C15_*"], "0.20" = ["Coupon_C20_*"] }
rule = "tightest that slides in by hand, with glue room"
```

Joints come from object custom properties that builders set: `obj["joints"]`, a JSON list shaped like `joints[]`.

## Ownership

| File | Owner |
|---|---|
| `model.toml`, `builders/`, `params.toml` | modelling repo |
| `manifest.json`, `parts.blend`, `stl/` | `blend print-pack` (bambi refuses to edit them) |
| `session.toml`, `results.json`, `thumb.png`, `out/` in the pack | bambi |

Recommendation ids carry the pack name when it isn't the main pack (`rec-coupon-20261011-01`), so ids from several packs can share one `model.toml` list. Collection packs (`[print.Coupon]`) keep their own `feedback_*` lists.

`bambi init <pack>` writes `session.toml` with:
- `[paths] kind = "pack"`
- `[source] spec_hash`, which identifies the geometry plus intent, ignoring timestamps.

bambi warns when the live spec hash differs from the one recorded, meaning the pack was re-packed since the last init or slice.
