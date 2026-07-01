---
name: opsforge-release
description: Release the current Git branch to internal OpsForge non-production environments from natural-language requests such as "发布到腾讯云测试"; use for local AI agents helping engineers publish a service branch through OpsForge, with production release blocked.
---

# OpsForge Release

Use this skill when the user asks to release, deploy, or publish the current service branch to an OpsForge non-production environment, especially with Chinese phrases like `发布到腾讯云测试`, `发测试环境`, or `部署到预发`.

## Operating Rules

- Treat the user's natural-language release request as the entrypoint. Do not ask the user to run low-level helper commands.
- Use the current working directory as the service repository.
- Use the current Git branch as the release branch.
- Infer the OpsForge app name from `git remote get-url origin`; ask for the service name only if inference fails.
- Use the fixed OpsForge base URL `https://opsforge.byai-inc.com`.
- Reject production release intent immediately. Do not confirm, inspect release pools, or call OpsForge release APIs for production.
- Require a human confirmation before triggering release. If the user has not replied with a clear release confirmation such as `发布` or `确认发布`, stop after presenting the summary.
- Never print passwords, cookies, tokens, or authorization headers.

## First Use

Run the inspect pass first. If `auth.status` is `missing` or `session_cookie_only`, ask the user for their OpsForge username and password before presenting the final release summary. After a successful login, the helper writes credentials to `~/.opsforge-skills/config.json` with `0600` permissions and caches session cookies under `~/.opsforge-skills/cache`.

Treat `config.json` as the long-lived local credential source. If a later OpsForge request returns 401/403, the helper uses this file to refresh the session once and retry the request without asking the user again.

## Helper

Use `scripts/opsforge_release.py` internally for deterministic checks and API calls. Typical flow:

1. Run an inspect/preflight pass from the service repository to resolve environment, branch, app name, and Git gates.
2. If credentials are missing, ask for username/password; do not treat credential input as release confirmation.
3. Show the release confirmation summary to the user, including app, branch, environment, Git status, and auth status.
4. After clear confirmation, run the release pass.
5. Report the returned `buildId` and release-pool evidence.

## Required Gates

- Current directory must be a Git repository.
- Current branch must not be detached.
- Worktree must not contain uncommitted changes unless the user explicitly requests `空发`. For `空发`, rerun the helper with `--empty-release`; this ignores local uncommitted/untracked files and publishes the current remote branch only.
- Current branch must not contain unpushed commits.
- Production environment aliases such as `生产`, `线上`, `正式环境`, `prod`, `production`, or `tencent-prod` must be rejected.
- Existing release-pool changes must be preserved. If the current branch is already in the target pool, reuse that change and do not create another one.
