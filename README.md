# AeroSphere

**From One Flight to a Trusted 3D World**

Drone video → intelligent frame analysis → informative frame selection → actual 3D reconstruction → spatial intelligence.

Local Python/Streamlit application using OpenCV, COLMAP CUDA, Open3D and bundled Plotly. Processing works offline after dependencies and optional model weights are installed. The original aerial-photo pipeline remains available.

## Start on this laptop

Double-click `run_aerosphere.bat`, or run `py -3.11 run_aerosphere.py`.
The ignored `config/local.json` selects the existing Python environment. Use `--port 8503 --no-browser` if needed. The server binds to localhost only.

Final source: `C:\Users\chand\Documents\ChatGPT\SIH\AeroSphere`.
Large existing datasets and some reconstruction artifacts remain on D:; local JSON pointers reference those assets. Source, configuration, tests and lightweight UI assets are in this repository. Generated data and machine paths are excluded from Git.

## Mission workflow

1. **HOME** — new mission, demo mission or mission library.
2. **MISSION** — upload MP4/MOV/AVI/MKV, upload an image sequence, or use a local file/folder. Save mission name and mode. Codec support depends on OpenCV. Upload limit is 512 MB per file; use a local path for larger videos.
3. **FLIGHT INTELLIGENCE** — duration, resolution, FPS, sampling counts, selection timeline and actual source thumbnails. Inspect sharpness, brightness, contrast, exposure, feature count and each decision.
4. **RECONSTRUCTION** — explicitly start selected-frame processing. COLMAP estimates cameras and sparse structure; optional CUDA stereo/fusion produces a dense cloud and Poisson mesh. Errors retain diagnostics and available sparse geometry.
5. **3D WORLD** — orbit, pan, zoom, fit/reset, model-axis viewpoints, colored mesh, wireframe, dense/sparse points and camera trajectory. GEO, MEASURE and optional historical context remain in this workspace.
6. **INTELLIGENCE** — exact sparse tracks and source pixels, approximate support/coverage reports and mission-specific review priorities. Optional cached generic COCO predictions.
7. **EXPORT** — full-resolution available geometry, tracks, metadata, reports and checksum manifest in a ZIP. Source photographs are not included.

## Frame selection

The decoder samples sequentially at a configurable interval (default 0.5 seconds, maximum 80 sampled frames in the UI). A cap can truncate the flight; the UI displays this warning. Sampling does not send all 60 FPS frames to reconstruction.

The analyzer rejects unreadable inputs, exact duplicates, very conservative near-duplicates and near-uniform frames with zero detected features. Other blur/exposure warnings retain potentially necessary overlap. A relative information score helps inspection; it is not a confidence score or validated information gain. Camera viewpoint diversity is not inferred from pixel displacement. Selected files are copied unchanged and SHA-256 checked.

## Implemented, validated, provisional, future

- **Implemented:** upload and path ingestion, bounded sampling, frame analysis/gallery/timeline, actual reconstruction, local interactive viewer, camera poses/trajectory, sparse evidence, mission profiles, exports, GPS context and model-space measurements.
- **Validated:** see `FINAL_VALIDATION.md` for the real local video run, the existing 77-image regression, automated tests and browser results. Synthetic codec fixtures are never represented as drone flights.
- **Provisional:** EXIF-based horizontal alignment; model coordinates remain arbitrary. Coverage is a support grid, not scene completeness. Mesh/dense clicks find nearby sparse evidence, not exact surface lineage. Mesh colors come from fused-cloud vertices, not UV textures.
- **Future:** surveyed metric accuracy, physical height, RTK/PPK/IMU synchronization, exact dense-surface provenance, aerial-specific semantic models and independently validated change detection. A historical comparison workflow exists, but no genuine historical pair is supplied.

CONNECT DRONE explicitly reports no connection. `app/drone.py` defines an extension contract; RTSP capture, SDK integration and live telemetry are not implemented. Missing GPS is never invented. Volume requires a watertight orientable model and remains in model units.

## Fresh Windows installation

Install Python 3.11 and a compatible COLMAP 4.2 CUDA build separately. Create `.venv` inside this repository and install `requirements.txt`. No CUDA binaries, environment, dataset or optional weights are in Git.

```powershell
py -3.11 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\run_aerosphere.bat
```

Default COLMAP launcher: `%USERPROFILE%\Downloads\colmap-x64-windows-cuda\COLMAP.bat`. CLI `--colmap` overrides it. Dense defaults are bounded for the GTX 1650 Ti 4 GB (1200 px, five stereo iterations, six source views); CPU mode applies only to sparse extraction/matching. Geometry quality and runtime depend on overlap, motion, texture and hardware. Clean installation on another computer remains unverified.

The 77-photo baseline is the CC0 OpenDroneMap Aukerman dataset: https://github.com/OpenDroneMap/odm_data_aukerman . Download separately into `input/aukerman/` if reproducing that baseline. Local pointers are machine-specific; generate new artifacts on a new installation.

## Tests

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s scripts -p "test_*.py" -v
```

Real-artifact tests require prepared baseline geometry, metadata and optional cached weights. Pure fixture tests can run separately (`test_ingestion.py`, `test_image_intelligence.py`, `test_reconstruction.py`). See validation documentation for exact results, including initial failures.

## Deployment

GitHub stores reproducible source. Vercel is outside immediate scope: this application needs local persistent files, Python, external COLMAP and CUDA processing. No cloud service is required by the core workflow.
