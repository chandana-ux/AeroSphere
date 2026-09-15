"""Synthetic media tests and real-artifact checks; never simulate reconstruction."""
import json
import sys
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
import pandas as pd
import open3d as o3d
from streamlit.testing.v1 import AppTest
from extract_video import extract_video
from extract_metadata import extract,coordinate

ROOT=Path(__file__).resolve().parents[1]


class CompletionTests(unittest.TestCase):
    def test_new_job_reports_insufficient_input(self):
        from pipeline import process
        from semantic import detect
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'raw';source.mkdir()
            cv2.imwrite(str(source/'SYNTHETIC_SINGLE.jpg'),np.zeros((120,160,3),np.uint8))
            job=ROOT/'results/jobs'/('TEST_INSUFFICIENT_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f'))
            result=process(source,job,reconstruct=True)
            self.assertEqual(result['status'],'failed')
            self.assertIn('Insufficient selected images',result['error'])
            self.assertFalse((job/'output/reconstruction/latest.json').exists())
            self.assertEqual(detect(source/'SYNTHETIC_SINGLE.jpg',Path(temp))['status'],'optional/unavailable')

    def test_streaming_video_formats_limits_and_invalid(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'raw';source.mkdir()
            for suffix,codec in [('avi','MJPG'),('mp4','mp4v')]:
                path=source/f'SYNTHETIC_TEST.{suffix}'
                writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*codec),10,(160,120))
                self.assertTrue(writer.isOpened())
                for i in range(20):
                    frame=np.zeros((120,160,3),dtype=np.uint8)
                    cv2.rectangle(frame,(i*4,30),(i*4+20,70),(0,255,0),-1);writer.write(frame)
                writer.release()
                report=extract_video(path,root/suffix,interval=0.4,max_frames=10)
                self.assertEqual(report['decoded_frames'],20)
                self.assertEqual(report['extracted_frames'],5)
                self.assertEqual(report['gps_status'],'GPS/telemetry unavailable')
                rows=pd.read_csv(root/suffix/'frame_timestamps.csv')
                self.assertTrue((np.diff(rows.timestamp_s)>0).all())
                self.assertEqual(extract_video(path,root/(suffix+'_cap'),interval=0.1,max_frames=2)['status'],'partial')
                with self.assertRaises(ValueError):extract_video(path,root/'invalid',interval=0)
            bad=source/'broken.mp4';bad.write_bytes(b'not video')
            with self.assertRaises(ValueError):extract_video(bad,root/'broken')
            with self.assertRaises(ValueError):extract_video(source/'missing.mp4',root/'missing')

    def test_exif_missing_and_bad_coordinates(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'plain.jpg';cv2.imwrite(str(p),np.zeros((10,10,3),np.uint8))
            r=extract(p,p.parent)
            self.assertEqual(r['status'],'missing_gps');self.assertIsNone(r['latitude'])
        self.assertAlmostEqual(coordinate((41,18,13.7576),'N',True),41.30382155555555)
        with self.assertRaises(ValueError):coordinate((95,0,0),'N',True)

    def test_real_artifact_counts(self):
        summary=json.loads((ROOT/'output/reconstruction/latest.json').read_text());run=Path(summary['run_directory'])
        self.assertEqual(summary['registered_images'],77)
        self.assertEqual(len(o3d.io.read_point_cloud(str(run/'sparse.ply')).points),29457)
        self.assertEqual(len(o3d.io.read_point_cloud(str(run/'dense/fused.ply')).points),495971)
        self.assertEqual(len(o3d.io.read_triangle_mesh(str(run/'dense/mesh.ply')).triangles),21600)
        self.assertAlmostEqual(summary['mean_point_reprojection_error_pixels'],1.242244151999799)

    def test_missing_optional_gps_dashboard(self):
        import streamlit as st
        original=pd.read_csv
        def missing(path,*args,**kwargs):
            df=original(path,*args,**kwargs)
            if str(path).endswith('image_metadata.csv'):
                df[['latitude','longitude','altitude_m','altitude_raw_m']]=np.nan
            return df
        st.cache_data.clear()
        with patch('pandas.read_csv',side_effect=missing):
            app=AppTest.from_file(str(ROOT/'app/dashboard.py'),default_timeout=60).run()
            self.assertEqual(len(app.exception),0)
            for page in ['Geospatial','Measurements']:
                app.sidebar.radio[0].set_value(page).run()
                self.assertEqual(len(app.exception),0,str(app.exception))
        st.cache_data.clear()


if __name__=='__main__':unittest.main()
