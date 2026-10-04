"""Model-space geometry measurements with explicit validity restrictions."""
from pathlib import Path
import json
import numpy as np

def triangle_area(a,b,c):
    return float(np.linalg.norm(np.cross(np.asarray(b)-a,np.asarray(c)-a))/2)

def render_model_measure(summary):
    import streamlit as st
    import open3d as o3d
    from world import model_tracks
    st.subheader('Model-space surface measurements')
    st.caption('Native arbitrary units. Geographic vertical and metric scale are not established; physical building height is unavailable.')
    try:
        _,points=model_tracks(summary)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        st.info(f'Sparse-point measurements are unavailable: {exc}')
        return
    ids=list(points)
    if not ids:
        st.info('Sparse-point measurements are unavailable until the mission has triangulated points.')
        return
    cols=st.columns(3)
    chosen=[c.selectbox('Point '+label,ids,index=min(i,len(ids)-1),key='measure_'+label) for i,(c,label) in enumerate(zip(cols,['A','B','C']))]
    a,b,c=[np.array(points[i]['xyz']) for i in chosen]
    distance=float(np.linalg.norm(a-b));area=triangle_area(a,b,c)
    x,y=st.columns(2);x.metric('Distance A–B',f'{distance:.5f} units');y.metric('Triangle A–B–C',f'{area:.5f} units²')
    st.caption('Straight segment and planar triangle through selected sparse points, not a traced surface or cadastral area.')
    import plotly.graph_objects as go
    from ui import offline_chart
    xyz=np.array([a,b,c,a]);fig=go.Figure(go.Scatter3d(x=xyz[:,0],y=xyz[:,1],z=xyz[:,2],mode='lines+markers+text',text=['A','B','C',''],marker=dict(size=6,color='#58bdd1')))
    fig.update_layout(height=350,template='plotly_dark',scene=dict(aspectmode='data'))
    offline_chart(fig,width='stretch')
    result={'point_ids':chosen,'distance_AB_model_units':distance,'triangle_area_model_units_squared':area,'metric_accuracy':'unvalidated','height':'unavailable: geographic vertical not established'}
    path=Path(summary['run_directory'])/'dense/mesh.ply'
    if path.exists():
        mesh=o3d.io.read_triangle_mesh(str(path))
        result['whole_mesh_area_model_units_squared']=float(mesh.get_surface_area())
        st.metric('Whole reconstructed mesh area',f"{result['whole_mesh_area_model_units_squared']:.4f} units²")
        if mesh.is_watertight() and mesh.is_orientable():
            try:
                result['enclosed_mesh_volume_model_units_cubed']=float(mesh.get_volume())
                st.metric('Enclosed mesh volume',f"{result['enclosed_mesh_volume_model_units_cubed']:.4f} units³")
                st.caption('Computed enclosed mesh volume; interpolated surfaces are not a verified physical object boundary.')
            except RuntimeError:st.info('Mesh volume is unavailable: orientation could not be validated.')
        else:st.info('Volume unavailable: the reconstructed mesh is not a closed, orientable surface.')
    st.download_button('Export model-space measurements',json.dumps(result,indent=2),file_name='model_measurements.json')

def render_mesh_measure(mesh_path):
    import json
    import streamlit as st
    from world import geometry

    mesh_path=Path(mesh_path)
    try:
        vertices,_,triangles=geometry(str(mesh_path),mesh_path.stat().st_mtime_ns,mesh=True)
    except (OSError,RuntimeError,ValueError) as exc:
        st.warning(f'Mesh measurements are unavailable: {exc}')
        return
    if len(vertices)<2:
        st.info('At least two mesh vertices are required for measurements.')
        return

    st.subheader('Mesh measurements · native relative units')
    st.caption('Selections use real PLY vertex coordinates. They are model units, not metres or surveyed surface dimensions.')
    columns=st.columns(3)
    ids=[
        int(columns[0].number_input('Vertex A index',0,len(vertices)-1,0,key='mesh_measure_a')),
        int(columns[1].number_input('Vertex B index',0,len(vertices)-1,min(1,len(vertices)-1),key='mesh_measure_b')),
        int(columns[2].number_input('Vertex C index',0,len(vertices)-1,min(2,len(vertices)-1),key='mesh_measure_c')),
    ]
    points=vertices[ids]
    distance=float(np.linalg.norm(points[0]-points[1]))
    area=triangle_area(*points)
    surface_area=None
    if len(triangles):
        faces=vertices[triangles]
        surface_area=float(np.linalg.norm(np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0]),axis=1).sum()/2)
    metrics=st.columns(3)
    metrics[0].metric('A–B distance',f'{distance:.5f} units')
    metrics[1].metric('A–B–C triangle area',f'{area:.5f} units²')
    metrics[2].metric('Whole mesh surface area',f'{surface_area:.5f} units²' if surface_area is not None else 'Unavailable')
    st.dataframe([{'Vertex':label,'Index':index,'X':float(point[0]),'Y':float(point[1]),'Z':float(point[2])}
                  for label,index,point in zip('ABC',ids,points)],hide_index=True,width='stretch')
    st.caption('The triangle area is computed from the three selected vertices and may not correspond to one mesh face. Total area sums the PLY triangle faces; it does not establish physical or cadastral area.')
    result={'mesh_file':mesh_path.name,'vertex_ids':ids,'vertices_xyz':points.tolist(),
            'distance_AB_model_units':distance,'triangle_ABC_area_model_units_squared':area,
            'whole_mesh_surface_area_model_units_squared':surface_area,
            'metric_accuracy':'unvalidated'}
    st.download_button('Export mesh measurements',json.dumps(result,indent=2),file_name='mesh_measurements.json')
