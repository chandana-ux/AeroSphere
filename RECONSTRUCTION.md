# AeroSphere COLMAP reconstruction

Run from the existing `aerosphere` directory using the parent Python 3.11 environment:

```powershell
& '..\.venv\Scripts\python.exe' scripts\run_reconstruction.py
```

This consumes the exact selected image directory in `results/image_intelligence/latest.json`. It uses the installed COLMAP under `C:\Users\chand\Downloads\colmap-x64-windows-cuda`. Override with `--colmap PATH`. The supplied batch wrapper fails on quoted paths containing spaces, so Python invokes that installation's `bin/colmap.exe` directly with the same DLL/plugin environment. Nothing is reinstalled.

Every run lives in `output/reconstruction/<UTC run ID>/`. `config.json` records input and executable paths; `stages.json` records the actual commands, exit codes and durations; `logs/` holds complete command output. Stage failures stop sparse processing and name the log. A mapping process exiting successfully is insufficient: the pipeline also requires registered cameras and finite 3D points. The largest component by camera count, then point count, is selected; other components are preserved.

Sparse settings: 1600-pixel maximum extraction dimension, SIFT feature target 8192 (actual extraction count can exceed this), GPU matching capped at 8192, exhaustive matching, four CPU threads, shared SIMPLE_RADIAL camera, CPU bundle adjustment. The Aukerman inputs were checked to share camera model and EXIF focal length. Shared intrinsics should be revisited for other datasets or zoom settings. `--cpu` enables a fresh CPU extraction/matching run; don't switch options while resuming an existing run.

Resume a run without repeating completed stages:

```powershell
& '..\.venv\Scripts\python.exe' scripts\run_reconstruction.py --resume 'output\reconstruction\RUN_ID'
```

Do not modify the images or successful stage artifacts between resumes. Start a fresh run when changing inputs. Failed-stage logs are replaced on retry. To attempt dense reconstruction after sparse success, use the same command with `--dense`. Dense processing undistorts to 800 pixels, uses six automatically chosen neighboring views, photometric PatchMatch (three iterations), 2 GB caches, then fusion and depth-8 Poisson meshing. This lightweight configuration trades detail and geometric filtering for speed. Dense/mesh failures are recorded in the summary while sparse outputs are retained; always check the status fields rather than treating pipeline exit alone as proof of dense success.

## Actual artifacts

- `database.db`: COLMAP SIFT features and verified image matches.
- `sparse/0/` (or other component): native COLMAP model, including cameras and poses.
- `text_N/`: human-readable camera/pose/point exports.
- `sparse.ply`: colored sparse point cloud.
- `camera_trajectory.csv`: image filenames, camera centers, original world-to-camera quaternion and translation.
- `camera_trajectory.png`: static point-cloud and trajectory plot.
- `summary.json`: measured counts, point reprojection errors, track lengths, coordinate limitations.
- `dense/fused.ply`, `dense/mesh.ply`: present only after corresponding stages produce results; consult summary status.
- `output/reconstruction/latest.json`: latest validated sparse run summary, including subsequent dense status.

Interactive viewer:

```powershell
& '..\.venv\Scripts\python.exe' scripts\view_reconstruction.py
& '..\.venv\Scripts\python.exe' scripts\view_reconstruction.py --mode dense
& '..\.venv\Scripts\python.exe' scripts\view_reconstruction.py --mode mesh
```

Drag to rotate, scroll to zoom. Orange markers/lines show camera centers connected in filename order. A missing requested artifact produces an error rather than substituting simulated data. `--run PATH` chooses a particular run. `--snapshot PATH.png` exercises rendering through a hidden Open3D window.

## Interpretation

COLMAP poses are world-to-camera. Camera center is `-R.T @ t`; quaternion order in the export is w,x,y,z. The synthetic parser test verifies translation inversion, rotation inversion and empty observation lines; synthetic fixtures are not reconstruction results.

This is an image-sequence experiment, not a video demonstration. Coordinates remain an arbitrary similarity frame: distances are not metres, GPS is not an applied georeferencing transform, and the model is not automatically oriented to geographic north/up. EXIF altitude references remain unverified. Filename-connected camera positions are not a timestamp-validated trajectory. Reprojection error is a pixel-domain model-fit statistic, not geographic or metric accuracy. Track length counts supporting observations; camera registration does not measure complete surface coverage. Triangulated points are estimates supported by imagery. Poisson surfaces interpolate and can bridge unseen gaps; they must not be presented as observed ground truth.

Test pose export:

```powershell
& '..\.venv\Scripts\python.exe' scripts\test_reconstruction.py
```

## Demo V1 update (2026-09-17)

New runs default to COLMAP camera grouping from image metadata instead of
forcing every image to one camera. Use `--camera-sharing single` only for a
known common camera. `--camera-model` supports SIMPLE_RADIAL/OPENCV and
`--camera-params` accepts optional known intrinsics in COLMAP parameter order.
No calibration is invented. COLMAP still estimates/refines camera parameters.

Dense stereo defaults to 1200 pixels, five photometric iterations, six source
views and a 1 GB stereo cache. `--dense-size 800` lowers memory demand; 1600 is
optional. Features remain bounded at 1600 pixels / 8192 requested features;
matching uses 25-image blocks. CPU extraction/matching is available; dense
PatchMatch requires CUDA. Sparse success survives a dense-stage failure.

`refine_mesh.py RUN_DIRECTORY` writes `dense/mesh_display.ply` plus a JSON
processing report. It removes duplicate/degenerate elements, computes normals
and transfers nearest fused-point colors. It does not smooth, move vertices,
fill holes, add triangles or replace the original mesh. Color distance is
reported in model units and does not imply geometric evidence. No UV texture
is generated. The viewer reports inferred surface geometry honestly.

Existing resume configurations are retained at their original 800-pixel dense
setting. New runs use unique directories. Completed stages are reused. Do not
alter selected input files in-place between resumes.

A fresh 18-image subset test completed with 10 images in its largest sparse
component (two components total), 1,507 sparse points, 144,943 dense points and
5,199 triangles. This validates execution, not complete coverage or improved
accuracy. Full-dataset validation is recorded separately in DEMO_VALIDATION.md.
