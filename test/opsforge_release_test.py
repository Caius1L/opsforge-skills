import importlib.util
import io
import json
import pathlib
import stat
import sys
import tempfile
import unittest
import urllib.error
from argparse import Namespace


sys.dont_write_bytecode = True
MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "skills" / "opsforge-release" / "scripts" / "opsforge_release.py"
SPEC = importlib.util.spec_from_file_location("opsforge_release", MODULE_PATH)
ops = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ops)


class OpsForgeReleaseTest(unittest.TestCase):
    def use_temp_opsforge_home(self, tmpdir):
        base = pathlib.Path(tmpdir) / ".opsforge-skills"
        ops.CONFIG_DIR = base
        ops.CONFIG_FILE = base / "config.json"
        ops.CACHE_DIR = base / "cache"
        ops.COOKIE_FILE = ops.CACHE_DIR / "opsforge-cookies.txt"

    def test_resolves_chinese_test_environment(self):
        self.assertEqual(ops.resolve_env_code("发布到腾讯云测试"), "tencent-test")
        self.assertEqual(ops.resolve_env_code("帮我发测试环境"), "tencent-test")

    def test_rejects_production_environment(self):
        with self.assertRaises(ops.OpsForgeSkillError) as ctx:
            ops.resolve_env_code("发布到生产")
        self.assertEqual(ctx.exception.error_type, "PROD_RELEASE_NOT_SUPPORTED")

    def test_infers_app_name_from_git_remote(self):
        self.assertEqual(ops.infer_app_name_from_remote("git@github.com:org/sop.git"), "sop")
        self.assertEqual(
            ops.infer_app_name_from_remote("https://gitlab.indata.cc/indata/sop-web-service.git"),
            "sop-web-service",
        )

    def test_finds_pool_change_by_branch(self):
        pool = [
            {"changeId": "a", "branch": "feature/other"},
            {"changeId": "b", "branch": "feature/current"},
        ]
        self.assertEqual(ops.find_pool_change_by_branch(pool, "feature/current")["changeId"], "b")
        self.assertIsNone(ops.find_pool_change_by_branch(pool, "feature/missing"))

    def test_persists_credentials_to_private_config_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.use_temp_opsforge_home(tmpdir)

            ops.save_credentials("alice", "secret")

            self.assertEqual(ops.load_credentials(), {"username": "alice", "password": "secret"})
            self.assertEqual(stat.S_IMODE(ops.CONFIG_DIR.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(ops.CONFIG_FILE.stat().st_mode), 0o600)

    def test_auth_cache_status_reports_missing_and_saved_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.use_temp_opsforge_home(tmpdir)

            self.assertEqual(ops.auth_cache_status()["status"], "missing")

            ops.save_credentials("alice", "secret")

            status = ops.auth_cache_status()
            self.assertEqual(status["status"], "credential_config_present")
            self.assertTrue(status["hasCredentialConfig"])
            self.assertFalse(status["hasSessionCookie"])

    def test_sanitize_redacts_sensitive_dict_values(self):
        payload = {"password": "secret", "nested": {"token": "abc"}, "safe": "value"}

        self.assertEqual(
            ops.sanitize(payload),
            {"password": "<redacted>", "nested": {"token": "<redacted>"}, "safe": "value"},
        )

    def test_collect_git_context_defaults_to_remote_branch_release_with_dirty_worktree(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = pathlib.Path(tmpdir)
            remote = base / "remote.git"
            repo = base / "repo"
            repo.mkdir()
            ops.run_git(str(base), ["init", "--bare", str(remote)])
            ops.run_git(str(repo), ["init"])
            ops.run_git(str(repo), ["config", "user.email", "tester@example.com"])
            ops.run_git(str(repo), ["config", "user.name", "Tester"])
            (repo / "README.md").write_text("initial\n", encoding="utf-8")
            ops.run_git(str(repo), ["add", "README.md"])
            ops.run_git(str(repo), ["commit", "-m", "init"])
            ops.run_git(str(repo), ["remote", "add", "origin", str(remote)])
            (repo / "local-only.txt").write_text("dirty\n", encoding="utf-8")

            context = ops.collect_git_context(str(repo))
            self.assertTrue(context["emptyRelease"])
            self.assertIn("?? local-only.txt", context["localChangesIgnored"])

    def test_collect_git_context_auto_pushes_missing_remote_branch_without_uncommitted_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = pathlib.Path(tmpdir)
            remote = base / "remote.git"
            repo = base / "repo"
            repo.mkdir()
            ops.run_git(str(base), ["init", "--bare", str(remote)])
            ops.run_git(str(repo), ["init"])
            ops.run_git(str(repo), ["config", "user.email", "tester@example.com"])
            ops.run_git(str(repo), ["config", "user.name", "Tester"])
            ops.run_git(str(repo), ["checkout", "-b", "test_skill_v2"])
            (repo / "README.md").write_text("committed\n", encoding="utf-8")
            ops.run_git(str(repo), ["add", "README.md"])
            ops.run_git(str(repo), ["commit", "-m", "init"])
            ops.run_git(str(repo), ["remote", "add", "origin", str(remote)])
            (repo / "local-only.txt").write_text("must not be pushed\n", encoding="utf-8")

            context = ops.collect_git_context(str(repo))

            self.assertTrue(context["remoteBranchExists"])
            self.assertTrue(context["remoteBranchAutoPushed"])
            self.assertEqual(context["pushedRefspec"], "HEAD:test_skill_v2")
            tree = ops.run_git(
                str(repo),
                ["--git-dir", str(remote), "ls-tree", "-r", "--name-only", "refs/heads/test_skill_v2"],
            )
            self.assertIn("README.md", tree.splitlines())
            self.assertNotIn("local-only.txt", tree.splitlines())

    def test_collect_git_context_does_not_push_when_remote_branch_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = pathlib.Path(tmpdir)
            remote = base / "remote.git"
            repo = base / "repo"
            repo.mkdir()
            ops.run_git(str(base), ["init", "--bare", str(remote)])
            ops.run_git(str(repo), ["init"])
            ops.run_git(str(repo), ["config", "user.email", "tester@example.com"])
            ops.run_git(str(repo), ["config", "user.name", "Tester"])
            ops.run_git(str(repo), ["checkout", "-b", "test_skill_v2"])
            (repo / "README.md").write_text("committed\n", encoding="utf-8")
            ops.run_git(str(repo), ["add", "README.md"])
            ops.run_git(str(repo), ["commit", "-m", "init"])
            ops.run_git(str(repo), ["remote", "add", "origin", str(remote)])
            ops.run_git(str(repo), ["push", "-u", "origin", "HEAD:test_skill_v2"])

            context = ops.collect_git_context(str(repo))

            self.assertTrue(context["remoteBranchExists"])
            self.assertFalse(context["remoteBranchAutoPushed"])
            self.assertEqual(context["pushedRefspec"], "")

    def test_request_refreshes_session_from_saved_config_after_403(self):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(self.payload).encode("utf-8")

        class FakeOpener:
            def __init__(self):
                self.calls = []
                self.protected_attempts = 0

            def open(self, request, timeout):
                self.calls.append((request.get_method(), request.full_url, request.data))
                if request.full_url.endswith("/api/protected"):
                    self.protected_attempts += 1
                    if self.protected_attempts == 1:
                        raise urllib.error.HTTPError(
                            request.full_url,
                            403,
                            "Forbidden",
                            {},
                            io.BytesIO(b"forbidden"),
                        )
                    return FakeResponse({"success": True, "data": {"value": 1}})
                if request.full_url.endswith("/api/user/login"):
                    return FakeResponse({"success": True, "data": {"ok": True}})
                raise AssertionError(request.full_url)

        with tempfile.TemporaryDirectory() as tmpdir:
            self.use_temp_opsforge_home(tmpdir)
            ops.save_credentials("alice", "secret")
            client = ops.OpsForgeClient()
            fake_opener = FakeOpener()
            client.opener = fake_opener

            self.assertEqual(client.request("GET", "/api/protected"), {"success": True, "data": {"value": 1}})
            methods = [method for method, _url, _data in fake_opener.calls]
            self.assertEqual(methods, ["GET", "POST", "GET"])

    def test_inspect_with_credentials_logs_in_and_reports_saved_config_before_release(self):
        class FakeClient:
            def __init__(self, timeout):
                self.timeout = timeout

            def login(self, username, password):
                ops.save_credentials(username, password)
                return {"ok": True}

        with tempfile.TemporaryDirectory() as tmpdir:
            self.use_temp_opsforge_home(tmpdir)
            repo = pathlib.Path(tmpdir) / "repo"
            repo.mkdir()
            ops.run_git(str(repo), ["init"])
            ops.run_git(str(repo), ["config", "user.email", "tester@example.com"])
            ops.run_git(str(repo), ["config", "user.name", "Tester"])
            (repo / "README.md").write_text("initial\n", encoding="utf-8")
            ops.run_git(str(repo), ["add", "README.md"])
            ops.run_git(str(repo), ["commit", "-m", "init"])
            remote = pathlib.Path(tmpdir) / "remote.git"
            ops.run_git(str(pathlib.Path(tmpdir)), ["init", "--bare", str(remote)])
            ops.run_git(str(repo), ["remote", "add", "origin", str(remote)])

            original_client = ops.OpsForgeClient
            ops.OpsForgeClient = FakeClient
            try:
                result = ops.run_inspect(
                    Namespace(
                        intent_text="发布到腾讯云测试",
                        repo_path=str(repo),
                        empty_release=False,
                        username="alice",
                        password="secret",
                        timeout=30,
                    )
                )
            finally:
                ops.OpsForgeClient = original_client

            self.assertEqual(result["auth"]["status"], "credential_config_present")
            self.assertEqual(ops.load_credentials(), {"username": "alice", "password": "secret"})

    def test_release_runs_without_confirmation(self):
        class FakeClient:
            def __init__(self, timeout):
                self.timeout = timeout
                self.created = False

            def get_profile(self, app_name, env_code):
                return {"defaultBranch": "master"}

            def get_pool_changes(self, app_name, env_code):
                return []

            def list_changes(self, app_name, branch):
                if not self.created:
                    return []
                return [{"changeId": "change-1", "branch": branch}]

            def create_change(self, app_name, branch, base_branch):
                self.created = True
                return {"ok": True}

            def release_changes(self, app_name, env_code, changes):
                return {"releaseId": "release-1", "changes": len(changes)}

        with tempfile.TemporaryDirectory() as tmpdir:
            self.use_temp_opsforge_home(tmpdir)
            repo = pathlib.Path(tmpdir) / "repo"
            remote = pathlib.Path(tmpdir) / "remote.git"
            repo.mkdir()
            ops.run_git(str(pathlib.Path(tmpdir)), ["init", "--bare", str(remote)])
            ops.run_git(str(repo), ["init"])
            ops.run_git(str(repo), ["config", "user.email", "tester@example.com"])
            ops.run_git(str(repo), ["config", "user.name", "Tester"])
            ops.run_git(str(repo), ["checkout", "-b", "test_skill_v2"])
            (repo / "README.md").write_text("initial\n", encoding="utf-8")
            ops.run_git(str(repo), ["add", "README.md"])
            ops.run_git(str(repo), ["commit", "-m", "init"])
            ops.run_git(str(repo), ["remote", "add", "origin", str(remote)])

            original_client = ops.OpsForgeClient
            ops.OpsForgeClient = FakeClient
            try:
                result = ops.run_release(
                    Namespace(
                        intent_text="发布到腾讯云测试",
                        repo_path=str(repo),
                        empty_release=False,
                        username="",
                        password="",
                        timeout=30,
                        app_name="",
                        confirmation="",
                    )
                )
            finally:
                ops.OpsForgeClient = original_client

            self.assertTrue(result["ok"])
            self.assertEqual(result["changeId"], "change-1")
            self.assertEqual(result["releaseResult"], {"releaseId": "release-1", "changes": 1})


if __name__ == "__main__":
    unittest.main()
