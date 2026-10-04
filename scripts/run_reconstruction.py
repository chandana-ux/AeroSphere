"""Run the detected COLMAP CLI with capability checks and dataset-local outputs."""
import argparse
import csv
import json
import os
import hashlib
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import sys
import atexit
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from reconstruction_runtime import Colmap, DependencyError, write_json

CURRENT = {}


def progress(stage=None, status=None, error=None):
    if not CURRENT:
        return
    if stage:
        CURRENT["stage"] = stage
    if status:
        CURRENT["stages"][CURRENT["stage"]] = status
    if error:
        CURRENT["error"] = str(error)
    write_json(Path(CURRENT["project"]) / "reconstruction_progress.json", CURRENT)


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
    parser.add_argument('--colmap', type=Path, help='COLMAP executable, launcher or installation directory')
    parser.add_argument('--images', type=Path)
    parser.add_argument('--resume', type=Path, help='Existing run directory; reuse successful stages')
    parser.add_argument('--dense', action='store_true', help='Attempt bounded low-resolution dense reconstruction after sparse succeeds')
    parser.add_argument('--camera-sharing', choices=['auto','single'], default='auto', help='Auto lets COLMAP group cameras from metadata; single shares estimated intrinsics; use only for one lens/zoom and resolution')
    parser.add_argument('--dense-size', type=int, choices=[800,1200,1600], default=800, help='Bounded MVS image dimension; 800 is the conservative 4 GB GPU default')
    parser.add_argument('--camera-model', choices=['SIMPLE_RADIAL','OPENCV'], default='SIMPLE_RADIAL')
    parser.add_argument('--camera-params', default='', help='Optional known intrinsics in COLMAP camera-model order')
    parser.add_argument('--cpu', action='store_true', help='CPU feature extraction/matching')
    parser.add_argument('--backend', choices=['colmap', 'opencv', 'auto'], default='colmap',
                        help='colmap = require the COLMAP CLI (default); opencv = OpenCV SfM fallback; auto = COLMAP when installed, otherwise OpenCV')
    parser.add_argument('--opencv-max-images', type=int, default=80, help='Frame cap for the OpenCV fallback backend')
    parser.add_argument('--project', type=Path, default=project, help='Separate artifact root for new-input jobs')
    args = parser.parse_args()
    project=args.project.resolve()
    lock = project / 'reconstruction.lock'
    project.mkdir(parents=True, exist_ok=True)
    try:
        with lock.open('x') as stream:
            stream.write(str(os.getpid()))
    except FileExistsError:
        parser.error('A reconstruction lock exists; another worker may be active. See local setup instructions for recovery.')
    atexit.register(lambda: lock.unlink(missing_ok=True))
    CURRENT.update(project=str(project), stage='sparse', stages={'sparse':'processing','dense':'not_started','mesh':'not_started'}, status='processing')
    progress()
    cli = None
    if args.backend in ('colmap', 'auto'):
        try:
            cli = Colmap(args.colmap)
        except DependencyError:
            if args.backend == 'colmap':
                raise
    images = args.images or Path(json.loads((project / 'results/image_intelligence/latest.json').read_text())['selected_directory'])
    if not images.is_dir():
        raise ValueError(f'Images missing: {images}')
    run = args.resume or project / 'output/reconstruction' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    run = run.resolve()
    if not run.is_relative_to(project):
        raise ValueError('Reconstruction run must be inside the selected dataset')
    run.mkdir(parents=True, exist_ok=True)
    CURRENT['run_directory'] = str(run)
    progress()
    if cli is None:
        from opencv_sfm import run as opencv_run
        print('COLMAP unavailable; running the OpenCV structure-from-motion fallback', flush=True)
        summary = opencv_run(images, project, run, dense=args.dense, max_images=args.opencv_max_images)
        CURRENT['stages'] = {'sparse': 'completed',
                             'dense': summary.get('dense_status', 'not_requested'),
                             'mesh': summary.get('mesh_status', 'not_requested')}
        CURRENT['status'] = 'partial' if args.dense and (summary.get('dense_status') != 'success' or summary.get('mesh_status') != 'success') else 'completed'
        progress()
        print(json.dumps(summary, indent=2), flush=True)
        return
    args.colmap = cli.executable
    logs = run / 'logs'
    logs.mkdir(exist_ok=True)
    state_path = run / 'stages.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    digest = hashlib.sha256()
    for image in sorted(images.iterdir()):
        if image.is_file():
            digest.update(image.name.encode('utf-8'))
            with image.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
    config = dict(image_fingerprint=digest.hexdigest(), images=str(images.resolve()), colmap=str(args.colmap.resolve()), max_image_size=1600,
                  max_features=8192, gpu=not args.cpu, camera_sharing=args.camera_sharing, camera_model=args.camera_model, camera_params=args.camera_params, dense_size=args.dense_size)
    config_path = run / 'config.json'
    if config_path.exists() and json.loads(config_path.read_text()) != config:
        raise ValueError('Resume configuration or image contents differ; start a fresh run')
    config_path.write_text(json.dumps(config, indent=2))
    env = cli.env
    executable = cli.executable

    def command(stage, name, options, timeout=1800):
        if state.get(stage, {}).get('success'):
            print(f'Reusing {stage}', flush=True)
            return
        if name != '-h':
            cli.probe(name)
            (logs / (name + '_help.txt')).write_text(cli.help[name], encoding='utf-8')
            options = cli.options(name, list(options) + ['--log_target', 'stderr', '--log_color', '0'])
        cmd = [str(executable), name] + list(map(str, options))
        CURRENT['command'] = stage
        progress()
        state[stage] = {'success':False, 'status':'processing', 'command':cmd}
        write_json(state_path, state)
        print(f'Starting {stage}; log: {logs / (stage + ".log")}', flush=True)
        start = time.perf_counter()
        with (logs / (stage + '.log')).open('w', encoding='utf-8') as log:
            try:
                result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, env=env, timeout=timeout)
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = -1
        state[stage] = dict(success=code == 0, returncode=code, seconds=time.perf_counter() - start, command=cmd)
        write_json(state_path, state)
        if code != 0:
            tail = (logs / (stage + '.log')).read_text(errors='replace')[-2500:]
            advice = ' Use overlapping views of a static textured subject with camera translation. A fixed camera, pure rotation, blur or moving objects may prevent triangulation.' if stage == 'mapping' else ''
            raise RuntimeError(f"{stage} failed ({code}).{advice} Inspect {logs / (stage + '.log')}: {tail}")
        print(f'Completed {stage} in {state[stage]["seconds"]:.1f}s', flush=True)

    command('version', '-h', [])
    db = run / 'database.db'
    sparse = run / 'sparse'
    sparse.mkdir(exist_ok=True)
    gpu = '0' if args.cpu else '1'
    command('features', 'feature_extractor', ['--database_path', db, '--image_path', images,
        '--ImageReader.single_camera', '1' if args.camera_sharing=='single' else '0', '--ImageReader.camera_model', args.camera_model,
        '--FeatureExtraction.max_image_size', '1600', '--FeatureExtraction.num_threads', '4',
        '--FeatureExtraction.use_gpu', gpu, '--FeatureExtraction.gpu_index', '0', '--SiftExtraction.max_num_features', '8192'] + (['--ImageReader.camera_params', args.camera_params] if args.camera_params else []))
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
        raise RuntimeError('No camera alignment could be recovered. Use a static textured subject, overlapping views and camera translation; avoid pure rotation, moving objects, blur and scene cuts. Inspect mapping.log.')
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
        sparse_status='success', mesh_status='not_requested', dense_status='not_requested', stage_seconds={k:v.get('seconds', 0) for k,v in state.items()})
    previous_summary = json.loads((run / 'summary.json').read_text()) if (run / 'summary.json').exists() else {}
    if not args.dense:
        for key in ('dense_status', 'dense_points', 'dense_error', 'mesh_status', 'mesh_vertices', 'mesh_display', 'mesh_triangles', 'mesh_error', 'mesh_caution'):
            if key in previous_summary:
                summary[key] = previous_summary[key]
        for stage, relative in [('dense', 'dense/fused.ply'), ('mesh', 'dense/mesh.ply')]:
            if summary.get(stage + '_status') == 'success' and (run / relative).is_file():
                CURRENT['stages'][stage] = 'completed'
    else:
        summary['dense_status'] = 'running'
    def save():
        write_json(run / 'summary.json', summary)
        write_json(project / 'output/reconstruction/latest.json', summary)
    save()
    progress('sparse', 'completed')
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
    print(json.dumps(summary, indent=2), flush=True)
    if args.dense:
        dense = run / 'dense'
        dense.mkdir(exist_ok=True)
        progress('dense', 'processing')
        try:
            cli.probe('patch_match_stereo')
            command('undistort', 'image_undistorter', ['--image_path', images, '--input_path', model,
                    '--output_path', dense, '--output_type', 'COLMAP', '--max_image_size', args.dense_size])
            stereo_config = dense / 'stereo/patch-match.cfg'
            if not state.get('stereo', {}).get('success'):
                lines = stereo_config.read_text().splitlines()
                stereo_config.write_text('\n'.join('__auto__, 6' if line.strip().startswith('__auto__') else line for line in lines) + '\n')
            # gpu_index selects a GPU; -1 is not a promise of CPU dense stereo.
            command('stereo', 'patch_match_stereo', ['--workspace_path', dense, '--workspace_format', 'COLMAP',
                    '--PatchMatchStereo.max_image_size', args.dense_size, '--PatchMatchStereo.gpu_index', '0',
                    '--PatchMatchStereo.geom_consistency', '0', '--PatchMatchStereo.num_iterations', '5',
                    '--PatchMatchStereo.num_threads', '4', '--PatchMatchStereo.cache_size', '1'], timeout=1800)
            command('fusion', 'stereo_fusion', ['--workspace_path', dense, '--workspace_format', 'COLMAP',
                    '--input_type', 'photometric', '--output_path', dense / 'fused.ply',
                    '--StereoFusion.num_threads', '4', '--StereoFusion.cache_size', '2'], timeout=600)
            import open3d as o3d
            cloud = o3d.io.read_point_cloud(str(dense / 'fused.ply'))
            if len(cloud.points) == 0 or not np.isfinite(np.asarray(cloud.points)).all():
                raise RuntimeError('Fusion produced zero points or nonfinite coordinates')
            summary.update(dense_status='success', dense_points=len(cloud.points), mesh_status='running')
            save()
            progress('dense', 'completed')
            progress('mesh', 'processing')
            try:
                command('mesh', 'poisson_mesher', ['--input_path', dense / 'fused.ply', '--output_path', dense / 'mesh.ply', '--PoissonMeshing.depth', '8', '--PoissonMeshing.trim', '5', '--PoissonMeshing.num_threads', '4'], timeout=600)
                mesh = o3d.io.read_triangle_mesh(str(dense / 'mesh.ply'))
                if not len(mesh.triangles) or not np.isfinite(np.asarray(mesh.vertices)).all():
                    raise RuntimeError('Mesh has no triangles or has nonfinite vertices')
                summary['mesh_vertices'] = len(mesh.vertices)
                try:
                    from refine_mesh import refine
                    summary['mesh_display'] = refine(run)
                except Exception as exc:
                    summary['mesh_display_error'] = str(exc)
                summary['mesh_triangles'] = len(mesh.triangles)
                summary['mesh_status'] = 'success' if len(mesh.triangles) else 'empty'
                progress('mesh', 'completed')
                summary['mesh_caution'] = 'Poisson interpolation may bridge unobserved gaps; mesh is inferred, not validated surface truth.'
            except Exception as exc:
                if 'mesh' in state:
                    state['mesh']['success'] = False
                    write_json(state_path, state)
                summary.update(mesh_status='failed', mesh_error=str(exc))
                progress('mesh', 'dependency_missing' if isinstance(exc, DependencyError) else 'failed', exc)
        except Exception as exc:
            if 'fusion' in state:
                state['fusion']['success'] = False
                write_json(state_path, state)
            summary.update(dense_status='dependency_missing' if isinstance(exc, DependencyError) else 'failed', dense_error=str(exc), mesh_status='not_started')
            progress('dense', summary['dense_status'], exc)
        summary['stage_seconds'] = {k:v.get('seconds', 0) for k,v in state.items()}
        save()
        print(json.dumps(summary, indent=2), flush=True)

    CURRENT['status'] = 'partial' if args.dense and (summary.get('dense_status') != 'success' or summary.get('mesh_status') != 'success') else 'completed'
    progress()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        if CURRENT:
            CURRENT['status'] = 'dependency_missing' if isinstance(exc, DependencyError) else 'failed'
            progress(status=CURRENT['status'], error=exc)
        print(str(exc), file=sys.stderr)
        sys.exit(1)
