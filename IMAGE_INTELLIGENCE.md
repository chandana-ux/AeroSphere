# AeroSphere image intelligence

From the aerosphere directory, run:

```powershell
& '..\.venv\Scripts\python.exe' scripts\analyze_images.py
```

Use `--input PATH` for another image directory. Original images are read only. Results are saved under `results/image_intelligence/<UTC run ID>/`; unchanged, SHA-256-verified selected images go to `selected_frames/<UTC run ID>/`. A rerun creates new directories and uses more disk space. `results/image_intelligence/latest.json` points to the latest completed run. Downstream COLMAP must use that exact selected directory, not the parent containing multiple runs.

## Measurements

Analysis uses a maximum dimension of 1200 pixels and CPU ORB with a 4000-feature cap. Blur is grayscale Laplacian variance, a sharpness proxy sensitive to texture, noise, and resizing. Brightness is grayscale mean; contrast is standard deviation. Dark and bright fractions count grayscale pixels <=5 and >=250. Features are ORB keypoint counts; occupied cells count feature spread in an 8x8 image grid. Neither feature spread nor feature count measures reconstructed scene coverage.

Quality = 0.5 * normalized sharpness + 0.25 * normalized contrast + 0.25 * unclipped fraction. Sharpness and contrast use dataset 10th/90th percentile normalization with clipping to [0,1]; constant values receive 0.5. Information score = 0.6 * quality + 0.25 * capped feature fraction + 0.15 * occupied grid fraction - duplicate penalty (1 for confirmed duplicates). This is a within-run heuristic ranking, not information theory, a calibrated probability, or a cross-dataset accuracy measure. Camera viewpoint change is not estimated here.

## Conservative selection

All readable nonduplicate images are retained regardless of score to avoid losing reconstruction overlap. Globally identical file hashes are removed. Near-duplicate checks consider the five most recent retained images and require equal analysis dimensions, mean absolute pixel difference <=2, pixel correlation >=0.999, at least 100 mutual ORB matches with Hamming distance <=32, matches covering at least 80% of the larger feature set, and 95th-percentile feature displacement <=0.002 of the image diagonal. Both feature and pixel evidence must agree. First/last filenames are protected against near-duplicate removal, but exact copies are still removed. Low-texture images are not rejected as near duplicates. Unknown or changed viewpoints are retained. The first retained duplicate representative is used; selection does not optimize which duplicate is sharpest.

Filename ordering is not guaranteed capture ordering. These intentionally strict rules may retain every image in an already curated aerial dataset. There is no target removal percentage. Pixel similarity is not proof of physical scene identity, and repeated textures can still mislead; exclusion evidence is saved for review. Future video selection will require explicit temporal/overlap evaluation.

## Outputs and configuration

- `image_quality.csv`: per-image measurements, warnings, score, hash, selection reason, error.
- `redundancy_pairs.csv`: measured candidate/reference comparisons. Blank match fields mean the pixel gate failed or comparison was unavailable.
- `selection_manifest.json`: retained source filenames and measured attributes.
- `summary.json`: actual counts, effective thresholds, paths, timing, and limitations.
- `quality_overview.png`: sharpness, feature count and score plots.

Optional `config/image_intelligence.json` overrides keys in `DEFAULTS` in the script. No additional dependencies are required. Decode errors are recorded, other readable images continue, and the CLI returns nonzero if any image fails. Copies are verified before the run is published as latest. Do not use an incomplete run after a disk/copy error.

Behavioral tests use synthetic fixtures (not drone demonstration data):

```powershell
& '..\.venv\Scripts\python.exe' scripts\test_image_intelligence.py
```

OpenCV ORB matching reference: https://docs.opencv.org/4.10.0/dc/dc3/tutorial_py_matcher.html
