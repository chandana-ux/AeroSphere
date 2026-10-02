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

from ingestion import save_uploads, frame_decisions
from mission import MODES, catalog, profile, read_json, save_profile
from legacy import render_legacy
from extras import render_extra
from lineage import render_lineage
from ui import apply_workspace_theme, status_strip, workspace_header
from world import render_world
from temporal import render_temporal
from measure import render_model_measure

ROOT = Path(os.environ.get('AEROSPHERE_DATA_ROOT', APP.parent))
CODE = APP.parent
PAGES = ['MISSION', 'FRAMES', 'RECONSTRUCTION', '3D WORLD', 'GEO', 'MEASURE', 'QUALITY', 'INTELLIGENCE']


def colmap_launcher():
    configured = os.environ.get('AEROSPHERE_COLMAP')
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_file() else None
    installed = shutil.which('colmap')
    if installed:
        return Path(installed)
    if os.name == 'nt':
        path = Path.home() / 'Downloads/colmap-x64-windows-cuda/COLMAP.bat'
        return path if path.is_file() else None
    return None

st.set_page_config(
    page_title='AeroSphere | 3D Reconstruction & Spatial Intelligence',
    page_icon='◈',
    layout='wide',
    initial_sidebar_state='expanded',
    menu_items={'Get Help': None, 'Report a bug': None, 'About': 'AeroSphere · single-pass aerial 3D world'}
)


def go(page):
    st.session_state['nav'] = page


def data(root):
    summary = read_json(root / 'output/reconstruction/latest.json')
    selection = read_json(root / 'results/image_intelligence/latest.json')
    try:
        meta = pd.read_csv(root / 'metadata/image_metadata.csv')
    except (OSError, ValueError):
        meta = pd.DataFrame(columns=['filename', 'latitude', 'longitude', 'altitude_raw_m'])
    for name in ('filename', 'latitude', 'longitude', 'altitude_raw_m'):
        if name not in meta:
            meta[name] = pd.NA
    return summary, selection, meta


def read_artifact_stats(run_dir):
    stats = {'FRAMES': 'N/A', 'SPARSE': 'N/A', 'DENSE': 'N/A', 'MESH': 'N/A', 'COORDINATE': 'RELATIVE', 'STATUS': 'READY'}
    try:
        import open3d as o3d
    except Exception:
        o3d = None

    if run_dir.exists():
        sparse_path = run_dir / 'sparse.ply'
        dense_path = run_dir / 'dense/fused.ply'
        mesh_path = run_dir / 'dense/mesh.ply'

        if sparse_path.exists() and o3d is not None:
            try:
                cloud = o3d.io.read_point_cloud(str(sparse_path))
                stats['SPARSE'] = f"{len(cloud.points):,.0f}"
            except Exception:
                pass

        if dense_path.exists() and o3d is not None:
            try:
                cloud = o3d.io.read_point_cloud(str(dense_path))
                stats['DENSE'] = f"{len(cloud.points):,.0f}"
            except Exception:
                pass

        if mesh_path.exists() and o3d is not None:
            try:
                mesh = o3d.io.read_triangle_mesh(str(mesh_path))
                verts = len(mesh.vertices)
                faces = len(mesh.triangles)
                stats['MESH'] = f"{faces:,.0f} TRIANGLES"
                stats['MESH_VERTICES'] = f"{verts:,.0f} VERTICES"
            except Exception:
                pass

    return stats


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
        stats['STATUS'] = 'PENDING'
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
    summary = read_json(root / 'output/reconstruction/latest.json')

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

    with st.container():
        interval = st.number_input('Sample interval (seconds)', min_value=.1, max_value=60., value=.5)
        cap = st.number_input('Maximum frames', min_value=3, max_value=300, value=80)
        st.caption('Samples are analyzed for sharpness, exposure, features and redundancy. A frame cap may shorten the processed flight.')

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
                if not is_video and not path.is_dir():
                    raise ValueError('Select an image folder.')
            job = ROOT / 'results/jobs' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
            job.mkdir(parents=True)
            save_profile(job, current['name'], current.get('mode', 'RECONNAISSANCE'))
            (job / 'job.json').write_text(json.dumps({'status': 'queued', 'stage': 'input', 'source': str(path)}))
            command = [
                sys.executable,
                str(CODE / 'scripts/pipeline.py'),
                '--input', str(path.resolve()),
                '--job', str(job),
                '--interval', str(interval),
                '--max-frames', str(cap)
            ]
            if colmap_launcher():
                command.extend(['--reconstruct', '--dense'])
            with (job / 'worker.log').open('w') as log:
                subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, cwd=CODE, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            st.session_state['active_root'] = str(job)
            st.success('Flight analysis started.')
            st.button('View frame analysis', on_click=go, args=('FRAMES',))
        except (OSError, ValueError) as exc:
            st.error(str(exc))

    st.markdown('<div class="thin-divider"></div>', unsafe_allow_html=True)
    status_summary = [
        ('Mission status', 'READY'),
        ('Source', 'Aerial survey'),
        ('Input', 'Image sequence / drone capture'),
        ('Reconstruction', 'AVAILABLE' if summary else 'PENDING'),
        ('Georeference', 'NOT AVAILABLE'),
    ]
    cards = st.columns(len(status_summary))
    for col, (label, value) in zip(cards, status_summary):
        with col:
            st.markdown(f'''<div class="summary-card"><span class="label">{label}</span><div class="value">{value}</div></div>''', unsafe_allow_html=True)

    st.markdown('<div class="thin-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="compact-label" style="margin-bottom: 0.6rem;">Mission pipeline</div>', unsafe_allow_html=True)
    stages = ['CAPTURE', 'FRAME INTELLIGENCE', 'SfM', 'DENSE MVS', 'MESH', '3D WORLD']
    cols = st.columns(len(stages))
    for col, label in zip(cols, stages):
        with col:
            st.markdown(f'''<div class="pipeline-step"><div class="step-number">{label}</div><div class="step-name">{label}</div><div class="step-meta">Ready</div></div>''', unsafe_allow_html=True)

    st.markdown('<div class="thin-divider"></div>', unsafe_allow_html=True)
    telemetry = st.columns(4)
    with telemetry[0]:
        st.metric('Frames', f"{selection.get('selected_images', 0):,}" if selection else '0')
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


