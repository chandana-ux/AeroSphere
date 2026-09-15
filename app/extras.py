"""Coverage, optional semantic AI and isolated input processing dashboard pages."""
import json
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def render_extra(page,project,code_root,metadata,selection,summary):
    if page=='Quality & Coverage':
        st.subheader('Trust & approximate coverage')
        path=project/'results/coverage/coverage_report.json'
        if not path.exists():st.info('Coverage report unavailable. Run the demo report command.');return
        coverage=json.loads(path.read_text())
        cols=st.columns(4)
        cols[0].metric('Registration ratio',f"{coverage['registration_ratio']:.1%}")
        cols[1].metric('Verified image pairs',coverage['verified_pairs'])
        cols[2].metric('Connected components',len(coverage['verified_graph_components']))
        cols[3].metric('Median supporting views',coverage['track_observation_median'])
        st.caption('Registration ratio is images registered / input images. It is not an accuracy or surface-completeness percentage.')
        grid=np.load(project/'results/coverage/coverage_grid.npz')
        fig=go.Figure(go.Heatmap(x=grid['x'],y=grid['y'],z=grid['state'].T,zmin=0,zmax=2,
           colorscale=[[0,'#283546'],[0.2499,'#283546'],[0.25,'#dd9d49'],[0.7499,'#dd9d49'],[0.75,'#45bba7'],[1,'#45bba7']],
           colorbar=dict(tickvals=[0,1,2],ticktext=['Insufficient','Sparse','Stronger']),
           customdata=np.stack([grid['count'].T,grid['mean_track'].T],axis=-1),
           hovertemplate='Points: %{customdata[0]}<br>Mean supporting views: %{customdata[1]:.1f}<extra></extra>'))
        fig.update_layout(template='plotly_dark',height=470,title='Approximate coverage · triangulated evidence distribution',
            xaxis_title='PCA plane X (model units)',yaxis_title='PCA plane Y (model units)',yaxis=dict(scaleanchor='x',scaleratio=1))
        st.plotly_chart(fig,width='stretch')
        st.warning(coverage['limitations'])
        st.caption(coverage['grid_rules'])
        st.subheader('Viewpoint changes from reconstructed camera poses')
        changes=pd.read_csv(project/'results/coverage/viewpoint_change.csv')
        st.line_chart(changes.set_index('filename')[['rotation_from_previous_degrees']])
        st.dataframe(changes,hide_index=True,width='stretch')
        st.caption('Actual estimated camera rotation/translation between adjacent filenames, computed after SfM. These values were not retroactively included in the original pre-reconstruction image score.')
        with st.expander('Machine-readable evidence report'):st.json(coverage)
    elif page=='Semantic AI':
        st.subheader('Optional pretrained object detection')
        st.caption('SSDLite320 MobileNetV3 · CPU · generic COCO classes. Predictions are not verified facts or calibrated confidence.')
        reports=sorted((project/'results/semantics').glob('*.json'))
        st.info('Semantic AI: available' if reports else 'Semantic AI: optional/unavailable — no saved predictions yet')
        name=st.selectbox('Image for detection',metadata.filename.tolist())
        saved=project/'results/semantics'/(Path(name).stem+'.json')
        if st.button('Run cached pretrained model on this image'):
            sys.path.insert(0,str(code_root/'scripts'))
            from semantic import detect
            with st.spinner('Running CPU detector…'):result=detect(Path(selection['source'])/name,project)
            if result['status']!='available':st.warning(result['reason'])
        if saved.exists():
            result=json.loads(saved.read_text())
            st.image(result['annotated_image'],width='stretch')
            st.write(f"{len(result['detections'])} predictions above threshold {result['threshold']}.")
            st.dataframe(pd.DataFrame(result['detections']),hide_index=True,width='stretch')
            st.warning(result['limitations'])
            st.download_button('Export predictions',saved.read_bytes(),file_name=saved.name)
        else:st.caption('No detections are fabricated when a model or prediction is unavailable. Initial weight download is optional and separate from offline demo launch.')
    elif page=='Process New Input':
        st.subheader('Process new input in a separate job')
        st.info('The Aukerman demo remains unchanged. Choose a local video or image-directory path; video is decoded sequentially instead of uploaded into browser memory.')
        with st.form('new_input'):
            source=st.text_input('Local video or image-directory path')
            interval=st.number_input('Video sample interval (seconds)',min_value=0.1,max_value=60.0,value=2.0)
            cap=st.number_input('Maximum extracted frames',min_value=2,max_value=1000,value=100)
            reconstruct=st.checkbox('Run COLMAP after selection (may take several minutes)',value=False)
            dense=st.checkbox('Also attempt dense reconstruction and mesh',value=False)
            submit=st.form_submit_button('Process new input')
        if submit:
            raw=Path(source.strip().strip('"'))
            if not source.strip() or not raw.exists():st.error('Input path does not exist.')
            else:
                job=code_root/'results/jobs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
                job.mkdir(parents=True)
                cmd=[sys.executable,str(code_root/'scripts/pipeline.py'),'--input',str(raw.resolve()),'--job',str(job),'--interval',str(interval),'--max-frames',str(cap)]
                if reconstruct:cmd.append('--reconstruct')
                if dense and reconstruct:cmd.append('--dense')
                with (job/'worker.log').open('w') as log:
                    subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,cwd=code_root,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                st.success(f'Job started: {job.name}')
        st.button('Refresh job status')
        for job in sorted((code_root/'results/jobs').glob('*'),reverse=True)[:8]:
            with st.expander('Job '+job.name):
                state_path=job/'job.json'
                if state_path.exists():
                    try:st.json(json.loads(state_path.read_text()))
                    except json.JSONDecodeError:st.info('Status update in progress; refresh.')
                else:st.info('Worker starting; refresh.')
                latest=job/'results/image_intelligence/latest.json'
                if latest.exists():
                    st.json(json.loads(latest.read_text()))
                vm=job/'video_ingestion/video_metadata.json'
                if vm.exists():st.json(json.loads(vm.read_text()))
                log=job/'pipeline.log'
                if log.exists():st.code(log.read_text(errors='replace')[-5000:],language='text')
                if (job/'output/reconstruction/latest.json').exists():st.success('Reconstruction available. Reload the page and select this job in the Dataset control.')
