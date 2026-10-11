#!/usr/bin/env node
// npx @notrealarchitecture/bambi <cmd>
//   install --target codex|opencode|claude|agents [--project DIR]   copy the skills (no Python needed)
//   anything else                                                   run the bambi CLI via uvx
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { version } = require("../package.json");

const SKILLS = path.resolve(__dirname, "../skills");
const STAMP = ".bambi-version";
const REF = process.env.BAMBI_REF || `v${version}`;
const FROM = `git+https://github.com/haitheredavid/bambi@${REF}`;
const HOME = os.homedir();
// Keep in sync with TARGETS in src/bambi/skills_install.py: [user dir, project dir].
const TARGETS = {
  claude: [path.join(HOME, ".claude/skills"), ".claude/skills"],
  codex: [path.join(HOME, ".codex/skills"), ".agents/skills"],
  opencode: [path.join(HOME, ".config/opencode/skills"), ".opencode/skills"],
  agents: [path.join(HOME, ".agents/skills"), ".agents/skills"],
};

function hasUv() {
  return spawnSync("uv", ["--version"], { stdio: "ignore" }).status === 0;
}

function uvHint() {
  console.error(
    "bambi's CLI runs on uv: https://docs.astral.sh/uv/getting-started/installation/\n" +
      "  curl -LsSf https://astral.sh/uv/install.sh | sh",
  );
}

function arg(args, name) {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : undefined;
}

function install(args) {
  const target = arg(args, "--target");
  if (!TARGETS[target]) {
    console.error(`--target is one of ${Object.keys(TARGETS).join(", ")}`);
    process.exit(1);
  }
  const project = arg(args, "--project");
  const dest = project ? path.resolve(project, TARGETS[target][1]) : TARGETS[target][0];
  fs.mkdirSync(dest, { recursive: true });
  for (const name of fs.readdirSync(SKILLS)) {
    if (!fs.existsSync(path.join(SKILLS, name, "SKILL.md"))) continue;
    const to = path.join(dest, name);
    if (fs.existsSync(to)) {
      if (!fs.existsSync(path.join(to, STAMP)) && !fs.lstatSync(to).isSymbolicLink()) {
        console.error(`${to} exists and wasn't installed by bambi`);
        process.exit(1);
      }
      fs.rmSync(to, { recursive: true, force: true });
    }
    fs.cpSync(path.join(SKILLS, name), to, { recursive: true });
    fs.writeFileSync(path.join(to, STAMP), `${version}\n`);
    console.log(`+ ${to}`);
  }
  if (target === "opencode") {
    console.log(
      'opencode: add "permission": {"bash": {"bambi printer send *--start*": "ask"}} ' +
        "to opencode.json (or run `bambi skills install --target opencode`, which does it)",
    );
  }
  if (!hasUv()) uvHint();
  else run(["doctor"]);
}

function run(args) {
  if (!hasUv()) {
    uvHint();
    process.exit(1);
  }
  const r = spawnSync("uvx", ["--quiet", "--from", FROM, "bambi", ...args], { stdio: "inherit" });
  process.exit(r.status ?? 1);
}

const args = process.argv.slice(2);
if (args[0] === "install") install(args.slice(1));
else run(args);
