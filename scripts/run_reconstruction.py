"""Run installed COLMAP 4.2, preserving logs and real sparse/dense outputs."""
import argparse
import csv
import json
import os
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation


def read_model(folder):
    cameras = []
    lines = (folder / 'images.txt').read_text().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line.startswith('#'):
            continue
        parts = line.split(maxsplit=9)
        q = np.array(list(map(float, parts[1:5])))
        t = np.array(list(map(float, parts[5:8])))
        center = -Rotation.from_quat([q[1], q[2], q[3], q[0]]).as_matrix().T @ t
        cameras.append(dict(image_id=int(parts[0]), filename=parts[9], camera_id=int(parts[8]),
                            x=float(center[0]), y=float(center[1]), z=float(center[2]),
                            qw=q[0], qx=q[1], qy=q[2], qz=q[3], tx=t[0], ty=t[1], tz=t[2]))
        i += 1  # Every registered image is followed by a POINTS2D line, possibly empty.
    points, errors, tracks = [], [], []
    for line in (folder / 'points3D.txt').read_text().splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        p = line.split()
        points.append(list(map(float, p[1:4])))
        errors.append(float(p[7]))
        tracks.append((len(p) - 8) // 2)
    return sorted(cameras, key=lambda c: c['filename']), np.array(points), errors, tracks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    project = Path(__file__).resolve().parents[1]
    parser.add_argument('--colmap', type=Path, default=Path.home() / 'Downloads/colmap-x64-windows-cuda/COLMAP.bat')
    parser.add_argument('--images', type=Path)
    parser.add_argument('--resume', type=Path, help='Existing run directory; reuse successful stages')
    parser.add_argument('--dense', action='store_true', help='Attempt bounded low-resolution dense reconstruction after sparse succeeds')
    parser.add_argument('--cpu', action='store_true', help='CPU feature extraction/matching')
    parser.add_argument('--project', type=Path, default=project, help='Separate artifact root for new-input jobs')
    args = parser.parse_args()
    project=args.project.resolve()
    if not args.colmap.is_file():
        parser.error(f'COLMAP launcher missing: {args.colmap}')
    images = args.images or Path(json.loads((project / 'results/image_intelligence/latest.json').read_text())['selected_directory'])
    if not images.is_dir():
        parser.error(f'Images missing: {images}')
    run = args.resume or project / 'output/reconstruction' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    run = run.resolve()
    run.mkdir(parents=True, exist_ok=True)
    logs = run / 'logs'
    logs.mkdir(exist_ok=True)
    state_path = run / 'stages.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    config = dict(images=str(images.resolve()), colmap=str(args.colmap.resolve()), max_image_size=1600,
                  max_features=8192, gpu=not args.cpu)
    config_path = run / 'config.json'
    if config_path.exists() and json.loads(config_path.read_text()) != config:
        parser.error('Resume configuration differs; supply original image path/GPU options or start a fresh run')
    config_path.write_text(json.dumps(config, indent=2))
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    # The supplied batch wrapper reparses quoted paths in an IF statement and
    # fails on spaces. Invoke its same executable with its same DLL/plugin setup.
    executable = args.colmap
    if executable.suffix.lower() == '.bat':
        install = executable.parent
        executable = install / 'bin' / 'colmap.exe'
        env['PATH'] = str(install / 'bin') + os.pathsep + env.get('PATH', '')
        env['QT_PLUGIN_PATH'] = str(install / 'plugins')

    def command(stage, name, options, timeout=1800):
        if state.get(stage, {}).get('success'):
            print(f'Reusing {stage}', flush=True)
            return
        cmd = [str(executable), name] + list(map(str, options))
        if name != '-h':
            cmd += ['--log_target', 'stderr', '--log_color', '0']
        print(f'Starting {stage}; log: {logs / (stage + ".log")}', flush=True)
        start = time.perf_counter()
        with (logs / (stage + '.log')).open('w', encoding='utf-8') as log:
            try:
                result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, env=env, timeout=timeout)
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = -1
        state[stage] = dict(success=code == 0, returncode=code, seconds=time.perf_counter() - start, command=cmd)
        state_path.write_text(json.dumps(state, indent=2))
        if code != 0:
            raise RuntimeError(f'{stage} failed ({code}); inspect {logs / (stage + ".log")}')
        print(f'Completed {stage} in {state[stage]["seconds"]:.1f}s', flush=True)

    command('version', '-h', [])
    db = run / 'database.db'
    sparse = run / 'sparse'
    sparse.mkdir(exist_ok=True)
    gpu = '0' if args.cpu else '1'
    command('features', 'feature_extractor', ['--database_path', db, '--image_path', images,
        '--ImageReader.single_camera', '1', '--ImageReader.camera_model', 'SIMPLE_RADIAL',
        '--FeatureExtraction.max_image_size', '1600', '--FeatureExtraction.num_threads', '4',
        '--FeatureExtraction.use_gpu', gpu, '--FeatureExtraction.gpu_index', '0', '--SiftExtraction.max_num_features', '8192'])
    command('matching', 'exhaustive_matcher', ['--database_path', db, '--FeatureMatching.use_gpu', gpu,
        '--FeatureMatching.gpu_index', '0', '--FeatureMatching.num_threads', '4',
        '--FeatureMatching.max_num_matches', '8192', '--ExhaustiveMatching.block_size', '25'])
    command('mapping', 'mapper', ['--database_path', db, '--image_path', images, '--output_path', sparse,
        '--Mapper.num_threads', '4', '--Mapper.ba_use_gpu', '0', '--Mapper.random_seed', '0'])
    models = []
    for folder in sorted(sparse.iterdir()):
        if not folder.is_dir() or not (folder / 'images.bin').exists():
            continue
        txt = run / ('text_' + folder.name)
        txt.mkdir(exist_ok=True)
        command('convert_' + folder.name, 'model_converter', ['--input_path', folder, '--output_path', txt, '--output_type', 'TXT'])
        parsed = read_model(txt)
        models.append((len(parsed[0]), len(parsed[1]), folder, txt, parsed))
    if not models:
        raise RuntimeError('Mapper produced no sparse models; inspect mapping.log')
    _, _, model, txt, (cameras, points, errors, tracks) = max(models, key=lambda m: (m[0], m[1]))
    if len(cameras) < 2 or len(points) == 0 or not np.isfinite(points).all():
        raise RuntimeError('Sparse output has insufficient cameras/points or nonfinite coordinates')
    command('analyzer', 'model_analyzer', ['--path', model])
    command('export_ply', 'model_converter', ['--input_path', model, '--output_path', run / 'sparse.ply', '--output_type', 'PLY'])
    with (run / 'camera_trajectory.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(cameras[0]))
        writer.writeheader()
        writer.writerows(cameras)
    with sqlite3.connect(f'{db.as_uri()}?mode=ro', uri=True) as conn:
        image_count = conn.execute('SELECT COUNT(*) FROM images').fetchone()[0]
        pairs = conn.execute('SELECT COUNT(*) FROM two_view_geometries WHERE rows > 0').fetchone()[0]
    summary = dict(status='sparse_success', run_directory=str(run), sparse_model=str(model),
        input_images=image_count, registered_images=len(cameras), sparse_points=len(points),
        sparse_components=len(models), verified_image_pairs=pairs,
        mean_point_reprojection_error_pixels=float(np.mean(errors)), median_point_reprojection_error_pixels=float(np.median(errors)),
        mean_track_length=float(np.mean(tracks)),
        coordinate_system='Arbitrary COLMAP similarity frame; distances are not metres; not georeferenced.',
        trajectory_order='Filename order, not independently verified capture chronology.',
        camera_pose_convention='COLMAP world-to-camera quaternion/translation; center = -R.T @ t.',
        evidence='Points are triangulated estimates supported by image tracks, not ground truth; hidden surfaces remain unknown.',
        dense_status='not_requested', stage_seconds={k:v['seconds'] for k,v in state.items()})
    previous_summary = json.loads((run / 'summary.json').read_text()) if (run / 'summary.json').exists() else {}
    if not args.dense:
        for key in ('dense_status', 'dense_points', 'dense_error', 'mesh_status', 'mesh_triangles', 'mesh_error', 'mesh_caution'):
            if key in previous_summary:
                summary[key] = previous_summary[key]
    else:
        summary['dense_status'] = 'running'
    def save():
        (run / 'summary.json').write_text(json.dumps(summary, indent=2))
        (project / 'output/reconstruction/latest.json').write_text(json.dumps(summary, indent=2))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    xyz = np.array([[c[k] for k in ('x','y','z')] for c in cameras])
    fig = plt.figure(figsize=(11, 8))
    ax = fig.add_subplot(111, projection='3d')
    sample = points[::max(1, len(points)//30000)]
    ax.scatter(*sample.T, s=0.2, alpha=0.4, c='#167d91')
    ax.plot(*xyz.T, c='#e07c27', linewidth=1, marker='.', label='Camera centers (filename order)')
    ax.set(xlabel='X (arbitrary units)', ylabel='Y (arbitrary units)', zlabel='Z (arbitrary units)', title=f'AeroSphere: {len(cameras)} registered cameras, {len(points):,} sparse points')
    ax.legend()
    fig.tight_layout()
    fig.savefig(run / 'camera_trajectory.png', dpi=150)
    plt.close(fig)
    save()
    print(json.dumps(summary, indent=2), flush=True)
    if args.dense:
        dense = run / 'dense'
        dense.mkdir(exist_ok=True)
        try:
            command('undistort', 'image_undistorter', ['--image_path', images, '--input_path', model,
                    '--output_path', dense, '--output_type', 'COLMAP', '--max_image_size', '800'])
            stereo_config = dense / 'stereo/patch-match.cfg'
            if not state.get('stereo', {}).get('success'):
                lines = stereo_config.read_text().splitlines()
                stereo_config.write_text('\n'.join('__auto__, 6' if line.strip().startswith('__auto__') else line for line in lines) + '\n')
            command('stereo', 'patch_match_stereo', ['--workspace_path', dense, '--workspace_format', 'COLMAP',
                    '--PatchMatchStereo.max_image_size', '800', '--PatchMatchStereo.gpu_index', '0',
                    '--PatchMatchStereo.geom_consistency', '0', '--PatchMatchStereo.num_iterations', '3',
                    '--PatchMatchStereo.num_threads', '4', '--PatchMatchStereo.cache_size', '2'], timeout=1800)
            command('fusion', 'stereo_fusion', ['--workspace_path', dense, '--workspace_format', 'COLMAP',
                    '--input_type', 'photometric', '--output_path', dense / 'fused.ply',
                    '--StereoFusion.num_threads', '4', '--StereoFusion.cache_size', '2'], timeout=600)
            import open3d as o3d
            cloud = o3d.io.read_point_cloud(str(dense / 'fused.ply'))
            if len(cloud.points) == 0 or not np.isfinite(np.asarray(cloud.points)).all():
                raise RuntimeError('Fusion produced zero points or nonfinite coordinates')
            summary.update(dense_status='success', dense_points=len(cloud.points))
            try:
                command('mesh', 'poisson_mesher', ['--input_path', dense / 'fused.ply', '--output_path', dense / 'mesh.ply', '--PoissonMeshing.depth', '8', '--PoissonMeshing.num_threads', '4'], timeout=600)
                mesh = o3d.io.read_triangle_mesh(str(dense / 'mesh.ply'))
                if not len(mesh.triangles) or not np.isfinite(np.asarray(mesh.vertices)).all():
                    raise RuntimeError('Mesh has no triangles or has nonfinite vertices')
                summary['mesh_triangles'] = len(mesh.triangles)
                summary['mesh_status'] = 'success' if len(mesh.triangles) else 'empty'
                summary['mesh_caution'] = 'Poisson interpolation may bridge unobserved gaps; mesh is inferred, not validated surface truth.'
            except Exception as exc:
                summary.update(mesh_status='failed', mesh_error=str(exc))
        except Exception as exc:
            summary.update(dense_status='failed', dense_error=str(exc))
        summary['stage_seconds'] = {k:v['seconds'] for k,v in state.items()}
        save()
        print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
