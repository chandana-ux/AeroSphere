"""Regression tests for dependency/version handling and honest per-dataset results."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'app'))
from reconstruction_runtime import Colmap, DependencyError, find_colmap, write_json, worker_alive


class RuntimeTests(unittest.TestCase):
    def test_worker_liveness_does_not_stop_current_process(self):
        self.assertTrue(worker_alive(os.getpid()))

    def test_exited_worker_does_not_display_processing_forever(self):
        from dashboard import live_reconstruction_progress
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_json(root/'reconstruction_progress.json', {
                'status':'processing', 'stage':'sparse', 'stages':{'sparse':'processing'}})
            (root/'reconstruction.lock').write_text('123')
            with patch('dashboard.worker_alive', return_value=False):
                state = live_reconstruction_progress(root)
                self.assertEqual(state['status'], 'failed')
                self.assertEqual(state['stages']['sparse'], 'failed')
            with patch('dashboard.worker_alive', return_value=True):
                self.assertEqual(live_reconstruction_progress(root)['status'], 'processing')

    def test_explicit_bad_path_does_not_silently_select_another_install(self):
        with patch.dict(os.environ, {'AEROSPHERE_COLMAP':str(ROOT/'missing/colmap.exe')}):
            self.assertIsNone(find_colmap())
            with self.assertRaises(DependencyError):
                Colmap()

    def test_version_option_aliases_and_required_option_failure(self):
        cli = Colmap.__new__(Colmap)
        cli.help = {'feature_extractor':'--database_path --SiftExtraction.use_gpu --SiftExtraction.max_image_size'}
        self.assertEqual(cli.options('feature_extractor', ['--FeatureExtraction.use_gpu','0','--log_color','0']), ['--SiftExtraction.use_gpu','0'])
        with self.assertRaisesRegex(DependencyError, 'camera_model'):
            cli.options('feature_extractor', ['--ImageReader.camera_model','OPENCV'])

    def test_missing_dependency_writes_terminal_sparse_state(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            env = dict(os.environ, AEROSPHERE_COLMAP=str(project/'missing.exe'))
            result = subprocess.run([sys.executable, str(ROOT/'scripts/run_reconstruction.py'), '--project', str(project)], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            progress = json.loads((project/'reconstruction_progress.json').read_text())
            self.assertEqual(progress['stages'], {'sparse':'dependency_missing','dense':'not_started','mesh':'not_started'})
            self.assertFalse((project/'output/reconstruction/latest.json').exists())
            self.assertFalse((project/'reconstruction.lock').exists())

    def test_existing_lock_preserves_running_status(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project/'reconstruction.lock').write_text('123')
            write_json(project/'reconstruction_progress.json', {'status':'processing'})
            result = subprocess.run([sys.executable, str(ROOT/'scripts/run_reconstruction.py'), '--project', str(project)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(json.loads((project/'reconstruction_progress.json').read_text()), {'status':'processing'})
            self.assertEqual((project/'reconstruction.lock').read_text(), '123')

    def test_latest_summary_cannot_cross_dataset_or_survive_failed_retry(self):
        from dashboard import data
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'mission'
            old = root/'output/reconstruction/old'
            old.mkdir(parents=True)
            (old/'sparse.ply').write_bytes(b'ply\n')
            latest = root/'output/reconstruction/latest.json'
            write_json(latest, {'run_directory':str(old)})
            self.assertTrue(data(root)[0])
            write_json(root/'reconstruction_progress.json', {'status':'failed','run_directory':str(root/'output/reconstruction/new')})
            self.assertFalse(data(root)[0])
            write_json(latest, {'run_directory':str(Path(temp)/'other-mission')})
            self.assertFalse(data(root)[0])

    def test_atomic_status_replaces_previous_document(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'nested/status.json'
            write_json(path, {'status':'processing'})
            write_json(path, {'status':'completed','points':12})
            self.assertEqual(json.loads(path.read_text()), {'status':'completed','points':12})
            self.assertFalse(list(path.parent.glob('*.tmp')))


if __name__ == '__main__':
    unittest.main()
