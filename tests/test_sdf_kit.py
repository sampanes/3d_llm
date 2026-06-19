"""End-to-end smoke test for the SDF meshing path (uses skimage + trimesh).

A sphere is the cheapest thing that exercises the whole pipeline: SDF eval ->
marching cubes -> Manifold weld. The contract that matters most is that the
result is watertight (so it survives the STL round-trip).
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sdf_kit as sk  # noqa: E402


class SdfMeshTests(unittest.TestCase):
    def test_sphere_meshes_watertight_with_expected_bbox(self):
        f = sk.sphere(5.0)
        m = sk.mesh(f, bounds=((-7, -7, -7), (7, 7, 7)), voxel=1.0, verbose=False)
        self.assertTrue(m.is_watertight)
        self.assertGreater(len(m.faces), 100)
        size = m.bounds[1] - m.bounds[0]
        for axis in size:
            self.assertAlmostEqual(float(axis), 10.0, delta=1.0)  # ~diameter, voxel slop

    def test_positive_everywhere_raises(self):
        # A sphere far outside the bounds -> no surface crossing -> clear error.
        f = sk.sphere(2.0, center=(100, 100, 100))
        with self.assertRaises(ValueError):
            sk.mesh(f, bounds=((-5, -5, -5), (5, 5, 5)), voxel=1.0, verbose=False)

    def test_save_stl_roundtrip_stays_watertight(self):
        import trimesh

        f = sk.smooth_union(1.0, sk.sphere(5.0), sk.sphere(4.0, center=(0, 0, 6)))
        m = sk.mesh(f, bounds=((-7, -7, -7), (7, 7, 14)), voxel=1.0, verbose=False)
        with tempfile.TemporaryDirectory() as d:
            stl = Path(d) / "blob.stl"
            sk.save_stl(m, stl, verbose=False)
            reloaded = trimesh.load(str(stl), force="mesh")
            self.assertTrue(reloaded.is_watertight)


if __name__ == "__main__":
    unittest.main()
