"""V1 failure, provenance, temporal, package and offline regression tests."""
import hashlib
import json
import os
import socket
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

CODE=Path(__file__).resolve().parents[1]
DATA=Path(os.environ.get('AEROSPHERE_DATA_ROOT',CODE))
sys.path.insert(0,str(CODE/'app'))
from temporal import similarity,compare_points
from lineage import load_tracks,supported_by
from mission import package_mission,save_profile,catalog

class V1Tests(unittest.TestCase):
    def test_landmark_alignment_and_change_scope(self):
        rng=np.random.default_rng(8);a=rng.normal(size=(40,3))
        rot=np.array([[0,-1,0],[1,0,0],[0,0,1]])
        b=3*a@rot+[5,3,-2]
        matrix,error=similarity(a[:8],b[:8])
        self.assertLess(error,1e-12)
        report,_,_,_=compare_points(a,b,matrix,.01)
        self.assertEqual(report['candidate_new_or_unobserved'],0)
        report,_,_,_=compare_points(a,np.r_[b,[[100,100,100]]],matrix,.01)
        self.assertEqual(report['candidate_new_or_unobserved'],1)
        self.assertIn('cannot be confirmed',report['classification'])
        with self.assertRaises(ValueError):similarity(np.ones((4,3)),np.ones((4,3)))
        with self.assertRaises(ValueError):compare_points(a,b,np.zeros((4,4)),1)
        with self.assertRaises(ValueError):compare_points(a,b,matrix,0)

    def test_exact_track_integrity_and_replay(self):
        summary=json.loads((DATA/'output/reconstruction/latest.json').read_text())
        folder=Path(summary['run_directory'])/('text_'+Path(summary['sparse_model']).name)
        images,points=load_tracks(folder)
        self.assertEqual(len(points),summary['sparse_points'])
        self.assertTrue(all(supported_by(p,images) for p in points.values()))
        self.assertFalse(any(supported_by(p,[next(iter(images))]) for p in points.values()))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'images.txt').write_text('1 1 0 0 0 0 0 0 1 a.jpg\n1 2 99\n2 1 0 0 0 0 0 0 1 b.jpg\n3 4 5\n')
            (p/'points3D.txt').write_text('5 0 0 0 255 255 255 1 1 0 2 0\n')
            with self.assertRaises(ValueError):load_tracks(p)

    def test_package_checksums_and_real_geometry(self):
        summary=json.loads((DATA/'output/reconstruction/latest.json').read_text())
        selection=json.loads((DATA/'results/image_intelligence/latest.json').read_text())
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);save_profile(root,'Test package','INFRASTRUCTURE')
            path=package_mission(root,summary,selection,{'validated_metric_accuracy':False})
            with zipfile.ZipFile(path) as z:
                self.assertIsNone(z.testzip())
                self.assertTrue({'geometry/sparse.ply','geometry/dense.ply','geometry/mesh_original.ply','lineage/images.txt','lineage/points3D.txt','MISSION_SUMMARY.md'}<=set(z.namelist()))
                for item in json.loads(z.read('manifest.json'))['files']:
                    self.assertEqual(hashlib.sha256(z.read(item['file'])).hexdigest(),item['sha256'])
                self.assertTrue(all(not n.startswith(('/', '..')) for n in z.namelist()))

    def test_empty_start_and_navigation_offline(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'AEROSPHERE_DATA_ROOT':d}),patch.object(socket.socket,'connect',side_effect=AssertionError('Network forbidden')):
            app=AppTest.from_file(str(CODE/'app/dashboard.py'),default_timeout=90).run()
            for page in ['HOME','MISSION','FLIGHT','3D WORLD','EVIDENCE','TEMPORAL','INSIGHTS','EXPORT']:
                app.sidebar.radio[0].set_value(page).run()
                self.assertFalse(app.exception,str(app.exception));self.assertFalse(app.error,[e.value for e in app.error])

    def test_cached_mission_navigation_offline(self):
        with patch.dict(os.environ,{'AEROSPHERE_DATA_ROOT':str(DATA)}),patch.object(socket.socket,'connect',side_effect=AssertionError('Network forbidden')):
            app=AppTest.from_file(str(CODE/'app/dashboard.py'),default_timeout=90).run()
            for page in ['HOME','MISSION','FLIGHT','3D WORLD','EVIDENCE','TEMPORAL','INSIGHTS','EXPORT']:
                app.sidebar.radio[0].set_value(page).run()
                self.assertFalse(app.exception,str(app.exception));self.assertFalse(app.error,[e.value for e in app.error])
            app.sidebar.radio[0].set_value('HOME').run()
            self.assertEqual(app.metric[0].value,'77')

    def test_missing_model_never_downloads(self):
        from semantic import detect
        with tempfile.TemporaryDirectory() as d,patch.object(socket.socket,'connect',side_effect=AssertionError('Network forbidden')):
            self.assertEqual(detect(Path(d)/'not_used.jpg',Path(d),allow_download=True)['status'],'optional/unavailable')

    def test_cached_detector_offline(self):
        from semantic import detect
        selection=json.loads((DATA/'results/image_intelligence/latest.json').read_text())
        image=sorted(Path(selection['source']).glob('*.JPG'))[0]
        with tempfile.TemporaryDirectory() as d,patch.object(socket.socket,'connect',side_effect=AssertionError('Network forbidden')):
            result=detect(image,Path(d),model_root=DATA)
            self.assertEqual(result['status'],'available',result)
            self.assertIsInstance(result['detections'],list)

    def test_model_space_area(self):
        from measure import triangle_area
        self.assertAlmostEqual(triangle_area(np.array([0.,0,0]),np.array([3.,0,0]),np.array([0.,4,0])),6)
        self.assertEqual(triangle_area(np.zeros(3),np.zeros(3),np.zeros(3)),0)

    def test_mission_profile_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);save_profile(p,'Inspection','INFRASTRUCTURE')
            entries=catalog(p)
            self.assertEqual(entries[0]['mode'],'INFRASTRUCTURE')
            self.assertEqual(entries[0]['category'],'INFRASTRUCTURE')
            self.assertIsNone(entries[0]['telemetry_extensions']['rtk'])

if __name__=='__main__':unittest.main()
