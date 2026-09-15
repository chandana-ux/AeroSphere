"""Coverage proxies from actual triangulation tracks and verified image graph."""
import json
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.spatial.transform import Rotation


def build_evidence(project):
    project=Path(project)
    summary=json.loads((project/'output/reconstruction/latest.json').read_text())
    run=Path(summary['run_directory']); model=Path(summary['sparse_model'])
    txt=run/('text_'+model.name)
    xyz=[];tracks=[]
    for line in (txt/'points3D.txt').read_text().splitlines():
        if line and not line.startswith('#'):
            p=line.split();xyz.append(list(map(float,p[1:4])));tracks.append((len(p)-8)//2)
    xyz=np.array(xyz);tracks=np.array(tracks)
    if not len(xyz):raise ValueError('No sparse points to assess')
    camera=pd.read_csv(run/'camera_trajectory.csv').sort_values('filename')
    coords=camera[['x','y','z']].to_numpy()
    rotations=Rotation.from_quat(camera[['qx','qy','qz','qw']].to_numpy())
    translation=np.linalg.norm(np.diff(coords,axis=0),axis=1)
    angles=(rotations[1:]*rotations[:-1].inv()).magnitude()*180/np.pi
    steps=pd.DataFrame({'filename':camera.filename.to_numpy(),'translation_from_previous_units':np.r_[np.nan,translation],
                        'rotation_from_previous_degrees':np.r_[np.nan,angles]})
    with sqlite3.connect(f"{(run/'database.db').as_uri()}?mode=ro",uri=True) as db:
        names=dict(db.execute('SELECT image_id,name FROM images'))
        pairs=list(db.execute('SELECT pair_id,rows FROM two_view_geometries WHERE rows>0'))
    graph={i:set() for i in names};edges=[]
    for pair,n in pairs:
        a,b=divmod(pair,2147483647)
        if a in graph and b in graph:
            graph[a].add(b);graph[b].add(a);edges.append({'image_a':names[a],'image_b':names[b],'verified_inliers':n})
    remaining=set(graph);components=[]
    while remaining:
        seen=set();pending=[next(iter(remaining))]
        while pending:
            node=pending.pop()
            if node in seen:continue
            seen.add(node);pending.extend(graph[node]-seen)
        remaining-=seen;components.append(len(seen))
    _,_,basis=np.linalg.svd(xyz-xyz.mean(0),full_matrices=False)
    xy=(xyz-xyz.mean(0))@basis[:2].T
    bins=24
    ex=np.linspace(xy[:,0].min(),xy[:,0].max(),bins+1);ey=np.linspace(xy[:,1].min(),xy[:,1].max(),bins+1)
    count,_,_=np.histogram2d(xy[:,0],xy[:,1],bins=[ex,ey])
    support,_,_=np.histogram2d(xy[:,0],xy[:,1],bins=[ex,ey],weights=tracks)
    mean=np.divide(support,count,out=np.zeros_like(count),where=count>0)
    state=np.where(count==0,0,np.where((count>=10)&(mean>=4),2,1))
    out=project/'results/coverage';out.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(out/'coverage_grid.npz',count=count,mean_track=mean,state=state,x=(ex[:-1]+ex[1:])/2,y=(ey[:-1]+ey[1:])/2)
    steps.to_csv(out/'viewpoint_change.csv',index=False)
    pd.DataFrame(edges).to_csv(out/'connectivity_edges.csv',index=False)
    report=dict(label='Approximate coverage',sparse_points=len(xyz),
                verified_graph_components=sorted(components,reverse=True),verified_pairs=len(edges),
                min_image_degree=min(map(len,graph.values())),max_image_degree=max(map(len,graph.values())),
                track_observation_min=int(tracks.min()),track_observation_median=float(np.median(tracks)),track_observation_max=int(tracks.max()),
                registration_ratio=summary['registered_images']/summary['input_images'],
                grid_cells=int(state.size),stronger_evidence_cells=int(np.sum(state==2)),sparse_evidence_cells=int(np.sum(state==1)),no_reconstructed_evidence_cells=int(np.sum(state==0)),
                grid_rules='24x24 PCA-plane grid. Stronger: >=10 points and mean track length >=4. Sparse: other populated cells. Insufficient: no reconstructed points.',
                limitations='Point density/track support, not exact surface visibility or completeness. Empty cells may be outside the surveyed footprint. Pose deltas use filename order and arbitrary translation units; no time-derived speed is claimed.')
    (out/'coverage_report.json').write_text(json.dumps(report,indent=2))
    return report
