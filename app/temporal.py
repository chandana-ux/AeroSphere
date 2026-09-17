from ui import offline_chart
"""Historical point-cloud comparison with explicit coordinate alignment."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree

def similarity(source, target):
    source=np.asarray(source,float);target=np.asarray(target,float)
    if source.shape != target.shape or source.ndim != 2 or source.shape[1] != 3 or len(source)<4:
        raise ValueError('At least four paired 3D landmarks are required')
    if not np.isfinite(source).all() or not np.isfinite(target).all():
        raise ValueError('Landmarks must be finite')
    a=source-source.mean(0);b=target-target.mean(0)
    if np.linalg.matrix_rank(a)<2 or np.linalg.matrix_rank(b)<2:
        raise ValueError('Landmarks must not be collinear')
    u,s,vt=np.linalg.svd(a.T@b)
    correction=np.eye(3);correction[-1,-1]=np.sign(np.linalg.det(u@vt))
    rotation=u@correction@vt
    scale=float(np.sum(s*np.diag(correction))/np.sum(a*a))
    if scale<=0:
        raise ValueError('Invalid scale')
    matrix=np.eye(4);matrix[:3,:3]=scale*rotation.T
    matrix[:3,3]=target.mean(0)-matrix[:3,:3]@source.mean(0)
    predicted=source@matrix[:3,:3].T+matrix[:3,3]
    return matrix,float(np.sqrt(np.mean(np.sum((predicted-target)**2,axis=1))))

def compare_points(historical,current,matrix,threshold):
    a=np.asarray(historical,float);b=np.asarray(current,float);matrix=np.asarray(matrix,float)
    if matrix.shape!=(4,4) or not np.isfinite(matrix).all() or not np.allclose(matrix[3],[0,0,0,1]):
        raise ValueError('Expected a finite 4×4 affine transform')
    if abs(np.linalg.det(matrix[:3,:3]))<1e-12:
        raise ValueError('Transform is singular')
    if threshold<=0 or not np.isfinite(threshold):
        raise ValueError('Threshold must be positive')
    if any(x.ndim!=2 or x.shape[1]!=3 or len(x)<3 or not np.isfinite(x).all() for x in (a,b)):
        raise ValueError('Both clouds need at least three finite points')
    aligned=a@matrix[:3,:3].T+matrix[:3,3]
    da=cKDTree(b).query(aligned,workers=2)[0]
    db=cKDTree(aligned).query(b,workers=2)[0]
    report={'historical_points':len(a),'current_points':len(b),'threshold_model_units':threshold,
            'candidate_removed_or_unobserved':int(np.sum(da>threshold)),
            'candidate_new_or_unobserved':int(np.sum(db>threshold)),
            'historical_to_current_median':float(np.median(da)),
            'current_to_historical_median':float(np.median(db)),
            'transform_historical_to_current':matrix.tolist(),
            'classification':'Distance candidates only; new/removed/modified cannot be confirmed without matched visibility and independent alignment validation.',
            'limitations':'Sampling, occlusion, reconstruction noise and misalignment can appear as change. No metric accuracy or damage classification is claimed.'}
    return report,aligned,da,db

def render_temporal(root,summary):
    import pandas as pd
    import open3d as o3d
    import plotly.graph_objects as go
    import streamlit as st
    st.subheader('Historical comparison')
    st.caption('Historical observation → spatial alignment → candidate changes')
    saved=Path(root)/'results/temporal/comparison.json'
    if saved.exists():
        with st.expander('Saved comparison report'):
            st.json(json.loads(saved.read_text()))
            st.download_button('Download saved comparison',saved.read_bytes(),file_name='temporal_comparison.json')
    else:st.info('No genuine historical/current pair is installed. Import a previous point cloud to compare it with this mission. No before/after imagery is generated.')
    st.write('V1 accepts a previous PLY point cloud and paired landmarks in both reconstructions. Previous mission models are supported through their exported PLY. Orthophotos, satellite imagery and GIS change analysis are planned.')
    with st.form('temporal_form'):
        previous=st.text_input('Historical point cloud (local PLY path)')
        date=st.text_input('Historical capture date or source label')
        alignment=st.radio('Alignment method',['Paired landmarks','Already in the same coordinate frame'])
        landmarks=st.file_uploader('Landmark CSV: hx,hy,hz,cx,cy,cz (at least four rows)',type=['csv'])
        confirmed=st.checkbox('I verified the two clouds share the same origin, orientation and scale')
        threshold=st.number_input('Candidate change threshold (current model units)',min_value=0.000001,value=0.1,format='%.6f')
        submitted=st.form_submit_button('Align and compare')
    if submitted:
        try:
            path=Path(previous.strip().strip('"'))
            if not previous.strip() or path.suffix.lower()!='.ply' or not path.is_file():
                raise ValueError('Select an existing historical PLY point cloud')
            current=Path(summary['run_directory'])/'dense/fused.ply'
            if not current.exists():current=Path(summary['run_directory'])/'sparse.ply'
            if path.resolve()==current.resolve():raise ValueError('Choose a different observation, not the current cloud')
            if not date.strip():raise ValueError('Provide the historical observation date or source label')
            matrix=np.eye(4);rmse=None
            if alignment=='Paired landmarks':
                if landmarks is None:raise ValueError('Provide corresponding landmarks for spatial alignment')
                pairs=pd.read_csv(landmarks)
                matrix,rmse=similarity(pairs[['hx','hy','hz']].to_numpy(),pairs[['cx','cy','cz']].to_numpy())
            elif not confirmed:raise ValueError('Confirm a shared coordinate frame or use landmark alignment')
            with st.spinner('Comparing real point clouds locally…'):
                a=np.asarray(o3d.io.read_point_cloud(str(path)).points)
                b=np.asarray(o3d.io.read_point_cloud(str(current)).points)
                # Bounded deterministic display/comparison sampling, explicitly reported.
                a=a[::max(1,(len(a)+99999)//100000)];b=b[::max(1,(len(b)+99999)//100000)]
                report,aligned,da,db=compare_points(a,b,matrix,threshold)
            report.update(historical_source=path.name,historical_label=date,current_source=current.name,
                          landmark_fit_rmse_model_units=rmse,sampling='At most 100,000 evenly indexed points per cloud; distances are to sampled clouds.')
            st.session_state['temporal_result']=(str(root),report,aligned,b,da,db)
            out=Path(root)/'results/temporal';out.mkdir(parents=True,exist_ok=True)
            (out/'comparison.json').write_text(json.dumps(report,indent=2,allow_nan=False))
        except (OSError,ValueError,KeyError) as exc:st.error(str(exc))
    result=st.session_state.get('temporal_result')
    if result and result[0]==str(root):
        _,report,a,b,da,db=result
        st.warning(report['classification'])
        cols=st.columns(2)
        cols[0].metric('Current-only candidates',report['candidate_new_or_unobserved'])
        cols[1].metric('Historical-only candidates',report['candidate_removed_or_unobserved'])
        fig=go.Figure()
        for xyz,dist,label,color in [(a,da,'Historical','#ffb66a'),(b,db,'Current','#58c6de')]:
            ix=np.linspace(0,len(xyz)-1,min(15000,len(xyz)),dtype=int)
            fig.add_trace(go.Scatter3d(x=xyz[ix,0],y=xyz[ix,1],z=xyz[ix,2],mode='markers',name=label,
                marker=dict(size=2,color=np.where(dist[ix]>report['threshold_model_units'],color,'#576574'))))
        fig.update_layout(height=550,template='plotly_dark',scene=dict(aspectmode='data'))
        offline_chart(fig,width='stretch')
        st.caption(report['sampling']+' '+report['limitations'])
        st.download_button('Export change analysis',json.dumps(report,indent=2),file_name='temporal_comparison.json')

