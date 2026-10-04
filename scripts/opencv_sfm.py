"""OpenCV structure-from-motion fallback for missions processed without COLMAP.

Detects features, matches them across overlapping frames, estimates relative
camera motion with the essential matrix and triangulates supported points. The
result is a real (arbitrary-scale) sparse cloud plus an estimated camera
trajectory written in the same layout the dashboard already consumes.

This is deliberately honest about its limits: it is a chained two-view
reconstruction, not a bundle-adjusted similarity solution. Intrinsics are
assumed, scale is arbitrary and no georeferencing is implied. COLMAP remains
the preferred backend and is used whenever it is installed.
"""
import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp'}
MIN_MATCHES = 40
MIN_INLIERS = 25
RATIO = 0.75


def _sorted_images(images_dir):
    images_dir = Path(images_dir)
    files = [p for p in sorted(images_dir.iterdir()) if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
    if not files:
        raise ValueError(f'No readable images in {images_dir}')
    return files


def assumed_intrinsics(width, height):
    """Approximate pinhole intrinsics; no calibration is available for uploads."""
    focal = 1.2 * max(width, height)
    return np.array([[focal, 0.0, width / 2.0], [0.0, focal, height / 2.0], [0.0, 0.0, 1.0]], dtype=np.float64)


def _detector(method):
    if method == 'sift' and hasattr(cv2, 'SIFT_create'):
        return cv2.SIFT_create(nfeatures=4096), cv2.NORM_L2
    return cv2.ORB_create(nfeatures=4096), cv2.NORM_HAMMING


def detect(path, method, max_dim=1280):
    image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f'OpenCV could not decode {path.name}')
    height, width = image.shape[:2]
    scale = min(1.0, max_dim / max(height, width))
    if scale < 1.0:
        image = cv2.resize(image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    detector, norm = _detector(method)
    keypoints, descriptors = detector.detectAndCompute(gray, None)
    points = np.array([k.pt for k in keypoints], dtype=np.float32).reshape(-1, 2)
    return dict(name=path.name, image=image, gray=gray, norm=norm, points=points, descriptors=descriptors)


def match(a, b):
    if a['descriptors'] is None or b['descriptors'] is None or len(a['points']) < 2 or len(b['points']) < 2:
        return np.empty((0, 2), np.float32), np.empty((0, 2), np.float32)
    matcher = cv2.BFMatcher(a['norm'])
    try:
        pairs = matcher.knnMatch(a['descriptors'], b['descriptors'], k=2)
    except cv2.error:
        return np.empty((0, 2), np.float32), np.empty((0, 2), np.float32)
    good = [m for m, n in (p for p in pairs if len(p) == 2) if m.distance < RATIO * n.distance]
    if len(good) < MIN_MATCHES:
        return np.empty((0, 2), np.float32), np.empty((0, 2), np.float32)
    pts_a = np.float32([a['points'][m.queryIdx] for m in good])
    pts_b = np.float32([b['points'][m.trainIdx] for m in good])
    return pts_a, pts_b


def estimate_motion(pts_a, pts_b, intrinsic):
    essential, mask = cv2.findEssentialMat(pts_a, pts_b, intrinsic, method=cv2.RANSAC, prob=0.999, threshold=1.5)
    if essential is None or essential.shape != (3, 3):
        return None
    inliers, rotation, translation, pose_mask = cv2.recoverPose(essential, pts_a, pts_b, intrinsic, mask=mask.copy())
    if inliers < MIN_INLIERS:
        return None
    mask = pose_mask.ravel().astype(bool)
    return rotation, translation.ravel(), mask


def _projection(r_wc, center, intrinsic):
    """World-to-camera projection matrix K[R|t] for camera-to-world pose (r_wc, center)."""
    world_to_camera = r_wc.T
    t = -world_to_camera @ center
    return intrinsic @ np.hstack([world_to_camera, t.reshape(3, 1)]).astype(np.float64)


def _write_ply(path, xyz, rgb):
    path = Path(path)
    xyz = np.asarray(xyz, dtype=np.float32)
    rgb = np.asarray(rgb, dtype=np.uint8)
    header = ('ply\nformat binary_little_endian 1.0\n'
              f'element vertex {len(xyz)}\n'
              'property float x\nproperty float y\nproperty float z\n'
              'property uchar red\nproperty uchar green\nproperty uchar blue\n'
              'end_header\n')
    lines = np.zeros(len(xyz), dtype=[('x', '<f4'), ('y', '<f4'), ('z', '<f4'),
                                      ('red', 'u1'), ('green', 'u1'), ('blue', 'u1')])
    lines['x'], lines['y'], lines['z'] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    lines['red'], lines['green'], lines['blue'] = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    with path.open('wb') as stream:
        stream.write(header.encode('ascii'))
        stream.write(lines.tobytes())



def reconstruct(images_dir, method='sift', max_dim=1280, max_images=80, sample_color=True):
    files = _sorted_images(images_dir)[:max_images]
    frames = []
    skipped = []
    for path in files:
        try:
            frames.append(detect(path, method, max_dim))
        except (ValueError, OSError) as exc:
            skipped.append({'filename': path.name, 'reason': str(exc)})
    if len(frames) < 2:
        raise ValueError('Fewer than two decodable frames are available for the OpenCV backend')

    poses = {0: (np.eye(3), np.zeros(3))}
    registered = [frames[0]['name']]
    all_points = []
    all_colors = []
    pair_stats = []
    previous = 0
    for index in range(1, len(frames)):
        pts_a, pts_b = match(frames[previous], frames[index])
        if not len(pts_a):
            skipped.append({'filename': frames[index]['name'], 'reason': 'insufficient matches'})
            continue
        intrinsic = assumed_intrinsics(frames[previous]['gray'].shape[1], frames[previous]['gray'].shape[0])
        motion = estimate_motion(pts_a, pts_b, intrinsic)
        if motion is None:
            skipped.append({'filename': frames[index]['name'], 'reason': 'essential-matrix estimation failed'})
            continue
        rotation, translation, mask = motion
        r_prev, c_prev = poses[previous]
        # camera-to-world composition: x_index = R x_previous + t
        r_wc = r_prev @ rotation.T
        center = r_wc @ (rotation @ r_prev.T @ c_prev - translation)
        poses[index] = (r_wc, center)
        proj_a = _projection(*poses[previous], intrinsic)
        proj_b = _projection(*poses[index], intrinsic)
        selected = mask
        homogeneous = cv2.triangulatePoints(proj_a, proj_b, pts_a[selected].T, pts_b[selected].T)
        xyz = (homogeneous[:3] / homogeneous[3]).T
        cam_a = (poses[previous][0].T @ (xyz.T - poses[previous][1].reshape(3, 1))).T
        cam_b = (poses[index][0].T @ (xyz.T - poses[index][1].reshape(3, 1))).T
        valid = np.isfinite(xyz).all(axis=1) & (cam_a[:, 2] > 0) & (cam_b[:, 2] > 0)
        xyz = xyz[valid]
        colors = np.empty((len(xyz), 3), np.uint8)
        if sample_color and len(xyz):
            uv = pts_a[selected][valid]
            height, width = frames[previous]['image'].shape[:2]
            cols = np.clip(uv[:, 0].astype(int), 0, width - 1)
            rows = np.clip(uv[:, 1].astype(int), 0, height - 1)
            colors = frames[previous]['image'][rows, cols][:, ::-1]
        all_points.append(xyz)
        all_colors.append(colors)
        pair_stats.append({'pair': [frames[previous]['name'], frames[index]['name']],
                           'matches': int(len(pts_a)), 'inliers': int(mask.sum()), 'triangulated': int(len(xyz))})
        registered.append(frames[index]['name'])
        previous = index

    if len(poses) < 2 or not all_points:
        raise ValueError('Camera motion could not be estimated from overlapping textured frames; '
                         'provide views with translation, texture and overlap, or install COLMAP.')
    points = np.concatenate(all_points)
    colors = np.concatenate(all_colors)
    # Merge near-duplicate estimates from neighbouring pairs.
    if len(points) > 1:
        rounded = np.round(points, 3)
        _, keep = np.unique(rounded, axis=0, return_index=True)
        keep = np.sort(keep)
        points, colors = points[keep], colors[keep]
    if not np.isfinite(points).all():
        raise ValueError('Triangulation produced nonfinite coordinates')
    return dict(frames=frames, poses=poses, points=points, colors=colors,
                registered=registered, skipped=skipped, pairs=pair_stats,
                intrinsic=assumed_intrinsics(frames[0]['gray'].shape[1], frames[0]['gray'].shape[0]))



def _quaternion(rotation):
    """Return (qw, qx, qy, qz) for a rotation matrix."""
    matrix = np.asarray(rotation, dtype=np.float64)
    trace = float(np.trace(matrix))
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2.0
        return 0.25 * s, (matrix[2, 1] - matrix[1, 2]) / s, (matrix[0, 2] - matrix[2, 0]) / s, (matrix[1, 0] - matrix[0, 1]) / s
    if matrix[0, 0] > matrix[1, 1] and matrix[0, 0] > matrix[2, 2]:
        s = math.sqrt(1.0 + matrix[0, 0] - matrix[1, 1] - matrix[2, 2]) * 2.0
        return (matrix[2, 1] - matrix[1, 2]) / s, 0.25 * s, (matrix[0, 1] + matrix[1, 0]) / s, (matrix[0, 2] + matrix[2, 0]) / s
    if matrix[1, 1] > matrix[2, 2]:
        s = math.sqrt(1.0 + matrix[1, 1] - matrix[0, 0] - matrix[2, 2]) * 2.0
        return (matrix[0, 2] - matrix[2, 0]) / s, (matrix[0, 1] + matrix[1, 0]) / s, 0.25 * s, (matrix[1, 2] + matrix[2, 1]) / s
    s = math.sqrt(1.0 + matrix[2, 2] - matrix[0, 0] - matrix[1, 1]) * 2.0
    return (matrix[1, 0] - matrix[0, 1]) / s, (matrix[0, 2] + matrix[2, 0]) / s, (matrix[1, 2] + matrix[2, 1]) / s, 0.25 * s


def run(images_dir, project, run=None, dense=False, method='sift', max_dim=1280, max_images=80):
    """Reconstruct a sparse cloud and camera trajectory; optionally mesh it."""
    project = Path(project)
    images_dir = Path(images_dir)
    run = Path(run) if run else project / 'output/reconstruction' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    run = run.resolve()
    if not run.is_relative_to(project.resolve()):
        raise ValueError('Reconstruction run must be inside the selected dataset')
    run.mkdir(parents=True, exist_ok=True)
    result = reconstruct(images_dir, method=method, max_dim=max_dim, max_images=max_images)

    _write_ply(run / 'sparse.ply', result['points'], result['colors'])
    cameras = []
    for frame_index in sorted(result['poses']):
        name = result['frames'][frame_index]['name']
        r_wc, center = result['poses'][frame_index]
        world_to_camera = r_wc.T
        t = -world_to_camera @ center
        qw, qx, qy, qz = _quaternion(world_to_camera)
        cameras.append(dict(filename=name, image_id=int(frame_index) + 1,
                            x=float(center[0]), y=float(center[1]), z=float(center[2]),
                            qw=float(qw), qx=float(qx), qy=float(qy), qz=float(qz),
                            tx=float(t[0]), ty=float(t[1]), tz=float(t[2])))
    with (run / 'camera_trajectory.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(cameras[0]))
        writer.writeheader()
        writer.writerows(cameras)

    summary = dict(
        status='sparse_success', backend='opencv_fallback', run_directory=str(run), sparse_model=None,
        input_images=len(_sorted_images(images_dir)), registered_images=len(cameras),
        sparse_points=len(result['points']), sparse_components=1,
        verified_image_pairs=len(result['pairs']),
        mean_point_reprojection_error_pixels=None, median_point_reprojection_error_pixels=None,
        mean_track_length=2.0,
        coordinate_system='Arbitrary scale from chained relative poses; distances are not metres; not georeferenced.',
        trajectory_order='Filename order, not independently verified capture chronology.',
        camera_pose_convention='World-to-camera quaternion/translation; center = -R.T @ t.',
        evidence='Points are triangulated estimates supported by matched image features, not ground truth; hidden surfaces remain unknown.',
        sparse_status='success', mesh_status='not_requested', dense_status='not_requested',
        backend_limitations=['Assumed pinhole intrinsics; no camera calibration was supplied.',
                             'Relative per-pair scale; the trajectory is not bundle-adjusted or metrically consistent.',
                             'Install COLMAP for bundle-adjusted sparse/dense/mesh reconstruction.'],
        pairs=result['pairs'], skipped_frames=result['skipped'])
    if dense:
        try:
            from mesh_from_cloud import mesh_from_cloud
            mesh_report = mesh_from_cloud(run / 'sparse.ply', run / 'dense/mesh.ply')
            summary.update(dense_status='unavailable',
                           dense_error='Multi-view stereo dense fusion requires the COLMAP dense pipeline.',
                           mesh_status='success', mesh_backend='open3d_poisson_from_sparse',
                           mesh_vertices=mesh_report['vertices'], mesh_triangles=mesh_report['triangles'],
                           mesh_caution='Poisson interpolation of the sparse cloud; faces are estimates, not a measured surface.')
        except Exception as exc:  # noqa: BLE001 - report the missing prerequisite instead of crashing
            summary.update(dense_status='unavailable', mesh_status='failed', mesh_error=str(exc))

    (run / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False), encoding='utf-8')
    latest = project / 'output/reconstruction/latest.json'
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps(summary, indent=2, allow_nan=False), encoding='utf-8')
    return summary



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--images', type=Path, required=True)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--run', type=Path)
    parser.add_argument('--dense', action='store_true')
    parser.add_argument('--method', choices=['sift', 'orb'], default='sift')
    parser.add_argument('--max-images', type=int, default=80)
    args = parser.parse_args()
    summary = run(args.images, args.project, args.run, args.dense, args.method, max_images=args.max_images)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

