const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { defaultTargetRoot, installSkill } = require("../src/install");

function makeTempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "opsforge-skills-test-"));
}

function writeSkill(packageRoot, name) {
  const skillRoot = path.join(packageRoot, "skills", name);
  fs.mkdirSync(path.join(skillRoot, "scripts"), { recursive: true });
  fs.writeFileSync(
    path.join(skillRoot, "SKILL.md"),
    "---\nname: " + name + "\ndescription: test skill\n---\n\n# Test\n",
  );
  fs.writeFileSync(path.join(skillRoot, "scripts", "run.py"), "#!/usr/bin/env python3\nprint('ok')\n");
  return skillRoot;
}

test("defaultTargetRoot prefers CODEX_HOME skills directory", () => {
  const home = makeTempDir();
  const target = defaultTargetRoot({ env: { CODEX_HOME: path.join(home, "codex") }, homeDir: home });
  assert.equal(target, path.join(home, "codex", "skills"));
});

test("installSkill copies skill files and marks scripts executable", () => {
  const root = makeTempDir();
  const packageRoot = path.join(root, "pkg");
  const targetRoot = path.join(root, "target");
  fs.mkdirSync(packageRoot, { recursive: true });
  writeSkill(packageRoot, "opsforge-release");

  const result = installSkill({
    packageRoot,
    targetRoot,
    skillName: "opsforge-release",
    timestamp: "20260701010101",
  });

  const installedSkill = path.join(targetRoot, "opsforge-release");
  assert.equal(result.installedTo, installedSkill);
  assert.equal(result.backupPath, "");
  assert.equal(fs.existsSync(path.join(installedSkill, "SKILL.md")), true);
  assert.equal(fs.existsSync(path.join(installedSkill, "scripts", "run.py")), true);
  assert.equal(fs.statSync(path.join(installedSkill, "scripts", "run.py")).mode & 0o111, 0o111);
});

test("installSkill backs up an existing skill before replacing it", () => {
  const root = makeTempDir();
  const packageRoot = path.join(root, "pkg");
  const targetRoot = path.join(root, "target");
  fs.mkdirSync(path.join(targetRoot, "opsforge-release"), { recursive: true });
  fs.writeFileSync(path.join(targetRoot, "opsforge-release", "old.txt"), "old");
  fs.mkdirSync(packageRoot, { recursive: true });
  writeSkill(packageRoot, "opsforge-release");

  const result = installSkill({
    packageRoot,
    targetRoot,
    skillName: "opsforge-release",
    timestamp: "20260701010101",
  });

  assert.equal(result.backupPath, path.join(targetRoot, "opsforge-release.bak.20260701010101"));
  assert.equal(fs.existsSync(path.join(result.backupPath, "old.txt")), true);
  assert.equal(fs.existsSync(path.join(targetRoot, "opsforge-release", "SKILL.md")), true);
});

test("installSkill rejects unknown skills", () => {
  const root = makeTempDir();
  assert.throws(
    () =>
      installSkill({
        packageRoot: root,
        targetRoot: path.join(root, "target"),
        skillName: "missing-skill",
        timestamp: "20260701010101",
      }),
    /Unknown skill: missing-skill/,
  );
});
