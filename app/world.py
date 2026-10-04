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
    try:
        import open3d as o3d
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            f'Open3D is unavailable in this Python runtime ({exc}). Install requirements with Python 3.11 or 3.12.'
        ) from exc
    if mesh:
        obj=o3d.io.read_triangle_mesh(path)
        if not len(obj.vertices) or not len(obj.triangles) or not np.isfinite(np.asarray(obj.vertices)).all():
            raise ValueError('Mesh is empty, unreadable or has nonfinite coordinates')
        obj.compute_vertex_normals()
        return np.asarray(obj.vertices),np.asarray(obj.vertex_colors),np.asarray(obj.triangles)
    obj=o3d.io.read_point_cloud(path)
    if not len(obj.points) or not np.isfinite(np.asarray(obj.points)).all():
        raise ValueError('Point cloud is empty, unreadable or has nonfinite coordinates')
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

def _scene_camera_from_bounds(bounds, mode='initial'):
    if bounds is None:
        bounds = (np.array([-1.0, -1.0, -1.0]), np.array([1.0, 1.0, 1.0]))
    if mode == 'fit':
        eye = np.array([2.0, 2.0, 1.65], dtype=float)
    else:
        eye = np.array([1.6, 1.6, 1.25], dtype=float)
    return {'eye': {'x': float(eye[0]), 'y': float(eye[1]), 'z': float(eye[2])}, 'center': {'x': 0.0, 'y': 0.0, 'z': 0.0}, 'up': {'x': 0.0, 'y': 0.0, 'z': 1.0}}


def mesh_path_for_mission(root, run):
    run = Path(run)
    mesh = run / 'dense/mesh.ply'
    if mesh.is_file():
        return mesh
    display_mesh = run / 'dense/mesh_display.ply'
    if display_mesh.is_file():
        return display_mesh
    code_root = Path(__file__).resolve().parents[1]
    demo_mesh = code_root / 'results/dense/mesh.ply'
    if Path(root).resolve() == code_root and demo_mesh.is_file():
        return demo_mesh
    return mesh


def run_directory_for_mission(root, summary):
    root = Path(root).resolve()
    candidate = Path(summary['run_directory']).resolve() if summary and summary.get('run_directory') else root / 'results'
    code_root = Path(__file__).resolve().parents[1]
    if root == code_root or candidate == root or candidate.is_relative_to(root):
        return candidate
    return root / 'results'


