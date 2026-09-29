"""Configuration safety checks with a synthetic password and mocked hasher."""

import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import configure


class ConfigureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.password = "synthetic-demo-password-only"
        self.hash = "$2a$14$" + "A" * 53
        previous_umask = os.umask(0o077)
        self.addCleanup(os.umask, previous_umask)

    def invoke(self, *extra: str, domain: str = "demo.example.com") -> None:
        with (
            patch.object(configure, "ROOT", self.root),
            patch("sys.argv", ["configure.py", "--domain", domain, *extra]),
            patch("getpass.getpass", return_value=self.password),
            patch("subprocess.check_output", return_value="abcdef123456\n"),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            configure.main()

    def test_password_only_uses_stdin_and_hash_is_saved(self) -> None:
        result = subprocess.CompletedProcess([], 0, (self.hash + "\n").encode(), b"")
        with patch("subprocess.run", return_value=result) as run:
            self.invoke()
        self.assertNotIn(self.password, str(run.call_args.args))
        self.assertEqual(run.call_args.kwargs["input"], (self.password + "\n").encode())
        saved = (self.root / "secrets/cloud-auth.caddy").read_text()
        self.assertEqual(saved, "demo " + self.hash + "\n")
        self.assertNotIn(self.password, saved)
        self.assertIn("HARU_DEMO_AI=off", (self.root / ".env.cloud").read_text())

    def test_existing_settings_are_not_overwritten(self) -> None:
        (self.root / ".env.cloud").write_text("existing")
        with patch("subprocess.run") as run, self.assertRaises(SystemExit):
            self.invoke()
        run.assert_not_called()
        self.assertEqual((self.root / ".env.cloud").read_text(), "existing")

    def test_failed_rotation_preserves_original_hash_and_settings(self) -> None:
        (self.root / "secrets").mkdir()
        auth = self.root / "secrets/cloud-auth.caddy"
        auth.write_text("original-hash")
        (self.root / ".env.cloud").write_text("original-settings")
        result = subprocess.CompletedProcess([], 0, b"not-a-valid-hash", b"")
        with (
            patch("subprocess.run", return_value=result),
            self.assertRaises(RuntimeError),
        ):
            self.invoke("--rotate-password")
        self.assertEqual(auth.read_text(), "original-hash")
        self.assertEqual((self.root / ".env.cloud").read_text(), "original-settings")

    def test_domain_cannot_inject_proxy_configuration(self) -> None:
        with patch("subprocess.run") as run, self.assertRaises(SystemExit):
            self.invoke(domain="demo.example.com\n}")
        run.assert_not_called()
        self.assertFalse((self.root / ".env.cloud").exists())


if __name__ == "__main__":
    unittest.main()
