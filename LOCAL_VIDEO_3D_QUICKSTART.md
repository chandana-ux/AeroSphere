# AeroSphere: real local video reconstruction

This Windows checkout uses Python 3.11.9, OpenCV 5.0.0, Open3D 0.19.0, Streamlit 1.63.0, FFmpeg 9.0.1 and the COLMAP 4.2.0 CUDA CLI. Python packages and the COLMAP application are separate installations.

## Run this computer's existing setup

```powershell
Set-Location D:\AeroSphere-github
.\.venv\Scripts\python.exe scripts\check_runtime.py
.\.venv\Scripts\python.exe run_aerosphere.py --port 8503
```

If the port is occupied, use `--port 8521` or another free port. During this task a validation server was started at http://127.0.0.1:8521. Restart an older running dashboard to load changed Python modules.

COLMAP was extracted from the existing `C:\Users\chand\Downloads\colmap-x64-windows-cuda.zip` into `D:\AeroSphere-github\tools\colmap`. This local tools directory is ignored by Git. No global PATH change or pycolmap installation is needed.

## Install on a fresh Windows machine

Install Python 3.11 x64. In PowerShell:

```powershell
Set-Location D:\AeroSphere-github
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-local.txt
winget install --id Gyan.FFmpeg --exact
```

Download the Windows COLMAP archive from the official [COLMAP releases](https://github.com/colmap/colmap/releases), following the [installation documentation](https://colmap.github.io/install.html). Use a CUDA build and a compatible NVIDIA driver for dense stereo. Extract the entire archive, including DLLs/plugins, not just the executable:

```powershell
New-Item -ItemType Directory -Force tools\colmap | Out-Null
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\colmap-x64-windows-cuda.zip" -DestinationPath tools\colmap
.\.venv\Scripts\python.exe scripts\check_runtime.py
```

The expected path is `tools\colmap\bin\colmap.exe`. If the archive has an extra enclosing folder or COLMAP is installed elsewhere, configure its actual path in the same terminal that starts AeroSphere:

```powershell
$env:AEROSPHERE_COLMAP = 'C:\Tools\COLMAP\COLMAP.bat'
# Alternatively: C:\Tools\COLMAP\bin\colmap.exe or the installation directory
.\.venv\Scripts\python.exe scripts\check_runtime.py
.\.venv\Scripts\python.exe run_aerosphere.py --port 8503
```

Restart PowerShell after installing FFmpeg if its PATH has not refreshed. OpenCV's built-in FFmpeg backend decodes frames; an external `ffprobe` supplies additional container diagnostics when present. `pycolmap` alone does not install the command-line program. The runtime checker probes each command, and the runner checks options against that installed command's help, including older SIFT option names. Availability of a dense command alone does not guarantee a usable GPU.

## Run your own video

1. Open **MISSION**, name the new mission, upload a video or select its existing local path.
2. Start with **0.5 seconds**, **40 frames**, reconstruction enabled, and CPU features/matching enabled. Increase the cap for longer captures; it deliberately bounds work and may process only the beginning of a video. Dense/mesh generation is optional.
3. Click **Analyze flight**, then choose the new **Active mission**. Frames and outputs belong to that mission. Workers run outside the dashboard process.
4. Open **RECONSTRUCTION**. This panel refreshes every three seconds and reports each stage independently. Sparse results become available before dense processing completes. Other pages update when navigated to or rerun.
5. Open **3D WORLD**. The available mesh, dense cloud or sparse cloud is selected initially; switches enable other available layers and wireframe. A failed mission never receives the bundled example's geometry.
6. **GEO** shows reconstructed camera centers and any supplied image GPS. **MEASURE** selects actual sparse point IDs. **QUALITY** displays counts, registration ratio and pixel reprojection errors. **INTELLIGENCE** shows model extents and source-image tracks.

A CLI example with a fresh, unique job folder:

```powershell
$job = 'results\jobs\' + (Get-Date -Format 'yyyyMMdd_HHmmss_ffff')
.\.venv\Scripts\python.exe scripts\pipeline.py --input 'C:\Videos\building.mp4' --job $job --interval 0.5 --max-frames 40 --reconstruct --dense --cpu
```

For a fixed-lens/constant-zoom video, add `--camera-sharing single` or enable **Same camera lens and zoom throughout** in Mission/Reconstruction. This shares estimated intrinsics and can substantially stabilize video alignment. It is an explicit assumption, not calibration.

Sparse only: omit `--dense`. Analyze only: omit `--reconstruct --dense`. Each job must be an immediate child of `results/jobs`. Reusing an existing processed job for ingestion is rejected.

Retry reconstruction of an already analyzed dataset (creates a fresh reconstruction run):

```powershell
.\.venv\Scripts\python.exe scripts\reconstruct_job.py --project 'results\jobs\YOUR_JOB' --dense --cpu
```

For an explicitly fixed lens/zoom, advanced users can share estimated intrinsics:

```powershell
.\.venv\Scripts\python.exe scripts\run_reconstruction.py --project 'results\jobs\YOUR_JOB' --camera-sharing single --dense --dense-size 800 --cpu
.\.venv\Scripts\python.exe scripts\pipeline.py --report 'results\jobs\YOUR_JOB'
```

`--cpu` applies to features/matching. Dense stereo selects GPU 0 and is not represented as a CPU fallback. The default 800-pixel dense resolution, six source views and bounded caches suit a small GPU. Poisson meshing uses depth 8 / trim 5; its surfaces are interpolated estimates, and success requires real finite vertices and triangles.

## Capture guidance and limitations

Use a textured static building or object. Walk/fly around it slowly with overlapping views and translation, keeping the subject in frame. Avoid stationary cameras, pure panning, motion blur, reflective/transparent surfaces, changing zoom, moving subjects and edited scene cuts. Try 10-30 seconds before a long mission. Video resolution and FPS are detected; frames are bounded to a 1280-pixel maximum dimension. More frames do not guarantee better geometry.

Reconstruction may register only part of the video or produce disconnected components. The largest component is displayed; component count and registered/selected ratio are retained. Geometry is not ground truth. Model distances are arbitrary units, not metres. Video GPS/flight telemetry is not automatically extracted; absent coordinates are never invented. Meshes may contain holes or bridges, and no watertightness, survey accuracy or semantic identity is promised.

## Diagnostics and recovery

Each dataset contains `job.json`, `reconstruction_job.json`, `reconstruction_progress.json`, `video_ingestion/`, `results/image_intelligence/`, and timestamped `output/reconstruction/` runs. COLMAP command logs, available option help, configuration and image-content fingerprint are retained with each run. `latest.json` references that dataset's latest successfully produced sparse geometry; the UI hides earlier output during a new attempt or after its failure.

Nonzero exits, empty point clouds and empty/nonfinite meshes are failures. Dense/mesh errors preserve a successful sparse result. Secondary report failures are reported as partial completion. New retries use fresh databases. `--resume` is an advanced CLI option requiring the original paths/options and unchanged input contents; legacy runs without a content fingerprint should be retried as fresh runs.

Only one reconstruction can hold a dataset's `reconstruction.lock`. If a worker is forcibly killed, its lock/progress can remain. Read the PID in the lock and confirm that worker has ended in Task Manager before removing that **specific dataset's lock**. Then retry through `scripts/reconstruct_job.py`. Do not remove a live worker's lock. Automatic cancellation/recovery after OS termination is not implemented.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s scripts -p 'test_*.py'
.\.venv\Scripts\python.exe scripts\verify_local_datasets.py results\jobs\validation_video_1 results\jobs\validation_video_2_shared results\jobs\validation_outdoor_fixed
```

See `docs/LOCAL_RECONSTRUCTION_VALIDATION.md` for measured video results and exact test scope. The verifier checks input hashes, decoded source-frame agreement, selected-frame hashes, geometry counts and all eight Streamlit pages. It does not treat synthetic fixtures or a precomputed mesh as successful video reconstruction.
