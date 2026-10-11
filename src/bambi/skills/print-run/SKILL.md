---
name: print-run
description: Slice a ready workspace with Bambu Studio and get it to the P1S. Run the strict build, report time, grams, filament swaps and the plate preview, then open it in Bambu Studio (cloud) or upload over LAN. Starting a print always needs the user's explicit go-ahead. Use for "slice it", "send it to the printer", "print it", "upload", or after the `print` skill reports ready.
argument-hint: <workspace> [--start]
---

# Slice and print

Target: the workspace the user named ($ARGUMENTS)

1. **Run `bambi build <ws> --strict`.**
   - **Sessions:** export, then check, then slice.
   - **Packs:** check, then slice.
   - If the strict check stops it, go back to the `print` skill rather than slicing anyway.
   - A slice failure prints Bambu's reason. Common causes:
     - A filament/plate mismatch, such as PETG on the Cool Plate.
     - An unknown override key.
     - An "empty layer" from a floating colour part, which needs `assemble = true`.
2. **Report to the user:**
   - time and grams, plus filament changes for multi-colour
   - the process, filament and plate
   - the thumbnail path (`thumb.png` in the workspace)

   Open and look at the thumbnail before reporting, to make sure the plate looks right.

   The slice is recorded in `results.json`.
3. **Ask how they want to print** (unless they already said):
   - **Bambu Cloud:** `bambi studio <ws>` opens the sliced file in Bambu Studio, and the user presses Print plate. No `.env` needed.
   - **LAN:**
     - `bambi printer status` (read-only)
     - `bambi printer ams <ws>` (read-only tray check)
     - `bambi printer send <ws>` uploads without starting.
4. **Starting a print is physical and needs explicit consent in this conversation**, every time, even if the user said "print it" earlier for something else.
   - Confirm plate, filament and tray first, then run `bambi printer send <ws> --start` (add `--plate N` for multi-plate slices).
   - In Claude Code the plugin hook also forces a permission prompt; elsewhere, without `-y` the CLI asks on a terminal and refuses when it has none.
   - When the print is started from the printer's screen, remind the user it defaults to tray 0 and needs remapping there.
5. **After printing:** ask how it went, then hand over to the `print-log` skill.
