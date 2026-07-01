#!/usr/bin/env python3
"""Internal OpsForge release helper for local AI-agent skills."""

from __future__ import annotations

import argparse
import getpass
import http.cookiejar
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


BASE_URL = "https://opsforge.byai-inc.com"
SOURCE_PROFILE_ENV_CODE = "tencent-prod"
CONFIG_DIR = Path.home() / ".opsforge-skills"
CONFIG_FILE = CONFIG_DIR / "config.json"
CACHE_DIR = CONFIG_DIR / "cache"
COOKIE_FILE = CACHE_DIR / "opsforge-cookies.txt"
PROD_ENV_ALIASES = (
    "tencent-prod",
    "production",
    "prod",
    "腾讯云生产",
    "生产环境",
    "正式环境",
    "线上环境",
    "生产",
    "正式",
    "线上",
)
ENV_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tencent-test", ("腾讯云测试", "测试环境", "发测试", "测试")),
    ("tencent-dev", ("腾讯云开发", "开发环境", "发开发", "开发")),
    ("tencent-pre", ("腾讯云预发", "预发环境", "发预发", "预发")),
    ("tencent-xjp-pre", ("新加坡预发", "xjp-pre", "sg-pre", "tencent-xjp-pre")),
)
CONFIRM_WORDS = ("确认发布", "发布", "继续发布", "确认", "继续", "可以")
CANCEL_WORDS = ("取消", "不要", "先等等", "停止", "别发", "不发")
SENSITIVE_PATTERN = re.compile(
    r"(?i)\b(password|passwd|token|secret|authorization|cookie|set-cookie)\b\s*[:=]\s*[^,\s;}]+"
)
SENSITIVE_KEYS = {"password", "passwd", "token", "secret", "authorization", "cookie", "set-cookie"}


class OpsForgeSkillError(RuntimeError):
    def __init__(self, error_type: str, message: str, detail: Any | None = None):
        self.error_type = error_type
        self.detail = detail
        super().__init__(message)


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, val in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                sanitized[key] = "<redacted>"
            else:
                sanitized[key] = sanitize(val)
        return sanitized
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        return SENSITIVE_PATTERN.sub(r"\1=<redacted>", value)
    return value


def resolve_env_code(text: str) -> str:
    normalized = str(text or "").strip().lower()
    if not normalized:
        raise OpsForgeSkillError("ENV_NOT_RESOLVED", "无法识别发布环境")

    for alias in PROD_ENV_ALIASES:
        if alias.lower() in normalized:
            raise OpsForgeSkillError(
                "PROD_RELEASE_NOT_SUPPORTED",
                "当前 skill 不支持生产发布。请通过 OpsForge 人工发布流程或公司规定的生产发布流程处理。",
            )

    for env_code, aliases in ENV_ALIASES:
        if env_code.lower() in normalized:
            return env_code
        for alias in aliases:
            if alias.lower() in normalized:
                return env_code

    raise OpsForgeSkillError("ENV_NOT_RESOLVED", "无法识别发布环境")


