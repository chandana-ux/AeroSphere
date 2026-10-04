"""AeroSphere workspace: single mission-control UI built around real reconstruction artifacts."""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))

from reconstruction_runtime import find_colmap, write_json, worker_alive
from ingestion import save_uploads, frame_decisions
from mission import MODES, catalog, profile, read_json, save_profile
from geo import gps_distance
from legacy import render_legacy
from extras import render_extra
from lineage import render_lineage
from ui import apply_workspace_theme, status_strip, workspace_header
from world import render_world
from world import render_world, geometry, mesh_path_for_mission
from temporal import render_temporal
from measure import render_model_measure, render_mesh_measure

ROOT = Path(os.environ.get('AEROSPHERE_DATA_ROOT', APP.parent))
CODE = APP.parent
PAGES = ['MISSION', 'FRAMES', 'RECONSTRUCTION', '3D WORLD', 'GEO', 'MEASURE', 'QUALITY', 'INTELLIGENCE']


def colmap_launcher():
    return find_colmap()

st.set_page_config(
    page_title='AeroSphere | 3D Reconstruction & Spatial Intelligence',
    page_icon='◈',
    layout='wide',
    initial_sidebar_state='expanded',
    menu_items={'Get Help': None, 'Report a bug': None, 'About': 'AeroSphere · single-pass aerial 3D world'}
)


def go(page):
    st.session_state['nav'] = page


def live_reconstruction_progress(root):
    progress = read_json(root / 'reconstruction_progress.json')
    if progress.get('status') == 'processing':
        lock = root / 'reconstruction.lock'
        try:
            pid = int(lock.read_text().strip())
        except (OSError, ValueError):
            pid = progress.get('pid')
        if pid and not worker_alive(pid):
            progress['status'] = 'failed'
            progress.setdefault('stages', {})[progress.get('stage', 'sparse')] = 'failed'
            progress['error'] = 'Reconstruction worker exited before saving a final status. Inspect the worker and COLMAP logs, then retry.'
    return progress


@st.fragment(run_every='3s')
def watch_reconstruction(root):
    progress = live_reconstruction_progress(root)
    signature = (progress.get('run_directory'), progress.get('status'),
                 tuple(sorted(progress.get('stages', {}).items())))
    key = 'reconstruction_watch_' + str(root)
    previous = st.session_state.get(key)
    st.session_state[key] = signature
    if previous is not None and previous != signature:
        if progress.get('status') == 'completed' and st.session_state.get('nav') == 'RECONSTRUCTION':
            st.session_state['nav'] = '3D WORLD'
        st.rerun()


def data(root):
    summary = read_json(root / 'output/reconstruction/latest.json')
    progress = read_json(root / 'reconstruction_progress.json')
    if summary:
        run = Path(summary.get('run_directory', '')).resolve()
        if not run.is_relative_to(root.resolve()) or (progress and progress.get('run_directory') != str(run)):
            summary = {}
        elif not (run / 'sparse.ply').is_file():
            summary = {}
    selection = read_json(root / 'results/image_intelligence/latest.json')
    try:
        meta = pd.read_csv(root / 'metadata/image_metadata.csv')
    except (OSError, ValueError):
        meta = pd.DataFrame(columns=['filename', 'latitude', 'longitude', 'altitude_raw_m'])
    for name in ('filename', 'latitude', 'longitude', 'altitude_raw_m'):
        if name not in meta:
            meta[name] = pd.NA
    return summary, selection, meta


def input_quality(root, selection):
    try:
        return frame_decisions(root, selection)
    except (OSError, ValueError, KeyError, pd.errors.ParserError) as exc:
        st.warning(f'Input image-quality report is unavailable: {exc}')
        return pd.DataFrame()


def read_artifact_stats(run_dir):
    stats = {'FRAMES': 'N/A', 'SPARSE': 'N/A', 'DENSE': 'N/A', 'MESH': 'N/A', 'COORDINATE': 'RELATIVE', 'STATUS': 'READY'}
    for label, path, element in (
        ('SPARSE', run_dir / 'sparse.ply', b'vertex'),
        ('DENSE', run_dir / 'dense/fused.ply', b'vertex'),
        ('MESH', run_dir / 'dense/mesh.ply', b'face'),
    ):
        counts = ply_header_counts(path)
        count = counts.get(element)
        if count is not None:
            stats[label] = f'{count:,}' + (' TRIANGLES' if label == 'MESH' else '')
        if label == 'MESH' and counts.get(b'vertex') is not None:
            stats['MESH_VERTICES'] = f"{counts[b'vertex']:,} VERTICES"

    return stats


def ply_header_counts(path):
    counts = {}
    try:
        with path.open('rb') as stream:
            if stream.readline().strip() != b'ply':
                return counts
            for line in stream:
                if line.strip() == b'end_header':
                    break
                fields = line.split()
                if len(fields) == 3 and fields[0] == b'element':
                    try:
                        counts[fields[1]] = int(fields[2])
                    except ValueError:
                        continue
    except OSError:
        pass
    return counts


def project_status(active, summary, selection):
    stats = read_artifact_stats(Path(summary['run_directory']) if summary and 'run_directory' in summary else active / 'results')
    if selection:
        stats['FRAMES'] = f"{selection.get('selected_images', 0):,}"
    if summary:
        if 'registered_images' in summary and summary['registered_images'] is not None:
            stats['FRAMES'] = f"{summary['registered_images']:,}"
        if 'sparse_points' in summary and summary['sparse_points'] is not None:
            stats['SPARSE'] = f"{int(summary['sparse_points']):,}"
        if 'dense_points' in summary and summary['dense_points'] is not None:
            stats['DENSE'] = f"{int(summary['dense_points']):,}"
        if 'mesh_triangles' in summary and summary['mesh_triangles'] is not None:
            stats['MESH'] = f"{int(summary['mesh_triangles']):,} TRIANGLES"
        stats['COORDINATE'] = 'RELATIVE'
        stats['STATUS'] = 'READY' if summary.get('dense_status') in (None, 'success', 'available') else 'PARTIAL'
    else:
        job = read_json(active / 'reconstruction_job.json') or read_json(active / 'job.json')
        if job.get('status') == 'failed':
            stats['STATUS'] = 'FAILED'
        elif job.get('status') in ('processing', 'running'):
            stats['STATUS'] = 'PROCESSING'
        elif selection:
            stats['STATUS'] = 'FRAME ANALYSIS READY'
        else:
            stats['STATUS'] = 'PENDING'
    progress = live_reconstruction_progress(active)
    worker = read_json(active / 'reconstruction_job.json') or read_json(active / 'job.json')
    current = progress.get('status') or worker.get('status')
    if current in ('processing', 'running', 'failed', 'dependency_missing', 'partial'):
        stats['STATUS'] = current.replace('_', ' ').upper()
    return stats


