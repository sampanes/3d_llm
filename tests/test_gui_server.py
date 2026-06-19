"""Unit tests for scripts.gui_server input guards + command whitelist (no server)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import gui_server as gs  # noqa: E402


class SafePathTests(unittest.TestCase):
    def test_traversal_outside_root_raises(self):
        with self.assertRaises(ValueError):
            gs._safe_path("../../../etc/passwd")

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            gs._safe_path("")

    def test_valid_relative_stays_inside_root(self):
        p = gs._safe_path("models/_template/spec.md")
        self.assertTrue(str(p).startswith(str(gs.ROOT)))


class NumberCoercionTests(unittest.TestCase):
    def test_positive_int_clamps_and_defaults(self):
        self.assertEqual(gs._positive_int("abc", 5), 5)
        self.assertEqual(gs._positive_int(100, 5, 1, 8), 8)
        self.assertEqual(gs._positive_int(-3, 5, 1, 8), 1)

    def test_optional_float(self):
        self.assertIsNone(gs._optional_float(""))
        self.assertIsNone(gs._optional_float(None))
        self.assertEqual(gs._optional_float("1.5"), 1.5)
        with self.assertRaises(ValueError):
            gs._optional_float("not-a-number")


class HostnameTests(unittest.TestCase):
    def test_strips_port(self):
        self.assertEqual(gs._hostname_only("127.0.0.1:8765"), "127.0.0.1")
        self.assertEqual(gs._hostname_only("localhost"), "localhost")
        self.assertEqual(gs._hostname_only("[::1]:8765"), "::1")
        self.assertEqual(gs._hostname_only("evil.example:8765"), "evil.example")


class BuildCommandTests(unittest.TestCase):
    def test_unsupported_action_raises(self):
        with self.assertRaises(ValueError):
            gs._build_command({"action": "rm -rf"})

    def test_generate_requires_nontrivial_prompt(self):
        with self.assertRaises(ValueError):
            gs._build_command({"action": "generate", "options": {"prompt": "x"}})

    def test_generate_builds_module_command(self):
        info = gs._build_command(
            {"action": "generate", "options": {"prompt": "a small gear", "llm": "anthropic"}}
        )
        cmd = info["command"]
        self.assertIn("-m", cmd)
        self.assertIn("scripts.generate", cmd)
        self.assertIn("a small gear", cmd)
        self.assertIn("--llm", cmd)

    def test_generate_rejects_unknown_provider(self):
        with self.assertRaises(ValueError):
            gs._build_command(
                {"action": "generate", "options": {"prompt": "a gear", "llm": "skynet"}}
            )

    def test_build_model_traversal_blocked(self):
        with self.assertRaises(ValueError):
            gs._build_command({"action": "build_model", "model_dir": "../../etc"})

    def test_edit_unknown_operation_raises(self):
        with self.assertRaises(ValueError):
            gs._build_command(
                {"action": "edit", "operation": "nuke", "mesh_file": "models/_template/spec.md"}
            )


if __name__ == "__main__":
    unittest.main()
