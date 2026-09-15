"""Real-artifact dashboard smoke tests plus synthetic alignment boundary checks."""
import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from geo import assess,fit_horizontal,transform,gps_distance


class DashboardTest(unittest.TestCase):
    def test_pages_and_measurements(self):
        app=AppTest.from_file(str(ROOT/'app/dashboard.py'),default_timeout=60).run()
        self.assertEqual(len(app.exception),0,str(app.exception))
        self.assertEqual(app.metric[0].value,'77')
        for page in ['Imagery','Geospatial','3D Explorer','Quality & Coverage','Measurements','Semantic AI','Process New Input','Exports & Trust']:
            app.sidebar.radio[0].set_value(page).run()
            self.assertEqual(len(app.exception),0,f'{page}: {app.exception}')
            if page=='Imagery':
                app.radio(key='collection').set_value('Selected images').run()
                self.assertEqual(len(app.exception),0,str(app.exception))
                app.selectbox[0].set_value('DSC00311.JPG').run()
                self.assertEqual(len(app.exception),0,str(app.exception))
            if page=='3D Explorer':
                for mode in ['Sparse point cloud','Mesh','Dense point cloud']:
                    app.radio(key='representation').set_value(mode).run()
                    self.assertEqual(len(app.exception),0,str(app.exception))
            if page=='Measurements':
                first=app.selectbox[0].value
                app.selectbox[1].set_value(first).run()
                self.assertEqual(app.metric[0].value,'0.00 m')
                app.radio(key='measurement_source').set_value('Reconstruction points').run()
                self.assertEqual(len(app.exception),0,str(app.exception))
                app.number_input[1].set_value(0).run()
                self.assertEqual(app.metric[0].value,'0.00000 reconstruction units')

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