def is_release_confirmation(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    if any(word in normalized for word in CANCEL_WORDS):
        return False
    return any(word in normalized for word in CONFIRM_WORDS)


def infer_app_name_from_remote(remote_url: str) -> str:
    value = str(remote_url or "").strip()
    if not value:
        return ""

    if ":" in value and not value.startswith(("http://", "https://", "ssh://")):
        value = value.rsplit(":", 1)[-1]
    else:
        parsed = urllib.parse.urlparse(value)
        value = parsed.path or value

    name = value.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name.strip()


def change_id_of(change: dict[str, Any]) -> str:
    for key in ("changeId", "id"):
        raw = change.get(key)
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return ""


def branch_of(change: dict[str, Any]) -> str:
    for key in ("branch", "changeBranch", "sourceBranch"):
        raw = change.get(key)
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return ""


def find_pool_change_by_branch(pool_changes: list[dict[str, Any]], branch: str) -> dict[str, Any] | None:
    target = str(branch or "").strip()
    for change in pool_changes:
        if branch_of(change) == target:
            return change
    return None


def run_git(repo_path: str, args: list[str], *, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and proc.returncode != 0:
        raise OpsForgeSkillError("GIT_ERROR", proc.stderr.strip() or proc.stdout.strip())
    return proc.stdout.strip()


def collect_git_context(repo_path: str, *, empty_release: bool = False) -> dict[str, Any]:
    root = run_git(repo_path, ["rev-parse", "--show-toplevel"])
    branch = run_git(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    if branch == "HEAD":
        raise OpsForgeSkillError("DETACHED_HEAD", "当前仓库处于 detached HEAD，无法发布")

    status = run_git(root, ["status", "--porcelain"])
    local_changes_ignored: list[str] = []
    if status and not empty_release:
        raise OpsForgeSkillError(
            "DIRTY_WORKTREE",
            "当前工作区存在未提交或未跟踪文件。请提交/清理后再发布；如果确认这些本地改动不参与本次发布，可以回复“空发”，skill 将基于远端当前分支继续发布。",
            {"status": status.splitlines()},
        )
    if status and empty_release:
        local_changes_ignored = status.splitlines()

    remote = run_git(root, ["remote", "get-url", "origin"])
    app_name = infer_app_name_from_remote(remote)
    if not app_name:
        raise OpsForgeSkillError("APP_NOT_RESOLVED", "无法从 git remote 推断服务名")

    upstream = run_git(root, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], check=False)
    if upstream:
        ahead = run_git(root, ["rev-list", "--count", f"{upstream}..HEAD"])
        if ahead and int(ahead) > 0:
            raise OpsForgeSkillError("BRANCH_NOT_PUSHED", "当前分支存在未 push commit，请先 push 后再发布")

    return {
        "repoPath": root,
        "branch": branch,
        "remote": remote,
        "appName": app_name,
        "emptyRelease": bool(empty_release),
        "localChangesIgnored": local_changes_ignored,
    }


def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CONFIG_DIR, 0o700)


def ensure_cache_dir() -> None:
    ensure_config_dir()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CACHE_DIR, 0o700)


