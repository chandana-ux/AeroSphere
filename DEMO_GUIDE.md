# AeroSphere Demo V1 — judge walkthrough

Launch `run_aerosphere.bat`. All processing and viewer assets are local. Keep the
launcher terminal open. No model or asset is downloaded at runtime.

1. **HOME** → **Open demo mission**. The figures are read from real COLMAP artifacts.
2. **3D WORLD**: orbit, pan and zoom. Toggle Mesh, Dense Cloud, Sparse Cloud,
   Cameras and Camera Trajectory independently. Fit model / Reset view restores
   framing; Isolate layer removes other geometry from the view.
3. Click a sparse point for its exact source observations. Clicking mesh/dense
   geometry finds a nearby sparse track and explicitly labels the distance and
   scope. It does not claim exact surface provenance. Source images show the
   recorded feature pixel, with a marker on the original image preview.
4. **Evidence View**: cyan denotes sparse estimates with image tracks; amber
   denotes inferred dense/mesh geometry. Unknown surfaces remain absent.
5. **GEO**: offline GPS path, raw source coordinates and provisional horizontal
   alignment. No basemap service is required. **MEASURE** distinguishes GPS
   camera distances from model-space distance/area; volume requires a closed
   orientable mesh. Physical height and validated metric surface measurements
   are unavailable.
6. **EVIDENCE**: inspect exact tracks, then move the observation replay slider.
   This reveals final-model points supported by at least two revealed images,
   in filename order. It is not recorded incremental solver history.
7. **QUALITY & COVERAGE**: registration, reprojection error, connectivity and
   the approximate support grid are real pipeline results. Empty grid cells do
   not prove a missing building or quantify scene completeness.
8. **TEMPORAL**: import an actual historical PLY with at least four noncollinear
   paired landmarks, or explicitly confirm a common coordinate frame. Results
   are distance-based change candidates; occlusion/noise can mimic change.
   No genuine historical pair is currently supplied.
9. **MISSION**: select a mission mode and save it. **INSIGHTS** changes review
   priorities for that mode. Cached generic TorchVision predictions can be
   inspected or generated locally. Zero detections is a valid result.
10. **EXPORT** → **Build mission package** → **Download mission ZIP**. It contains
    full-resolution available geometry, source tracks, camera/GPS metadata,
    quality reports, mission summary and checksums for copied artifacts.

## Process a new flight

MISSION accepts a local image-folder or video-file path. Analyze flight creates
an isolated job. FLIGHT shows actual analysis, retention/rejection reasons and
worker status. Run reconstruction explicitly from FLIGHT; dense cloud/mesh is
optional. Refresh status while processing, then open the cached model. Images
need adequate texture and overlap; three files alone do not guarantee success.

CPU mode covers feature extraction/matching; COLMAP dense stereo needs CUDA.
Sparse output is retained if dense reconstruction fails. Errors expose a short
user message with engineering details in a collapsed diagnostics section.

## Honesty checklist for narration

- This dataset consists of aerial photographs, not validated single-pass video.
- Geometry/poses are estimated; image observations are recorded evidence.
- Mesh color is nearest-cloud vertex appearance, not a UV texture.
- Model units are arbitrary. Reprojection pixels are not geographic accuracy.
- GPS is unvalidated; there is no supplied IMU, RTK, PPK or ground control.
- Generic COCO AI does not detect buildings, roads, vegetation, debris or damage.
- A historical workflow does not establish that a historical dataset exists.
