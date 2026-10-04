"""Check camera-center convention and COLMAP text parsing on synthetic fixtures."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
from unittest.mock import Mock, patch
import run_reconstruction
from run_reconstruction import read_model
from reconstruction_runtime import sparse_model_files, validate_sparse_depths


class PoseTest(unittest.TestCase):
    def test_mapper_success_without_model_stops_before_dense(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            images = root / 'images'
            images.mkdir()
            (images / 'frame.jpg').write_bytes(b'fixture')
            cli = Mock(executable=root / 'colmap.exe', env={}, help={})
            cli.probe.side_effect = lambda name: cli.help.setdefault(name, '--help')
            cli.options.side_effect = lambda name, options: list(map(str, options))
            with patch.object(run_reconstruction, 'Colmap', return_value=cli), \
                 patch.object(run_reconstruction.subprocess, 'run', return_value=Mock(returncode=0)) as execute, \
                 patch('sys.argv', ['run_reconstruction.py', '--project', str(root), '--images', str(images), '--dense']):
                try:
                    with self.assertRaisesRegex(RuntimeError, 'No valid sparse model exists; dense processing stopped'):
                        run_reconstruction.main()
                    commands = [call.args[0][1] for call in execute.call_args_list]
                    self.assertIn('mapper', commands)
                    self.assertNotIn('image_undistorter', commands)
                    self.assertNotIn('patch_match_stereo', commands)
                finally:
                    run_reconstruction.CURRENT.clear()

    def test_sparse_model_requires_complete_file_set(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'images.bin').write_bytes(b'partial')
            with self.assertRaisesRegex(RuntimeError, 'missing or empty'):
                sparse_model_files(root)
            for name in ('cameras', 'images', 'points3D'):
                (root / f'{name}.txt').write_text('# model\n')
            self.assertTrue(all(p.suffix == '.txt' for p in sparse_model_files(root)))

    def test_sparse_depths_reject_empty_behind_camera_and_float_cancellation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'images.txt').write_text('1 1 0 0 0 0 0 -1 1 a.jpg\n\n2 1 0 0 0 0 0 -1 1 b.jpg\n\n')
            for z in (None, -2, 1.00000000001):
                with self.subTest(z=z):
                    (root / 'points3D.txt').write_text('' if z is None else f'1 0 0 {z} 255 0 0 0.1 1 0 2 0\n')
                    cameras, _, _, _ = read_model(root)
                    with self.assertRaisesRegex(RuntimeError, 'no numerically reliable positive-depth'):
                        validate_sparse_depths(root, cameras)
            (root / 'points3D.txt').write_text('1 0 0 2 255 0 0 0.1 1 0 2 0\n')
            validate_sparse_depths(root, cameras)

    def test_depth_support_is_required_for_each_registered_image(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'images.txt').write_text('1 1 0 0 0 0 0 0 1 a.jpg\n\n2 1 0 0 0 0 0 0 1 b.jpg\n\n')
            (root / 'points3D.txt').write_text('1 0 0 2 255 0 0 0.1 1 0\n')
            cameras, _, _, _ = read_model(root)
            with self.assertRaisesRegex(RuntimeError, 'including b.jpg'):
                validate_sparse_depths(root, cameras)

    def test_depth_validation_does_not_impose_an_absolute_scene_scale(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'images.txt').write_text('1 1 0 0 0 0 0 0 1 a.jpg\n\n2 1 0 0 0 0 0 0 1 b.jpg\n\n')
            (root / 'points3D.txt').write_text('1 0 0 1e-12 255 0 0 0.1 1 0 2 0\n')
            cameras, _, _, _ = read_model(root)
            validate_sparse_depths(root, cameras)

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
