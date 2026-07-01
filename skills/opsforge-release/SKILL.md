---
name: opsforge-release
description: Release the current Git branch to internal OpsForge non-production environments from natural-language requests such as "发布到腾讯云测试"; use for local AI agents helping engineers publish a service branch through OpsForge, with production release blocked.
---

# OpsForge Release

Use this skill when the user asks to release, deploy, or publish the current service branch to an OpsForge non-production environment, especially with Chinese phrases like `发布到腾讯云测试`, `发测试环境`, or `部署到预发`.

## Operating Rules

- Treat the user's natural-language release request as the entrypoint. Do not ask the user to run low-level helper commands.
- Use the current working directory as the service repository.
- Release the remote branch with the same name as the current Git branch. Local uncommitted or untracked files are never part of the release.
- Infer the OpsForge app name from `git remote get-url origin`; ask for the service name only if inference fails.
- Use the fixed OpsForge base URL `https://opsforge.byai-inc.com`.
- Reject production release intent immediately. Do not confirm, inspect release pools, or call OpsForge release APIs for production.
- Treat the user's non-production release request as release authorization. Do not ask for a second `确认发布` reply.
- Never print passwords, cookies, tokens, or authorization headers.

## First Use

Run the inspect pass first. If `auth.status` is `missing` or `session_cookie_only`, ask the user for their OpsForge username and password, then continue the release directly after successful login. After a successful login, the helper writes credentials to `~/.opsforge-skills/config.json` with `0600` permissions and caches session cookies under `~/.opsforge-skills/cache`.

Treat `config.json` as the long-lived local credential source. If a later OpsForge request returns 401/403, the helper uses this file to refresh the session once and retry the request without asking the user again.

## Helper

Use `scripts/opsforge_release.py` internally for deterministic checks and API calls. Typical flow:

1. Run an inspect/preflight pass from the service repository to resolve environment, branch, app name, and Git gates. If `origin/<current-branch>` does not exist, the helper runs `git push -u origin HEAD:<current-branch>` before continuing.
2. If credentials are missing, ask for username/password and continue directly after login succeeds.
3. Run the release pass without requiring a second confirmation message.
4. Report a concise result: app, environment, branch, changeId, and OpsForge returned id. Do not list release-pool change IDs, risk tables, or confidence commentary unless the user asks for troubleshooting details.

## Required Gates

- Current directory must be a Git repository.
- Current branch must not be detached.
- Local uncommitted or untracked files do not block release and are not pushed. The helper only pushes the current `HEAD` commit when it needs to create a missing remote branch.
- If `origin/<current-branch>` does not exist, create it with `git push -u origin HEAD:<current-branch>`. This only pushes committed objects reachable from `HEAD`; it never stages, commits, or pushes worktree changes.
- If `origin/<current-branch>` exists but does not match local `HEAD`, stop and ask the user to push deliberately before release.
- Production environment aliases such as `生产`, `线上`, `正式环境`, `prod`, `production`, or `tencent-prod` must be rejected.
- Existing release-pool changes must be preserved. If the current branch is already in the target pool, reuse that change and do not create another one.
