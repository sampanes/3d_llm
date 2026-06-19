"""Unit tests for scripts.generate path-rewriting + slug helpers (no network)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.generate import (  # noqa: E402
    _rewrite_cadquery_export,
    _rewrite_sdf_save_stl,
    _slugify,
)

TARGET = Path("output") / "stl" / "foo.stl"


class SlugifyTests(unittest.TestCase):
    def test_lowercases_and_replaces_punctuation(self):
        self.assertEqual(_slugify("A small Box, with lid!"), "a_small_box_with_lid")

    def test_truncates_to_max_len(self):
        self.assertLessEqual(len(_slugify("x" * 200, max_len=40)), 40)


class CadqueryRewriteTests(unittest.TestCase):
    def test_rewrites_exporters_export_and_keeps_variable(self):
        code = "result = cq.Workplane()\ncq.exporters.export(result, 'thing.stl')\n"
        out = _rewrite_cadquery_export(code, TARGET)
        self.assertNotIn("thing.stl", out)
        self.assertIn("foo.stl", out)
        self.assertIn("export(result,", out)

    def test_rewrites_exportstl_method(self):
        code = "solid.val().exportStl('whatever.stl')\n"
        out = _rewrite_cadquery_export(code, TARGET)
        self.assertNotIn("whatever.stl", out)
        self.assertIn("foo.stl", out)

    def test_appends_export_when_absent(self):
        code = "result = make_box(10)\n"  # no export call at all
        out = _rewrite_cadquery_export(code, TARGET)
        self.assertIn("cq.exporters.export(result,", out)
        self.assertIn("foo.stl", out)


class SdfRewriteTests(unittest.TestCase):
    def test_rewrites_save_stl_and_keeps_mesh_var(self):
        code = "m = sk.mesh(f, bounds=b, voxel=0.5)\nsk.save_stl(m, 'model.stl')\n"
        out = _rewrite_sdf_save_stl(code, TARGET)
        self.assertNotIn("model.stl", out)
        self.assertIn("foo.stl", out)
        self.assertIn("save_stl(m,", out)

    def test_raises_when_no_save_stl(self):
        with self.assertRaises(RuntimeError):
            _rewrite_sdf_save_stl("m = build()\nprint(m)\n", TARGET)


if __name__ == "__main__":
    unittest.main()
