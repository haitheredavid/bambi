#!/usr/bin/env node
// Copy the canonical skills (src/bambi/skills) into this package. --check: fail if out of date.
const fs = require("node:fs");
const path = require("node:path");

const src = path.resolve(__dirname, "../../src/bambi/skills");
const dest = path.resolve(__dirname, "../skills");

function list(dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.name === ".DS_Store") continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...list(p).map((f) => path.join(e.name, f)));
    else out.push(e.name);
  }
  return out.sort();
}

if (process.argv.includes("--check")) {
  const a = list(src);
  const b = fs.existsSync(dest) ? list(dest) : [];
  const same =
    a.join() === b.join() &&
    a.every((f) => fs.readFileSync(path.join(src, f)).equals(fs.readFileSync(path.join(dest, f))));
  if (!same) {
    console.error("npm/skills is out of date; run `npm run prepack` in npm/");
    process.exit(1);
  }
  console.log("npm/skills matches src/bambi/skills");
} else {
  fs.rmSync(dest, { recursive: true, force: true });
  fs.cpSync(src, dest, { recursive: true, filter: (p) => !p.endsWith(".DS_Store") });
  fs.copyFileSync(path.resolve(__dirname, "../../LICENSE"), path.resolve(__dirname, "../LICENSE"));
  console.log(`skills -> ${dest}`);
}
