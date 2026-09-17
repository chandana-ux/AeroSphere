# AeroSphere walkthrough

1. Launch `run_aerosphere.bat` and choose **New mission**.
2. Upload a real drone video (or choose a local path), set its sampling interval and click **Analyze flight**.
3. Open **Flight Intelligence** and refresh while processing. Show the video metadata, selected/rejected timeline and actual selected-frame thumbnails. The gallery is paginated in groups of twelve.
4. Expand frame quality to explain the measured indicators and recorded decisions. Keeping all sampled frames is a valid result when they are informative and not redundant.
5. Continue to **Reconstruction** and start local processing. Dense cloud and mesh are optional. Show actual status and failures; never switch silently to an unrelated demo.
6. Open **3D World**. Rotate, pan, zoom, change viewpoints and toggle mesh/wireframe, points, camera poses and trajectory. Sparse-only missions open with sparse points enabled.
7. Select sparse evidence to inspect recorded source pixels. Mesh/dense clicks provide explicitly labeled nearby sparse context.
8. Use GEO and MEASURE where data permits. Missing GPS and unvalidated model scale remain visible. Historical context is optional and separate.
9. Use **Intelligence** for evidence, support/quality and mission priorities.
10. Build and download the mission ZIP from **Export**.

Use **Open demo mission** for a saved reconstruction or **Mission library** for another real mission. The aerial-photo baseline remains a regression reference. Read `FINAL_VALIDATION.md` before quoting results.

Do not call vertex colors UV textures, support density completeness, pixel error centimetre accuracy, generic COCO predictions aerial damage detection, or a sparse track exact mesh-surface evidence.
