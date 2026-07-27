import importlib.util
import json
import stat
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "deploy" / "install_webhook.py"
SPEC = importlib.util.spec_from_file_location("install_webhook", MODULE_PATH)
assert SPEC and SPEC.loader
install_webhook = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(install_webhook)


class InstallWebhookTests(unittest.TestCase):
    def test_secret_and_hook_installation_are_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret_file = root / "webhook-secret"
            hooks_file = root / "hooks.json"
            hooks_file.write_text(
                json.dumps([{"id": "existing-hook", "execute-command": "/bin/true"}]),
                encoding="utf-8",
            )

            secret = install_webhook.load_or_create_secret(secret_file)
            self.assertEqual(secret, install_webhook.load_or_create_secret(secret_file))
            self.assertEqual(stat.S_IMODE(secret_file.stat().st_mode), 0o600)

            hook = install_webhook.build_hook(
                secret=secret,
                repository="owner/repository",
            )
            self.assertTrue(install_webhook.update_hooks(hooks_file, hook))
            self.assertFalse(install_webhook.update_hooks(hooks_file, hook))

            hooks = json.loads(hooks_file.read_text(encoding="utf-8"))
            self.assertEqual(
                [item["id"] for item in hooks],
                ["existing-hook", "deploy-youtube-bot"],
            )
            self.assertEqual(
                len(list(root.glob("hooks.json.backup-*"))),
                1,
            )


if __name__ == "__main__":
    unittest.main()
