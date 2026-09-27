"""Installer checks use isolated command stubs; never install software on the host."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="showandtell install ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "commands.jsonl"
        self.env = {**os.environ, "PATH": str(self.bin), "INSTALL_TEST_ROOT": str(self.root)}
        self.installer = self.copy_script(ROOT / "install.sh", self.root / "install.sh")
        self.command("uname", 'print("Darwin")')
        self.command("python3", '''
if "version_info" in sys.argv[-1] and (root / "need-python").exists():
    sys.exit(1)
os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
''')
        self.command("codex", '''
with (root / "commands.jsonl").open("a") as stream:
    stream.write(json.dumps(sys.argv[1:]) + "\\n")
args = sys.argv[1:]
if "--help" in args:
    sys.exit(0)
if args == ["plugin", "marketplace", "list", "--json"]:
    print((root / "marketplaces.json").read_text() if (root / "marketplaces.json").exists() else '{"marketplaces": []}')
elif args[:3] == ["plugin", "marketplace", "add"]:
    (root / "marketplaces.json").write_text(json.dumps({"marketplaces": [{"name": "showandtell", "marketplaceSource": {"sourceType": "git", "source": "https://github.com/milind-soni/showandtell.git"}}]}))
''')
        for name in ("ffmpeg", "ffprobe"):
            self.command(name, 'sys.exit(1 if (root / "need-ffmpeg").exists() else 0)')
        self.command("brew", '''
with (root / "commands.jsonl").open("a") as stream:
    stream.write(json.dumps(["brew", *sys.argv[1:]]) + "\\n")
if (root / "brew-fails").exists():
    sys.exit(1)
if "codex" in sys.argv:
    (root / "bin/codex").write_bytes((root / "codex-template").read_bytes())
    (root / "bin/codex").chmod(0o755)
for package in ("python", "ffmpeg"):
    if package in sys.argv:
        (root / ("need-" + package)).unlink(missing_ok=True)
''')

    def copy_script(self, source, target):
        # Replace both standard Homebrew locations so no host tool can leak into a test.
        target.write_text(source.read_text().replace("/opt/homebrew", str(self.root / "brew-arm"))
                          .replace("/usr/local", str(self.root / "brew-intel")))
        return target

    def command(self, name, code):
        path = self.bin / name
        path.write_text(f"#!{sys.executable}\nimport json, os, pathlib, sys\nroot = pathlib.Path(os.environ['INSTALL_TEST_ROOT'])\n{code}\n")
        path.chmod(0o755)

    def run_installer(self):
        return subprocess.run(["/bin/sh", str(self.installer)], env=self.env,
                              capture_output=True, text=True, timeout=20)

    def commands(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_clean_install_and_repeat_upgrade_only_this_marketplace(self):
        for _ in range(2):
            result = self.run_installer()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("/hooks", result.stdout)
            self.assertIn("does not grant", result.stdout)
        commands = self.commands()
        self.assertEqual(commands.count(["plugin", "marketplace", "add", "milind-soni/showandtell"]), 1)
        self.assertEqual(commands.count(["plugin", "marketplace", "upgrade", "showandtell"]), 1)
        self.assertEqual(commands.count(["plugin", "add", "showandtell@showandtell"]), 2)
        self.assertFalse(any(command[0] == "brew" for command in commands))

    def test_missing_codex_is_installed_but_unsupported_cli_is_not_replaced(self):
        (self.bin / "codex").rename(self.root / "codex-template")
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(["brew", "install", "--cask", "codex"], self.commands())
        self.log.unlink()
        self.command("codex", "sys.exit(1)")
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Update Codex CLI", result.stderr)
        self.assertFalse(self.log.exists())

    def test_missing_dependencies_installed_and_failures_stop_before_plugin_add(self):
        for package in ("python", "ffmpeg"):
            (self.root / ("need-" + package)).touch()
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(["brew", "install", "python"], self.commands())
        self.assertIn(["brew", "install", "ffmpeg"], self.commands())
        self.log.unlink()
        (self.root / "need-ffmpeg").touch()
        (self.root / "brew-fails").touch()
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Homebrew could not install ffmpeg", result.stderr)
        self.assertNotIn(["plugin", "add", "showandtell@showandtell"], self.commands())

    def test_missing_homebrew_and_conflicting_marketplace_are_actionable(self):
        (self.bin / "brew").unlink()
        (self.root / "need-ffmpeg").touch()
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("https://brew.sh", result.stderr)
        (self.root / "need-ffmpeg").unlink()
        (self.root / "marketplaces.json").write_text(json.dumps({"marketplaces": [
            {"name": "showandtell", "marketplaceSource": {"sourceType": "local", "source": "/elsewhere"}}
        ]}))
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("different or local marketplace", result.stderr)
        self.assertNotIn(["plugin", "add", "showandtell@showandtell"], self.commands())

    def test_launcher_skips_old_python_and_preserves_arguments(self):
        launcher = self.copy_script(ROOT / "plugins/showandtell/scripts/run.sh", self.root / "run.sh")
        (self.root / "need-python").touch()
        brew_bin = self.root / "brew-arm/bin"
        brew_bin.mkdir(parents=True)
        (brew_bin / "python3").symlink_to(sys.executable)
        (self.bin / "dirname").symlink_to(shutil.which("dirname"))
        (self.root / "showandtell.py").write_text("import json, os, sys; print(json.dumps([sys.argv[1:], os.environ['PATH']]))")
        result = subprocess.run(["/bin/sh", str(launcher), "hook", "value with spaces"],
                                env=self.env, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        args, path = json.loads(result.stdout)
        self.assertEqual(args, ["hook", "value with spaces"])
        self.assertIn(str(brew_bin), path.split(":"))


if __name__ == "__main__":
    unittest.main()