def mission_library(items):
    st.subheader('Mission library')
    category = st.segmented_control('Category', ['ALL', 'URBAN', 'INFRASTRUCTURE', 'DISASTER', 'HISTORICAL'], default='ALL')
    visible = [m for m in items if category in ('ALL', m['category'])]
    if not visible:
        st.info('No missions in this category. Add real observations through Mission setup.')
    for item in visible:
        with st.container(border=True):
            a, b = st.columns([4, 1])
            summary, selection, meta = data(item['root'])
            a.markdown(f"**{item['name']}**")
            gps = meta.dropna(subset=['latitude', 'longitude'])
            location = f"{gps.latitude.mean():.5f}°, {gps.longitude.mean():.5f}°" if len(gps) else 'Location unavailable'
            alt = int(meta.get('altitude_raw_m', pd.Series(dtype=float)).notna().sum())
            a.caption(f"{item['capture']} · {item['images']} images · GPS {len(gps)} · raw altitude {alt} · {location} · {item['status']}")

            def open_mission(path=item['root']):
                st.session_state['active_root'] = str(path)
                st.session_state['nav'] = '3D WORLD' if (path / 'output/reconstruction/latest.json').exists() else 'FRAMES'

            b.button('Open mission', key='open_' + str(item['root']), on_click=open_mission)


