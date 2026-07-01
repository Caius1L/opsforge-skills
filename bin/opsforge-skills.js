#!/usr/bin/env node

const path = require("node:path");
const { defaultTargetRoot, installSkill } = require("../src/install");

function usage() {
  return [
    "Usage:",
    "  opsforge-skills install <skill-name> [--target <skills-dir>]",
    "",
    "Example:",
    "  opsforge-skills install opsforge-release",
  ].join("\n");
}

function parseArgs(argv) {
  const args = argv.slice(2);
  const command = args[0] || "";
  const skillName = args[1] || "";
  let targetRoot = "";

  for (let index = 2; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "--target") {
      targetRoot = args[index + 1] || "";
      index += 1;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }

  return { command, skillName, targetRoot };
}

function main() {
  const { command, skillName, targetRoot } = parseArgs(process.argv);
  if (command !== "install" || !skillName) {
    console.error(usage());
    process.exitCode = 2;
    return;
  }

  const packageRoot = path.resolve(__dirname, "..");
  const result = installSkill({
    packageRoot,
    targetRoot: targetRoot || defaultTargetRoot(),
    skillName,
  });

  console.log(`Installed ${result.skillName} to ${result.installedTo}`);
  if (result.backupPath) {
    console.log(`Previous installation backed up to ${result.backupPath}`);
  }
  console.log('Use it from a service repository by asking: "发布到腾讯云测试"');
}

try {
  main();
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
