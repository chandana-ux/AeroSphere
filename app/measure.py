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
    _,points=model_tracks(summary);ids=list(points)
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
