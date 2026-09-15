"""CPU image quality analysis and deliberately conservative duplicate filtering."""
import argparse
import csv
import hashlib
import json
import shutil
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

DEFAULTS = dict(max_dimension=1200, orb_features=4000, comparison_window=5,
                max_pixel_mae=2.0, min_correlation=0.999, min_matches=100,
                min_match_fraction=0.8, max_displacement_fraction=0.002,
                blur_warning=50.0, contrast_warning=15.0, feature_warning=200)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def analyze(path, cfg):
    image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('OpenCV could not decode image')
    height, width = image.shape[:2]
    scale = min(1.0, cfg['max_dimension'] / max(height, width))
    if scale < 1:
        image = cv2.resize(image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    keypoints, descriptors = cv2.ORB_create(nfeatures=cfg['orb_features']).detectAndCompute(gray, None)
    points = np.array([k.pt for k in keypoints], dtype=np.float32).reshape(-1, 2)
    row = dict(width=width, height=height, analysis_width=gray.shape[1], analysis_height=gray.shape[0],
               blur_laplacian_variance=float(cv2.Laplacian(gray, cv2.CV_64F).var()),
               brightness_mean=float(gray.mean()), contrast_std=float(gray.std()),
               dark_fraction=float(np.mean(gray <= 5)), bright_fraction=float(np.mean(gray >= 250)),
               orb_keypoints=len(keypoints), feature_cells_occupied=0)
    if len(points):
        cells = np.minimum((points / [gray.shape[1], gray.shape[0]] * 8).astype(int), 7)
        row['feature_cells_occupied'] = len(set(map(tuple, cells)))
    warnings = []
    for condition, label in [(row['blur_laplacian_variance'] < cfg['blur_warning'], 'low_sharpness_proxy'),
                             (row['contrast_std'] < cfg['contrast_warning'], 'low_contrast'),
                             (len(points) < cfg['feature_warning'], 'few_features'),
                             (row['dark_fraction'] + row['bright_fraction'] > 0.5, 'heavy_clipping')]:
        if condition:
            warnings.append(label)
    row['warnings'] = ';'.join(warnings)
    return row, gray, points, descriptors


def compare(a, b, cfg):
    """Require near-identical pixels AND many spatially stationary feature matches."""
    ga, pa, da = a
    gb, pb, db = b
    result = dict(pixel_mae=None, correlation=None, matches=0, match_fraction=0.0,
                  displacement_p95_fraction=None, near_duplicate=False)
    if ga.shape != gb.shape:
        return result
    result['pixel_mae'] = float(np.mean(np.abs(ga.astype(np.float32) - gb.astype(np.float32))))
    if ga.std() == 0 or gb.std() == 0:
        return result  # Featureless images never prove a repeated viewpoint.
    result['correlation'] = float(np.corrcoef(ga.ravel(), gb.ravel())[0, 1])
    if da is None or db is None:
        return result
    if result['pixel_mae'] > cfg['max_pixel_mae'] or result['correlation'] < cfg['min_correlation']:
        return result
    matches = [m for m in cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(da, db) if m.distance <= 32]
    result['matches'] = len(matches)
    result['match_fraction'] = len(matches) / max(len(pa), len(pb))
    if matches:
        displacement = np.linalg.norm(np.array([pa[m.queryIdx] - pb[m.trainIdx] for m in matches]), axis=1)
        result['displacement_p95_fraction'] = float(np.percentile(displacement, 95) / np.hypot(*ga.shape))
    result['near_duplicate'] = bool(len(matches) >= cfg['min_matches'] and
        result['match_fraction'] >= cfg['min_match_fraction'] and
        result['displacement_p95_fraction'] <= cfg['max_displacement_fraction'])
    return result


def score(rows, cfg):
    """Dataset-relative heuristic rank, never a confidence or geometry quality."""
    valid = [r for r in rows if r['status'] == 'ok']
    if not valid:
        return
    def normalize(key):
        values = np.array([r[key] for r in valid], float)
        lo, hi = np.percentile(values, [10, 90])
        return np.clip((values - lo) / (hi - lo), 0, 1) if hi > lo else np.full(len(values), 0.5)
    sharp, contrast = normalize('blur_laplacian_variance'), normalize('contrast_std')
    for i, row in enumerate(valid):
        exposure = max(0, 1 - row['dark_fraction'] - row['bright_fraction'])
        features = min(row['orb_keypoints'] / cfg['orb_features'], 1)
        spread = row['feature_cells_occupied'] / 64
        row['quality_score'] = float(0.5 * sharp[i] + 0.25 * contrast[i] + 0.25 * exposure)
        row['information_score'] = float(0.6 * row['quality_score'] + 0.25 * features + 0.15 * spread
                                         - (1 if row['reason'] in ('exact_duplicate', 'near_duplicate') else 0))


def write_csv(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    if not fields:
        fields = ['candidate', 'reference', 'near_duplicate']
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(source, project, cfg):
    started = time.perf_counter()
    cv2.setNumThreads(2)
    cv2.setRNGSeed(0)
    source, project = source.resolve(), project.resolve()
    if source == project or source in project.parents:
        raise ValueError('Project/output directory must not be inside raw input')
    paths = sorted(p for p in source.rglob('*') if p.is_file() and p.suffix.lower() in ('.jpg', '.jpeg', '.png', '.tif', '.tiff'))
    if not paths:
        raise ValueError(f'No images in {source}')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    report = project / 'results' / 'image_intelligence' / run_id
    selected = project / 'selected_frames' / run_id
    report.mkdir(parents=True, exist_ok=False)
    selected.mkdir(parents=True, exist_ok=False)
    rows, pairs, hashes = [], [], {}
    recent = deque(maxlen=cfg['comparison_window'])
    for index, path in enumerate(paths):
        name = path.relative_to(source).as_posix()
        row = dict(filename=name, status='ok', selected=False, reason='', duplicate_of='', sha256='', error='')
        try:
            row['sha256'] = digest(path)
            metrics, gray, points, descriptors = analyze(path, cfg)
            row.update(metrics)
            current = (gray, points, descriptors)
            if row['sha256'] in hashes:
                row.update(reason='exact_duplicate', duplicate_of=hashes[row['sha256']])
            else:
                for reference, data in reversed(recent):
                    pair = compare(current, data, cfg)
                    pairs.append(dict(candidate=name, reference=reference, **pair))
                    if pair['near_duplicate'] and index not in (0, len(paths) - 1):
                        row.update(reason='near_duplicate', duplicate_of=reference)
                        break
                if not row['reason']:
                    row.update(selected=True, reason='retained_conservatively')
                    recent.append((name, current))
                    hashes[row['sha256']] = name
        except Exception as exc:
            row.update(status='error', reason='unreadable_or_analysis_error', error=f'{type(exc).__name__}: {exc}')
        rows.append(row)
        print(f'[{index + 1}/{len(paths)}] {name}: {row["reason"]}', flush=True)
    score(rows, cfg)
    # Copy unchanged originals into a unique run directory; never clear previous selections.
    for row in rows:
        if row['selected']:
            target = selected / row['filename']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / row['filename'], target)
            if digest(target) != row['sha256']:
                raise RuntimeError(f'Copy verification failed: {target}')
    write_csv(report / 'image_quality.csv', rows)
    write_csv(report / 'redundancy_pairs.csv', pairs)
    (report / 'selection_manifest.json').write_text(json.dumps([r for r in rows if r['selected']], indent=2), encoding='utf-8')
    summary = dict(input_images=len(rows), selected_images=sum(r['selected'] for r in rows),
        exact_duplicates=sum(r['reason'] == 'exact_duplicate' for r in rows),
        near_duplicates=sum(r['reason'] == 'near_duplicate' for r in rows),
        analysis_errors=sum(r['status'] == 'error' for r in rows),
        images_with_quality_warnings=sum(bool(r.get('warnings')) for r in rows),
        source=str(source), selected_directory=str(selected), report_directory=str(report), config=cfg,
        notes=['Filename order is used, not a verified flight chronology.',
               'Scores are heuristic ranks, not confidence probabilities or validated reconstruction quality.',
               'Quality warnings do not discard potentially necessary overlap.',
               'Near-duplicate comparisons use recent retained images; exact hashes are checked globally.',
               'Pixel/feature displacement does not estimate camera pose or prove viewpoint diversity.',
               'All retained image copies are SHA-256 verified. No source images are modified.'])
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    valid = [r for r in rows if r['status'] == 'ok']
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), constrained_layout=True)
    for ax, key, title in zip(axes, ['blur_laplacian_variance', 'orb_keypoints', 'information_score'],
                             ['Sharpness proxy (Laplacian variance)', 'ORB feature count (capped)', 'Heuristic information score (not confidence)']):
        ax.plot([r[key] for r in valid], '.', color='#147d92')
        ax.set_title(title)
        ax.set_xlabel('Readable image index in filename order')
        ax.grid(alpha=0.2)
    fig.savefig(report / 'quality_overview.png', dpi=140)
    plt.close(fig)
    summary['processing_seconds'] = time.perf_counter() - started
    (report / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    (project / 'results' / 'image_intelligence' / 'latest.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    return summary


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=project / 'input' / 'aukerman')
    parser.add_argument('--project', type=Path, default=project)
    parser.add_argument('--config', type=Path, default=project / 'config' / 'image_intelligence.json')
    args = parser.parse_args()
    cfg = DEFAULTS.copy()
    if args.config.exists():
        custom = json.loads(args.config.read_text(encoding='utf-8-sig'))
        if set(custom) - set(cfg):
            parser.error('Unknown configuration keys')
        cfg.update(custom)
    if cfg['max_dimension'] < 64 or cfg['orb_features'] < 100 or cfg['comparison_window'] < 1:
        parser.error('Invalid analysis dimensions, feature count, or comparison window')
    summary = run(args.input, args.project, cfg)
    raise SystemExit(1 if summary['analysis_errors'] else 0)


if __name__ == '__main__':
    main()