def render_world(root,summary,selection,metadata):
    run = run_directory_for_mission(root, summary)
    camera_trajectory = run / 'camera_trajectory.csv'
    cameras = pd.DataFrame(columns=['filename', 'x', 'y', 'z', 'image_id'])
    if camera_trajectory.exists():
        try:
            loaded_cameras = pd.read_csv(camera_trajectory)
            if {'filename', 'x', 'y', 'z'}.issubset(loaded_cameras.columns):
                cameras = loaded_cameras.sort_values('filename')
        except (OSError, pd.errors.ParserError, ValueError):
            pass
    try:
        if summary and 'run_directory' in summary:
            images,points=model_tracks(summary)
        else:
            images,points={},{}
    except (OSError,ValueError,KeyError,IndexError):images,points={},{}

    mesh_path = mesh_path_for_mission(root, run)
    dense_path = run/'dense/fused.ply'
    if summary.get('mesh_status') in ('failed', 'empty', 'running', 'not_started', 'not_requested'):
        mesh_path = run / 'unavailable_mesh.ply'
    if summary.get('dense_status') in ('failed', 'dependency_missing', 'running', 'not_requested'):
        dense_path = run / 'unavailable_dense.ply'
    mesh_vertices = 0
    mesh_triangles = 0
    dense_points_count = 0
    mesh_bounds = None
    mesh_error = None
    if mesh_path.exists():
        try:
            mesh_xyz, _, mesh_triangles_arr = geometry(str(mesh_path), mesh_path.stat().st_mtime_ns, mesh=True)
            mesh_vertices = len(mesh_xyz)
            mesh_triangles = len(mesh_triangles_arr)
            print(f'MESH_PATH={mesh_path}')
            print(f'MESH_VERTICES={mesh_vertices}')
            print(f'MESH_TRIANGLES={mesh_triangles}')
            if len(mesh_xyz):
                mesh_bounds = (mesh_xyz.min(0), mesh_xyz.max(0))
                mesh_center = (mesh_bounds[0] + mesh_bounds[1]) / 2.0
                mesh_extent = mesh_bounds[1] - mesh_bounds[0]
                print(f'MESH_MIN={mesh_bounds[0].tolist()}')
                print(f'MESH_MAX={mesh_bounds[1].tolist()}')
                print(f'MESH_CENTER={mesh_center.tolist()}')
                print(f'MESH_EXTENT={mesh_extent.tolist()}')
        except Exception as exc:
            mesh_vertices = 0
            mesh_triangles = 0
            mesh_error = f'{type(exc).__name__}: {exc}'
    if dense_path.exists():
        try:
            dense_xyz, _, _ = geometry(str(dense_path), dense_path.stat().st_mtime_ns, mesh=False)
            dense_points_count = len(dense_xyz)
            if len(dense_xyz) and mesh_bounds is None:
                mesh_bounds = (dense_xyz.min(0), dense_xyz.max(0))
        except Exception:
            dense_points_count = 0

    st.markdown(f'''
    <div style="margin: 0 0 0.7rem 0; padding: 0.4rem 0 0.6rem 0; border-bottom: 1px solid rgba(148,177,196,0.18); line-height: 1.35;">
      <div style="font-size:0.68rem; letter-spacing:0.18em; text-transform:uppercase; color:#6ac7d8; font-weight:700;">3D WORLD</div>
      <div style="font-size:1.15rem; font-weight:700; margin-top:0.2rem;">AeroSphere Reconstruction</div>
      <div style="display:flex; gap:1rem; flex-wrap:wrap; margin-top:0.45rem; color:#bfd0db; font-size:0.68rem; letter-spacing:0.08em; text-transform:uppercase;">
        <span>MESH · {mesh_vertices:,} vertices · {mesh_triangles:,} triangles</span>
        <span>DENSE · {dense_points_count:,} points</span>
        <span>SCALE · RELATIVE / NOT GEOREFERENCED</span>
      </div>
    </div>
    ''', unsafe_allow_html=True)

    left,right=st.columns([4.2,1.15],gap='small')
    if mesh_error:
        with left:
            st.warning(f'Mesh file could not be loaded: {mesh_error}')
    with right:
        st.markdown('<div class="compact-label">View</div>', unsafe_allow_html=True)
        has_mesh=mesh_path.is_file() and mesh_error is None and mesh_triangles > 0
        has_dense=dense_path.exists()
        has_sparse=(run/'sparse.ply').exists() or bool(points)
        mesh=st.checkbox('Mesh', value=has_mesh, key='world_mesh_toggle', disabled=not has_mesh)
        dense=st.checkbox('Dense cloud', value=has_dense and not has_mesh, key='world_dense_toggle', disabled=not has_dense)
        sparse=st.checkbox('Sparse cloud', value=has_sparse and not has_dense and not has_mesh, key='world_sparse_toggle', disabled=not has_sparse)
        wire=st.checkbox('Wireframe', value=False, key='world_wireframe_toggle', disabled=not has_mesh)
        st.markdown('<div class="compact-label" style="margin-top:0.7rem;">Overlays</div>', unsafe_allow_html=True)
        show_cameras=st.checkbox('Cameras', value=False, key='world_cameras_toggle', disabled=cameras.empty)
        trajectory=st.checkbox('Trajectory', value=False, key='world_trajectory_toggle', disabled=cameras.empty)
        for label, available in [('Mesh / Wireframe', has_mesh), ('Dense cloud', has_dense), ('Sparse cloud', has_sparse)]:
            if not available:
                st.caption(label + ' unavailable for this dataset.')
        if cameras.empty:
            st.caption('Camera trajectory unavailable; the mesh can still be inspected.')
        if 'world_evidence_mode' not in st.session_state:
            st.session_state['world_evidence_mode'] = 'Normal model'
        evidence_value = st.session_state.get('world_evidence_mode', 'Normal model')
        evidence = st.radio('Evidence',['Normal model','Evidence View'],index=0 if evidence_value == 'Normal model' else 1,label_visibility='collapsed', key='world_evidence_mode')
        budget=st.select_slider('Point display budget',[10000,30000,60000,100000],value=60000)
        isolate=st.selectbox('Layer',['All enabled','Mesh','Dense Cloud','Sparse Cloud','Cameras'])
        st.markdown('<div class="compact-label" style="margin-top:0.7rem;">Camera</div>', unsafe_allow_html=True)
        if st.button('Fit model', use_container_width=True, key='fit_model_world'):
            st.session_state['world_camera_mode'] = 'fit'
        if st.button('Reset view', use_container_width=True, key='reset_view_world'):
            st.session_state['world_camera_mode'] = 'reset'
        selected=st.session_state.get('world_point')
        supported=st.checkbox('Only supporting cameras',False,disabled=selected not in points)
        st.caption('Native model units · geographic up unverified')
        if evidence=='Evidence View':st.caption('Cyan: sparse estimates with recorded observations. Amber: dense/mesh estimates. Unknown surfaces are absent, not fabricated.')
    fig=go.Figure();all_xyz=[];counts=[]
    model_origin = np.zeros(3, dtype=float)
    if mesh_bounds is not None:
        model_origin = (mesh_bounds[0] + mesh_bounds[1]) / 2.0
    for enabled,label,relative,is_mesh in [(mesh or wire,'Mesh','dense/mesh_display.ply',True),(dense,'Dense Cloud','dense/fused.ply',False),(sparse or evidence=='Evidence View','Sparse Cloud','sparse.ply',False)]:
        if not enabled or isolate not in ('All enabled',label):continue
        path=run/relative
        if label == 'Dense Cloud':path=dense_path
        if is_mesh and not has_mesh:continue
        if is_mesh and not path.exists():path=mesh_path
        if not path.exists():
            with left:st.info(label+' is not available for this reconstruction.')
            continue
        if is_mesh and mesh_error:
            continue
        try:
            xyz,colors,triangles=geometry(str(path),path.stat().st_mtime_ns,is_mesh)
        except Exception as exc:
            with left:st.warning(f'{label} geometry could not be loaded: {type(exc).__name__}: {exc}')
            continue
        if not len(xyz):continue
        if label=='Sparse Cloud' and points:
            ids=list(points);xyz=np.array([points[i]['xyz'] for i in ids]);colors=np.empty((0,3))
        else:ids=None
        display_xyz = xyz - model_origin
        print(f'PLOTLY_COORDS={label}: x_range=({float(display_xyz[:,0].min())},{float(display_xyz[:,0].max())}), y_range=({float(display_xyz[:,1].min())},{float(display_xyz[:,1].max())}), z_range=({float(display_xyz[:,2].min())},{float(display_xyz[:,2].max())})')
        all_xyz.append(display_xyz)
        if is_mesh:
            if mesh:
                fig.add_trace(go.Mesh3d(x=display_xyz[:,0].tolist(),y=display_xyz[:,1].tolist(),z=display_xyz[:,2].tolist(),
                    i=triangles[:,0].tolist(),j=triangles[:,1].tolist(),k=triangles[:,2].tolist(),
                    vertexcolor=(np.clip(colors,0,1)*255).astype(int).tolist() if len(colors) and evidence=='Normal model' else None,
                    color='#dca55e',name=label,flatshading=False,lighting=dict(ambient=.65,diffuse=.85,specular=.12,roughness=.85),
                    hovertemplate='Interpolated surface · click for nearby sparse evidence<extra></extra>'))
            counts.append(f'{len(triangles):,} triangles')
            if wire:
                edges=np.unique(np.sort(np.concatenate([triangles[:,[0,1]],triangles[:,[1,2]],triangles[:,[2,0]]]),axis=1),axis=0)
                edge_points=display_xyz[edges[::max(1,len(edges)//25000)]]
                lines=np.full((len(edge_points),3,3),np.nan);lines[:,:2]=edge_points;lines=lines.reshape(-1,3)
                fig.add_trace(go.Scatter3d(x=lines[:,0],y=lines[:,1],z=lines[:,2],mode='lines',line=dict(color='#70dacf',width=1),name='Wireframe',hoverinfo='skip'))
        else:
            ix=np.linspace(0,len(display_xyz)-1,min(budget,len(display_xyz)),dtype=int)
            rgb=['rgb(%d,%d,%d)'%tuple(c) for c in (np.clip(colors[ix],0,1)*255).astype(int)] if len(colors) and evidence=='Normal model' else ('#5ed5dd' if ids else '#dca55e')
            fig.add_trace(go.Scatter3d(x=display_xyz[ix,0].tolist(),y=display_xyz[ix,1].tolist(),z=display_xyz[ix,2].tolist(),mode='markers',
                customdata=[ids[i] for i in ix] if ids else None,marker=dict(size=1.7,color=rgb),name=label,
                hovertemplate='Click to inspect supporting evidence<extra>'+label+'</extra>'))
            counts.append(f'{len(ix):,} / {len(display_xyz):,} {label.lower()} points')
    visible_cameras=cameras.copy()
    if supported and selected in points:
        visible_cameras=cameras[cameras.image_id.isin([o['image_id'] for o in points[selected]['track']])]
    camera_xyz=visible_cameras[['x','y','z']].to_numpy(dtype=float)-model_origin if not visible_cameras.empty else np.empty((0,3))
    if isolate in ('All enabled','Cameras') and (show_cameras or trajectory):
        if show_cameras:fig.add_trace(go.Scatter3d(x=camera_xyz[:,0].tolist(),y=camera_xyz[:,1].tolist(),z=camera_xyz[:,2].tolist(),mode='markers',marker=dict(size=4,color='#eab46f'),text=visible_cameras.filename.tolist(),name='Cameras',hovertemplate='%{text}<extra>Estimated camera</extra>'))
        if trajectory:fig.add_trace(go.Scatter3d(x=camera_xyz[:,0].tolist(),y=camera_xyz[:,1].tolist(),z=camera_xyz[:,2].tolist(),mode='lines',line=dict(width=3,color='#eab46f'),name='Camera Trajectory',hoverinfo='skip'))
    if selected in points:
        p=np.asarray(points[selected]['xyz'])-model_origin;fig.add_trace(go.Scatter3d(x=[p[0]],y=[p[1]],z=[p[2]],mode='markers',marker=dict(size=7,color='#ffffff'),name='Selected point',customdata=[selected]))
    if mesh_bounds is not None:
        bounds = (mesh_bounds[0]-model_origin, mesh_bounds[1]-model_origin)
    elif all_xyz:
        ref_xyz = np.concatenate(all_xyz)
        bounds = (ref_xyz.min(0), ref_xyz.max(0))
    elif not cameras.empty:
        bounds = (camera_xyz.min(0), camera_xyz.max(0))
    else:
        bounds = (np.array([-1.0, -1.0, -1.0]), np.array([1.0, 1.0, 1.0]))
    camera_mode = st.session_state.get('world_camera_mode', 'initial')
    if camera_mode == 'fit':
        camera = _scene_camera_from_bounds(bounds, mode='fit')
    elif camera_mode == 'reset':
        st.session_state['world_camera_mode'] = 'initial'
        camera = _scene_camera_from_bounds(bounds, mode='initial')
    else:
        camera = _scene_camera_from_bounds(bounds, mode='initial')
    if show_cameras or trajectory:all_xyz.append(camera_xyz)
    if all_xyz:
        reference=np.concatenate(all_xyz)
    elif not cameras.empty:
        reference=cameras[['x','y','z']].to_numpy()
    else:
        reference=np.array([[-1.0, -1.0, -1.0], [1.0, 1.0, 1.0]])
    lo=reference.min(0);hi=reference.max(0);span=np.maximum(hi-lo,1e-4);pad=span*.12
    scene_camera=camera
    axes={k:dict(range=[float(lo[i]-pad[i]),float(hi[i]+pad[i])],visible=False,showbackground=False,showgrid=False,zeroline=False) for i,k in enumerate(('xaxis','yaxis','zaxis'))}
    fig.update_layout(height=780,paper_bgcolor='#0d171c',font=dict(color='#bfceca'),margin=dict(l=0,r=0,t=0,b=0),
        scene=dict(**axes,aspectmode='data',bgcolor='#0d171c',camera=scene_camera),
        legend=dict(orientation='h',y=.02,x=.02,bgcolor='rgba(16,24,32,.75)'),uirevision=f'{run}-oblique')
    with left:
        if fig.data:
            event=_world(figure=fig.to_json(),key='world_'+str(root),default=None)
        else:
            event=None
            st.info('No geometry is available in this mission yet. Run image analysis and reconstruction, or select a mission with saved PLY artifacts.')
        with st.expander('Display details'):st.caption(' · '.join(counts)+'. Original resolution is retained in exports. Trajectory follows filename order. The mesh remains the default subject; overlays are optional.')
    if event and event.get('nonce')!=st.session_state.get('world_event') and points and event.get('layer') not in ('Cameras','Camera Trajectory'):
        st.session_state['world_event']=event['nonce']
        pid=event.get('point_id');scope='Exact sparse-point observation track.'
        if pid not in points:
            from scipy.spatial import cKDTree
            ids=list(points);query_xyz=np.asarray(event['xyz'],dtype=float)+model_origin
            distance,index=cKDTree([points[i]['xyz'] for i in ids]).query(query_xyz)
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
