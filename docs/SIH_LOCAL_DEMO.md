# SIH local demo recording checklist

Use the outer project at `D:\AeroSphere-github`, not the untracked nested `AeroSphere` checkout. The application preserves the AEROSPHERE / From One Flight to a Trusted 3D World header and dark/cyan layout.

## Open the tested app

If the validation server is still running, open http://127.0.0.1:8521. Otherwise:

```powershell
.\.venv\Scripts\python.exe run_aerosphere.py --port 8521
```

## Record the functional demonstration

1. **MISSION:** select `Video 1 - buildings and railway`. Explain that this geometry was reconstructed locally from Sample Video 1, rather than loaded from the separate bundled example.
2. To show a fresh run, upload `uploads/888ef1798c3840cdb7583ace3ae28805/Sample Video - 1.mp4`, name a new mission, use 0.5-second sampling and a 40-frame cap, enable reconstruction/dense/mesh, and uncheck CPU features to reproduce the tested GPU configuration. Automatic camera grouping was used for the verified first video.
3. **FRAMES:** show the actual extracted images, timestamps, selected/rejected decisions and warnings.
4. **RECONSTRUCTION:** show independent stage states and the current COLMAP step. Processing takes minutes. A clearly labeled recording cut or time-lapse is appropriate; do not present it as instantaneous. Preserve mission identity across the cut.
5. **3D WORLD:** show the new mesh, then Dense cloud, Sparse cloud and Wireframe. Rotate/zoom as available in the browser. Exact counts can vary on rerun; show the current measured values.
6. **GEO:** show reconstructed relative camera positions. State that these videos do not include GPS, so this is not a georeferenced map.
7. **MEASURE:** open model-space measurements and select two actual sparse point IDs. Read the distance in model units, not metres.
8. **QUALITY:** show registered/selected views, point counts, mesh statistics and reprojection error. These are reconstruction indicators, not a survey-accuracy score.
9. **INTELLIGENCE:** show reconstructed geometry extents and the image observations supporting a sparse point. Do not describe these as automatic building/vehicle identification.
10. Switch **Active mission** to `Video 2 - residential street`. Show its different source frames and geometry. The verified run uses 0.75-second sampling, 24 frames, CPU features and **Same camera lens and zoom throughout** enabled. Reconstructing it afresh requires the same settings and a new mission.
11. Optionally select `Fixed-camera video - expected failure`. Show the initialization failure and absent geometry as an example of honest unsuitable-input handling.

The validated stored outputs contain 40,601 triangles for Video 1 and 101,900 for Video 2. These are example run results, not promises for new videos. The original precomputed example remains separately named and should not be represented as a reconstruction of an uploaded video.

## Claims supported by this task

- Two distinct real aerial videos produced their own sparse cloud, dense cloud and mesh.
- Three distinct inputs have verified frame provenance and separate output folders.
- All eight pages and four available geometry modes passed Streamlit/payload checks.
- Unsuitable fixed-camera input failed without fake geometry.

Browser automation was unavailable; visually rehearse camera rotation, zoom, layout and recording in your own browser before submitting. Cloud deployment, the newly introduced experimental OpenCV fallback, semantic detector weights, metric georeferencing and survey accuracy were not validated.
