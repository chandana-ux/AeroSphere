"""Provisional horizontal GPS alignment; never assigns an absolute height datum."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from pyproj import Transformer, Geod


def fit_horizontal(x, y):
    center = x.mean(axis=0)
    _, singular, axes = np.linalg.svd(x - center, full_matrices=False)
    if singular[1] < 1e-8 or singular[1] / singular[0] < 0.05:
        raise ValueError('Camera geometry is too linear for a stable horizontal fit')
    basis = axes[:2].T
    plane = (x - center) @ basis
    target_center = y.mean(axis=0)
    u, _, vt = np.linalg.svd(plane.T @ (y - target_center))
    rotation = u @ vt  # Reflection is permitted because PCA basis handedness is arbitrary.
    scale = float(np.sum((plane @ rotation) * (y - target_center)) / np.sum(plane**2))
    return dict(center=center.tolist(), basis=basis.tolist(), rotation=rotation.tolist(),
                scale=scale, target_center=target_center.tolist(),
                out_of_plane_ratio=float(singular[2] / singular[1]))


def transform(x, fit):
    return ((np.asarray(x) - fit['center']) @ np.asarray(fit['basis']) @ np.asarray(fit['rotation'])) * fit['scale'] + fit['target_center']


def assess(metadata, cameras):
    joined = cameras.merge(metadata, on='filename', validate='one_to_one')
    joined = joined.replace([np.inf, -np.inf], np.nan).dropna(subset=['x','y','z','latitude','longitude'])
    joined = joined[joined.latitude.between(-90, 90) & joined.longitude.between(-180, 180)].sort_values('filename').reset_index(drop=True)
    report = dict(matched_gps_cameras=len(joined), full_3d_georeferencing=False,
                  validated_metric_accuracy=False, absolute_altitude_available=False,
                  status='unavailable', reason='',
                  limitations=['GPS datum is assumed WGS84; EXIF datum was not supplied.',
                               'GPS uncertainty and independent ground control are unavailable.',
                               'Altitude reference is missing; raw altitude is not used in alignment.',
                               'Camera-plane projection approximates horizontal orientation and may bias relief-dependent positions.',
                               'Holdout errors compare with the same GPS source, not independent survey truth.',
                               'No height, area, volume, or metre-scaled 3D model measurements are validated.'])
    if len(joined) < 10:
        report['reason'] = 'Fewer than 10 matched GPS camera positions'
        return report, joined
    lon, lat = joined.longitude.to_numpy(), joined.latitude.to_numpy()
    zone = min(60, max(1, int((np.median(lon) + 180) // 6) + 1))
    epsg = (32600 if np.median(lat) >= 0 else 32700) + zone
    east, north = Transformer.from_crs(4326, epsg, always_xy=True).transform(lon, lat)
    y = np.column_stack([east, north])
    x = joined[['x','y','z']].to_numpy()
    try:
        full = fit_horizontal(x, y)
        errors = np.linalg.norm(transform(x, full) - y, axis=1)
        # Five deterministic interleaved folds; each camera is predicted once out-of-fit.
        heldout = np.zeros(len(x))
        scales = []
        for fold in range(5):
            test = np.arange(len(x)) % 5 == fold
            fitted = fit_horizontal(x[~test], y[~test])
            heldout[test] = np.linalg.norm(transform(x[test], fitted) - y[test], axis=1)
            scales.append(fitted['scale'])
        extent = float(np.linalg.norm(np.ptp(y, axis=0)))
        rmse = float(np.sqrt(np.mean(errors**2)))
        cv_rmse = float(np.sqrt(np.mean(heldout**2)))
        stable = bool(full['out_of_plane_ratio'] < 0.1 and cv_rmse < 0.05 * extent and
                      np.ptp(scales) / full['scale'] < 0.1)
        report.update(status='provisional_horizontal_fit' if stable else 'fit_not_reliable',
                      reason='Engineering screening passed; not accuracy certification' if stable else 'Fit stability/geometry screening failed',
                      epsg=epsg, fit=full, scale_metres_per_unit=full['scale'],
                      camera_fit_rmse_m=rmse, heldout_camera_rmse_m=cv_rmse,
                      heldout_max_error_m=float(heldout.max()),
                      fold_scales=scales, gps_extent_diagonal_m=extent,
                      screening_rules={'max_out_of_plane_ratio':0.1,'max_cv_rmse_fraction_of_extent':0.05,'max_fold_scale_range_fraction':0.1})
        predicted = transform(x, full)
        joined['easting_m'], joined['northing_m'] = east, north
        joined['fit_easting_m'], joined['fit_northing_m'] = predicted.T
        joined['fit_residual_m'], joined['heldout_residual_m'] = errors, heldout
    except (ValueError, np.linalg.LinAlgError) as exc:
        report['reason'] = str(exc)
    return report, joined


def gps_distance(a, b):
    return float(Geod(ellps='WGS84').inv(float(a.longitude), float(a.latitude), float(b.longitude), float(b.latitude))[2])


def prepare(project):
    project = Path(project)
    summary = json.loads((project / 'output/reconstruction/latest.json').read_text())
    run = Path(summary['run_directory'])
    report, positions = assess(pd.read_csv(project / 'metadata/image_metadata.csv'), pd.read_csv(run / 'camera_trajectory.csv'))
    out = project / 'results/geospatial'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'alignment_report.json').write_text(json.dumps(report, indent=2, allow_nan=False))
    positions.to_csv(out / 'camera_gps_alignment.csv', index=False)
    return report
