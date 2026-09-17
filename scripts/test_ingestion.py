"""Upload persistence and actual decode/selection integration; no fake 3D."""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np
from streamlit.testing.v1 import AppTest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from ingestion import save_uploads,frame_decisions
from extract_video import extract_video
from analyze_images import run,DEFAULTS

class Upload(io.BytesIO):
    def __init__(self,name,data):super().__init__(data);self.name=name

class IngestionTests(unittest.TestCase):
    def test_video_upload_decode_select_and_timestamps(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); source=root/'fixture.avi'
            writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'MJPG'),10,(160,120))
            rng=np.random.default_rng(7);frame=rng.integers(0,256,(120,160,3),dtype=np.uint8)
            for _ in range(20):writer.write(frame)
            writer.release()
            uploaded=save_uploads([Upload('flight.avi',source.read_bytes())],root,True)
            self.assertEqual(uploaded.read_bytes(),source.read_bytes())
            job=root/'job';video=extract_video(uploaded,job/'video_ingestion',.2,20)
            selection=run(job/'video_ingestion/frames',job,DEFAULTS.copy())
            rows=frame_decisions(job,selection)
            self.assertEqual(video['extracted_frames'],10)
            self.assertLess(selection['selected_images'],10)
            self.assertTrue(rows.timestamp_s.notna().all())
            for name in rows[rows.selected].filename:
                self.assertTrue((Path(selection['selected_directory'])/name).is_file())
            bad=save_uploads([Upload('broken.mp4',b'not a video')],root,True)
            with self.assertRaises(ValueError):extract_video(bad,root/'bad')

    def test_image_upload_paths_and_duplicates(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            folder=save_uploads([Upload('../../photo.jpg',b'image')],root)
            self.assertEqual((folder/'photo.jpg').read_bytes(),b'image')
            self.assertEqual(folder.parent,root/'uploads')
            with self.assertRaises(ValueError):save_uploads([Upload('a.jpg',b'a'),Upload('A.jpg',b'b')],root)
            with self.assertRaises(ValueError):save_uploads([Upload('script.exe',b'a')],root)

    def test_upload_controls_and_empty_reconstruction(self):
        with tempfile.TemporaryDirectory() as d,patch.dict('os.environ',{'AEROSPHERE_DATA_ROOT':d}):
            app=AppTest.from_file(str(ROOT/'app/dashboard.py'),default_timeout=60).run()
            app.sidebar.radio[0].set_value('MISSION').run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.get('file_uploader')),1)
            next(r for r in app.radio if r.label=='Input method').set_value('UPLOAD IMAGE SEQUENCE').run()
            self.assertEqual(len(app.get('file_uploader')),1)
            next(r for r in app.radio if r.label=='Input method').set_value('CONNECT DRONE').run()
            self.assertTrue(any('NO DRONE CONNECTED' in i.value for i in app.info))
            app.sidebar.radio[0].set_value('RECONSTRUCTION').run()
            self.assertFalse(app.exception)
            self.assertFalse(any(b.label=='Start 3D reconstruction' for b in app.button))

if __name__=='__main__':unittest.main()
