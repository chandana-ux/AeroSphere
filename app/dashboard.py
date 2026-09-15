"""Local AeroSphere demonstration using verified artifacts, not reconstruction reruns."""
import csv
import io
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from PIL import Image

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))
from geo import assess, gps_distance
from extras import render_extra

ROOT = APP.parent
st.set_page_config(page_title='AeroSphere | Spatial Intelligence', page_icon='🌐', layout='wide')
st.markdown('''<style>
.stApp {background:#0b111c;color:#e4edf6} [data-testid="stSidebar"] {background:#111d2d}
h1,h2,h3 {letter-spacing:-.025em} [data-testid="stMetric"] {background:#142235;border:1px solid #25415b;border-radius:12px;padding:16px}
.eyebrow {color:#56d6c3;font-size:12px;letter-spacing:3px;font-weight:700} .hero {padding:12px 0 24px} .hero h1 {font-size:46px;margin:0}
.hero p {color:#a7b8cb;font-size:18px} .status {color:#56d6c3;background:#122e32;padding:8px 14px;border-radius:20px;display:inline-block;font-size:13px}
.hero.compact {padding:0 0 10px} .hero.compact h1 {font-size:28px} .hero.compact p {font-size:14px;margin:4px 0} .hero.compact .status {display:none}
[data-testid="stMainBlockContainer"] {padding-top:2.5rem;padding-bottom:2rem}
</style>''', unsafe_allow_html=True)


@st.cache_data
def table(path, mtime):
    return pd.read_csv(path)


def read_table(path):
    return table(str(path), path.stat().st_mtime_ns)


@st.cache_data
def geometry(path, mtime, mesh=False):
    import open3d as o3d
    if mesh:
        obj = o3d.io.read_triangle_mesh(path)
        return np.asarray(obj.vertices), np.asarray(obj.vertex_colors), np.asarray(obj.triangles)
    obj = o3d.io.read_point_cloud(path)
    return np.asarray(obj.points), np.asarray(obj.colors), np.empty((0,3), dtype=int)


@st.cache_data
def thumbnail(path, mtime):
    with Image.open(path) as im:
        im.thumbnail((1200, 850))
        data = io.BytesIO()
        im.convert('RGB').save(data, format='JPEG', quality=88)
        return data.getvalue()


def chart_style(fig, height=500):
    fig.update_layout(template='plotly_dark', paper_bgcolor='#0b111c', plot_bgcolor='#0b111c',
                      margin=dict(l=20,r=20,t=35,b=20), height=height,
                      legend=dict(orientation='h', y=1.08))
    return fig


