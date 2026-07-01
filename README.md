# OpsForge Skills

Internal skill package for installing the `opsforge-release` skill into local AI-agent environments.

## Install

```bash
npx --yes --package git+ssh://git@github.com/Caius1L/opsforge-skills.git#main \
  opsforge-skills install opsforge-release
```

By default the installer writes to:

1. `$CODEX_HOME/skills` when `CODEX_HOME` is set.
2. `~/.codex/skills` when `~/.codex` exists or no agent home exists.
3. `~/.agents/skills` when only `~/.agents` exists.

## Use

After installation, open a service repository in your local AI agent and ask:

```text
发布到腾讯云测试
```

The skill uses the current Git repository and branch, infers the OpsForge app from `origin`, checks release gates, asks for confirmation, and then releases through OpsForge.

## Safety

- Production releases are blocked.
- OpsForge base URL is fixed to `https://opsforge.byai-inc.com`.
- Usernames and passwords are never bundled in this repository.
- The release helper caches only session cookies under `~/.opsforge-skills/cache`.
- Existing OpsForge release-pool changes are preserved.

## Development

```bash
npm test
```

Before pushing, verify the install path with an isolated `CODEX_HOME`:

```bash
CODEX_HOME="$(mktemp -d)" \
npx --yes --package git+ssh://git@github.com/Caius1L/opsforge-skills.git#main \
  opsforge-skills install opsforge-release
```
