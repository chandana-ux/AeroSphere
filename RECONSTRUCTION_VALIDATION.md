# Verified Aukerman reconstruction — 2026-09-15

Run: `output/reconstruction/20260915T014456_030136Z`

Installed COLMAP 4.2.0, commit be5e291, reports CUDA support. `COLMAP.bat -h` succeeds. The batch wrapper fails when arguments contain the spaces in this project's path (`Tranfer was unexpected at this time`). The pipeline therefore calls the same installation's colmap.exe with its DLL/plugin environment. No reinstallation was performed.

## Actual output

| Metric | Result |
|---|---:|
| Input images | 77 |
| Registered images | 77 |
| Sparse components | 1 |
| Sparse points | 29,457 |
| Verified image pairs | 1,418 |
| Point observations | 157,792 |
| Mean point reprojection error | 1.242244 pixels |
| Median point reprojection error | 1.224887 pixels |
| Mean track length | 5.356689 views |
| Depth maps | 77 |
| Fused dense points | 495,971 |
| Mesh vertices | 11,688 |
| Mesh triangles | 21,600 |

The COLMAP analyzer and exported sparse data agree. Open3D loaded the sparse and dense PLY files and mesh. Coordinates were checked finite; mesh triangle indices are in range. The camera CSV contains 77 unique image names and finite camera centers. All 77 originals and selected images still match their pre-reconstruction SHA-256 hashes.

Synthetic pose-parser tests passed for rotation/translation inversion, image filenames with spaces, and empty observation lines. The synthetic fixtures are not part of the aerial demo. Resume testing reused all completed sparse stages and preserved dense/mesh success status. Hidden Open3D rendering succeeded for sparse and mesh outputs. The initial mesh render exposed back-face culling; two-sided display was enabled and the corrected render inspected.

## Limits

The dense run experienced an approximately two-hour tool/wait interruption. Logs record wall-clock stereo time of 7,232.8 seconds; this is not a useful uninterrupted performance benchmark. Sparse stages recorded approximately 21.1 seconds extraction, 62.6 seconds matching, and 203.2 seconds mapping on this run, not a general performance guarantee.

The mesh is coarse, with gaps and smooth interpolated patches; it is not a complete or validated measurement surface. Poisson interpolation can bridge missing evidence. All geometry remains in arbitrary COLMAP coordinates and units. No GPS alignment, metric scale, RTK validation, or hidden-surface accuracy is established by this experiment. Pixel reprojection error is not metre/centimetre accuracy. This dataset consists of aerial photographs, not continuous video.

## Open the result

From `aerosphere`:

```powershell
& '..\.venv\Scripts\python.exe' scripts\view_reconstruction.py --mode mesh
```

Use `--mode dense` or `--mode sparse` to inspect the other real outputs. Orange points/lines are camera centers connected in filename order, not independently validated temporal flight tracks. The viewer renders both sides of triangles because geographic up is not yet established.

To reuse this run and verify all stages without recomputing successful stages:

```powershell
& '..\.venv\Scripts\python.exe' scripts\run_reconstruction.py --resume 'output\reconstruction\20260915T014456_030136Z' --dense
```

Full commands and outputs are in the run's `stages.json` and `logs/`. Use `RECONSTRUCTION.md` for settings, file descriptions and limitations.
