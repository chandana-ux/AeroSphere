# Final priority build validation — 17 September 2026

## Real aerial video

Local input: `12183581-hd_1080_1920_60fps.mp4` from Downloads. Sampled images show an aerial town flyover; no capture metadata proving flight platform, camera calibration or survey accuracy was supplied. The other local clip was inspected but not reconstructed.

- Decoder: H.264, 720 × 1280, 60 FPS, 1,153 decoded frames, reported duration 19.217 seconds.
- Sampling: 0.5-second interval, cap 50; 39 extracted, analyzed and selected frames. No truncation. All 39 were retained by the conservative filter; no rejection percentage was fabricated.
- Actual COLMAP result: 39/39 registered images in one component, 22,714 sparse points, 131,790 dense points and 7,331 mesh triangles. Mean reprojection error 0.704252 pixels, not metric accuracy.
- Features, matching and mapping ran on selected files from this video. No cached photograph model was substituted.
- Approximate recorded stage times: extraction 10.46 seconds, features 3.96 seconds, matching 11.25 seconds, sparse mapping 618.96 seconds, successful undistortion 1.97 seconds, stereo 279.94 seconds, fusion 20.47 seconds, mesh 1.99 seconds. These are individual logged durations, not an uninterrupted end-to-end benchmark.
- First dense attempt failed during undistortion after C: ran low on space and D: storage was linked. Resuming with approved access and the original configuration succeeded. Sparse reconstruction was reused. An attempted 800-pixel resume was correctly rejected because it differed from the original 1200-pixel configuration.
- Dense geometry is stored on D: through a directory junction beneath the mission run. Original input remains unchanged. Mission reports were refreshed after successful resume.
- GPS absent. Geometry is arbitrary scale. Moving traffic, limited viewpoints, occlusion and Poisson interpolation remain limitations. A successful reconstruction is not proof of accurate or complete surfaces.

## Regression and workflow checks

Final automated result: **21 tests passed** (112.125 seconds on this prepared machine). The actual upload browser check completed analysis and found 13 image elements (12 gallery thumbnails plus the detailed preview). A separate completed browser check loaded the real video mesh, exercised drag/rotation and fit/reset, inspected the gallery/timeline and reported no JavaScript errors with external page requests blocked. Final screenshots were visually inspected. The reconstructed mesh is coarse and incomplete; the screenshot is actual output, not a generated model.

Baseline before changes: 18 tests ran; 17 passed and one failed because the staging copy lacked `output/reconstruction/latest.json`. This was an artifact-location failure, not a reconstruction failure. The final source folder has the baseline pointers and metadata, reusing preserved D: assets.

The revised suite covers existing photo geometry, camera math, all seven navigation pages, measurement behavior and absent GPS, exact sparse lineage, historical alignment math, offline optional inference, checksummed ZIPs, mission profiles, actual upload persistence, filename traversal/duplicates, real codec decoding, invalid video, frame decisions/timestamps, selected-file existence and input controls. Home assertions were updated to require no hero metrics. New featureless-frame rejection is covered by the existing quality fixture; viewpoint-changing and blurred-but-useful frames remain preserved.

Browser verification uses headless Edge with external page requests blocked. The built-in browser tool failed initialization, so the installed Playwright runtime was used. Screenshots are under `docs/screenshots/final-*.png`. The upload test uses the same real local video, then checks actual processing and source thumbnails. Decoder fixtures in automated tests are synthetic and are not presented as real flights.

## Boundaries

No clean installation on a second computer was performed. Baseline integration tests require local data/weights and are not standalone source-only tests. RTSP/SDK drone connection is an interface contract, not a working hardware integration. UV texture mapping, exact dense-surface lineage, surveyed scale/height, aerial damage detection and genuine historical change validation remain future work. Vercel is excluded from immediate scope because the Python/COLMAP/CUDA pipeline needs persistent local processing.
