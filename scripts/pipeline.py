"""Demo reporting or isolated new-input processing; preserves the Aukerman run."""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from geo import prepare
from evidence import build_evidence


def report(project):
    project=Path(project)
    geo=prepare(project);coverage=build_evidence(project)
    reconstruction=json.loads((project/'output/reconstruction/latest.json').read_text())
    quality=json.loads((project/'results/image_intelligence/latest.json').read_text())
    metadata=pd.read_csv(project/'metadata/image_metadata.csv')
    details=[]
    for name in metadata.filename:
        with Image.open(Path(quality['source'])/name) as im:
            exif=im.getexif();extra=exif.get_ifd(34665) if 34665 in exif else {}
            focal=extra.get(37386)
            details.append(dict(filename=name,focal_length_mm=float(focal) if focal is not None else None,exif_orientation=exif.get(274)))
    pd.DataFrame(details).to_csv(project/'metadata/image_metadata_details.csv',index=False)
    gps=metadata.dropna(subset=['latitude','longitude'])
    geographic=dict(gps_available=len(gps),center_latitude=float(gps.latitude.mean()) if len(gps) else None,
                    center_longitude=float(gps.longitude.mean()) if len(gps) else None,
                    bounds=dict(south=float(gps.latitude.min()),north=float(gps.latitude.max()),west=float(gps.longitude.min()),east=float(gps.longitude.max())) if len(gps) else None)
    semantics=list((project/'results/semantics').glob('*.json'))
    result=dict(input_type='aerial image dataset' if project==ROOT else 'processed input (see job/video metadata)',
                target_input='Single-pass drone video + GPS/flight metadata',input_images=len(metadata),
                reconstruction=reconstruction,image_intelligence=quality,geographic_context=geographic,
                geospatial_assessment=geo,coverage=coverage,
                semantic_status='available (saved predictions)' if semantics else 'optional/unavailable',
                limitations=['Approximate geospatial context — metric accuracy requires validated scale/georeferencing or RTK/PPK/GCP support.',
                             'Observed imagery differs from inferred geometry and unknown hidden surfaces.',
                             'Image dataset reconstruction does not validate continuous drone video reconstruction.',
                             'No validated metric surface measurements; GPS distances and model-space distances are distinguished.'])
    (project/'results/aerosphere_summary.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    lines=['# AeroSphere reconstruction report','',f'Input: {len(metadata)} images; GPS available for {len(gps)}.',
           f"Registered: {reconstruction['registered_images']}/{reconstruction['input_images']}; sparse points: {reconstruction['sparse_points']:,}.",
           f"Dense points: {reconstruction.get('dense_points','unavailable')}; mesh triangles: {reconstruction.get('mesh_triangles','unavailable')}.",
           f"Mean reprojection error: {reconstruction['mean_point_reprojection_error_pixels']:.6f} pixels (not metric accuracy).",
           f"Selection: {quality['selected_images']}/{quality['input_images']}; exact duplicates: {quality['exact_duplicates']}; near duplicates: {quality['near_duplicates']}.",
           f"Coverage: {coverage['label']}; verified image graph components: {coverage['verified_graph_components']}.",
           f"Geospatial: {geo['status']}; semantic status: {result['semantic_status']}.",'','## Limitations',*['- '+v for v in result['limitations']],
           '','## Outputs',f"Reconstruction folder: {reconstruction['run_directory']}",
           'Metadata: metadata/image_metadata.csv and image_metadata_details.csv',
           'Coverage and viewpoint reports: results/coverage/',
           'GPS fit: results/geospatial/',
           'Machine-readable summary: results/aerosphere_summary.json']
    (project/'results/aerosphere_report.md').write_text('\n\n'.join(lines),encoding='utf-8')
    return result


def process(source,job=None,interval=2,max_frames=300,reconstruct=False,dense=False):
    source=Path(source).resolve()
    if not source.exists():raise ValueError('Input path does not exist')
    job=Path(job).resolve() if job else ROOT/'results/jobs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    base=(ROOT/'results/jobs').resolve()
    if job.parent!=base:raise ValueError('Jobs must be immediate children of results/jobs')
    job.mkdir(parents=True,exist_ok=True)
    if (job/'job.json').exists():
        previous=json.loads((job/'job.json').read_text())
        if previous.get('status')!='queued':raise ValueError('Job already exists; create a new job')
    state=dict(status='processing',source=str(source),job=str(job),stage='input',started_utc=datetime.now(timezone.utc).isoformat())
    def save(): (job/'job.json').write_text(json.dumps(state,indent=2))
    def run(args):
        with (job/'pipeline.log').open('a') as log:
            subprocess.run([sys.executable,*map(str,args)],stdout=log,stderr=subprocess.STDOUT,check=True)
    save()
    try:
        if source.is_file():
            from extract_video import extract_video
            state['stage']='video extraction';save()
            video=extract_video(source,job/'video_ingestion',interval,max_frames)
            state['video']=video;source=job/'video_ingestion/frames'
        state['stage']='metadata';save()
        run([ROOT/'scripts/extract_metadata.py','--input',source,'--output',job/'metadata/image_metadata.csv'])
        state['stage']='image intelligence';save()
        run([ROOT/'scripts/analyze_images.py','--input',source,'--project',job])
        if reconstruct:
            selected_info=json.loads((job/'results/image_intelligence/latest.json').read_text())
            if selected_info['selected_images']<3:
                raise ValueError('Insufficient selected images for reconstruction: provide at least three overlapping, textured views')
            scores=pd.read_csv(Path(selected_info['report_directory'])/'image_quality.csv')
            if scores.orb_keypoints.fillna(0).max()<50:
                raise ValueError('Insufficient visual texture/features for a reliable reconstruction attempt')
            state['stage']='COLMAP';save()
            cmd=[ROOT/'scripts/run_reconstruction.py','--project',job]
            if dense:cmd.append('--dense')
            run(cmd)
            state['stage']='reports';save();report(job)
        state.update(status='completed',stage='ready',reconstruction_requested=reconstruct)
    except Exception as exc:
        state.update(status='failed',error=str(exc),diagnostic='Inspect pipeline.log and any COLMAP stage logs. Check overlap, image texture, input codec and disk space.')
    state['finished_utc']=datetime.now(timezone.utc).isoformat();save()
    return state


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--demo',action='store_true');p.add_argument('--input',type=Path);p.add_argument('--job',type=Path);p.add_argument('--interval',type=float,default=2);p.add_argument('--max-frames',type=int,default=300);p.add_argument('--reconstruct',action='store_true');p.add_argument('--dense',action='store_true')
    a=p.parse_args()
    if a.demo:result=report(ROOT)
    elif a.input:result=process(a.input,a.job,a.interval,a.max_frames,a.reconstruct,a.dense)
    else:p.error('Use --demo or --input PATH')
    print(json.dumps(result,indent=2));raise SystemExit(1 if result.get('status')=='failed' else 0)
