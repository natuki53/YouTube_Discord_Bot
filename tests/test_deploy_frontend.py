import tempfile
import unittest
from pathlib import Path

from deploy.publish_web import publish


class PublishFrontendTests(unittest.TestCase):
    def test_switches_index_and_keeps_assets_for_existing_browser_tabs(self):
        with tempfile.TemporaryDirectory() as directory:
            source, destination = Path(directory) / "build", Path(directory) / "live"
            (source / "assets").mkdir(parents=True)
            (destination / "assets").mkdir(parents=True)
            (destination / "index.html").write_text("old")
            (destination / "assets/old.js").write_text("old bundle")
            (source / "index.html").write_text('<script src="assets/new.js"></script>')
            (source / "assets/new.js").write_text("new bundle")
            publish(source, destination)
            self.assertIn("new.js", (destination / "index.html").read_text())
            self.assertEqual((destination / "assets/old.js").read_text(), "old bundle")
            self.assertEqual((destination / "assets/new.js").read_text(), "new bundle")

    def test_invalid_build_leaves_the_published_index_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            source, destination = Path(directory) / "build", Path(directory) / "live"
            source.mkdir()
            destination.mkdir()
            (destination / "index.html").write_text("old")
            with self.assertRaises(ValueError):
                publish(source, destination)
            self.assertEqual((destination / "index.html").read_text(), "old")
