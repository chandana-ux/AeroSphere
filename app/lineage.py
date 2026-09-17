from ui import offline_chart
"""Read actual COLMAP tracks; never infer surface provenance from proximity."""
import json
import math
from pathlib import Path


def load_tracks(folder):
    folder = Path(folder)
    images = {}
    lines = iter((folder / 'images.txt').read_text().splitlines())
    for line in lines:
        if not line.strip() or line.startswith('#'):
            continue
        fields = line.split(maxsplit=9)
        observations = next(lines, '').split()
        if len(fields) != 10 or len(observations) % 3:
            raise ValueError('Malformed COLMAP image record')
        images[int(fields[0])] = {
            'name': fields[9], 'pose': list(map(float, fields[1:8])),
            'xy': [(float(observations[i]), float(observations[i+1]), int(observations[i+2]))
                   for i in range(0, len(observations), 3)]}
    points = {}
    for line in (folder / 'points3D.txt').read_text().splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        f = line.split()
        if len(f) < 12 or (len(f)-8) % 2:
            raise ValueError('Malformed or unsupported COLMAP point track')
        pid = int(f[0])
        track = []
        seen = set()
        for i in range(8, len(f), 2):
            image_id, index = int(f[i]), int(f[i+1])
            if image_id not in images or index < 0 or index >= len(images[image_id]['xy']) or (image_id,index) in seen:
                raise ValueError(f'Invalid or duplicate observation for point {pid}')
            seen.add((image_id,index))
            image = images[image_id]
            x, y, linked = image['xy'][index]
            if linked != pid:
                raise ValueError(f'Non-reciprocal track for point {pid}')
            track.append({'image_id': image_id, 'filename': image['name'],
                          'point2D_index': index, 'x': x, 'y': y})
        xyz=list(map(float,f[1:4]));error=float(f[7])
        if len({image_id for image_id,index in seen})<2 or not all(math.isfinite(v) for v in xyz+[error]) or error<0:
            raise ValueError(f'Invalid triangulated point {pid}')
        points[pid] = {'xyz': xyz, 'error_px': error, 'track': track}
    if not points:
        raise ValueError('No triangulated tracks available')
    return images, points


def supported_by(point, image_ids):
    return len({o['image_id'] for o in point['track']} & set(image_ids)) >= 2


def render_lineage(root, summary, selection):
    import numpy as np
    import plotly.graph_objects as go
    import streamlit as st
    from PIL import Image, ImageDraw

    st.subheader('Evidence → Geometry → Supporting observations')
    st.caption('Real sparse-point lineage • evidence-state context • observation replay')
    folder = Path(summary['run_directory']) / ('text_' + Path(summary['sparse_model']).name)

    @st.cache_data
    def cached_tracks(path, image_time, point_time):
        return load_tracks(path)

    try:
        images, points = cached_tracks(str(folder), (folder/'images.txt').stat().st_mtime_ns,
                                      (folder/'points3D.txt').stat().st_mtime_ns)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        st.warning(f'Lineage unavailable for this dataset: {exc}')
        return
    st.info('OBSERVED: recorded image features and source frames. INFERRED: triangulated points, camera poses and mesh. Sparse points have exact observation tracks; mesh surfaces lack exact lineage. UNKNOWN: unseen geometry and independent metric accuracy.')
    ordered = sorted(images, key=lambda i: images[i]['name'])
    count = st.slider('Observation replay: images revealed in filename order', 1, len(ordered), len(ordered)) if len(ordered)>1 else 1
    revealed = set(ordered[:count])
    eligible = [pid for pid, point in points.items() if supported_by(point, revealed)]
    st.caption('Replay reveals final-model points after two supporting images are available. It does not rerun reconstruction or represent recorded solver history; filename order is not verified flight chronology.')
    st.metric('Points with at least two revealed observations', f'{len(eligible):,}')
    if not eligible:
        st.info('Reveal more observations to inspect supported points.')
        return
    step = max(1, (len(eligible)+7999)//8000)
    sampled = eligible[::step]
    xyz = np.array([points[pid]['xyz'] for pid in sampled])
    fig = go.Figure(go.Scatter3d(x=xyz[:,0], y=xyz[:,1], z=xyz[:,2], mode='markers',
        customdata=sampled, marker=dict(size=2, color='#56d6c3'),
        hovertemplate='Point %{customdata}<extra>Observed track support</extra>'))
    fig.update_layout(height=500, scene=dict(aspectmode='data'), margin=dict(l=0,r=0,t=0,b=0))
    offline_chart(fig, width='stretch')
    st.caption(f'Viewer samples {len(sampled):,} points. Choose an exact point ID below to inspect its recorded observations. Coordinates are reconstruction units.')
    pid = st.selectbox('Triangulated point ID', eligible)
    point = points[pid]
    st.write(f"Point {pid}: {len(point['track'])} source observations · mean reprojection error {point['error_px']:.3f} px")
    observations = [o for o in point['track'] if o['image_id'] in revealed]
    chosen = st.selectbox('Supporting source frame', range(len(observations)),
                          format_func=lambda i: observations[i]['filename'])
    obs = observations[chosen]
    source = Path(selection['source']).resolve()
    path = (source / obs['filename']).resolve()
    if path.is_relative_to(source) and path.is_file():
        with Image.open(path) as original:
            original_size = original.size
            preview = original.convert('RGB')
            preview.thumbnail((1400, 1000))
            x = obs['x'] * preview.width / original_size[0]
            y = obs['y'] * preview.height / original_size[1]
            draw = ImageDraw.Draw(preview)
            draw.ellipse((x-12,y-12,x+12,y+12), outline='#ff6600', width=4)
            draw.line((x-20,y,x+20,y), fill='#ff6600', width=2)
            draw.line((x,y-20,x,y+20), fill='#ff6600', width=2)
            st.image(preview, caption=f"Recorded image observation: ({obs['x']:.2f}, {obs['y']:.2f}) pixels", width='stretch')
    else:
        st.warning('Source image unavailable; track metadata remains inspectable.')
    st.dataframe(observations, hide_index=True, width='stretch')
    with st.expander('Source camera pose'):
        st.json(dict(zip(['qw','qx','qy','qz','tx','ty','tz'], images[obs['image_id']]['pose'])))
        st.caption('COLMAP world-to-camera transform; translation uses arbitrary model units.')
    package = {'point_id': pid, **point, 'model_directory': str(folder),
               'camera_poses': {str(o['image_id']): images[o['image_id']]['pose'] for o in point['track']},
               'limitations': 'Sparse-point provenance only. No dense/mesh surface lineage or validated metric accuracy.'}
    st.download_button('Export selected point evidence (JSON)', json.dumps(package, indent=2),
                       file_name=f'evidence_point_{pid}.json', mime='application/json')
    st.caption('Exact surface visibility and mission-weighted reconstruction remain future work. Historical point-cloud alignment is available in Temporal.')

