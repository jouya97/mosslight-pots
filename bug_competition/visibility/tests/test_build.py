import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from bug_competition.visibility.build import ALLOWED_FILES, DOCUMENT_OVERRIDES, build_agent_tree


SOURCE = Path(__file__).resolve().parents[2] / "mosslight"


class VisibilityTests(unittest.TestCase):
    def test_inventory_is_deterministic_and_public_suite_passes(self):
        with tempfile.TemporaryDirectory() as folder:
            first, second = Path(folder) / "first", Path(folder) / "second"
            result = build_agent_tree(SOURCE, first)
            self.assertEqual(result, build_agent_tree(SOURCE, second))
            actual = {p.relative_to(first).as_posix() for p in first.rglob("*") if p.is_file()}
            self.assertEqual(actual, {entry["path"] for entry in result["files"]})
            self.assertEqual(actual, set(ALLOWED_FILES) | {"tests/test_smoke.py"})
            for entry in result["files"]:
                data = (first / entry["path"]).read_bytes()
                self.assertEqual(entry["size"], len(data))
                self.assertEqual(entry["sha256"], hashlib.sha256(data).hexdigest())
            original_tests = {p.relative_to(SOURCE).as_posix() for p in (SOURCE / "tests").rglob("*") if p.is_file()}
            self.assertFalse(original_tests & actual)
            templates = Path(__file__).resolve().parents[1] / "templates"
            for name in DOCUMENT_OVERRIDES:
                self.assertEqual((first / name).read_bytes(), (templates / name).read_bytes())
            for name in ALLOWED_FILES:
                if name.startswith("mosslight/"):
                    self.assertEqual((first / name).read_bytes(), (SOURCE / name).read_bytes())
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
            env.pop("PYTHONPATH", None)
            run = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
                                 cwd=first, env=env, capture_output=True, text=True, timeout=90)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_extra_artifacts_and_symlinks_never_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source, destination = folder / "source", folder / "agent"
            shutil.copytree(SOURCE, source, symlinks=True)
            sentinel = "HOST_ONLY_SENTINEL_76fd90c1"
            for relative in (".env", ".env.local", ".git/config", "manifest.json", "fix.patch",
                             "host_only/answers.py", "archives/clean.py", "clean_snapshot/model.py",
                             "mosslight/manifest.py", "mosslight/.env", "mosslight/host_only/answers.py",
                             "mosslight/static/answers.js", "examples/manifest.json", "tests/test_secret.py"):
                path = source / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(sentinel)
            outside = folder / "private.txt"
            outside.write_text(sentinel)
            (source / "DESIGN.md").unlink()
            (source / "DESIGN.md").symlink_to(outside)
            shutil.rmtree(source / "examples")
            (source / "examples").symlink_to(folder, target_is_directory=True)
            result = build_agent_tree(source, destination)
            for path in destination.rglob("*"):
                self.assertFalse(path.is_symlink())
                if path.is_file():
                    self.assertNotIn(sentinel.encode(), path.read_bytes())
            self.assertNotIn("DESIGN.md", {entry["path"] for entry in result["files"]})
            self.assertFalse((destination / "examples").exists())

    def test_unsafe_destinations_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = folder / "source"
            shutil.copytree(SOURCE, source)
            with self.assertRaises(ValueError):
                build_agent_tree(source, source / "nested")
            with self.assertRaises(ValueError):
                build_agent_tree(source, folder)
            with self.assertRaises(ValueError):
                build_agent_tree(source, folder / "unused" / ".." / "agent")
            existing = folder / "existing"
            existing.mkdir()
            marker = existing / "keep"
            marker.write_text("keep")
            with self.assertRaises(FileExistsError):
                build_agent_tree(source, existing)
            self.assertEqual(marker.read_text(), "keep")
            linked = folder / "linked"
            linked.symlink_to(source, target_is_directory=True)
            with self.assertRaises(ValueError):
                build_agent_tree(linked, folder / "agent")

    def test_new_application_files_require_explicit_review(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source, destination = folder / "source", folder / "agent"
            shutil.copytree(SOURCE, source)
            for name in ("mosslight/new_feature.py", "mosslight/static/theme.css",
                         "examples/workflow.json", "WORKFLOW.md"):
                path = source / name
                path.write_text("new application content")
                with self.assertRaisesRegex(ValueError, "application allowlist update required"):
                    build_agent_tree(source, destination)
                self.assertFalse(destination.exists())
                path.unlink()


if __name__ == "__main__":
    unittest.main()
