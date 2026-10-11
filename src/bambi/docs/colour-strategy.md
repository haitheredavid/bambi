# Colour strategy

`bambi colour <ws>` slices the parts into layers and counts filament changes: one per extra colour per layer, starting each layer on the filament the previous layer ended on. It then prices the result in time and purge waste:
- about 80 s and 0.36 g per swap
- the anubis-head pair: 690 swaps meant 18h30 and 361 g, against 3h06 and 113.5 g as glue-in

After slicing, `filament_changes` in the slice run is the real count, read from the gcode.

| Strategy | When | Cost | Model changes |
|---|---|---|---|
| **AMS bands** | Each layer is one colour; the colour changes at heights (flip-coupon: 13 swaps) | cheap | One object per colour band |
| **AMS inlay** | Colours share layers. Fine over a short Z span (a flat sign face); expensive when tall. | swaps × 80 s | One object per colour; floating parts need `[slice] assemble = true` (the knife's eyes: "empty layer between 0 and 15.2") |
| **Glue-in** | Inlays over a tall Z (anubis eyes and trim), or materials that won't bond | 0 swaps, an extra print and glue | Pocket 1.2 mm deep in the body; pieces inset 0.25 mm per side, printed flat in their own session or pack |
| **Paint** | Many colours, small details, single-material print | your time | Optional 0.4–0.6 mm recessed outlines as guides (colossus, cat mask) |
| **Engrave** | Text or logos read by shadow | free | Cut 0.6 mm or more into the surface (knife v2b) |

**Rules of thumb:**
- Under ~15 swaps, just use the AMS. Over ~60, prefer glue-in.
- Watch material bonding. PLA eyes would not bond to Support-for-PLA (knife v1b). PETG to PLA bonds poorly.
- Glue: CA for PLA, epoxy or slow CA for PETG. Wood glue does not bond PETG.
- Tray mapping: `bambi printer ams <ws> --write` fills `[[filaments]]` from the loaded trays.
  - Starting from the printer's screen defaults to tray 0, so remap it there.
  - `printer send` refuses when a tray's material doesn't match.

**Setting it up:**
- **Native session:** add `[[filaments]]` (profile, color, ams_slot) and `[objects]` (STL stem = filament number).
- **Pack:**
  1. Upstream, set `[[print.filament]]` and per-part `filament` / `colour = "ams"` (+ `into`).
  2. `bambi init --force` turns these into `[[filaments]]`, `[objects]` and `assemble`.
