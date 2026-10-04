"""Real-artifact dashboard smoke tests plus synthetic alignment boundary checks."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from PIL import Image
from streamlit.testing.v1 import AppTest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from geo import assess,fit_horizontal,transform,gps_distance
from world import mesh_path_for_mission, run_directory_for_mission


class DashboardTest(unittest.TestCase):
    def test_mesh_path_stays_with_active_mission(self):
        bundled_mesh=ROOT/'results/dense/mesh.ply'
        self.assertTrue(bundled_mesh.is_file())
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)
            first_run=base/'mission-one'/'output'/'reconstruction'/'run-one'
            first_mesh=first_run/'dense/mesh.ply'
            first_mesh.parent.mkdir(parents=True)
            first_mesh.write_bytes(b'mission one')
            self.assertEqual(mesh_path_for_mission(base/'mission-one',first_run),first_mesh)
            empty_run=base/'mission-two'/'output'/'reconstruction'/'run-two'
            self.assertEqual(mesh_path_for_mission(base/'mission-two',empty_run),empty_run/'dense/mesh.ply')
            self.assertNotEqual(mesh_path_for_mission(base/'mission-two',empty_run),bundled_mesh)
        self.assertEqual(mesh_path_for_mission(ROOT,ROOT/'results'),bundled_mesh)

    def test_external_run_directory_is_rejected_for_mission(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'mission';root.mkdir()
            outside=Path(temp)/'other-mission'/'output/reconstruction/run'
            self.assertEqual(run_directory_for_mission(root,{'run_directory':str(outside)}),root/'results')
            self.assertEqual(run_directory_for_mission(root,{'run_directory':str(root/'output/reconstruction/run')}),root/'output/reconstruction/run')

    def test_input_only_mission_pages_without_cross_mission_geometry(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,{'AEROSPHERE_DATA_ROOT':temp}):
            root=Path(temp)
            source=root/'input';source.mkdir()
            Image.new('RGB',(96,64),(80,130,170)).save(source/'frame.png')
            report=root/'results/image_intelligence/run';report.mkdir(parents=True)
            selected=root/'selected_frames';selected.mkdir()
            pd.DataFrame([{'filename':'frame.png','status':'ok','selected':True,'reason':'retained_conservatively',
                           'blur_laplacian_variance':22.5,'brightness_mean':100.0,'contrast_std':30.0,
                           'orb_keypoints':12,'information_score':0.4,'warnings':'few_features'}]).to_csv(report/'image_quality.csv',index=False)
            Image.new('RGB',(96,64),(80,130,170)).save(selected/'frame.png')
            selection={'input_images':1,'selected_images':1,'source':str(source),'selected_directory':str(selected),'report_directory':str(report)}
            latest=root/'results/image_intelligence/latest.json';latest.parent.mkdir(parents=True,exist_ok=True);latest.write_text(json.dumps(selection))
            metadata=root/'metadata/image_metadata.csv';metadata.parent.mkdir();pd.DataFrame([{'filename':'frame.png','latitude':None,'longitude':None,'altitude_raw_m':None}]).to_csv(metadata,index=False)
            (root/'job.json').write_text(json.dumps({'status':'completed','stage':'ready','source':str(source)}))
            app=AppTest.from_file(str(ROOT/'app/dashboard.py'),default_timeout=60).run()
            app.session_state['nav']='RECONSTRUCTION';app.run()
            self.assertFalse(app.exception,str(app.exception))
            self.assertTrue(any(button.label=='Open precomputed 3D demo' for button in app.button))
            for page in ['GEO','MEASURE','QUALITY','INTELLIGENCE','3D WORLD']:
                next(button for button in app.button if button.label==page).click().run()
                self.assertFalse(app.exception,f'{page}: {app.exception}')
            world_text='\n'.join(element.value for element in app.markdown)
            self.assertNotIn('38,933 vertices',world_text)
            self.assertTrue(any('No geometry is available in this mission' in item.value for item in app.info))

    def test_pages_and_measurements(self):
        app=AppTest.from_file(str(ROOT/'app/dashboard.py'),default_timeout=60)
        app.session_state['active_root']=str(ROOT)
        app.session_state['nav']='3D WORLD'
        app.run()
        self.assertEqual(len(app.exception),0,str(app.exception))
        for page in ['MISSION','FRAMES','RECONSTRUCTION','3D WORLD','GEO','MEASURE','QUALITY','INTELLIGENCE']:
            next(button for button in app.button if button.label==page).click().run()
            self.assertEqual(len(app.exception),0,f'{page}: {app.exception}')
            if page=='MEASURE':
                values={metric.label:metric.value for metric in app.metric}
                self.assertIn('A–B distance',values)
                self.assertIn('Whole mesh surface area',values)
                self.assertNotEqual(values['Whole mesh surface area'],'Unavailable')

    def test_failed_input_diagnostic(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,{'AEROSPHERE_DATA_ROOT':temp}):
            root=Path(temp)
            (root/'job.json').write_text(json.dumps({'status':'failed','stage':'input','error':'unsupported codec'}))
            app=AppTest.from_file(str(ROOT/'app/dashboard.py'),default_timeout=60).run()
            app.session_state['nav']='RECONSTRUCTION'
            app.run()
            self.assertEqual(len(app.exception),0,str(app.exception))
            self.assertTrue(any('Processing status · FAILED · input' in item.value for item in app.caption))
            self.assertTrue(any('unsupported codec' in item.value for item in app.error))
            self.assertTrue(any('counts are unavailable' in item.value for item in app.info))

    def test_alignment_math_and_degeneracy(self):
        rng=np.random.default_rng(10)
        x=np.column_stack([rng.normal(size=(30,2)),np.zeros(30)])
        y=12*x[:,:2]@np.array([[0,-1],[1,0]])+[500000,4500000]
        fitted=fit_horizontal(x,y)
        np.testing.assert_allclose(transform(x,fitted),y,atol=1e-8)
        self.assertAlmostEqual(fitted['scale'],12)
        with self.assertRaises(ValueError):
            fit_horizontal(np.column_stack([np.arange(20),np.zeros((20,2))]),np.ones((20,2)))
        cameras=pd.DataFrame(columns=['filename','x','y','z'])
        meta=pd.DataFrame(columns=['filename','latitude','longitude'])
        report,_=assess(meta,cameras)
        self.assertEqual(report['status'],'unavailable')
        p=pd.Series({'longitude':-81.75,'latitude':41.3})
        self.assertEqual(gps_distance(p,p),0)


if __name__=='__main__':
    unittest.main()
