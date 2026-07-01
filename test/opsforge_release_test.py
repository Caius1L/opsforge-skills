import importlib.util
import pathlib
import sys
import unittest


sys.dont_write_bytecode = True
MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "skills" / "opsforge-release" / "scripts" / "opsforge_release.py"
SPEC = importlib.util.spec_from_file_location("opsforge_release", MODULE_PATH)
ops = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ops)


class OpsForgeReleaseTest(unittest.TestCase):
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

    def test_confirmation_intent(self):
        self.assertTrue(ops.is_release_confirmation("确认发布"))
        self.assertTrue(ops.is_release_confirmation("发布"))
        self.assertFalse(ops.is_release_confirmation("先等等"))

    def test_finds_pool_change_by_branch(self):
        pool = [
            {"changeId": "a", "branch": "feature/other"},
            {"changeId": "b", "branch": "feature/current"},
        ]
        self.assertEqual(ops.find_pool_change_by_branch(pool, "feature/current")["changeId"], "b")
        self.assertIsNone(ops.find_pool_change_by_branch(pool, "feature/missing"))


if __name__ == "__main__":
    unittest.main()
