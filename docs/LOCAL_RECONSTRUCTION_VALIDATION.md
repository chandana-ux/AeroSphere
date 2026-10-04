# Local reconstruction validation ? 2026-10-04

## Environment and scope

Windows, Python 3.11.9 in `.venv`, OpenCV 5.0.0, Open3D 0.19.0, Streamlit 1.63.0, FFmpeg 9.0.1. The existing downloaded COLMAP archive was extracted into `tools/colmap`; its executable reports **COLMAP 4.2.0, commit be5e291, CUDA**. GPU: NVIDIA GTX 1650 Ti, 4096 MiB; driver 592.82. No Python package was treated as a replacement for the COLMAP CLI.

Real video processing uses OpenCV's FFmpeg decoder, feature detection/matching, COLMAP pose estimation/triangulation, CUDA PatchMatch, fusion and Poisson meshing. Each test has its own job folder and timestamped reconstruction runs. No bundled mesh or synthetic geometry was substituted.

## Distinct input videos

- **Sample Video - 1.mp4**: oblique aerial view of buildings and a railway, 720?1280, 60 FPS, 24.0167 seconds. Sampling: 0.5 seconds, cap 40; 40 extracted/selected frames. Job: `results/jobs/validation_video_1`. Final run uses GPU features/matching and automatic camera grouping.
- **Sample video - 2.mp4**: downward aerial view along a residential street, 720?1280, 60 FPS, 19.2167 seconds. Sampling: 0.75 seconds, cap 24; 24 extracted/selected frames. Job: `results/jobs/validation_video_2_shared`. Uses CPU features/matching and shared intrinsics (`--camera-sharing single`), assuming unchanged lens/zoom.
- **OpenCV vtest.avi**: fixed-camera outdoor scene with pedestrians, 768?576, 10 FPS, 79.5 seconds. Sampling: 1 second, cap 15; 15 extracted/selected frames. Job: `results/jobs/validation_outdoor_fixed`. Source: [OpenCV official sample](https://github.com/opencv/opencv/blob/4.x/samples/data/vtest.avi). Used to test unsuitable input, not as a positive reconstruction example.

The initially discovered third local filename was byte-identical to Sample Video 2 and was excluded. Video SHA-256 values and frame-provenance checks are recorded in `results/local_video_validation.json`.

## Measured results

Final measured table is generated from the verification report below.

## What was exercised

- Actual COLMAP executable and individual command help, GPU and CPU feature/matching paths, camera sharing, sparse/dense/mesh stages.
- Separate dataset folders, agreement between decoded original video and extracted first frame, SHA-256 equality of every selected copy with its extracted source, distinct source hashes, in-dataset output paths and independently read PLY counts.
- All eight pages using Streamlit AppTest for each distinct dataset, with the active dataset asserted throughout.
- Actual geometry payloads supplied to the 3D component for Mesh, Dense cloud, Sparse cloud and Wireframe; mesh triangle indices and point coordinates are present.
- Geo displays reconstructed relative camera centers; Measure computes from selected real sparse points; Quality displays measured counts/registration ratio/reprojection error; Intelligence displays actual bounds and sparse image observations.
- Dependency-missing terminal state, invalid executable override, older SIFT option aliases, unsupported required options, concurrent-run lock protection, atomic status replacement, stale/cross-dataset output rejection, existing upload/invalid-media/geometry tests.
- `pip check`: no broken requirements. The local server at `http://127.0.0.1:8521` returns `ok` from `/_stcore/health`.

Browser automation was unavailable (no connected browsers). UI checks are Streamlit AppTest and serialized viewer geometry checks, not a claim of screenshot/WebGL inspection.

## Honest failures and tuning observations

The first meshing attempt used depth 8 with COLMAP's default trim 10. COLMAP exited zero but wrote no triangles; this is now correctly a failed mesh stage. Trim 5 produced a finite triangle mesh, and a subsequent full fresh reconstruction confirmed the final pipeline behavior. The original failed run/logs remain under the same dataset for inspection.

The initial automatic-camera attempt on Sample Video 2 repeatedly adjusted independent camera intrinsics and was deliberately stopped after roughly 13 minutes of mapping. Its failed/interrupted record remains in `results/jobs/validation_video_2`; it is **not** counted as a successful run. The final `validation_video_2_shared` run uses a new dataset/database with 24 frames and shared intrinsics. Changing both sampling and camera sharing means the timing difference is not a controlled benchmark.

The fixed-camera outdoor video failed at COLMAP initialization: no good initial image pair / no sparse model. Sparse is Failed; Dense and Mesh are Not started. No geometry or geographic coordinates were fabricated. The interface provides capture advice and the actual command log.

## Remaining limitations

Successful reconstruction means finite triangulated/dense/mesh output, not photogrammetric ground truth. Geometry may contain holes, disconnected surfaces or interpolated bridges; scale/orientation are arbitrary. None of these videos supplied GPS, calibrated scale, RTK/PPK or ground control. GPS-bearing inputs retain existing EXIF support, but no new georeferenced real-video test was available. Measurements are in native model units. Semantic object detection remains optional and requires local weights; it was not validated here.

Sampling caps truncate long captures. GPU/backend/build support limits dense reconstruction. Fresh reruns can differ numerically because matching/mapping includes nondeterministic computation. Version-option aliases were regression-tested; only the installed COLMAP 4.2 binary was exercised end to end. After a forcibly killed worker, manual stale-lock recovery may be necessary; see the quickstart.

## Files changed

- `app/reconstruction_runtime.py` (new): shared discovery, launcher/DLL setup, command/option probing and atomic JSON writes.
- `scripts/run_reconstruction.py`: real version-aware commands, locked runs, input fingerprints, live stage states, finite-output validation, bounded GPU dense processing and usable mesh settings.
- `scripts/reconstruct_job.py`, `scripts/pipeline.py`: CPU/shared-camera settings, error/partial outcomes, per-dataset workers, report-failure separation.
- `scripts/extract_video.py`: explicit OpenCV FFmpeg decoder and optional external ffprobe metadata.
- `app/dashboard.py`: active-dataset guards, background controls, live independent status, retries, relative Geo, geometry Intelligence and missing-artifact handling.
- `app/world.py`: valid per-dataset geometry, automatic available layer, independent wireframe, honest dense counts and empty/corrupt geometry errors.
- `app/mission.py`: dataset-derived names and actual processing status.
- `app/extras.py`: registration ratio and mesh counts in Quality.
- `scripts/check_runtime.py` (new), `scripts/test_reconstruction_runtime.py` (new), `scripts/verify_local_datasets.py` (new): diagnostics and regression/real-dataset verification.
- `requirements.txt`: Open3D pin corrected to the installed/tested Windows 0.19.0 version.
- `.gitignore`: local COLMAP tools excluded.
- `README.md`, `LOCAL_VIDEO_3D_QUICKSTART.md`, this report: exact installation, run, verification and limitation documentation.

See [the quickstart](../LOCAL_VIDEO_3D_QUICKSTART.md) for complete installation and run commands.