def main():
    code_root=APP.parent
    choices={'Aukerman demo':code_root}
    for p in sorted((code_root/'results/jobs').glob('*/output/reconstruction/latest.json')):
        choices['Job '+p.parents[2].name]=p.parents[2]
    dataset=st.sidebar.selectbox('Dataset',list(choices))
    ROOT=choices[dataset]
    try:
        summary = json.loads((ROOT/'output/reconstruction/latest.json').read_text())
        selection = json.loads((ROOT/'results/image_intelligence/latest.json').read_text())
        run = Path(summary['run_directory'])
        metadata = read_table(ROOT/'metadata/image_metadata.csv')
        details=ROOT/'metadata/image_metadata_details.csv'
        if details.exists():metadata=metadata.merge(read_table(details),on='filename',how='left',validate='one_to_one')
        quality = read_table(Path(selection['report_directory'])/'image_quality.csv')
        cameras = read_table(run/'camera_trajectory.csv')
        geo, positions = assess(metadata, cameras)
    except (OSError, ValueError, KeyError) as exc:
        st.error(f'Required artifact could not be loaded: {exc}')
        st.stop()
    gps = metadata.dropna(subset=['latitude','longitude'])
    st.sidebar.markdown('## AEROSPHERE')
    st.sidebar.caption('LOCAL MISSION WORKSPACE')
    page = st.sidebar.radio('Workspace', ['Overview','Imagery','Geospatial','3D Explorer','Quality & Coverage','Measurements','Semantic AI','Process New Input','Exports & Trust'], label_visibility='collapsed')
    st.sidebar.divider()
    st.sidebar.markdown('**'+('Aukerman · aerial image dataset' if dataset=='Aukerman demo' else dataset)+'**')
    st.sidebar.caption('Real reconstruction · existing artifacts\n\nNo reconstruction rerun on launch.')
    st.sidebar.info(('GPS context is available.' if len(gps) else 'GPS/telemetry unavailable.')+' Absolute height and validated metric 3D accuracy are not established.')
    hero_class='hero' if page=='Overview' else 'hero compact'
    st.markdown(f'<div class="{hero_class}"><div class="eyebrow">AERIAL RECONSTRUCTION / LOCAL MVP</div><h1>AeroSphere</h1><p>From One Flight to a Trusted 3D World.</p><span class="status">REAL DATA · RECONSTRUCTION READY</span></div>', unsafe_allow_html=True)
    if page in ('Quality & Coverage','Semantic AI','Process New Input'):
        render_extra(page,ROOT,code_root,metadata,selection,summary)
    elif page == 'Overview':
        columns = st.columns(5)
        for col, label, value in zip(columns, ['Input images','Selected images','Registered cameras','Dense points','Reprojection error'],
                                    [len(metadata),selection['selected_images'],f"{summary['registered_images']} / {len(metadata)}",f"{summary['dense_points']:,}" if 'dense_points' in summary else 'Unavailable',f"{summary['mean_point_reprojection_error_pixels']:.3f} px"]):
            col.metric(label,value)
        st.write('')
        left,right = st.columns([2,1])
        with left:
            st.subheader('Reconstructed site')
            preview = run/'dense_view.png'
            if preview.exists():
                st.image(str(preview), caption='Actual dense point cloud. Open 3D Explorer to rotate and inspect it.', width='stretch')
            else:
                st.info('Open 3D Explorer for the real geometry.')
        with right:
            st.subheader('Evidence at a glance')
            st.metric('GPS availability', f'{len(gps)} / {len(metadata)}')
            st.metric('Sparse points', f"{summary['sparse_points']:,}")
            st.metric('Mesh triangles', f"{summary.get('mesh_triangles',0):,}")
            st.caption('Registration counts are not a surface-completeness percentage. Pixel reprojection error does not establish metre accuracy.')
        st.info('Current prototype: aerial image reconstruction. Target SIH input: single-pass drone video + GPS/flight metadata. Video ingestion is available separately; its reconstruction quality is not established by the Aukerman dataset.')
        st.caption('AI-Powered Single-Pass Aerial 3D Reconstruction & Spatial Intelligence')
        st.write(f"Input summary: {len(metadata)} images; resolutions: " + ', '.join(f'{int(w)} × {int(h)}' for w,h in metadata[['width','height']].dropna().drop_duplicates().itertuples(index=False,name=None)))
        vm=ROOT/'video_ingestion/video_metadata.json'
        if vm.exists():
            with st.expander('Source video metadata'):st.json(json.loads(vm.read_text()))
        else:st.caption('Input type: aerial photographs. Video duration/FPS: not applicable.')
        semantic_available=bool(list((ROOT/'results/semantics').glob('*.json')))
        st.dataframe(pd.DataFrame({'Stage':['Input','Frame intelligence','SfM','Dense reconstruction','Mesh','Geospatial','Trust / coverage','Semantic AI'],
            'Status':['COMPLETED','COMPLETED','COMPLETED',summary.get('dense_status','unavailable').upper(),summary.get('mesh_status','unavailable').upper(),'WARNING: approximate context','READY' if (ROOT/'results/coverage/coverage_report.json').exists() else 'UNAVAILABLE','AVAILABLE' if semantic_available else 'OPTIONAL / UNAVAILABLE']}),hide_index=True,width='stretch')
    elif page == 'Imagery':
        st.subheader('Visual evidence & selection')
        collection = st.radio('Image collection',['Input images','Selected images'],horizontal=True,key='collection')
        names = sorted(metadata.filename.tolist() if collection=='Input images' else quality.loc[quality.selected.astype(str).str.lower()=='true','filename'].tolist())
        name = st.selectbox('Image',names)
        folder = Path(selection['source'] if collection=='Input images' else selection['selected_directory'])
        image_path = folder/name
        a,b = st.columns([2,1])
        a.image(thumbnail(str(image_path),image_path.stat().st_mtime_ns),caption=name,width='stretch')
        with b:
            st.dataframe(metadata[metadata.filename==name].T.rename(columns={metadata.index[metadata.filename==name][0]:'Value'}).astype(str).replace('nan','Not available'),width='stretch')
        st.caption(f"{selection['selected_images']} of {selection['input_images']} images retained by conservative filtering; there is no target removal percentage.")
        st.dataframe(quality[['filename','blur_laplacian_variance','brightness_mean','contrast_std','orb_keypoints','information_score','selected','reason']],width='stretch',hide_index=True)
        st.caption('Sharpness and information scores are heuristic image metrics, not reconstruction confidence.')
    elif page == 'Geospatial':
        st.subheader('GPS positions & provisional alignment')
        st.caption('Offline geographic plots: no basemap service or internet connection required. WGS84 is assumed for the EXIF coordinates.')
        if len(gps):
            st.write(f'Geographic center: {gps.latitude.mean():.6f}°, {gps.longitude.mean():.6f}°. Bounding box: latitude {gps.latitude.min():.6f}–{gps.latitude.max():.6f}°, longitude {gps.longitude.min():.6f}–{gps.longitude.max():.6f}°.')
        else:st.warning('GPS/telemetry unavailable')
        st.caption('Approximate geospatial context — metric accuracy requires validated scale/georeferencing or RTK/PPK/GCP support.')
        fig = go.Figure(go.Scatter(x=gps.longitude,y=gps.latitude,mode='markers+lines',text=gps.filename,
                     marker=dict(color='#56d6c3',size=7),line=dict(width=1),name='EXIF GPS (filename order)',hovertemplate='%{text}<br>Lon %{x:.6f}<br>Lat %{y:.6f}<extra></extra>'))
        fig.update_xaxes(title='Longitude (degrees)'); fig.update_yaxes(title='Latitude (degrees)')
        st.plotly_chart(chart_style(fig,420),width='stretch')
        if geo['status']=='provisional_horizontal_fit':
            c = st.columns(3)
            c[0].metric('Provisional scale',f"{geo['scale_metres_per_unit']:.3f} m/unit")
            c[1].metric('Camera fit RMSE',f"{geo['camera_fit_rmse_m']:.3f} m")
            c[2].metric('Held-out camera RMSE',f"{geo['heldout_camera_rmse_m']:.3f} m")
            st.warning('These errors are agreement with the supplied GPS, not independently validated geographic accuracy. This is a 2D camera-plane fit, not a full 3D georeference.')
            fig = go.Figure()
            for prefix,label,color in [('', 'EXIF GPS','#56d6c3'),('fit_','Fitted visual cameras','#ffa657')]:
                fig.add_trace(go.Scatter(x=positions[prefix+'easting_m'],y=positions[prefix+'northing_m'],mode='markers',text=positions.filename,name=label,marker=dict(color=color,size=7)))
            fig.update_xaxes(title=f"Easting (m), EPSG:{geo['epsg']}"); fig.update_yaxes(title='Northing (m)',scaleanchor='x',scaleratio=1)
            st.plotly_chart(chart_style(fig),width='stretch')
            st.dataframe(positions[['filename','latitude','longitude','fit_residual_m','heldout_residual_m']],hide_index=True,width='stretch')
        else:
            st.warning(f"Horizontal fit unavailable: {geo['reason']}")
        st.error('Absolute altitude and metre-scaled 3D model measurements are not established. Raw altitude values are not used as a validated vertical reference.')
        with st.expander('Alignment method and limitations'):
            st.write('PCA camera-plane projection + least-squares 2D similarity fit. Five interleaved held-out folds test camera-position consistency. No GPS-altitude values are used.')
            st.json(geo)
    elif page == '3D Explorer':
        st.subheader('Interactive reconstruction')
        mode = st.radio('Representation',['Dense point cloud','Sparse point cloud','Mesh'],index=0 if (run/'dense/fused.ply').exists() else 1,horizontal=True,key='representation')
        paths = {'Dense point cloud':'dense/fused.ply','Sparse point cloud':'sparse.ply','Mesh':'dense/mesh.ply'}
        path = run/paths[mode]
        if not path.exists():
            st.error(f'{mode} artifact is unavailable.'); st.stop()
        xyz, colors, triangles = geometry(str(path),path.stat().st_mtime_ns,mode=='Mesh')
        fig = go.Figure()
        if mode=='Mesh':
            fig.add_trace(go.Mesh3d(x=xyz[:,0],y=xyz[:,1],z=xyz[:,2],i=triangles[:,0],j=triangles[:,1],k=triangles[:,2],
                vertexcolor=(np.clip(colors,0,1)*255).astype(np.uint8) if len(colors) else None,color='#4fc1ad',name='Inferred mesh',hoverinfo='skip'))
            st.caption(f'Actual mesh: {len(xyz):,} vertices / {len(triangles):,} triangles. Surfaces are interpolated and may bridge unobserved gaps.')
        else:
            count = st.select_slider('Display point budget',options=[10000,30000,60000],value=30000)
            idx = np.linspace(0,len(xyz)-1,min(count,len(xyz)),dtype=int)
            rgb = [f'rgb({r},{g},{b})' for r,g,b in (np.clip(colors[idx],0,1)*255).astype(np.uint8)] if len(colors) else '#56d6c3'
            fig.add_trace(go.Scatter3d(x=xyz[idx,0],y=xyz[idx,1],z=xyz[idx,2],mode='markers',marker=dict(size=1.5,color=rgb),name=mode,hoverinfo='skip'))
            st.caption(f'Displaying {len(idx):,} of {len(xyz):,} real points for browser performance. Exports retain full resolution.')
        if st.checkbox('Show camera trajectory',value=True):
            fig.add_trace(go.Scatter3d(x=cameras.x,y=cameras.y,z=cameras.z,mode='lines+markers',text=cameras.filename,
                marker=dict(size=3,color='#ffa657'),line=dict(width=3,color='#ffa657'),name='Camera centers',hovertemplate='%{text}<extra></extra>'))
        fig.update_layout(scene=dict(aspectmode='data',xaxis_title='X (arbitrary units)',yaxis_title='Y (arbitrary units)',zaxis_title='Z (arbitrary units)'),uirevision='keep-camera')
        st.plotly_chart(chart_style(fig,550),width='stretch',config={'displaylogo':False})
        st.caption('Drag to rotate; scroll to zoom. Axes are COLMAP coordinates, not geographic north/up. Camera lines follow filename order.')
    elif page == 'Measurements':
        st.subheader('Measurements with explicit units')
        kind = st.radio('Measurement source',['GPS camera positions','Reconstruction points'],horizontal=True,key='measurement_source')
        if kind=='GPS camera positions':
            if len(gps)<2:
                st.info('At least two valid GPS camera positions are required.'); st.stop()
            valid = gps.set_index('filename')
            names = valid.index.tolist()
            c=st.columns(2)
            first=c[0].selectbox('GPS point A',names,index=0)
            second=c[1].selectbox('GPS point B',names,index=min(1,len(names)-1))
            distance=gps_distance(valid.loc[first],valid.loc[second])
            st.metric('Horizontal geodesic distance',f'{distance:.2f} m')
            st.warning('Distance between recorded camera GPS positions on the assumed WGS84 ellipsoid. Not a building/ground-surface dimension; GPS accuracy is unknown. Altitude is excluded.')
            result=dict(source='EXIF GPS',point_a=first,point_b=second,horizontal_distance_m=distance,datum_assumption='WGS84',accuracy='unvalidated')
        else:
            path=run/'sparse.ply'; xyz,_,_=geometry(str(path),path.stat().st_mtime_ns)
            c=st.columns(2)
            a=int(c[0].number_input('Sparse point row A (zero-based)',min_value=0,max_value=len(xyz)-1,value=0,step=1))
            b=int(c[1].number_input('Sparse point row B (zero-based)',min_value=0,max_value=len(xyz)-1,value=1,step=1))
            distance=float(np.linalg.norm(xyz[a]-xyz[b]))
            st.metric('3D point-to-point distance',f'{distance:.5f} reconstruction units')
            st.dataframe(pd.DataFrame([xyz[a],xyz[b]],columns=['X','Y','Z'],index=['A','B']))
            fig=go.Figure(go.Scatter3d(x=xyz[[a,b],0],y=xyz[[a,b],1],z=xyz[[a,b],2],mode='lines+markers+text',text=['A','B'],marker=dict(size=7)))
            fig.update_layout(scene=dict(aspectmode='data',xaxis_title='X (units)',yaxis_title='Y (units)',zaxis_title='Z (units)'))
            st.plotly_chart(chart_style(fig,350),width='stretch')
            st.info('Metres, height, area and volume are disabled for the model. A provisional horizontal camera fit is insufficient to validate arbitrary 3D surface measurements.')
            result=dict(source='sparse.ply row indices',point_a=a,point_b=b,distance_reconstruction_units=distance,metric_scale='not_applied')
        st.download_button('Export this measurement',json.dumps(result,indent=2),file_name='aerosphere_measurement.json',mime='application/json')
    else:
        st.subheader('Exports & evidence status')
        st.dataframe(pd.DataFrame([
            ['OBSERVED','Captured images and recorded metadata','Source evidence; GPS values are unvalidated measurements'],
            ['INFERRED','Camera poses, sparse/dense points and mesh','Estimated from imagery; mesh may interpolate gaps'],
            ['UNKNOWN','Hidden surfaces, absolute vertical datum, true metric accuracy','Not measured or certified by this demo']],columns=['Status','Applies to','Meaning']),hide_index=True,width='stretch')
        st.caption('These are provenance categories, not calibrated per-point confidence classes. No unknown-surface coverage percentage is invented.')
        exports=[('Sparse cloud',run/'sparse.ply'),('Dense cloud',run/'dense/fused.ply'),('Mesh',run/'dense/mesh.ply'),
                 ('Image metadata',ROOT/'metadata/image_metadata.csv'),('Camera trajectory',run/'camera_trajectory.csv'),
                 ('Reconstruction statistics',run/'summary.json'),('Image quality',Path(selection['report_directory'])/'image_quality.csv')]
        for label,path in exports:
            if path.exists():
                st.download_button(f'Download {label}',path.read_bytes(),file_name=path.name,key=label)
        st.download_button('Download horizontal alignment assessment',json.dumps(geo,indent=2),file_name='alignment_report.json',mime='application/json')
        st.download_button('Download GPS alignment table',positions.to_csv(index=False),file_name='camera_gps_alignment.csv',mime='text/csv')
        with st.expander('Actual reconstruction statistics'):
            st.json(summary)
        for label,path in [('Consolidated summary',ROOT/'results/aerosphere_summary.json'),('Human-readable report',ROOT/'results/aerosphere_report.md'),('Coverage report',ROOT/'results/coverage/coverage_report.json')]:
            if path.exists():st.download_button('Download '+label,path.read_bytes(),file_name=path.name,key=label)
        manifest=Path(selection['report_directory'])/'selection_manifest.json'
        if manifest.exists():st.download_button('Download selected-frame manifest',manifest.read_bytes(),file_name=manifest.name)
        selected_names=sorted(quality.loc[quality.selected.astype(str).str.lower()=='true','filename'].tolist())
        if selected_names:
            frame_name=st.selectbox('Selected frame to export',selected_names)
            st.download_button('Download selected frame',(Path(selection['selected_directory'])/frame_name).read_bytes(),file_name=Path(frame_name).name)
        st.warning('Not demonstrated: validated continuous-drone-video reconstruction, validated 3D metric measurements, or full georeferencing. Semantic predictions, when available, are unvalidated generic model outputs. The interrupted dense-run timing is not a performance benchmark.')


main()
