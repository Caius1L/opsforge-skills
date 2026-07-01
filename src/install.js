const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

function defaultTargetRoot({ env = process.env, homeDir = os.homedir() } = {}) {
  if (env.CODEX_HOME && env.CODEX_HOME.trim()) {
    return path.join(env.CODEX_HOME.trim(), "skills");
  }

  const codexRoot = path.join(homeDir, ".codex");
  const agentsRoot = path.join(homeDir, ".agents");
  if (fs.existsSync(codexRoot) || !fs.existsSync(agentsRoot)) {
    return path.join(codexRoot, "skills");
  }
  return path.join(agentsRoot, "skills");
}

function ensureSkillExists(skillRoot, skillName) {
  if (!fs.existsSync(skillRoot) || !fs.statSync(skillRoot).isDirectory()) {
    throw new Error(`Unknown skill: ${skillName}`);
  }
  const skillFile = path.join(skillRoot, "SKILL.md");
  if (!fs.existsSync(skillFile)) {
    throw new Error(`Invalid skill ${skillName}: missing SKILL.md`);
  }
}

function copyDirectory(source, destination) {
  fs.cpSync(source, destination, {
    recursive: true,
    errorOnExist: false,
    force: true,
    preserveTimestamps: true,
  });
}

function uniqueBackupPath(destination, timestamp) {
  let candidate = `${destination}.bak.${timestamp}`;
  let suffix = 1;
  while (fs.existsSync(candidate)) {
    candidate = `${destination}.bak.${timestamp}.${suffix}`;
    suffix += 1;
  }
  return candidate;
}

function chmodScripts(skillRoot) {
  const scriptsRoot = path.join(skillRoot, "scripts");
  if (!fs.existsSync(scriptsRoot)) {
    return;
  }

  for (const entry of fs.readdirSync(scriptsRoot, { recursive: true, withFileTypes: true })) {
    if (!entry.isFile()) {
      continue;
    }
    const filePath = path.join(entry.parentPath || scriptsRoot, entry.name);
    fs.chmodSync(filePath, 0o755);
  }
}

function installSkill({
  packageRoot,
  targetRoot,
  skillName,
  timestamp = new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 14),
} = {}) {
  if (!packageRoot) {
    throw new Error("packageRoot is required");
  }
  if (!targetRoot) {
    throw new Error("targetRoot is required");
  }
  if (!skillName) {
    throw new Error("skillName is required");
  }

  const sourceSkill = path.join(packageRoot, "skills", skillName);
  ensureSkillExists(sourceSkill, skillName);

  fs.mkdirSync(targetRoot, { recursive: true, mode: 0o755 });
  const destination = path.join(targetRoot, skillName);
  let backupPath = "";
  if (fs.existsSync(destination)) {
    backupPath = uniqueBackupPath(destination, timestamp);
    fs.renameSync(destination, backupPath);
  }

  copyDirectory(sourceSkill, destination);
  chmodScripts(destination);
  ensureSkillExists(destination, skillName);

  return {
    skillName,
    installedTo: destination,
    backupPath,
  };
}

module.exports = {
  defaultTargetRoot,
  installSkill,
};
