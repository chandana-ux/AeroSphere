# Demo V1 implementation plan

Baseline inspected 2026-09-17: live project on D: drive; nine existing tests pass.
Existing dashboard.py, extras.py, geo.py and lineage.py provide real artifact views;
scripts contain COLMAP 4.2 orchestration, Open3D geometry, conservative frame
selection, EXIF, bounded OpenCV video ingestion, coverage and cached TorchVision.
Only Aukerman imagery is installed. Preserve the existing uncommitted lineage work.

1. Preserve existing analytical pages as reusable views; add mission navigation,
   persistent mission profiles, graceful empty states and a real dataset library.
2. Add an entirely local layered Plotly viewer with click-to-track inspection,
   camera framing, replay and explicitly scoped evidence coloring.
3. Improve derived mesh appearance/normals without filling or inventing geometry;
   expose bounded COLMAP presets and camera grouping; validate a fresh real run.
4. Add historical import/alignment/distance workflow, model-space measurements,
   offline model loading and checksummed mission ZIP exports.
5. Test failure cases, all navigation, cached reopening, offline network denial,
   real reconstruction and browser rendering; document verified limits.