def setup(root, selection, meta):
    current = profile(root)
    summary, _, _ = data(root)

    st.markdown('<div class="workspace-panel"><div class="compact-label">Mission input</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="compact-label" style="margin: 0.4rem 0 0.5rem;">INPUT → ANALYZE → RECONSTRUCT → 3D WORLD</div>', unsafe_allow_html=True)

    source_type = st.radio('Input method', ['UPLOAD DRONE VIDEO', 'UPLOAD IMAGE SEQUENCE', 'EXISTING DATA'], horizontal=True)
    if source_type == 'EXISTING DATA':
        st.caption('Use an existing local file or folder already on this computer.')

    is_video = source_type == 'UPLOAD DRONE VIDEO'
    uploaded = st.file_uploader(
        'Drone video' if is_video else 'Image sequence',
        type=['mp4', 'mov', 'avi', 'mkv'] if is_video else ['jpg', 'jpeg', 'png', 'tif', 'tiff'],
        accept_multiple_files=not is_video,
        key='video_upload' if is_video else 'image_upload'
    )

    st.markdown('<div class="compact-label" style="margin-top: 0.45rem;">Use a file or folder already on this computer</div>', unsafe_allow_html=True)
    source = st.text_input('Local video path' if is_video else 'Local image folder', key='source_path')
    default_mission_name = 'New mission ' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    mission_name = st.text_input('New mission name', value=default_mission_name, key='new_mission_name_' + str(root))

    with st.container():
        interval = st.number_input('Sample interval (seconds)', min_value=.1, max_value=60., value=.5)
        cap = st.number_input('Maximum frames', min_value=3, max_value=300, value=80)
        st.caption('Samples are analyzed for sharpness, exposure, features and redundancy. A frame cap may shorten the processed flight.')

    auto_reconstruct = st.checkbox('Reconstruct after frame analysis', value=True)
    build_dense = st.checkbox('Also build dense cloud and mesh', value=True)
    cpu_features = st.checkbox('Use CPU for features and matching', value=True)
    shared_camera = st.checkbox('Same camera lens and zoom throughout', value=False, key='input_shared_camera')
    st.caption('Enable shared intrinsics for a fixed-lens video; leave off for mixed cameras or changing zoom.')

    if st.button('Analyze flight', type='primary', use_container_width=True):
        try:
            if uploaded:
                path = save_uploads([uploaded] if is_video else uploaded, ROOT, video=is_video)
            else:
                path = Path(source.strip().strip('"'))
                if not source.strip() or not path.exists():
                    raise ValueError('Upload a file or select an existing local source.')
                if is_video and not path.is_file():
                    raise ValueError('Select a video file.')
                if source_type == 'UPLOAD IMAGE SEQUENCE' and not path.is_dir():
                    raise ValueError('Select an image folder.')
            job = ROOT / 'results/jobs' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
            job.mkdir(parents=True)
            save_profile(job, mission_name, current.get('mode', 'RECONNAISSANCE'))
            (job / 'job.json').write_text(json.dumps({'status': 'queued', 'stage': 'input', 'source': str(path)}))
            command = [
                sys.executable,
                str(CODE / 'scripts/pipeline.py'),
                '--input', str(path.resolve()),
                '--job', str(job),
                '--interval', str(interval),
                '--max-frames', str(cap)
            ]
            if auto_reconstruct:
                command.extend(['--reconstruct', '--camera-sharing', 'single' if shared_camera else 'auto'])
                if cpu_features:
                    command.append('--cpu')
                if build_dense:
                    command.append('--dense')
            with (job / 'worker.log').open('w') as log:
                subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, cwd=CODE, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            st.session_state['active_root'] = str(job)
            st.success('Flight analysis started.')
            st.button('View frame analysis', on_click=go, args=('FRAMES',))
        except (OSError, ValueError) as exc:
            st.error(str(exc))

    st.markdown('<div class="thin-divider"></div>', unsafe_allow_html=True)
    job_state = read_json(root / 'job.json')
    reconstruction_state = read_json(root / 'reconstruction_job.json')
    gps = meta.dropna(subset=['latitude', 'longitude'])
    video_path = root / 'video_ingestion/video_metadata.json'
    source_kind = 'DRONE VIDEO' if video_path.is_file() else ('IMAGE SEQUENCE' if selection else 'NOT ANALYZED')
    if summary:
        mission_status = 'RECONSTRUCTION AVAILABLE'
    elif job_state.get('status') == 'failed':
        mission_status = f"FAILED · {job_state.get('stage', 'input')}"
    elif job_state.get('status') == 'processing':
        mission_status = f"PROCESSING · {job_state.get('stage', 'input')}"
    elif selection:
        mission_status = 'FRAME ANALYSIS COMPLETE'
    elif reconstruction_state.get('status'):
        mission_status = reconstruction_state['status'].upper()
    else:
        mission_status = 'PENDING'
    input_count = selection.get('input_images') if selection else None
    status_summary = [
        ('Mission', current.get('name', root.name)),
        ('Source', source_kind),
        ('Input frames', f'{input_count:,}' if input_count is not None else 'NOT ANALYZED'),
        ('Reconstruction', mission_status),
        ('GPS fixes', f'{len(gps):,}' if len(gps) else 'UNAVAILABLE'),
    ]
    cards = st.columns(len(status_summary))
    for col, (label, value) in zip(cards, status_summary):
        with col:
            st.markdown(f'''<div class="summary-card"><span class="label">{label}</span><div class="value">{value}</div></div>''', unsafe_allow_html=True)

    st.markdown('<div class="thin-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="compact-label" style="margin-bottom: 0.6rem;">Project readiness</div>', unsafe_allow_html=True)
    mesh_present = (Path(summary.get('run_directory', root / 'results')) / 'dense/mesh.ply').is_file()
    if not mesh_present and root.resolve() == CODE.resolve():
        mesh_present = (CODE / 'results/dense/mesh.ply').is_file()
    readiness = [
        ('FRAME INTELLIGENCE', 'AVAILABLE' if selection else 'PENDING', 'Selected source frames and quality evidence'),
        ('3D ARTIFACTS', 'AVAILABLE' if summary or mesh_present else 'PENDING', 'Reconstruction summary or mesh file'),
        ('GPS METADATA', 'AVAILABLE' if len(gps) else 'UNAVAILABLE', f'{len(gps):,} records; model georeferencing remains separate'),
    ]
    cols = st.columns(len(readiness))
    for col, (label, value, detail) in zip(cols, readiness):
        with col:
            st.markdown(f'''<div class="pipeline-step"><div class="step-number">{label}</div><div class="step-name">{value}</div><div class="step-meta">{detail}</div></div>''', unsafe_allow_html=True)

    st.markdown('<div class="thin-divider"></div>', unsafe_allow_html=True)
    telemetry = st.columns(4)
    with telemetry[0]:
        st.metric('Frames', f"{selection.get('selected_images', 0):,}" if selection else 'N/A')
    with telemetry[1]:
        st.metric('Sparse points', f"{int(summary.get('sparse_points', 0)):,}" if summary and summary.get('sparse_points') is not None else 'N/A')
    with telemetry[2]:
        st.metric('Dense points', f"{int(summary.get('dense_points', 0)):,}" if summary and summary.get('dense_points') is not None else 'N/A')
    with telemetry[3]:
        st.metric('Mesh triangles', f"{int(summary.get('mesh_triangles', 0)):,}" if summary and summary.get('mesh_triangles') is not None else 'N/A')

    with st.expander('Mission Configuration', expanded=False):
        a, b = st.columns([2, 1])
        with a:
            name = st.text_input('Mission name', value=current['name'])
            mode = st.selectbox('Mission type', list(MODES), index=list(MODES).index(current.get('mode', 'RECONNAISSANCE')))
            st.caption(MODES[mode][0])
            if st.button('Save mission settings', use_container_width=True):
                save_profile(root, name, mode)
                st.success('Mission settings saved locally.')
        with b:
            st.markdown('#### Telemetry')
            st.write('GPS · ' + ('Available' if meta[['latitude', 'longitude']].notna().all(axis=1).any() else 'Unavailable'))
            st.write('Raw altitude · ' + ('Available; datum unverified' if meta.get('altitude_raw_m', pd.Series(dtype=float)).notna().any() else 'Unavailable'))
            st.caption('IMU / RTK / PPK · not supplied')


