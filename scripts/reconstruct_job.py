"""Background reconstruction for an already analyzed mission."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"app"))
from reconstruction_runtime import write_json

def run(project,dense=False,cpu=False,camera_sharing="auto"):
    project=Path(project);status=project/'reconstruction_job.json'
    state={'status':'running','started_utc':datetime.now(timezone.utc).isoformat()}
    write_json(status, state)
    try:
        selection=json.loads((project/'results/image_intelligence/latest.json').read_text())
        if selection['selected_images']<3:raise ValueError('At least three overlapping images are required')
        cmd=[sys.executable,str(Path(__file__).parent/'run_reconstruction.py'),'--project',str(project),'--camera-sharing',camera_sharing]
        if dense:cmd.append('--dense')
        if cpu:cmd.append('--cpu')
        subprocess.run(cmd,check=True)
        from pipeline import report
        try:
            report(project)
        except Exception as exc:
            state['report_error'] = str(exc)
        summary=json.loads((project/'output/reconstruction/latest.json').read_text())
        state['status']='partial' if state.get('report_error') or (dense and (summary.get('dense_status')!='success' or summary.get('mesh_status')!='success')) else 'completed'
    except Exception as exc:
        progress_path = project/'reconstruction_progress.json'
        progress = json.loads(progress_path.read_text()) if progress_path.exists() else {}
        state.update(status=progress.get('status') if progress.get('status') in ('failed', 'dependency_missing') else 'failed',error=progress.get('error', str(exc)))
    state['finished_utc']=datetime.now(timezone.utc).isoformat();write_json(status, state)
    return state

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--project',type=Path,required=True);p.add_argument('--dense',action='store_true');p.add_argument('--cpu',action='store_true');p.add_argument('--camera-sharing',choices=['auto','single'],default='auto')
    a=p.parse_args();state=run(a.project,a.dense,a.cpu,a.camera_sharing);print(json.dumps(state));sys.exit(1 if state['status'] in ('failed', 'dependency_missing') else 0)
