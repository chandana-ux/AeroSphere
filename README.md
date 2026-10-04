# AeroSphere

**From One Flight to a Trusted 3D World**

Drone video → intelligent frame analysis → informative frame selection → actual 3D reconstruction → spatial intelligence.

Local Python/Streamlit application using OpenCV, COLMAP CUDA, Open3D and bundled Plotly. Processing works offline after dependencies and optional model weights are installed. The original aerial-photo pipeline remains available.


## Local reconstruction from your own videos

For Windows COLMAP installation/detection, bounded frame sampling, independent stage status,
per-dataset geometry, camera-sharing settings and exact run/test commands, see
[Local video reconstruction quickstart](LOCAL_VIDEO_3D_QUICKSTART.md).
Measured results and limitations are in [Local reconstruction validation](docs/LOCAL_RECONSTRUCTION_VALIDATION.md).


## Start on this laptop

Double-click `run_aerosphere.bat`, or run `py -3.11 run_aerosphere.py`.
The ignored `config/local.json` selects the existing Python environment. Use `--port 8503 --no-browser` if needed. The server binds to localhost only.

Final source: `C:\Users\chand\Documents\ChatGPT\SIH\AeroSphere`.
Large existing datasets and some reconstruction artifacts remain on D:; local JSON pointers reference those assets. Source, configuration, tests and lightweight UI assets are in this repository. Generated data and machine paths are excluded from Git.

## Mission workflow

1. **MISSION** — name a mission, choose its mode, and upload MP4/MOV/AVI/MKV or an image sequence, or select an existing local path. Each input gets a separate mission/output folder. Upload limit is 512 MB per file; use a path for larger videos.
2. **FRAMES** — inspect the input-specific duration, resolution, FPS, frame timestamps, thumbnails, selection counts and image-quality reasons. Sampling uses decoded timestamps/FPS and records truncation when the configured frame cap is reached.
3. **RECONSTRUCTION** — analyze frames, then run COLMAP 4.2 sparse reconstruction. Dense stereo/Poisson mesh is optional and requires a compatible NVIDIA/CUDA runtime. Per-stage progress, command logs and failures are kept with that mission. If COLMAP is missing, new reconstruction is disabled and the separate precomputed mesh demo is clearly labeled.
4. **3D WORLD** — inspect only the selected mission’s available sparse cloud, dense cloud, mesh, wireframe and camera path. Missing/failed outputs remain unavailable; another dataset’s demo mesh is never substituted.
5. **GEO / MEASURE / QUALITY / INTELLIGENCE** — display source GPS or relative camera/mesh coordinates; measure actual mesh/sparse geometry in native units; review reconstruction counts and reprojection error; inspect selected-frame evidence and sparse tracks. These outputs are not metre-accurate or semantic facts. Optional COCO detection requires cached local weights.

Not every video is suitable for photogrammetry: a fixed camera, pure panning, moving subjects, low texture, blur, cuts, or insufficient overlap can prevent an initial camera pair or produce incomplete geometry. See the measured successes and genuine failure in [Local reconstruction validation](docs/LOCAL_RECONSTRUCTION_VALIDATION.md).

## Frame selection

The decoder samples sequentially at a configurable interval (default 0.5 seconds, maximum 80 sampled frames in the UI). A cap can truncate the flight; the UI displays this warning. Sampling does not send all 60 FPS frames to reconstruction.

The analyzer rejects unreadable inputs, exact duplicates, very conservative near-duplicates and near-uniform frames with zero detected features. Other blur/exposure warnings retain potentially necessary overlap. A relative information score helps inspection; it is not a confidence score or validated information gain. Camera viewpoint diversity is not inferred from pixel displacement. Selected files are copied unchanged and SHA-256 checked.

## Implemented, validated, provisional, future

- **Implemented:** per-mission upload/path ingestion, bounded video sampling, frame analysis/gallery/timeline, COLMAP sparse and optional dense/mesh reconstruction, mission-scoped 3D viewer, camera positions/trajectory, GPS/relative-coordinate views, geometry measurements and input-derived quality/intelligence pages.
- **Validated:** [local reconstruction validation](docs/LOCAL_RECONSTRUCTION_VALIDATION.md) records two distinct aerial-video runs with verified sparse, dense and mesh PLYs, plus the fixed-camera clip's actual sparse-initialization failure. `scripts/verify_local_datasets.py` checks source/frame provenance, geometry and all eight sidebar pages/viewer modes. Synthetic codec fixtures are reported separately from real footage.
- **Not currently exposed in navigation:** `mission.package_mission()` can build a checksummed ZIP from completed artifacts, but the workspace Export button does not yet invoke it. Optional COCO detection requires separately cached weights.
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

COLMAP discovery supports `AEROSPHERE_COLMAP`, PATH and `tools/colmap/bin/colmap.exe`; CLI `--colmap` overrides discovery. Dense defaults are bounded for the GTX 1650 Ti 4 GB (800 px, five stereo iterations, six source views); CPU mode applies only to sparse extraction/matching. Geometry quality and runtime depend on overlap, motion, texture and hardware. Clean installation on another computer remains unverified.

The 77-photo CC0 OpenDroneMap Aukerman baseline remains useful for the photo-only regression: https://github.com/OpenDroneMap/odm_data_aukerman . It is separate from the two validated local video datasets. Local inputs and reconstruction outputs are machine-specific and excluded from Git.

## Tests

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s scripts -p "test_*.py" -v
& .\.venv\Scripts\python.exe scripts\check_runtime.py
& .\.venv\Scripts\python.exe scripts\verify_local_datasets.py results\jobs\validation_video_1 results\jobs\validation_video_2_shared results\jobs\validation_outdoor_fixed
```

Real-artifact tests require prepared baseline geometry, metadata and optional cached weights. Pure fixture tests can run separately (`test_ingestion.py`, `test_image_intelligence.py`, `test_reconstruction.py`). See validation documentation for exact results, including initial failures.

## Deployment

GitHub stores reproducible source. Vercel is outside immediate scope: this application needs local persistent files, Python, external COLMAP and CUDA processing. No cloud service is required by the core workflow.

### Streamlit Community Cloud

The bundled demo mesh and dashboard can be viewed in the cloud when the app is deployed with Python 3.11 or 3.12; Open3D 0.19.0 publishes wheels for those versions (and up through Python 3.12). Select a supported version in the app's Advanced settings and keep the pinned `requirements.txt`. Python 3.13+ is not supported by the pinned Open3D release. The deployment's Python version cannot be pinned by this repository's requirements file.

Cloud deployment does not include the local COLMAP executable or a CUDA GPU, so starting new COLMAP reconstruction, especially dense reconstruction, is not supported there. COLMAP must be installed separately on a local machine; the app only enables new reconstruction when its launcher is found. The video reader uses OpenCV rather than invoking the FFmpeg command directly. Local FFmpeg is installed on the development machine, but codec support in another environment depends on that environment's OpenCV build. Streamlit Cloud cannot read paths on a user's computer; use uploads there. Treat cloud storage as temporary, and use a local deployment for persistent mission data and full reconstruction.