def flight(root, summary, selection, meta):
    job = read_json(root / 'job.json')
    if job:
        st.caption('Processing status · ' + job.get('status', 'unknown').upper() + ' · ' + job.get('stage', ''))
        if job.get('status') == 'failed':
            st.error('Processing could not finish. Check input overlap, texture and file readability; diagnostics are available below.')

    if not selection:
        st.info('Analyze an image folder or video in Mission setup. This page will show retained frames and selection reasons.')
        st.button('Back to Mission', on_click=go, args=('MISSION',))
        return

    quality = frame_decisions(root, selection)
    video = read_json(root / 'video_ingestion/video_metadata.json')
    st.subheader('Frame intelligence')
    if video:
        cols = st.columns(4)
        values = [
            f"{video.get('reported_duration_s', 0):.1f} s" if video.get('reported_duration_s') else 'Unknown',
            f"{video.get('width')} × {video.get('height')}",
            video.get('fps') or 'Unknown',
            video.get('reported_frame_count') or 'Unknown'
        ]
        for col, label, value in zip(cols, ['Duration', 'Resolution', 'FPS', 'Source frames'], values):
            col.metric(label, value)
        if video.get('warning'):
            st.warning(video['warning'])
        with st.expander('Play source video'):
            if Path(video['source']).exists():
                st.video(video['source'])

    evidence_cols = st.columns(3)
    for col, label, value in zip(evidence_cols, ['Frames analyzed', 'Frames selected', 'Frames rejected'], [len(quality), int(quality.selected.sum()), int((~quality.selected).sum())]):
        col.metric(label, value)

    timeline = quality.copy()
    timeline['position'] = timeline.timestamp_s if video else range(len(timeline))
    fig = px.scatter(
        timeline,
        x='position',
        y='decision',
        color='decision',
        hover_data=['filename', 'reason'],
        color_discrete_map={'Selected': '#58d6c3', 'Rejected': '#ed976a'}
    )
    fig.update_traces(marker=dict(size=11, symbol='square'))
    fig.update_layout(
        height=180,
        margin=dict(l=0, r=0, t=5, b=0),
        xaxis_title='Video time (seconds)' if video else 'Image order',
        yaxis_title=None,
        showlegend=False,
        paper_bgcolor='#0d141c',
        plot_bgcolor='#111c27'
    )
    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
    st.caption('Selected frames retain useful overlap. Warnings are shown; no target rejection percentage is imposed.')

    selected_rows = quality[quality.selected]
    if len(selected_rows):
        pages = max(1, (len(selected_rows) + 11) // 12)
        page_idx = int(st.number_input('Frame gallery page', min_value=1, max_value=pages, value=1, key='gallery_' + str(root)))
        cols = st.columns(4)
        for i, (_, row) in enumerate(selected_rows.iloc[(page_idx - 1) * 12:page_idx * 12].iterrows()):
            path = Path(selection['source']) / row.filename
            if path.exists():
                stamp = f'{row.timestamp_s:.2f}s · ' if pd.notna(row.timestamp_s) else ''
                cols[i % 4].image(str(path), caption=stamp + row.filename, width='stretch')

    with st.expander('Inspect frame quality and selection reasons'):
        selected = st.selectbox('Source frame', quality.filename.tolist())
        row = quality[quality.filename == selected].iloc[0]
        a, b = st.columns([2, 1])
        source = Path(selection['source']) / selected
        if source.exists() and row.status == 'ok':
            a.image(str(source), width='stretch')
        b.markdown('#### ' + row.decision.upper())
        b.write(str(row.reason).replace('_', ' '))
        fields = ['blur_laplacian_variance', 'brightness_mean', 'contrast_std', 'dark_fraction', 'bright_fraction', 'orb_keypoints', 'information_score', 'warnings']
        b.dataframe(row.reindex(fields).rename('Value').astype(str).replace('nan', 'Unavailable'))
        st.dataframe(quality, hide_index=True, width='stretch')

    st.button('Continue to reconstruction', type='primary', on_click=go, args=('RECONSTRUCTION',))


@st.fragment(run_every='3s')
def reconstruction(root, summary, selection):
    summary, selection, _ = data(root)
    st.markdown('<div class="workspace-panel"><div class="compact-label">Reconstruction / pipeline</div></div>', unsafe_allow_html=True)
    state = read_json(root / 'reconstruction_job.json')
    input_job = read_json(root / 'job.json')
    if input_job.get('status') == 'failed' and not state:
        state = input_job
    progress = live_reconstruction_progress(root)
    if progress.get('status'):
        state = {**state, 'status': progress['status'], 'stage': progress.get('stage', '')}
    summary = summary or {}
    run_dir = Path(summary.get('run_directory', root / 'results'))
    sparse_path = run_dir / 'sparse.ply'
    dense_path = run_dir / 'dense/fused.ply'
    mesh_path = run_dir / 'dense/mesh.ply'
    if not mesh_path.is_file() and root.resolve() == CODE.resolve():
        demo_mesh = CODE / 'results/dense/mesh.ply'
        if demo_mesh.is_file():
            mesh_path = demo_mesh

    sparse_header = ply_header_counts(sparse_path)
    dense_header = ply_header_counts(dense_path)
    mesh_header = ply_header_counts(mesh_path)

    def count_text(value):
        return f'{int(value):,}' if value is not None else 'N/A'

    selected_images = selection.get('selected_images') if selection else None
    registered = summary.get('registered_images')
    sparse_points = summary.get('sparse_points')
    if sparse_points is None:
        sparse_points = sparse_header.get(b'vertex')
    dense_points = summary.get('dense_points')
    if dense_points is None:
        dense_points = dense_header.get(b'vertex')
    mesh_vertices = summary.get('mesh_vertices')
    if mesh_vertices is None:
        mesh_vertices = mesh_header.get(b'vertex')
    mesh_triangles = summary.get('mesh_triangles')
    if mesh_triangles is None:
        mesh_triangles = mesh_header.get(b'face')

    sparse_available = bool(sparse_header.get(b'vertex', 0))
    dense_available = bool(dense_header.get(b'vertex', 0)) and summary.get('dense_status') == 'success'
    mesh_available = bool(mesh_header.get(b'face', 0)) and (summary.get('mesh_status') == 'success' or root.resolve() == CODE.resolve())
    job_status = state.get('status')
    dense_status = summary.get('dense_status')
    labels = {'processing':'PROCESSING', 'completed':'COMPLETED', 'failed':'FAILED',
              'dependency_missing':'DEPENDENCY MISSING', 'not_started':'NOT STARTED'}
    def stage_label(stage, available):
        value = progress.get('stages', {}).get(stage)
        if value:
            if value == 'completed' and not available:
                return 'FAILED (OUTPUT MISSING)'
            return labels.get(value, value.upper())
        if available:
            return 'COMPLETED'
        if stage == 'sparse':
            if job_status in ('running', 'processing'):
                return 'PROCESSING'
            if job_status == 'failed':
                return 'FAILED'
            if selection and not colmap_launcher():
                return 'DEPENDENCY MISSING'
        return 'NOT STARTED'
    sparse_status = stage_label('sparse', sparse_available)
    dense_state = stage_label('dense', dense_available)
    mesh_state = stage_label('mesh', mesh_available)

    registered_text = count_text(registered)
    if selected_images is not None:
        registered_text += f' / {int(selected_images):,} selected'
    camera_file = run_dir / 'camera_trajectory.csv'
    if not camera_file.is_file() and root.resolve() == CODE.resolve() and run_dir == root / 'results':
        camera_file = CODE / 'results/camera_trajectory.csv'
    camera_text = 'Camera positions recorded' if camera_file.is_file() else 'Camera positions unavailable'
    stages = [
        ('01 · SPARSE RECONSTRUCTION', sparse_status,
         'Image features are matched across views to estimate camera poses and triangulate supported 3D points.',
         f'Registered images: {registered_text} · Sparse points: {count_text(sparse_points)} · {camera_text}'),
        ('02 · DENSE RECONSTRUCTION', dense_state,
         'Multi-view stereo uses the estimated cameras to densify observed surfaces; it builds on the sparse alignment.',
         f'Dense points: {count_text(dense_points)} · Processing: {dense_status or "not recorded"}'),
        ('03 · MESH GENERATION', mesh_state,
         'The dense cloud is converted to an inspectable triangle surface; interpolated faces are estimates, not ground truth.',
         f'Vertices: {count_text(mesh_vertices)} · Triangles: {count_text(mesh_triangles)}'),
    ]

    st.markdown('<div class="compact-label" style="margin: 0.8rem 0 0.6rem;">Three-stage reconstruction workflow</div>', unsafe_allow_html=True)
    cols = st.columns(3)
    for col, (label, status, description, metric) in zip(cols, stages):
        with col:
            st.markdown(
                f'''<div class="pipeline-step" data-state="{status}">
                    <div class="step-number">{label}</div>
                    <div class="stage-state">{status}</div>
                    <div class="step-description">{description}</div>
                    <div class="step-meta">{metric}</div>
                </div>''',
                unsafe_allow_html=True,
            )

    st.markdown('<div class="thin-divider"></div>', unsafe_allow_html=True)
    if state:
        st.caption('Processing status · ' + state.get('status', 'unknown').upper() + ' · ' + state.get('stage', ''))
    if state.get('report_error'):
        st.warning('Geometry is saved, but additional reporting failed: ' + state['report_error'])
    if progress.get('error'):
        st.error(progress['error'])
    if progress.get('command'):
        st.caption('Latest COLMAP step: ' + progress['command'])
        log_root = Path(progress.get('run_directory', root / 'results'))
        log_path = log_root / 'logs' / (progress['command'] + '.log')
        if log_root.resolve().is_relative_to(root.resolve()) and log_path.is_file():
            with log_path.open('rb') as stream:
                stream.seek(max(0, log_path.stat().st_size - 1500))
                lines = stream.read().decode('utf-8', errors='replace').strip().splitlines()
            if lines:
                st.caption('Latest worker output: ' + lines[-1])
    if progress.get('status') == 'processing':
        done = sum(value == 'completed' for value in progress.get('stages', {}).values())
        st.progress(min(done / 3, 1.0), text='Completed reconstruction stages (not a time estimate)')
    if state.get('status') == 'failed':
        detail = state.get('error') or state.get('diagnostic') or 'No additional failure details were recorded.'
        st.error(f"Processing failed during {state.get('stage', 'an unknown stage')}: {detail}")
        if not sparse_available and not dense_available and not mesh_available:
            st.info('No reconstruction artifacts were produced; frame, sparse, dense and mesh counts are unavailable until input processing or reconstruction succeeds.')
        with st.expander('Failure diagnostics'):
            st.json(state)
            for path in (root / 'pipeline.log', root / 'reconstruction_worker.log'):
                if path.is_file():
                    st.code(path.read_text(errors='replace')[-4000:])
    if not selection:
        st.info('Analyze an image folder or video in Mission setup. Stage indicators above reflect only saved reconstruction artifacts and job status.')
        return

    running = state.get('status') in ('running', 'processing') or progress.get('status') == 'processing'
    if running:
        st.info('Reconstruction is running locally. Status updates automatically. Sparse geometry is saved before dense processing.')
    elif summary:
        st.success('Available geometry is ready to inspect.')
        st.button('Open 3D World', type='primary', on_click=go, args=('3D WORLD',), use_container_width=True)
        if summary.get('dense_status') not in (None, 'success'):
            st.warning('Dense processing did not complete; sparse output is available.')
        elif summary.get('mesh_status') not in (None, 'success'):
            st.warning('Mesh processing did not complete; point clouds remain available.')
        with st.expander('Technical details'):
            st.json(summary)
    if not running:
        if not colmap_launcher():
            st.caption('See LOCAL_VIDEO_3D_QUICKSTART.md. Set AEROSPHERE_COLMAP to your COLMAP launcher and restart the app.')
            st.info('The precomputed demo model remains available in 3D World. New reconstruction is disabled because COLMAP is not installed in this runtime.')
            st.caption('This mission has input-derived frame analysis only; the bundled model is a separate precomputed demo, not a reconstruction of these frames.')
        else:
            dense = st.checkbox('Build dense cloud and mesh', True)
            cpu = st.checkbox('CPU feature extraction and matching', True)
            shared_camera = st.checkbox('Same camera lens and zoom throughout', False, key='recon_shared_camera')
            st.caption('Dense stereo requires CUDA. CPU mode applies to feature extraction and matching only.')
            if st.button('Start 3D reconstruction', type='primary', disabled=selection['selected_images'] < 3 or (root / 'reconstruction.lock').exists(), use_container_width=True):
                write_json(root / 'reconstruction_job.json', {'status': 'running', 'stage': 'queued'})
                command = [sys.executable, str(CODE / 'scripts/reconstruct_job.py'), '--project', str(root), '--camera-sharing', 'single' if shared_camera else 'auto']
                if dense:
                    command.append('--dense')
                if cpu:
                    command.append('--cpu')
                with (root / 'reconstruction_worker.log').open('w') as log:
                    subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, cwd=CODE, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                st.success('Reconstruction started. Refresh to follow the stages.')

    if root.resolve() != CODE.resolve() and (CODE / 'results/dense/mesh.ply').is_file():
        if st.button('Open precomputed 3D demo', key='open_precomputed_demo'):
            st.session_state['active_root'] = str(CODE)
            st.session_state['nav'] = '3D WORLD'
            st.rerun()


def render_context_panel(page, root, summary, selection, meta):
    st.markdown('<div class="context-panel"><div class="small-label">Context</div>', unsafe_allow_html=True)
    if page == 'MISSION':
        st.write('Mission state')
        st.write(f"Name: {profile(root).get('name', root.name)}")
        st.write(f"Mode: {profile(root).get('mode', 'RECONNAISSANCE')}")
        st.write(f"Artifacts: {'Available' if summary else 'Pending'}")
    elif page == 'FRAMES':
        st.write('Frame intelligence')
        if selection:
            st.write(f"Selected: {selection.get('selected_images', 0):,}")
            st.write(f"Input: {selection.get('input_images', 0):,}")
        else:
            st.write('No frame selection available')
    elif page == 'RECONSTRUCTION':
        st.write('Pipeline state')
        progress = live_reconstruction_progress(root)
        pipeline_state = progress.get('status') or ('Available' if summary else 'Pending')
        st.write('Reconstruction: ' + pipeline_state.replace('_', ' ').title())
        if summary:
            st.write(f"Sparse points: {summary.get('sparse_points', 'N/A'):,}" if isinstance(summary.get('sparse_points'), (int, float)) else f"Sparse points: {summary.get('sparse_points', 'N/A')}")
    elif page == 'GEO':
        gps = meta.dropna(subset=['latitude', 'longitude'])
        st.write('Geospatial status')
        st.write(f"GPS points: {len(gps)}")
        st.write('Current reconstruction: Not georeferenced')
    elif page == 'MEASURE':
        st.write('Measurement mode')
        st.write('Relative reconstruction units are not metric units')
    elif page == 'QUALITY':
        st.write('Quality evidence')
        if summary:
            st.write(f"Registered images: {summary.get('registered_images', 'N/A')}")
            st.write(f"Dense points: {summary.get('dense_points', 'N/A')}")
    elif page == 'INTELLIGENCE':
        st.write('Evidence lineage')
        st.write('Sparse point provenance is retained; mesh surface lineage is not exact.')
    st.markdown('</div>', unsafe_allow_html=True)


def render_geometry_summary(summary):
    st.subheader('Reconstructed scene statistics')
    run = Path(summary['run_directory'])
    for label, relative, mesh in [('Mesh', 'dense/mesh.ply', True), ('Dense cloud', 'dense/fused.ply', False), ('Sparse cloud', 'sparse.ply', False)]:
        path = run / relative
        if not path.is_file():
            continue
        try:
            xyz, _, triangles = geometry(str(path), path.stat().st_mtime_ns, mesh)
            if len(xyz):
                st.write(f'{label}: {len(xyz):,} points/vertices; {len(triangles):,} triangles.')
                st.dataframe(pd.DataFrame({'Axis':['X','Y','Z'], 'Minimum':xyz.min(0), 'Maximum':xyz.max(0), 'Extent':xyz.max(0)-xyz.min(0)}), hide_index=True)
        except (OSError, ValueError, RuntimeError) as exc:
            st.info(f'{label} statistics unavailable: {exc}')
    st.caption('Bounds describe reconstructed geometry in arbitrary model units. They do not establish building dimensions, semantic identities or complete scene coverage.')


def main():
    apply_workspace_theme()
    items = catalog(ROOT)
    if 'nav' not in st.session_state:
        st.session_state['nav'] = '3D WORLD'

    page = st.session_state.get('nav', '3D WORLD')

    st.sidebar.markdown('<div class="aerosphere-brand"><span class="aerosphere-mark">◈</span> AeroSphere</div>', unsafe_allow_html=True)
    st.sidebar.markdown('<div class="compact-label" style="padding: 0 0.1rem 0.5rem;">Single-pass spatial intelligence</div>', unsafe_allow_html=True)

    nav_buttons = st.sidebar.container()
    nav_items = PAGES
    for nav_page in nav_items:
        with nav_buttons:
            active = nav_page == page
            if st.button(nav_page, key=f'nav_{nav_page}', use_container_width=True, type='primary' if active else 'secondary'):
                st.session_state['nav'] = nav_page
                page = nav_page

    st.sidebar.markdown('<div class="thin-divider"></div>', unsafe_allow_html=True)
    if 'active_root' not in st.session_state:
        # The repository root is a mesh-only example, not the latest local mission.
        # Select a valid reconstruction once; subsequent user selections stay explicit.
        reconstructed = []
        for item in items:
            root = item['root']
            summary = data(root)[0] if root != ROOT else {}
            if not summary or summary.get('dense_status') not in ('success', 'completed'):
                continue
            run = Path(summary['run_directory'])
            if all(ply_header_counts(run / path).get(b'vertex', 0) > 0
                   for path in ('sparse.ply', 'dense/fused.ply')):
                reconstructed.append(root)
        st.session_state['active_root'] = str(max(
            reconstructed,
            key=lambda root: (root / 'output/reconstruction/latest.json').stat().st_mtime,
            default=ROOT,
        ))
    active = Path(st.session_state['active_root'])
    if not active.exists():
        st.warning(f'The selected dataset folder is missing: {active}. Choose another mission; no example geometry is substituted.')
    options = {str(m['root']): m['name'] for m in items}
    if str(active) not in options:
        options[str(active)] = active.name
    chosen = st.sidebar.selectbox('Active mission', list(options), index=list(options).index(str(active)), format_func=options.get)
    if chosen != str(active):
        st.session_state['active_root'] = chosen
        st.session_state.pop('world_point', None)
        active = Path(chosen)

    if st.session_state.get('world_root') != str(active):
        for key in ('world_point', 'world_point_picker', 'world_scope', 'world_event', 'world_source', 'world_mesh_toggle', 'world_dense_toggle', 'world_sparse_toggle', 'world_wireframe_toggle', 'world_cameras_toggle', 'world_trajectory_toggle', 'measure_A', 'measure_B', 'measure_C', 'mesh_measure_a', 'mesh_measure_b', 'mesh_measure_c'):
            st.session_state.pop(key, None)
        st.session_state['world_root'] = str(active)

    watch_reconstruction(active)
    summary, selection, meta = data(active)
    mission = profile(active)
    demo_mesh_available = (active / 'results/dense/mesh.ply').is_file()
    job_state = read_json(active / 'job.json')
    header_status = project_status(active, summary, selection)['STATUS']
    if demo_mesh_available and not summary:
        header_status = 'PRECOMPUTED EXAMPLE'
    st.sidebar.caption(mission.get('mode', 'RECONNAISSANCE'))
    st.sidebar.markdown('<div class="compact-label">Local processing</div>', unsafe_allow_html=True)
    if demo_mesh_available and not summary:
        processing_caption = 'Bundled precomputed mesh demo; it is not reconstructed from another mission.'
    elif header_status in ('PROCESSING', 'RUNNING'):
        processing_caption = 'This mission is being reconstructed. Status updates automatically.'
    elif summary:
        processing_caption = 'This mission has saved reconstruction outputs.'
    elif selection:
        processing_caption = 'Frame analysis is ready. COLMAP is required for new 3D reconstruction.'
    elif job_state.get('status') in ('processing', 'running'):
        processing_caption = f"Input processing · {job_state.get('stage', 'starting')}"
    else:
        processing_caption = 'Analyze input to create mission-specific frames and outputs.'
    st.sidebar.caption(processing_caption)
    repo = os.environ.get('AEROSPHERE_REPOSITORY_URL', 'https://github.com/chandana-ux/AeroSphere')
    if repo.startswith('https://github.com/'):
        st.sidebar.link_button('Project repository ↗', repo)

    workspace_header(
        title=f'AEROSPHERE / {page} / {mission["name"]}',
        mission_name=mission.get('name', active.name),
        status_label=header_status,
        actions=[
            {'type': 'button', 'label': 'Reset View', 'key': 'reset_view', 'on_click': lambda: st.session_state.update(world_point=None)},
            {'type': 'button', 'label': 'Export', 'key': 'export_btn'},
        ],
    )

    if page == 'MISSION':
        left, right = st.columns([3.2, 1.05])
        with left:
            setup(active, selection, meta)
        with right:
            render_context_panel(page, active, summary, selection, meta)
    elif page == 'FRAMES':
        left, right = st.columns([3.2, 1.05])
        with left:
            flight(active, summary, selection, meta)
        with right:
            render_context_panel(page, active, summary, selection, meta)
    elif page == 'RECONSTRUCTION':
        left, right = st.columns([3.2, 1.05])
        with left:
            reconstruction(active, summary, selection)
        with right:
            render_context_panel(page, active, summary, selection, meta)
    elif page == '3D WORLD':
        render_world(active, summary, selection, meta)
    elif page == 'GEO':
        left, right = st.columns([3.2, 1.05])
        with left:
            if summary and selection:
                trajectory_path = Path(summary['run_directory']) / 'camera_trajectory.csv'
                if trajectory_path.is_file():
                    positions = pd.read_csv(trajectory_path)
                    st.subheader('Reconstructed camera positions')
                    st.caption('Relative COLMAP coordinates; axes and scale are not geographic directions or metres.')
                    st.plotly_chart(px.scatter_3d(positions, x='x', y='y', z='z', hover_name='filename'), width='stretch')
                    st.dataframe(positions[['filename', 'x', 'y', 'z']], hide_index=True)
                if len(meta.dropna(subset=['latitude', 'longitude'])):
                    render_legacy('Geospatial', active, CODE)
                else:
                    st.info('No GPS observations accompany this dataset. Relative camera positions are shown above.')
            elif selection:
                gps = meta.dropna(subset=['latitude', 'longitude'])
                gps = gps[gps.latitude.between(-90, 90) & gps.longitude.between(-180, 180)]
                if gps.empty:
                    st.info('This mission has no usable EXIF GPS positions. The reconstruction coordinate frame remains relative and cannot be placed on a map.')
                else:
                    st.subheader('Observed GPS positions')
                    st.caption('Coordinates are read from source-image EXIF. The 3D reconstruction is not aligned to these positions.')
                    st.metric('Images with GPS', f'{len(gps):,} / {len(meta):,}')
                    fig = px.scatter(gps, x='longitude', y='latitude', hover_name='filename')
                    fig.update_traces(marker=dict(color='#58bdd1', size=9))
                    fig.update_layout(height=420, paper_bgcolor='#0d171c', plot_bgcolor='#111c22',
                                      xaxis_title='Longitude (degrees)', yaxis_title='Latitude (degrees)')
                    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
                    st.dataframe(gps[['filename', 'latitude', 'longitude', 'altitude_raw_m']], hide_index=True, width='stretch')
                    st.info('GPS camera positions are observations, not validated ground control. Model coordinates remain relative until an alignment is computed and validated.')
            else:
                demo_mesh = CODE / 'results/dense/mesh.ply'
                if active.resolve() == CODE.resolve() and demo_mesh.is_file():
                    st.subheader('Relative coordinates · precomputed demo mesh')
                    st.info('No GPS or geographic alignment is supplied for this mesh. The values below are actual native model coordinates, not metres.')
                    try:
                        xyz, _, _ = geometry(str(demo_mesh), demo_mesh.stat().st_mtime_ns, mesh=True)
                        if len(xyz):
                            bounds = pd.DataFrame({'Axis': ['X', 'Y', 'Z'], 'Minimum': xyz.min(axis=0), 'Maximum': xyz.max(axis=0)})
                            st.dataframe(bounds.round(3), hide_index=True, width='stretch')
                    except (OSError, RuntimeError, ValueError) as exc:
                        st.warning(f'Relative mesh bounds are unavailable: {exc}')
                    if st.button('Open relative model in 3D World', key='open_geo_demo_world'):
                        st.session_state['nav'] = '3D WORLD'
                        st.rerun()
                else:
                    st.info('Analyze a mission with source metadata to inspect its GPS positions. No GPS coordinates are generated for this mission.')
        with right:
            render_context_panel(page, active, summary, selection, meta)
    elif page == 'MEASURE':
        left, right = st.columns([3.2, 1.05])
        with left:
            if summary and selection:
                gps = meta.dropna(subset=['latitude', 'longitude'])
                if len(gps) >= 2:
                    render_legacy('Measurements', active, CODE)
                else:
                    st.info('GPS distance is unavailable; actual sparse points and mesh measurements are shown below in native model units.')
                with st.expander('3D model-space distance and area'):
                    try:
                        render_model_measure(summary)
                    except (OSError, ValueError, KeyError, IndexError, RuntimeError, ImportError) as exc:
                        st.info(f'Model-space measurements are unavailable: {exc}')
            elif (active / 'results/dense/mesh.ply').is_file():
                render_mesh_measure(active / 'results/dense/mesh.ply')
            elif selection:
                gps = meta.dropna(subset=['latitude', 'longitude'])
                gps = gps[gps.latitude.between(-90, 90) & gps.longitude.between(-180, 180)]
                if len(gps) < 2:
                    st.info('At least two source images with valid GPS coordinates are required. No 3D measurement is available before reconstruction.')
                else:
                    st.subheader('Source GPS point-to-point distance')
                    first, second = st.columns(2)
                    names = gps.filename.tolist()
                    point_a = first.selectbox('GPS point A', names, key='input_gps_point_a')
                    point_b = second.selectbox('GPS point B', names, index=1, key='input_gps_point_b')
                    row_a = gps[gps.filename == point_a].iloc[0]
                    row_b = gps[gps.filename == point_b].iloc[0]
                    distance = gps_distance(row_a, row_b)
                    st.metric('Horizontal geodesic distance', f'{distance:.2f} m')
                    st.caption('WGS84 distance between recorded camera GPS positions. This is not a surface/building measurement; GPS accuracy is unvalidated and altitude is excluded.')
                    st.dataframe(gps[gps.filename.isin([point_a, point_b])][['filename', 'latitude', 'longitude']], hide_index=True, width='stretch')
            else:
                st.info('Analyze a mission to enable measurements. No distances are generated for the precomputed demo mesh without source coordinates.')
        with right:
            render_context_panel(page, active, summary, selection, meta)
    elif page == 'QUALITY':
        left, right = st.columns([3.2, 1.05])
        with left:
            if summary:
                try:
                    render_extra('Quality & Coverage', active, CODE, meta, selection, summary)
                except (OSError, ValueError, KeyError, IndexError) as exc:
                    st.warning(f'Additional quality artifacts unavailable: {exc}')
            elif selection:
                quality = input_quality(active, selection)
                if quality.empty:
                    st.info('Frame-analysis metrics are unavailable for this mission.')
                else:
                    st.subheader('Input image quality')
                    warned = quality.get('warnings', pd.Series('', index=quality.index)).fillna('').astype(str).str.len().gt(0).sum()
                    columns = st.columns(4)
                    columns[0].metric('Images analyzed', f"{len(quality):,}")
                    columns[1].metric('Frames retained', f"{int(quality.selected.sum()):,}")
                    columns[2].metric('Frames with warnings', f'{int(warned):,}')
                    columns[3].metric('Analysis errors', f"{int((quality.status != 'ok').sum()):,}")
                    fields = ['filename', 'selected', 'reason', 'blur_laplacian_variance', 'brightness_mean', 'contrast_std', 'orb_keypoints', 'information_score', 'warnings']
                    st.dataframe(quality.reindex(columns=fields), hide_index=True, width='stretch')
                    st.info('These are image-quality and selection indicators, not reconstruction quality. Registered images, point counts, mesh counts, and reprojection error are unavailable until COLMAP outputs exist.')
            else:
                st.info('Analyze a mission to produce input-quality metrics. Reconstruction quality is unavailable until actual geometry is produced.')
        with right:
            render_context_panel(page, active, summary, selection, meta)
    elif page == 'INTELLIGENCE':
        left, right = st.columns([3.2, 1.05])
        with left:
            if summary:
                render_geometry_summary(summary)
                try:
                    if summary.get('sparse_model') and selection.get('source'):
                        render_lineage(active, summary, selection)
                    else:
                        st.info('Exact image lineage requires COLMAP tracks and source-frame metadata; geometry statistics remain available.')
                except (OSError, ValueError, KeyError, IndexError) as exc:
                    st.info(f'Sparse observation lineage unavailable: {exc}')
            else:
                st.info('Reconstructed spatial insights require geometry for this dataset. Input-derived evidence is shown when available.')
            if selection:
                quality = input_quality(active, selection)
                if quality.empty:
                    st.info('Input-derived intelligence is unavailable because the frame-quality report is missing.')
                else:
                    st.subheader('Input-derived image intelligence')
                    selected_count = int(quality.selected.sum())
                    warning_count = int(quality.get('warnings', pd.Series('', index=quality.index)).fillna('').astype(str).str.len().gt(0).sum())
                    cols = st.columns(3)
                    cols[0].metric('Images analyzed', f'{len(quality):,}')
                    cols[1].metric('Frames retained', f'{selected_count:,}')
                    cols[2].metric('Image-quality warnings', f'{warning_count:,}')
                    retained = quality[quality.selected]
                    choices = retained.filename.tolist() if not retained.empty else quality.filename.tolist()
                    filename = st.selectbox('Input frame', choices, key='intelligence_frame_' + str(active))
                    row = quality[quality.filename == filename].iloc[0]
                    source_root = Path(selection['source']).resolve()
                    image_path = (source_root / filename).resolve()
                    if image_path.is_relative_to(source_root) and image_path.is_file():
                        st.image(str(image_path), caption=filename, width='stretch')
                    else:
                        st.info('The original image is no longer available at its recorded source path.')
                    fields = ['selected', 'reason', 'blur_laplacian_variance', 'brightness_mean', 'contrast_std', 'orb_keypoints', 'information_score', 'warnings']
                    st.dataframe(row.reindex(fields).rename('Value').astype(str).replace('nan', 'Unavailable').to_frame(), width='stretch')
                    st.caption('Quality scores and warnings are input-derived heuristics, not detection certainty or reconstruction confidence.')
                    with st.expander('Optional local object predictions'):
                        render_extra('Semantic AI', active, CODE, meta, selection, summary)
            else:
                st.info('Analyze a video or image sequence to inspect input-derived frame evidence. Sparse-point lineage requires actual COLMAP tracks.')
        with right:
            render_context_panel(page, active, summary, selection, meta)

    status_stats = project_status(active, summary, selection)
    if demo_mesh_available and not summary:
        status_stats['STATUS'] = 'READY'
    status_strip(status_stats)


if __name__ == '__main__':
    main()
