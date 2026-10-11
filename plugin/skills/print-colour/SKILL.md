---
name: print-colour
description: Choose how a multi-colour print gets its colours on the P1S. Compare AMS bands, AMS inlays, glue-in trim, paint and engraving by filament swaps, extra time and purge waste, then set up filaments, object mapping, assemble and AMS trays. Use for "multi-colour", "AMS", "inlay", "two colours", "how many swaps", "glue-in trim", or when /bambi:print routes row H here.
argument-hint: <workspace>
---

# Colour strategy

Target: $ARGUMENTS

Read `${CLAUDE_PLUGIN_ROOT}/references/colour-strategy.md`.

1. **Run `bambi colour <ws>`.** It gives each strategy's swaps, extra minutes, purge grams and the model changes it needs, plus a recommendation. If the workspace is still single-colour but the user wants colour, first decide which parts get which colour, then come back.
2. **Present the trade-off in one table** and give a recommendation:
   - Under ~15 swaps: AMS.
   - Over ~60: glue-in.
   - Many small colours: paint.
   - Text or logos read by shadow: engrave.
   - Material bonding matters: PLA does not bond to Support-for-PLA, and PETG bonds poorly to PLA.
3. **Set it up:**
   - **AMS (session):**
     - `[[filaments]]` (profile, color, ams_slot) and `[objects]` (STL stem = filament number).
     - `[slice] assemble = true` when a colour part sits off the bed or inside another.
     - `bambi printer ams <ws> --write --slots ...` fills the filaments from what's loaded (read-only without `--write`).
   - **AMS (pack):**
     - Upstream: `[[print.filament]]`, plus per-part `filament`, `colour = "ams"` and `into`.
     - Re-pack, then `bambi init --force`.
   - **Glue-in:**
     - In the model: pockets 1.2 mm deep in the body; trim pieces inset 0.25 mm per side, laid flat.
     - The trim prints in its own session or pack, one per colour (anubis-head with anubis-gold/saddle).
     - Glue: CA for PLA, epoxy for PETG.
   - **Paint / engrave:** single colour. Recesses 0.4–0.6 mm deep as paint guides; engraving ≥ 0.6 mm deep.
4. **After slicing**, compare the real `filament_changes` in `bambi log show <ws>` against the estimate, and mention any big gap.
