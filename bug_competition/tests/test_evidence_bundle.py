"""Evidence exports must preserve bytes and detect incomplete or altered bundles."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bug_competition.host_only.tools import evidence_bundle as bundle


class EvidenceBundleTests(unittest.TestCase):
    def test_roundtrip_and_member_integrity_without_extracting(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory).resolve()
            source = repo / "bug_competition/host_only/rollouts/example"
            source.mkdir(parents=True)
            original = b'{"historical": "unchanged"}\n'
            (source / "summary.json").write_bytes(original)
            (source / "__pycache__").mkdir()
            (source / "__pycache__/unused.pyc").write_bytes(b"cache")
            archive, manifest = repo / "bundle.tar.gz", repo / "bundle.json"
            with patch.object(bundle, "REPO", repo):
                result = bundle.create(source, archive, manifest)
                self.assertTrue(result["verified"])
                self.assertEqual(result["file_count"], 1)
                self.assertEqual((source / "summary.json").read_bytes(), original)
                self.assertEqual(bundle.verify(manifest), result)
                record = json.loads(manifest.read_text())
                record["files"][0]["sha256"] = "0" * 64
                manifest.write_text(json.dumps(record))
                with self.assertRaisesRegex(ValueError, "member checksum"):
                    bundle.verify(manifest)
                archive.write_bytes(archive.read_bytes() + b"altered")
                with self.assertRaisesRegex(ValueError, "archive checksum"):
                    bundle.verify(manifest)

    def test_refuses_links_and_overwriting_existing_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory).resolve()
            source = repo / "bug_competition/host_only/rollouts/example"
            source.mkdir(parents=True)
            (source / "link").symlink_to(repo / "outside")
            archive, manifest = repo / "bundle.tar.gz", repo / "bundle.json"
            with patch.object(bundle, "REPO", repo):
                with self.assertRaisesRegex(ValueError, "symbolic link"):
                    bundle.create(source, archive, manifest)
                archive.write_bytes(b"existing")
                with self.assertRaisesRegex(ValueError, "new paths"):
                    bundle.create(source, archive, manifest)


if __name__ == "__main__":
    unittest.main()