def save_credentials(username: str, password: str) -> None:
    if not username or not password:
        raise OpsForgeSkillError("AUTH_REQUIRED", "OpsForge 需要登录，请输入用户名和密码。")
    ensure_config_dir()
    tmp_file = CONFIG_FILE.with_name(f"{CONFIG_FILE.name}.tmp")
    fd = os.open(tmp_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fp:
        json.dump({"username": username, "password": password}, fp, ensure_ascii=False, indent=2)
        fp.write("\n")
    os.replace(tmp_file, CONFIG_FILE)
    os.chmod(CONFIG_FILE, 0o600)


def load_credentials() -> dict[str, str] | None:
    if not CONFIG_FILE.exists():
        return None
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    username = str(payload.get("username") or payload.get("userName") or "").strip()
    password = str(payload.get("password") or "").strip()
    if not username or not password:
        return None
    return {"username": username, "password": password}


def auth_cache_status() -> dict[str, Any]:
    has_credentials = load_credentials() is not None
    has_cookie = COOKIE_FILE.exists()
    if has_credentials:
        status = "credential_config_present"
    elif has_cookie:
        status = "session_cookie_only"
    else:
        status = "missing"
    return {
        "status": status,
        "hasCredentialConfig": has_credentials,
        "hasSessionCookie": has_cookie,
        "configPath": str(CONFIG_FILE),
        "cookiePath": str(COOKIE_FILE),
    }


class OpsForgeClient:
    def __init__(self, base_url: str = BASE_URL, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        ensure_cache_dir()
        self.cookie_jar = http.cookiejar.MozillaCookieJar(str(COOKIE_FILE))
        if COOKIE_FILE.exists():
            try:
                self.cookie_jar.load(ignore_discard=True, ignore_expires=True)
            except (OSError, http.cookiejar.LoadError):
                self.cookie_jar.clear()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar))

    def save_cookies(self) -> None:
        ensure_cache_dir()
        self.cookie_jar.save(ignore_discard=True, ignore_expires=True)
        os.chmod(COOKIE_FILE, 0o600)

    def request(
        self,
        method: str,
        path: str,
        body: Any | None = None,
        query: dict[str, Any] | None = None,
        *,
        allow_auth_retry: bool = True,
    ) -> Any:
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            finally:
                exc.close()
            if exc.code in (401, 403):
                if allow_auth_retry and self.refresh_session_from_config():
                    return self.request(method, path, body, query, allow_auth_retry=False)
                raise OpsForgeSkillError("AUTH_REQUIRED", "OpsForge 需要登录，请输入用户名和密码。")
            raise OpsForgeSkillError("HTTP_ERROR", f"OpsForge HTTP {exc.code}: {sanitize(detail)}")
        except urllib.error.URLError as exc:
            raise OpsForgeSkillError("HTTP_ERROR", f"OpsForge request failed: {sanitize(str(exc))}")

        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OpsForgeSkillError("HTTP_RESPONSE_INVALID", f"OpsForge returned non-JSON response: {exc}")

    def login(self, username: str, password: str, *, persist: bool = True) -> Any:
        if not username or not password:
            raise OpsForgeSkillError("AUTH_REQUIRED", "OpsForge 需要登录，请输入用户名和密码。")
        result = self.request(
            "POST",
            "/api/user/login",
            {"userName": username, "password": password},
            allow_auth_retry=False,
        )
        self.save_cookies()
        if persist:
            save_credentials(username, password)
        return result

    def refresh_session_from_config(self) -> bool:
        credentials = load_credentials()
        if not credentials:
            return False
        try:
            self.login(credentials["username"], credentials["password"], persist=False)
            return True
        except OpsForgeSkillError:
            return False

    def get_profile(self, app_name: str, env_code: str) -> dict[str, Any]:
        return require_success(self.request("GET", f"/api/v1/app/{quote(app_name)}/profile/{quote(env_code)}"))

    def get_pool_changes(self, app_name: str, env_code: str) -> list[dict[str, Any]]:
        data = require_success(self.request("GET", f"/api/v2/app/{quote(app_name)}/release/{quote(env_code)}/changes"))
        return list_payload(data)

    def list_changes(self, app_name: str, branch: str) -> list[dict[str, Any]]:
        data = require_success(
            self.request("GET", f"/api/v1/app/{quote(app_name)}/changes", query={"branch": branch, "pageSize": 50})
        )
        return list_payload(data)

    def create_change(self, app_name: str, branch: str, base_branch: str) -> Any:
        return require_success(
            self.request(
                "POST",
                f"/api/v1/app/{quote(app_name)}/change",
                {
                    "appName": app_name,
                    "name": f"{branch} release",
                    "branch": branch,
                    "baseBranch": base_branch,
                    "deleteBranchAfterDone": False,
                    "useExistingBranch": True,
                },
            )
        )

    def release_changes(self, app_name: str, env_code: str, changes: list[dict[str, Any]]) -> Any:
        return require_success(
            self.request(
                "POST",
                f"/api/v2/app/{quote(app_name)}/release/{quote(env_code)}/changes",
                {"changes": changes},
            )
        )


