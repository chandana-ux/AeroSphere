"""Verify real dataset provenance, geometry counts and all eight dashboard pages.

Run after reconstruction; this does not create or simulate any geometry.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import cv2
import numpy as np
import open3d as o3d
import pandas as pd
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'app'))
from reconstruction_runtime import write_json
from mission import read_json
from world import run_directory_for_mission


def verify(project):
    project = Path(project).resolve()
    video = read_json(project/'video_ingestion/video_metadata.json')
    selection = read_json(project/'results/image_intelligence/latest.json')
    summary = read_json(project/'output/reconstruction/latest.json')
    progress = read_json(project/'reconstruction_progress.json')
    assert progress.get('status') != 'processing', 'Wait for reconstruction to finish'
    source = Path(video['source'])
    rows = pd.read_csv(project/'video_ingestion/frame_timestamps.csv')
    assert len(rows) == video['extracted_frames']
    cap = cv2.VideoCapture(str(source), cv2.CAP_FFMPEG)
    first = rows.iloc[0]
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(first.source_frame_index))
    ok, original = cap.read()
    cap.release()
    assert ok
    target = cv2.imread(str(project/'video_ingestion/frames'/first.filename))
    if original.shape != target.shape:
        original = cv2.resize(original, (target.shape[1], target.shape[0]), interpolation=cv2.INTER_AREA)
    error = float(np.abs(original.astype(float)-target.astype(float)).mean())
    assert error < 12, f'Extracted frame does not match source: {error}'
    selected = Path(selection['selected_directory'])
    for frame in selected.iterdir():
        assert hashlib.sha256(frame.read_bytes()).digest() == hashlib.sha256((Path(selection['source'])/frame.name).read_bytes()).digest()
    result = dict(project=str(project), source=str(source), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        width=video['width'],height=video['height'],fps=video['fps'],duration_s=video['reported_duration_s'],
        extracted_frames=len(rows),selected_frames=selection['selected_images'],
        first_frame_mean_absolute_decode_error=error, stages=progress.get('stages'), geometry={})
    if summary:
        run = run_directory_for_mission(project, summary)
        assert run.is_relative_to(project)
        assert str(run) == progress['run_directory'], 'Latest summary is stale'
        result.update(registered_images=summary['registered_images'], sparse_components=summary['sparse_components'],
                      reprojection_error_px=summary['mean_point_reprojection_error_pixels'])
        for label, relative, field in [('sparse','sparse.ply','sparse_points'), ('dense','dense/fused.ply','dense_points'), ('mesh','dense/mesh.ply','mesh_vertices')]:
            if label != 'sparse' and summary.get(label+'_status') != 'success':
                continue
            path = run/relative
            obj = o3d.io.read_triangle_mesh(str(path)) if label == 'mesh' else o3d.io.read_point_cloud(str(path))
            xyz = np.asarray(obj.vertices if label == 'mesh' else obj.points)
            assert len(xyz)>0 and np.isfinite(xyz).all()
            assert len(xyz) == summary[field]
            stats = {'vertices_or_points':len(xyz), 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            if label == 'mesh':
                assert len(obj.triangles) == summary['mesh_triangles'] and len(obj.triangles)>0
                stats['triangles'] = len(obj.triangles)
            result['geometry'][label] = stats
    app = AppTest.from_file(str(ROOT/'app/dashboard.py'), default_timeout=120)
    app.session_state['active_root'] = str(project)
    app.session_state['nav'] = '3D WORLD'
    app.run()
    result['pages'] = {}
    for page in ['MISSION','FRAMES','RECONSTRUCTION','3D WORLD','GEO','MEASURE','QUALITY','INTELLIGENCE']:
        next(b for b in app.button if b.label == page).click().run()
        assert not app.exception, f'{page}: {app.exception}'
        assert app.session_state['active_root'] == str(project)
        if page == 'MEASURE' and summary:
            assert any('Distance A' in m.label for m in app.metric), 'No actual model measurement'
        if page == 'QUALITY' and summary:
            assert any(m.label == 'Registered images' and m.value.startswith(str(summary['registered_images'])) for m in app.metric)
        if page == 'GEO' and summary:
            assert any('Reconstructed camera positions' in s.value for s in app.subheader)
        if page == 'INTELLIGENCE' and summary:
            assert any('Reconstructed scene statistics' in s.value for s in app.subheader)
        if page == '3D WORLD' and summary:
            components = app.get('component_instance')
            assert components, 'Viewer geometry component missing'
            text = '\n'.join(m.value for m in app.markdown)
            assert 'AeroSphere Reconstruction' in text
        result['pages'][page] = 'passed'
    result['viewer_modes'] = {}
    if summary:
        next(b for b in app.button if b.label == '3D WORLD').click().run()
        for mode, expected, stage in [('Mesh','Mesh','mesh'),('Dense cloud','Dense Cloud','dense'),('Sparse cloud','Sparse Cloud','sparse'),('Wireframe','Wireframe','mesh')]:
            if stage != 'sparse' and summary.get(stage+'_status') != 'success':
                result['viewer_modes'][mode] = 'unavailable'
                continue
            for checkbox in app.checkbox:
                if checkbox.label in ('Mesh','Dense cloud','Sparse cloud','Wireframe') and not checkbox.disabled:
                    checkbox.set_value(checkbox.label == mode)
            app.run()
            assert not app.exception, str(app.exception)
            component = app.get('component_instance')[0]
            figure = json.loads(json.loads(component.proto.json_args)['figure'])
            trace = next(t for t in figure['data'] if t.get('name') == expected)
            assert trace.get('x'), f'{mode} has no coordinates'
            if mode == 'Mesh':
                assert trace.get('i'), 'Mesh has no triangle indices'
            result['viewer_modes'][mode] = 'passed'
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('projects', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, default=ROOT/'results/local_video_validation.json')
    args = parser.parse_args()
    results = [verify(project) for project in args.projects]
    assert len({r['source_sha256'] for r in results}) == len(results), 'Inputs are duplicate videos'
    assert len({r['project'] for r in results}) == len(results)
    write_json(args.output, results)
    print(json.dumps(results, indent=2))
