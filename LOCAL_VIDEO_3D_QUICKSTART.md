# AeroSphere — Local Video → 3D Quick Start

This copy preserves the existing Demo Movie 1 interface. The Mission > Upload Drone Video workflow now automatically runs:

**video → sampled frames → frame intelligence → selected frames → COLMAP SfM → dense MVS → mesh → existing 3D World viewer**

## Start

1. Make sure Python 3.11 and the existing AeroSphere dependencies are installed.
2. Make sure FFmpeg and COLMAP are installed locally.
3. If COLMAP is not in the default Windows location, set `AEROSPHERE_COLMAP` to the COLMAP launcher/executable before starting.
4. Double-click `START_AEROSPHERE_8503.bat`.
5. Open `http://127.0.0.1:8503/` if the browser does not open automatically.

## Use

1. Open **Mission**.
2. Select **UPLOAD DRONE VIDEO**.
3. Upload an actual MP4/MOV/AVI/MKV drone video.
4. Click **Analyze flight**.
5. Wait for frame selection and reconstruction to finish. The reconstruction runs locally in the background.
6. Open **Flight Intelligence** to inspect selected frames.
7. Open **Reconstruction** / **3D World** to inspect the actual generated sparse/dense/mesh output.

## Important

- This is an offline/local workflow; no cloud reconstruction is required.
- No fake 3D model or fake telemetry is generated.
- If the video does not contain enough overlapping visual information, COLMAP may fail; the app should report the failure instead of treating extracted frames as a successful 3D reconstruction.
- The current prototype does not claim absolute metric accuracy without independent scale/georeferencing validation.
- The existing image-sequence reconstruction remains available as a regression/reference path.
