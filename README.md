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

On first use, the agent asks for the OpsForge username and password. After a successful login, credentials are saved locally in `~/.opsforge-skills/config.json` so expired sessions can be refreshed automatically.

The release target is always the remote branch with the same name as the current branch. Local uncommitted or untracked files are ignored and are not released. If the remote branch does not exist, the helper creates it with:

```bash
git push -u origin HEAD:<current-branch>
```

That command only pushes the current committed `HEAD`; it does not stage, commit, or push local worktree changes.

## Safety

- Production releases are blocked.
- OpsForge base URL is fixed to `https://opsforge.byai-inc.com`.
- Usernames and passwords are never bundled in this repository or printed in logs.
- Usernames and passwords are saved only on the user's machine in `~/.opsforge-skills/config.json`; the file is written with `0600` permissions.
- Session cookies are cached under `~/.opsforge-skills/cache`.
- Local uncommitted or untracked files are never pushed by the helper.
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
