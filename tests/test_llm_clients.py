"""Unit tests for scripts.llm_clients pure helpers (no network)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.llm_clients import extract_code, load_images  # noqa: E402


class ExtractCodeTests(unittest.TestCase):
    def test_pulls_inner_of_fenced_block(self):
        text = "Here you go:\n```openscad\ncube(10);\n```\nEnjoy."
        self.assertEqual(extract_code(text), "cube(10);")

    def test_python_fence(self):
        text = "```python\nresult = box(5)\n```"
        self.assertEqual(extract_code(text), "result = box(5)")

    def test_returns_longest_block_when_multiple(self):
        text = "```\nshort\n```\nblah\n```python\nthe_real_code = 1\nmore = 2\n```"
        self.assertIn("the_real_code", extract_code(text))

    def test_fallback_strips_stray_backticks(self):
        self.assertEqual(extract_code("`just text`"), "just text")


class LoadImagesTests(unittest.TestCase):
    def test_none_returns_empty(self):
        self.assertEqual(load_images(None), [])

    def test_unsupported_extension_raises(self):
        with self.assertRaises(ValueError):
            load_images(["photo.tiff"])

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_images(["does_not_exist_12345.png"])


if __name__ == "__main__":
    unittest.main()