def quote(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def require_success(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    if payload.get("success") is False or payload.get("code") not in (None, 0, "0", 200, "200"):
        raise OpsForgeSkillError("OPSFORGE_ERROR", "OpsForge API returned failure", sanitize(payload))
    for key in ("data", "result"):
        if key in payload:
            return payload[key]
    return payload


def list_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "records", "list", "changes", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def normalize_change(change: dict[str, Any], app_name: str, branch: str, base_branch: str) -> dict[str, Any]:
    enriched = dict(change)
    enriched["changeId"] = change_id_of(enriched)
    enriched["appName"] = enriched.get("appName") or app_name
    enriched["branch"] = enriched.get("branch") or branch
    enriched["baseBranch"] = enriched.get("baseBranch") or base_branch
    enriched["deleteBranchAfterDone"] = False
    enriched["useExistingBranch"] = True
    return enriched


def merge_pool(pool: list[dict[str, Any]], current: dict[str, Any]) -> list[dict[str, Any]]:
    current_id = change_id_of(current)
    if not current_id:
        raise OpsForgeSkillError("CHANGE_ID_MISSING", "current change has no changeId")
    merged: list[dict[str, Any]] = []
    replaced = False
    for change in pool:
        if change_id_of(change) == current_id:
            merged.append(current)
            replaced = True
        else:
            merged.append(change)
    if not replaced:
        merged.append(current)
    return merged


def build_preflight(intent_text: str, repo_path: str, *, empty_release: bool = False) -> dict[str, Any]:
    env_code = resolve_env_code(intent_text)
    git_context = collect_git_context(repo_path, empty_release=empty_release)
    return {
        "ok": True,
        "baseUrl": BASE_URL,
        "envCode": env_code,
        "auth": auth_cache_status(),
        **git_context,
    }


def run_inspect(args: argparse.Namespace) -> dict[str, Any]:
    context = build_preflight(args.intent_text, args.repo_path, empty_release=args.empty_release)
    if args.username:
        password = args.password or getpass.getpass("OpsForge password: ")
        client = OpsForgeClient(timeout=args.timeout)
        client.login(args.username, password)
        context["auth"] = auth_cache_status()
    return context


def run_release(args: argparse.Namespace) -> dict[str, Any]:
    if not is_release_confirmation(args.confirmation):
        raise OpsForgeSkillError("CONFIRMATION_REQUIRED", "发布前必须获得用户明确确认")

    context = build_preflight(args.intent_text, args.repo_path, empty_release=args.empty_release)
    client = OpsForgeClient(timeout=args.timeout)
    if args.username:
        password = args.password or getpass.getpass("OpsForge password: ")
        client.login(args.username, password)
    elif load_credentials() and not COOKIE_FILE.exists():
        client.refresh_session_from_config()

    app_name = args.app_name or context["appName"]
    env_code = context["envCode"]
    branch = context["branch"]

    profile = client.get_profile(app_name, SOURCE_PROFILE_ENV_CODE)
    base_branch = str(profile.get("defaultBranch") or profile.get("default_branch") or "").strip()
    if not base_branch:
        raise OpsForgeSkillError("DEFAULT_BRANCH_MISSING", "OpsForge profile.defaultBranch is empty")

    pool_before = client.get_pool_changes(app_name, env_code)
    current = find_pool_change_by_branch(pool_before, branch)
    change_source = "release_pool"
    if current is None:
        changes = client.list_changes(app_name, branch)
        current = changes[0] if changes else None
        change_source = "existing_change" if current else "created_change"
        if current is None:
            client.create_change(app_name, branch, base_branch)
            changes = client.list_changes(app_name, branch)
            if not changes:
                raise OpsForgeSkillError("CHANGE_NOT_FOUND", "change was created but cannot be queried")
            current = changes[0]

    current = normalize_change(current, app_name, branch, base_branch)
    pool_target = merge_pool(pool_before, current)
    release_result = client.release_changes(app_name, env_code, pool_target)

    return {
        "ok": True,
        **context,
        "appName": app_name,
        "changeSource": change_source,
        "changeId": change_id_of(current),
        "poolBeforeChangeIds": [change_id_of(change) for change in pool_before if change_id_of(change)],
        "poolTargetChangeIds": [change_id_of(change) for change in pool_target if change_id_of(change)],
        "releaseResult": sanitize(release_result),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OpsForge local skill helper.")
    parser.add_argument("--action", choices=("inspect", "release"), default="inspect")
    parser.add_argument("--intent-text", required=True)
    parser.add_argument("--repo-path", default=".")
    parser.add_argument("--confirmation", default="")
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--app-name", default="")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--empty-release", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        result = run_release(args) if args.action == "release" else run_inspect(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except OpsForgeSkillError as exc:
        print(
            json.dumps(
                {"ok": False, "errorType": exc.error_type, "message": str(exc), "detail": sanitize(exc.detail)},
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
