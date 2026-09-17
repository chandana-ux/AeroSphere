"""Local mission catalog, honest capabilities and portable artifact packaging."""
import hashlib
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

MODES = {
    'RECONNAISSANCE': ('Structures · vehicles · obstacles', ['car', 'truck', 'bus', 'motorcycle', 'person']),
    'INFRASTRUCTURE': ('Structures · roads · inspection evidence', ['truck', 'bus', 'car']),
    'DISASTER ASSESSMENT': ('Affected infrastructure · access · evidence gaps', ['person', 'car', 'truck', 'boat']),
    'URBAN MAPPING': ('Buildings · roads · land-use context', ['car', 'bus', 'truck', 'bicycle']),
}

def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {} if default is None else default

def profile(root):
    return read_json(Path(root)/'mission.json', {'name': 'Aukerman aerial survey', 'mode': 'URBAN MAPPING', 'category': 'URBAN'})

def save_profile(root, name, mode):
    if mode not in MODES:
        raise ValueError('Unknown mission type')
    path = Path(root)/'mission.json'
    data = {'name': name.strip() or 'Untitled mission', 'mode': mode,
            'category': {'URBAN MAPPING':'URBAN', 'RECONNAISSANCE':'URBAN', 'INFRASTRUCTURE':'INFRASTRUCTURE', 'DISASTER ASSESSMENT':'DISASTER'}[mode],
            'updated_utc': datetime.now(timezone.utc).isoformat(),
            'telemetry_extensions': {'imu': None, 'rtk': None, 'ppk': None, 'calibration': None}}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)
    return data

def catalog(code_root):
    roots = [Path(code_root)] + sorted((Path(code_root)/'results/jobs').glob('*'), reverse=True)
    result = []
    for root in roots:
        if not root.is_dir() or root.name.startswith('TEST_'):
            continue
        selection = read_json(root/'results/image_intelligence/latest.json')
        recon = read_json(root/'output/reconstruction/latest.json')
        job = read_json(root/'job.json')
        if 'SYNTHETIC_' in job.get('source','').upper():
            continue  # Test fixtures never masquerade as mission observations.
        if root != Path(code_root) and not (selection or recon or job):
            continue
        p = profile(root) if (root/'mission.json').exists() or root == Path(code_root) else {'name': 'Mission '+root.name, 'mode':'RECONNAISSANCE', 'category':'URBAN'}
        result.append({'root':root, **p, 'images':selection.get('input_images',0),
                       'status':'3D ready' if recon else job.get('status','Awaiting input'),
                       'capture':'Video' if (root/'video_ingestion/video_metadata.json').exists() else 'Images'})
    return result

def package_mission(root, summary, selection, geo):
    """Stream files into a ZIP on disk; all entries are relative and checksummed."""
    root = Path(root); run = Path(summary['run_directory'])
    dest = root/'results/exports'; dest.mkdir(parents=True, exist_ok=True)
    target = dest/'aerosphere_mission.zip'; temp = dest/'aerosphere_mission.tmp'
    sources = [(run/'sparse.ply','geometry/sparse.ply'), (run/'dense/fused.ply','geometry/dense.ply'),
               (run/'dense/mesh.ply','geometry/mesh_original.ply'), (run/'dense/mesh_display.ply','geometry/mesh_display.ply'),
               (run/'dense/mesh_display.json','reports/mesh_processing.json'),
               (run/'camera_trajectory.csv','metadata/camera_trajectory.csv'),
               (root/'metadata/image_metadata.csv','metadata/image_metadata.csv'),
               (root/'metadata/image_metadata_details.csv','metadata/camera_metadata.csv'),
               (run/'summary.json','reports/reconstruction.json'),
               (Path(selection['report_directory'])/'image_quality.csv','reports/frame_quality.csv'),
               (Path(selection['report_directory'])/'selection_manifest.json','reports/selection_manifest.json'),
               (root/'results/coverage/coverage_report.json','reports/coverage.json'),
               (root/'results/coverage/connectivity_edges.csv','metadata/connectivity.csv'),
               (root/'video_ingestion/frame_timestamps.csv','metadata/video_timestamps.csv'),
               (root/'mission.json','mission.json')]
    text = run/('text_'+Path(summary['sparse_model']).name)
    sources += [(text/n,'lineage/'+n) for n in ('images.txt','points3D.txt','cameras.txt')]
    sources += [(p,'temporal/'+p.name) for p in (root/'results/temporal').glob('*.json')]
    records=[]
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as archive:
        for source, name in sources:
            if not source.is_file():
                continue
            h=hashlib.sha256()
            with source.open('rb') as stream, archive.open(name,'w') as out:
                for block in iter(lambda: stream.read(1024*1024),b''):
                    h.update(block); out.write(block)
            records.append({'file':name,'bytes':source.stat().st_size,'sha256':h.hexdigest()})
        archive.writestr('reports/geospatial.json',json.dumps(geo,indent=2,allow_nan=False))
        archive.writestr('MISSION_SUMMARY.md', '# AeroSphere mission\n\n'+profile(root)['name']+'\n\n'+
            f"Registered cameras: {summary['registered_images']}; sparse points: {summary['sparse_points']}.\n\n"+
            'Observed evidence: source image observations recorded in COLMAP tracks. Geometry and poses are estimates. '+
            'Mesh appearance is derived from nearest fused-cloud colors, not a UV texture. '+
            'Hidden surfaces and independent metric accuracy remain unknown. All geometry uses native model units. '+
            'Source photographs are not bundled; frame filenames and pixel observations are included.\n')
        archive.writestr('manifest.json',json.dumps({'files':records,'scope':'Checksums cover copied source artifacts; generated reports are not checksummed.'},indent=2))
    os.replace(temp,target)
    return target
