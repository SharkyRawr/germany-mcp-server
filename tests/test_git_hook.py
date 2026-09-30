"""Check hook installation and formatting without changing the real index."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("black"), "System Black is not installed")
class GitHookTest(unittest.TestCase):
    def test_hook_formats_without_staging(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (".githooks", "scripts"):
                shutil.copytree(source / name, root / name)

            def run(*args, check=True):
                return subprocess.run(
                    args, cwd=root, check=check, capture_output=True, text=True
                )

            run("git", "init")
            run("./scripts/setup-hooks.sh")
            self.assertEqual(
                run("git", "config", "--local", "core.hooksPath").stdout.strip(),
                ".githooks",
            )
            code = root / "example.py"
            code.write_text("answer=42\n")
            run("git", "add", "example.py")
            self.assertNotEqual(run(".githooks/pre-commit", check=False).returncode, 0)
            self.assertEqual(code.read_text(), "answer = 42\n")
            self.assertEqual(run("git", "show", ":example.py").stdout, "answer=42\n")
            run("git", "add", "example.py")
            run(".githooks/pre-commit")


if __name__ == "__main__":
    unittest.main()
