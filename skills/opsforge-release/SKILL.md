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

If no valid OpsForge session cache exists, ask the user for their OpsForge username and password. After login, cache only the session/cookie under `~/.opsforge-skills/cache`; do not store the plaintext password.

## Helper

Use `scripts/opsforge_release.py` internally for deterministic checks and API calls. Typical flow:

1. Run an inspect/preflight pass from the service repository to resolve environment, branch, app name, and Git gates.
2. Show the release confirmation summary to the user.
3. After clear confirmation, run the release pass.
4. Report the returned `buildId` and release-pool evidence.

## Required Gates

- Current directory must be a Git repository.
- Current branch must not be detached.
- Worktree must not contain uncommitted changes.
- Current branch must not contain unpushed commits.
- Production environment aliases such as `生产`, `线上`, `正式环境`, `prod`, `production`, or `tencent-prod` must be rejected.
- Existing release-pool changes must be preserved. If the current branch is already in the target pool, reuse that change and do not create another one.