def reconstruction(root, summary, selection):
    st.markdown('<div class="workspace-panel"><div class="compact-label">Reconstruction / pipeline</div></div>', unsafe_allow_html=True)
    if not selection:
        st.info('Analyze a video or image sequence first.')
        return

    state = read_json(root / 'reconstruction_job.json')
    stages = [
        ('01 INPUT', 'Source ready', 'Image sequence / video'),
        ('02 FRAME INTELLIGENCE', 'Quality review', f"{selection.get('selected_images', 0):,} selected"),
        ('03 CAMERA / SfM', 'Registered' if summary else 'Awaiting SfM', f"{summary.get('registered_images', 0) if summary else 0} / {summary.get('registered_images', 0) if summary else 0} registered" if summary else 'Awaiting output'),
        ('04 DENSE MVS', 'Available' if summary and summary.get('dense_status') in (None, 'success', 'available') else 'Awaiting output', f"{int(summary.get('dense_points', 0)):,} points" if summary and summary.get('dense_points') is not None else 'No dense cloud yet'),
        ('05 SURFACE', 'Available' if (root / 'output/reconstruction/latest.json').exists() else 'Awaiting mesh', f"{int(summary.get('mesh_triangles', 0)):,} triangles" if summary and summary.get('mesh_triangles') is not None else 'Mesh pending'),
        ('06 3D WORLD', 'Rendered', 'Active scene')
    ]

    cols = st.columns(len(stages))
    for col, (index, status, metric) in zip(cols, stages):
        with col:
            st.markdown(f'''<div class="pipeline-step"><div class="step-number">{index}</div><div class="step-name">{status}</div><div class="step-meta">{metric}</div></div>''', unsafe_allow_html=True)

    st.markdown('<div class="thin-divider"></div>', unsafe_allow_html=True)
    if state.get('status') == 'running':
        st.info('Reconstruction is running locally. Refresh to update. Sparse geometry is saved before dense processing.')
    elif summary:
        st.success('Available geometry is ready to inspect.')
        st.button('Open 3D World', type='primary', on_click=go, args=('3D WORLD',), use_container_width=True)
        if summary.get('dense_status') not in (None, 'success'):
            st.warning('Dense processing did not complete; sparse output is available.')
        with st.expander('Technical details'):
            st.json(summary)
    else:
        if state.get('status') == 'failed':
            st.error('Reconstruction failed. Try additional overlapping, textured images. Diagnostics show the failing stage.')
        if not colmap_launcher():
            st.info('The precomputed demo model remains available in 3D World. New reconstruction is disabled because COLMAP is not installed in this runtime.')
        else:
            dense = st.checkbox('Build dense cloud and mesh', True)
            cpu = st.checkbox('CPU feature extraction and matching', False)
            st.caption('Dense stereo requires CUDA. CPU mode applies to feature extraction and matching only.')
            if st.button('Start 3D reconstruction', type='primary', disabled=selection['selected_images'] < 3, use_container_width=True):
                (root / 'reconstruction_job.json').write_text(json.dumps({'status': 'running', 'stage': 'queued'}))
                command = [sys.executable, str(CODE / 'scripts/reconstruct_job.py'), '--project', str(root)]
                if dense:
                    command.append('--dense')
                if cpu:
                    command.append('--cpu')
                with (root / 'reconstruction_worker.log').open('w') as log:
                    subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, cwd=CODE, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                st.success('Reconstruction started. Refresh to follow the stages.')

    with st.expander('Engineering diagnostics'):
        st.json(state)
        for p in (root / 'pipeline.log', root / 'reconstruction_worker.log'):
            if p.exists():
                st.code(p.read_text(errors='replace')[-4000:])


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
        st.write(f"Reconstruction: {'Available' if summary else 'Pending'}")
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
    active = Path(st.session_state.get('active_root', ROOT))
    if not active.exists():
        active = ROOT
    options = {str(m['root']): m['name'] for m in items}
    if str(active) not in options:
        options[str(active)] = active.name
    chosen = st.sidebar.selectbox('Active mission', list(options), index=list(options).index(str(active)), format_func=options.get)
    if chosen != str(active):
        st.session_state['active_root'] = chosen
        st.session_state.pop('world_point', None)
        active = Path(chosen)

    if st.session_state.get('world_root') != str(active):
        for key in ('world_point', 'world_point_picker', 'world_scope', 'world_event', 'world_source'):
            st.session_state.pop(key, None)
        st.session_state['world_root'] = str(active)

    summary, selection, meta = data(active)
    mission = profile(active)
    demo_mesh_available = (active / 'results/dense/mesh.ply').is_file()
    st.sidebar.caption(mission.get('mode', 'RECONNAISSANCE'))
    st.sidebar.markdown('<div class="compact-label">Local processing</div>', unsafe_allow_html=True)
    st.sidebar.caption('Precomputed demo geometry. New reconstruction is available when local COLMAP is installed.')
    repo = os.environ.get('AEROSPHERE_REPOSITORY_URL', 'https://github.com/chandana-ux/AeroSphere')
    if repo.startswith('https://github.com/'):
        st.sidebar.link_button('Project repository ↗', repo)

    workspace_header(
        title=f'AEROSPHERE / {page} / {mission["name"]}',
        mission_name=mission.get('name', active.name),
        status_label='READY' if summary or demo_mesh_available else 'PENDING',
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
                render_legacy('Geospatial', active, CODE)
            else:
                st.info('Geospatial context is unavailable in the precomputed-mesh demo because source metadata and camera alignment files are not included.')
        with right:
            render_context_panel(page, active, summary, selection, meta)
    elif page == 'MEASURE':
        left, right = st.columns([3.2, 1.05])
        with left:
            if summary and selection:
                render_legacy('Measurements', active, CODE)
            else:
                st.info('Reconstruction measurements are unavailable until a mission with its real sparse-point evidence is selected.')
        with right:
            render_context_panel(page, active, summary, selection, meta)
    elif page == 'QUALITY':
        left, right = st.columns([3.2, 1.05])
        with left:
            if summary:
                render_extra('Quality & Coverage', active, CODE, meta, selection, summary)
            else:
                st.info('Quality and coverage reports are unavailable because no reconstruction summary or coverage evidence is included with the precomputed mesh.')
        with right:
            render_context_panel(page, active, summary, selection, meta)
    elif page == 'INTELLIGENCE':
        left, right = st.columns([3.2, 1.05])
        with left:
            if summary and selection:
                render_lineage(active, summary, selection)
            else:
                st.info('Evidence lineage is unavailable in this deployment because source frames and COLMAP track files are not included.')
        with right:
            render_context_panel(page, active, summary, selection, meta)

    status_stats = project_status(active, summary, selection)
    if demo_mesh_available and not summary:
        status_stats['STATUS'] = 'READY'
    status_strip(status_stats)


if __name__ == '__main__':
    main()
