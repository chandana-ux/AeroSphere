"""Layered offline 3D world; exact sparse tracks and scoped proximity lookup."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit.components.v1 import declare_component
from lineage import load_tracks

_world=declare_component('aerosphere_world',path=str(Path(__file__).parent/'viewer_component'))

@st.cache_data
def geometry(path,mtime,mesh=False):
    import open3d as o3d
    if mesh:
        obj=o3d.io.read_triangle_mesh(path)
        obj.compute_vertex_normals()
        return np.asarray(obj.vertices),np.asarray(obj.vertex_colors),np.asarray(obj.triangles)
    obj=o3d.io.read_point_cloud(path)
    return np.asarray(obj.points),np.asarray(obj.colors),np.empty((0,3),int)

@st.cache_data
def tracks(path,mtime,point_mtime):
    return load_tracks(path)

def model_tracks(summary):
    folder=Path(summary['run_directory'])/('text_'+Path(summary['sparse_model']).name)
    return tracks(str(folder),(folder/'images.txt').stat().st_mtime_ns,(folder/'points3D.txt').stat().st_mtime_ns)

def render_inspector(summary,selection,pid,metadata=None):
    from PIL import Image,ImageDraw
    images,points=model_tracks(summary)
    if pid not in points:return
    point=points[pid]
    st.subheader(f'Point {pid} · supporting evidence')
    st.caption('OBSERVED image features → INFERRED triangulated point. Exact reciprocal COLMAP tracks.')
    cols=st.columns(3)
    cols[0].metric('Source frames',len({o['image_id'] for o in point['track']}))
    cols[1].metric('Reprojection error',f"{point['error_px']:.3f} px")
    cols[2].metric('Evidence state','Track supported')
    obs=st.selectbox('Supporting source frame',point['track'],format_func=lambda o:o['filename'],key='world_source')
    root=Path(selection['source']).resolve();path=(root/obs['filename']).resolve()
    if path.is_relative_to(root) and path.is_file():
        with Image.open(path) as im:
            w,h=im.size;im=im.convert('RGB');im.thumbnail((1000,640))
            x,y=obs['x']*im.width/w,obs['y']*im.height/h
            ImageDraw.Draw(im).ellipse((x-10,y-10,x+10,y+10),outline='#ffb454',width=3)
            st.image(im,caption=f"{obs['filename']} · recorded feature ({obs['x']:.1f}, {obs['y']:.1f}) px",width='stretch')
    else:st.info('Source image is unavailable; recorded observations remain inspectable.')
    with st.expander('Observations, camera pose and metadata'):
        st.dataframe(point['track'],hide_index=True)
        st.json(dict(zip(['qw','qx','qy','qz','tx','ty','tz'],images[obs['image_id']]['pose'])))
        if metadata is not None:st.dataframe(metadata[metadata.filename==obs['filename']],hide_index=True)
    st.download_button('Export selected evidence',json.dumps({'point_id':pid,**point,'scope':'Exact sparse track, not dense/mesh surface lineage'},indent=2),file_name=f'evidence_{pid}.json')

def render_world(root,summary,selection,metadata):
    run=Path(summary['run_directory']);cameras=pd.read_csv(run/'camera_trajectory.csv').sort_values('filename')
    try:images,points=model_tracks(summary)
    except (OSError,ValueError,KeyError,IndexError):images,points={},{}
    left,right=st.columns([4.6,1.25],gap='medium')
    with right:
        st.markdown('#### MODEL')
        mesh=st.checkbox('Mesh',True)
        dense=st.checkbox('Dense Cloud',False)
        sparse=st.checkbox('Sparse Cloud',False)
        show_cameras=st.checkbox('Cameras',True)
        trajectory=st.checkbox('Camera Trajectory',True)
        evidence=st.radio('Evidence',['Normal model','Evidence View'],label_visibility='collapsed')
        budget=st.select_slider('Point display budget',[10000,30000,60000,100000],value=60000)
        isolate=st.selectbox('Isolate layer',['All enabled','Mesh','Dense Cloud','Sparse Cloud','Cameras'])
        reset=st.button('Fit model / Reset view',width='stretch')
        selected=st.session_state.get('world_point')
        supported=st.checkbox('Only supporting cameras',False,disabled=selected not in points)
        st.caption('Native model units · geographic up unverified')
        if evidence=='Evidence View':st.caption('Cyan: sparse estimates with recorded observations. Amber: dense/mesh estimates. Unknown surfaces are absent, not fabricated.')
    fig=go.Figure();all_xyz=[];counts=[]
    for enabled,label,relative,is_mesh in [(mesh,'Mesh','dense/mesh_display.ply',True),(dense,'Dense Cloud','dense/fused.ply',False),(sparse or evidence=='Evidence View','Sparse Cloud','sparse.ply',False)]:
        if not enabled or isolate not in ('All enabled',label):continue
        path=run/relative
        if is_mesh and not path.exists():path=run/'dense/mesh.ply'
        if not path.exists():
            with left:st.info(label+' is not available for this reconstruction.')
            continue
        xyz,colors,triangles=geometry(str(path),path.stat().st_mtime_ns,is_mesh)
        if not len(xyz):continue
        if label=='Sparse Cloud' and points:
            ids=list(points);xyz=np.array([points[i]['xyz'] for i in ids]);colors=np.empty((0,3))
        else:ids=None
        all_xyz.append(xyz)
        if is_mesh:
            fig.add_trace(go.Mesh3d(x=xyz[:,0].tolist(),y=xyz[:,1].tolist(),z=xyz[:,2].tolist(),
                i=triangles[:,0].tolist(),j=triangles[:,1].tolist(),k=triangles[:,2].tolist(),
                vertexcolor=(np.clip(colors,0,1)*255).astype(int).tolist() if len(colors) and evidence=='Normal model' else None,
                color='#dca55e',name=label,flatshading=False,lighting=dict(ambient=.65,diffuse=.85,specular=.12,roughness=.85),
                hovertemplate='Interpolated surface · click for nearby sparse evidence<extra></extra>'))
            counts.append(f'{len(triangles):,} triangles')
        else:
            ix=np.linspace(0,len(xyz)-1,min(budget,len(xyz)),dtype=int)
            rgb=['rgb(%d,%d,%d)'%tuple(c) for c in (np.clip(colors[ix],0,1)*255).astype(int)] if len(colors) and evidence=='Normal model' else ('#5ed5dd' if ids else '#dca55e')
            fig.add_trace(go.Scatter3d(x=xyz[ix,0].tolist(),y=xyz[ix,1].tolist(),z=xyz[ix,2].tolist(),mode='markers',
                customdata=[ids[i] for i in ix] if ids else None,marker=dict(size=1.7,color=rgb),name=label,
                hovertemplate='Click to inspect supporting evidence<extra>'+label+'</extra>'))
            counts.append(f'{len(ix):,} / {len(xyz):,} {label.lower()} points')
    visible_cameras=cameras
    if supported and selected in points:
        visible_cameras=cameras[cameras.image_id.isin([o['image_id'] for o in points[selected]['track']])]
    if isolate in ('All enabled','Cameras') and (show_cameras or trajectory):
        if show_cameras:fig.add_trace(go.Scatter3d(x=visible_cameras.x.tolist(),y=visible_cameras.y.tolist(),z=visible_cameras.z.tolist(),mode='markers',marker=dict(size=4,color='#eab46f'),text=visible_cameras.filename.tolist(),name='Cameras',hovertemplate='%{text}<extra>Estimated camera</extra>'))
        if trajectory:fig.add_trace(go.Scatter3d(x=visible_cameras.x.tolist(),y=visible_cameras.y.tolist(),z=visible_cameras.z.tolist(),mode='lines',line=dict(width=3,color='#eab46f'),name='Camera Trajectory',hoverinfo='skip'))
    if selected in points:
        p=points[selected]['xyz'];fig.add_trace(go.Scatter3d(x=[p[0]],y=[p[1]],z=[p[2]],mode='markers',marker=dict(size=7,color='#ffffff'),name='Selected point',customdata=[selected]))
    # Frame the dominant geometry plane from the camera side without changing
    # coordinates or claiming that the PCA normal is geographic vertical.
    eye=dict(x=1.35,y=-1.6,z=1.2);up=dict(x=0,y=0,z=1)
    if all_xyz:
        base=all_xyz[0][::max(1,len(all_xyz[0])//20000)]
        _,_,axes_pca=np.linalg.svd(base-base.mean(0),full_matrices=False)
        if len(axes_pca)==3:
            normal=axes_pca[2]
            if np.dot(normal,cameras[['x','y','z']].to_numpy().mean(0)-base.mean(0))<0:normal=-normal
            direction=1.8*normal+.8*axes_pca[0]-.6*axes_pca[1]
            eye=dict(zip(('x','y','z'),map(float,direction)))
            up=dict(zip(('x','y','z'),map(float,axes_pca[1])))
    if show_cameras or trajectory:all_xyz.append(visible_cameras[['x','y','z']].to_numpy())
    reference=np.concatenate(all_xyz) if all_xyz else cameras[['x','y','z']].to_numpy()
    lo=reference.min(0);hi=reference.max(0);span=np.maximum(hi-lo,1e-4);pad=span*.06
    revision=st.session_state.get('view_revision',0)+int(reset);st.session_state['view_revision']=revision
    axes={k:dict(range=[float(lo[i]-pad[i]),float(hi[i]+pad[i])],visible=False) for i,k in enumerate(('xaxis','yaxis','zaxis'))}
    fig.update_layout(height=640,paper_bgcolor='#101820',font=dict(color='#bdd0df'),margin=dict(l=0,r=0,t=0,b=0),
        scene=dict(**axes,aspectmode='data',bgcolor='#101820',camera=dict(eye=eye,up=up)),
        legend=dict(orientation='h',y=.02,x=.02,bgcolor='rgba(16,24,32,.75)'),uirevision=f'{run}-{revision}')
    with left:
        event=_world(figure=fig.to_json(),key='world_'+str(root),default=None)
        st.caption(' · '.join(counts)+'. Original resolution is retained in exports. Trajectory follows filename order.')
    if event and event.get('nonce')!=st.session_state.get('world_event') and points and event.get('layer') not in ('Cameras','Camera Trajectory'):
        st.session_state['world_event']=event['nonce']
        pid=event.get('point_id');scope='Exact sparse-point observation track.'
        if pid not in points:
            from scipy.spatial import cKDTree
            ids=list(points);distance,index=cKDTree([points[i]['xyz'] for i in ids]).query(event['xyz'])
            pid=ids[index];scope=f'Nearest sparse track, {distance:.5f} model units from the selected geometry. This is contextual evidence, not exact surface provenance.'
        st.session_state['world_point']=pid;st.session_state['world_point_picker']=pid;st.session_state['world_scope']=scope
        st.rerun()
    if points:
        ids=list(points)
        pid=st.selectbox('Inspect exact sparse point',ids,index=ids.index(st.session_state['world_point']) if st.session_state.get('world_point') in points else 0,key='world_point_picker')
        if pid!=st.session_state.get('world_point'):
            st.session_state['world_point']=pid;st.session_state['world_scope']='Exact sparse-point observation track.'
        st.caption(st.session_state.get('world_scope','Exact sparse-point observation track.'))
        render_inspector(summary,selection,pid,metadata)
