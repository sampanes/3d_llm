"""Unit tests for scripts.validate_stl against real meshes (uses trimesh)."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.validate_stl import validate_stl  # noqa: E402


class ValidateStlTests(unittest.TestCase):
    def test_watertight_box_passes(self):
        import trimesh

        with tempfile.TemporaryDirectory() as d:
            stl = Path(d) / "box.stl"
            trimesh.creation.box(extents=(10.0, 10.0, 10.0)).export(str(stl))
            report = validate_stl(stl)
            self.assertTrue(report.passed)
            self.assertTrue(report.is_watertight)
            self.assertTrue(report.is_volume)
            for axis in report.bbox_size:
                self.assertAlmostEqual(axis, 10.0, places=3)

    def test_empty_file_fails_with_error(self):
        with tempfile.TemporaryDirectory() as d:
            stl = Path(d) / "empty.stl"
            stl.write_bytes(b"")
            report = validate_stl(stl)
            self.assertFalse(report.passed)
            self.assertTrue(report.errors)

    def test_missing_file_fails_with_error(self):
        report = validate_stl(Path("definitely_missing_98765.stl"))
        self.assertFalse(report.passed)
        self.assertTrue(any("not found" in e.lower() for e in report.errors))


if __name__ == "__main__":
    unittest.main()
