"""Targeted real-data checks for Intelligence, Dense Cloud and Sparse Cloud."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'app'))
from mission import read_json
from world import geometry, model_tracks

PROJECTS = [ROOT/'results/jobs/validation_video_1', ROOT/'results/jobs/validation_video_2_shared']
AVAILABLE = all((p/'output/reconstruction/latest.json').is_file() for p in PROJECTS)


def app_for(project):
    app = AppTest.from_file(str(ROOT/'app/dashboard.py'), default_timeout=90)
    app.session_state['active_root'] = str(project)
    app.session_state['nav'] = '3D WORLD'
    return app.run()


def figure(app):
    return json.loads(json.loads(app.get('component_instance')[0].proto.json_args)['figure'])


@unittest.skipUnless(AVAILABLE, 'Requires reconstructed local Video 1 and Video 2')
class SelectedDatasetFeatures(unittest.TestCase):
    def assert_cloud(self, app, project, label):
        self.assertFalse(app.exception, str(app.exception))
        summary = read_json(project/'output/reconstruction/latest.json')
        run = Path(summary['run_directory'])
        mesh = run/'dense/mesh.ply'
        vertices, _, _ = geometry(str(mesh), mesh.stat().st_mtime_ns, True)
        origin = (vertices.min(0)+vertices.max(0))/2
        traces = figure(app)['data']
        self.assertFalse(any(t.get('type') == 'mesh3d' for t in traces), 'Opaque mesh obscures cloud')
        cloud = next(t for t in traces if t.get('name') == label)
        displayed = np.column_stack([cloud[k] for k in ('x','y','z')]) + origin
        if label == 'Dense Cloud':
            path = run/'dense/fused.ply'
            actual, _, _ = geometry(str(path), path.stat().st_mtime_ns)
        else:
            _, points = model_tracks(summary)
            actual = np.array([p['xyz'] for p in points.values()])
            self.assertEqual(cloud['customdata'], list(points))
        indices = np.linspace(0, len(actual)-1, min(60000, len(actual)), dtype=int)
        np.testing.assert_allclose(displayed, actual[indices], atol=1e-10)

    def test_layer_menu_activates_clouds_and_switches_dataset(self):
        app = app_for(PROJECTS[0])
        for project in PROJECTS:
            with self.subTest(project=project.name):
                next(s for s in app.selectbox if s.label == 'Active mission').set_value(str(project)).run()
                for label in ['Dense Cloud', 'Sparse Cloud']:
                    next(s for s in app.selectbox if s.label == 'Layer').set_value(label).run()
                    self.assert_cloud(app, project, label)

    def test_checkboxes_make_clouds_visible_over_default_mesh(self):
        for project in PROJECTS:
            with self.subTest(project=project.name):
                app = app_for(project)
                for checkbox, label in [('Dense cloud','Dense Cloud'),('Sparse cloud','Sparse Cloud')]:
                    next(c for c in app.checkbox if c.label == checkbox).check().run()
                    self.assert_cloud(app, project, label)
                    next(c for c in app.checkbox if c.label == checkbox).uncheck().run()

    def test_sparse_text_geometry_remains_visible_without_ply(self):
        original = Path.exists
        for project in PROJECTS:
            app = app_for(project)
            run = Path(read_json(project/'output/reconstruction/latest.json')['run_directory'])
            def exists(path):
                return False if path == run/'sparse.ply' else original(path)
            with patch.object(Path, 'exists', exists):
                next(s for s in app.selectbox if s.label == 'Layer').set_value('Sparse Cloud').run()
                self.assert_cloud(app, project, 'Sparse Cloud')

    def test_intelligence_survives_missing_quality_report_and_selection(self):
        for project in PROJECTS:
            for missing in ['quality', 'selection']:
                with self.subTest(project=project.name, missing=missing):
                    app = app_for(project)
                    def selection_missing(path, default=None):
                        if Path(path) == project/'results/image_intelligence/latest.json':
                            return {}
                        return read_json(path, default)
                    context = patch('ingestion.frame_decisions', side_effect=FileNotFoundError('Frame-quality report missing')) if missing == 'quality' else patch('mission.read_json', side_effect=selection_missing)
                    with context:
                        next(b for b in app.button if b.label == 'INTELLIGENCE').click().run()
                    self.assertFalse(app.exception, str(app.exception))
                    self.assertTrue(any(s.value == 'Reconstructed scene statistics' for s in app.subheader))
                    run = Path(read_json(project/'output/reconstruction/latest.json')['run_directory'])
                    frames = [d.value for d in app.dataframe if {'Axis','Minimum','Maximum','Extent'}.issubset(d.value.columns)]
                    self.assertEqual(len(frames), 3)
                    for frame, relative, mesh in zip(frames, ['dense/mesh.ply','dense/fused.ply','sparse.ply'], [True, False, False]):
                        path = run/relative
                        xyz, _, _ = geometry(str(path), path.stat().st_mtime_ns, mesh)
                        np.testing.assert_allclose(frame['Minimum'], xyz.min(0))
                        np.testing.assert_allclose(frame['Maximum'], xyz.max(0))
                    if missing == 'quality':
                        count = next(m for m in app.metric if m.label == 'Points with at least two revealed observations')
                        self.assertEqual(int(count.value.replace(',', '')), read_json(project/'output/reconstruction/latest.json')['sparse_points'])


if __name__ == '__main__':
    unittest.main()
