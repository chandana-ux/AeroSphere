# Demo V1 validation — 2026-09-17

## Verified before installation

- Nine original baseline tests passed before editing the live project.
- Nine new V1 tests passed: complete cached-mission navigation with socket
  connections forbidden; empty-start navigation; exact reciprocal track integrity
  and replay boundaries; malformed-track rejection; known-transform historical
  alignment and change-candidate math; checksummed full-resolution ZIP exports;
  missing-model behavior; cached real TorchVision inference with network denied;
  model-space area; persistent mission profile roundtrip.
- AppTest navigated all eight main pages plus GEO, MEASURE, coverage and replay.
- Browser loaded the new Home and 3D World. Clicking actual mesh geometry opened
  a nearby real sparse point with three recorded source observations and an
  explicit proximity limitation. Exact sparse-ID selection is also available.
- Fresh 18-image original-data run completed features, matching, sparse mapping,
  dense stereo/fusion and mesh. Largest component: 10/18 cameras, 1,507 points;
  two sparse components; 144,943 dense points; 5,199 triangles; mean error
  0.758530 px. This subset does not demonstrate complete registration.
- Full 77-image reconstruction is being validated separately. Do not infer its
  outcome from the existing cached model or from the subset run.

## Limits of these checks

Network-denied tests block Python socket connections; they do not physically
switch off Wi-Fi. Browser assets are local and cloud-share controls are removed.
No real historical pair is installed; temporal math uses explicitly synthetic
unit-test points, never presented as historical imagery. Field accuracy, height,
RTK/PPK, damage classification and single-pass-video reconstruction quality are
not validated. Mesh color is derived appearance, not UV texturing.

## Original prototype validation (historical record)
# AeroSphere dashboard validation — 2026-09-15

Existing metadata, image selection and reconstruction were reused, not rebuilt.

## Verified working

- Overview shows 77 input images, 77 selected images, 77 registered cameras, 29,457 sparse points, 495,971 dense points, 21,600 mesh triangles and 1.242 px mean reprojection error from existing artifacts.
- Image browser covers original and selected files, metadata and actual quality values.
- Offline latitude/longitude and UTM GPS plots require no basemap service.
- Camera/GPS alignment assessed on all 77 matched camera positions: provisional horizontal scale 24.532755 m/unit; fit RMSE 0.687352 m; five-fold held-out RMSE 0.709687 m against the same EXIF GPS source. These are not independent survey accuracy results.
- Plotly renders real sparse/dense clouds and the actual mesh with camera centers. Browser point sampling is labeled; exports retain complete geometry.
- GPS geodesic distances are in metres assuming WGS84; same-point zero-distance behavior was tested. The initial DSC00229/DSC00230 pair displays 41.05 m. Model point-to-point distances remain in arbitrary units.
- Export buttons expose full PLY files, metadata, trajectory, quality, reconstruction statistics, GPS assessment and measurement JSON.
- Observed/inferred/unknown provenance and missing altitude/accuracy limitations are visible.
- One-command Windows launcher uses the existing parent virtual environment and serves only localhost. It generates the consolidated GPS/coverage reports and does not rerun COLMAP. It was launched on temporary port 8502 and its health endpoint checked; only that test process tree was stopped.
- Streaming video ingestion was tested on generated AVI/MJPEG and MP4 files, including frame caps and invalid/empty input behavior. A browser-submitted synthetic AVI job decoded all 20 frames, extracted five samples at 0.4-second intervals, and completed metadata and image selection. This is an ingestion test, not a drone-video reconstruction claim.
- Coverage uses real tracks and verified image connectivity: 1,418 edges, one component containing 77 images, median track support four views. A 24x24 evidence grid and real reconstructed camera rotation/translation deltas are exported.
- Optional cached SSDLite CPU inference works. DSC00229.JPG produced zero predictions above 0.5; the UI displays zero rather than inventing detections. Scores are uncalibrated generic-model outputs.
- New-input jobs have separate artifact roots. A deliberately insufficient single-image job was rejected before COLMAP with a clear diagnostic and without altering the demo.

## Tests

The full suite passed nine tests, covering metadata/missing GPS, image analysis, duplicates and selection, pose export, alignment math, real artifact counts, bounded video decoding, malformed input, insufficient reconstruction input, optional-model absence, and all nine dashboard pages. GPS and model-space zero-distance checks passed. Streamlit also passed with GPS/altitude fields deliberately missing.

Headless Microsoft Edge, driven by the bundled Playwright runtime, exercised browser navigation, 3D dense/mesh rendering, coverage, cached semantics, measurements, video-job submission and exports. All external page requests were blocked to verify offline operation; no external request was needed. No Streamlit exception or browser JavaScript error occurred. A metadata download was saved and checked to contain 77 records. Screenshots were inspected. The built-in browser tool was unavailable, so verification used the existing browser/runtime instead of adding a project browser dependency.

Only Streamlit and its missing dependencies were installed; existing CV/reconstruction components were left intact. The original input and reconstruction artifacts were not rebuilt or altered by dashboard work.

## Deliberate limits

The horizontal fit uses the visual camera plane. It is not a full 3D georeference; altitude-reference tags and independent control are missing. No validated metre-scale 3D surface measurement, height, area, volume, semantic accuracy, hidden-surface truth or continuous-drone-video reconstruction is claimed. The mesh contains coarse interpolated surfaces. Registration and evidence-grid density do not measure surface completeness. IMU/RTK/PPK/GCP integration remains optional future work.

See README.md for the launch command, demo sequence and module descriptions.

