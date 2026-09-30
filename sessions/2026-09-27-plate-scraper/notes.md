# Notes

## Intent
Simple PLA scraper (90 x 30 mm, 6 mm handle tapering to ~1 mm chisel edge) for lifting stray filament off the textured PEI plate. Mainly an end-to-end smoke test: plan -> Blender MCP -> export/check/slice -> LAN send.

## Iterations
- v1 (2026-09-27): single `Scraper` bmesh, 90x30x6 mm. 6 mm handle to x=55, then wedge down to 1 mm blade edge. R4 corners on handle end, 0.4 mm bottom chamfer (not on blade tip), 1 mm top bevel on handle. Printed flat, no supports. Slice: 19 min, 8.4 g, 0.20mm_standard / pla_basic / Textured PEI, AMS slot 1 (slot 0 holds PLA Silk). Uploaded over LAN. Gotcha: first attempt modelled into another open Blender (tmg-base-kit) that owned MCP port 9876.

## Print results
- 2026-09-27: `just print -y` uploaded OK but printer ignored start (HMS_0500_0400_0001_0007, LAN command not authorised without Developer Mode); CLI still printed "started". Cloud route via Studio reported "no geometry" (file itself is valid). Started from printer SD card instead: RUNNING, 30 layers, ~19 min.
