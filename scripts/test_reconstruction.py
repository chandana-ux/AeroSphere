"""Check camera-center convention and COLMAP text parsing on synthetic fixtures."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
from run_reconstruction import read_model


class PoseTest(unittest.TestCase):
    def test_world_to_camera_inversion_and_empty_observations(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root.joinpath('images.txt').write_text('# model\n1 1 0 0 0 1 2 3 1 image one.jpg\n\n2 0.7071067811865476 0 0 0.7071067811865476 1 0 0 1 image two.jpg\n10 20 1\n')
            root.joinpath('points3D.txt').write_text('# points\n1 1 2 3 255 0 0 0.5 1 0 2 0\n')
            cameras, points, errors, tracks = read_model(root)
            np.testing.assert_allclose([cameras[0][k] for k in ('x','y','z')], [-1,-2,-3])
            np.testing.assert_allclose([cameras[1][k] for k in ('x','y','z')], [0,1,0], atol=1e-12)
            self.assertEqual(cameras[0]['filename'], 'image one.jpg')
            self.assertEqual(tracks, [2])
            self.assertEqual(errors, [0.5])


if __name__ == '__main__':
    unittest.main()
