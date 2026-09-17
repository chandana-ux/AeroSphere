"""Background reconstruction for an already analyzed mission."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime,timezone

def run(project,dense=False,cpu=False):
    project=Path(project);status=project/'reconstruction_job.json'
    state={'status':'running','started_utc':datetime.now(timezone.utc).isoformat()}
    status.write_text(json.dumps(state))
    try:
        selection=json.loads((project/'results/image_intelligence/latest.json').read_text())
        if selection['selected_images']<3:raise ValueError('At least three overlapping images are required')
        cmd=[sys.executable,str(Path(__file__).parent/'run_reconstruction.py'),'--project',str(project)]
        if dense:cmd.append('--dense')
        if cpu:cmd.append('--cpu')
        subprocess.run(cmd,check=True)
        from pipeline import report
        report(project)
        summary=json.loads((project/'output/reconstruction/latest.json').read_text())
        state['status']='partial' if dense and summary.get('dense_status')!='success' else 'completed'
    except Exception as exc:state.update(status='failed',error=str(exc))
    state['finished_utc']=datetime.now(timezone.utc).isoformat();status.write_text(json.dumps(state,indent=2))
    return state

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--project',type=Path,required=True);p.add_argument('--dense',action='store_true');p.add_argument('--cpu',action='store_true')
    a=p.parse_args();state=run(a.project,a.dense,a.cpu);print(json.dumps(state));sys.exit(1 if state['status']=='failed' else 0)
