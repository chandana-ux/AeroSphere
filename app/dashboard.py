"""AeroSphere Demo V1: one local mission workflow, backed by real artifacts."""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import streamlit as st

APP=Path(__file__).resolve().parent
sys.path.insert(0,str(APP))
from mission import MODES,catalog,profile,read_json,save_profile,package_mission
from geo import assess
from legacy import render_legacy
from extras import render_extra
from lineage import render_lineage
from world import render_world
from temporal import render_temporal

ROOT=Path(os.environ.get('AEROSPHERE_DATA_ROOT',APP.parent))
CODE=APP.parent
PAGES=['HOME','MISSION','FLIGHT','3D WORLD','EVIDENCE','TEMPORAL','INSIGHTS','EXPORT']
st.set_page_config(page_title='AeroSphere | Demo V1',page_icon='◈',layout='wide',initial_sidebar_state='expanded',menu_items={'Get Help':None,'Report a bug':None,'About':'AeroSphere Demo V1 · local aerial reconstruction'})
st.markdown('''<style>
.stApp{background:#0d141c;color:#e1e9ef}[data-testid="stHeader"]{background:#0d141c}[data-testid="stToolbar"]{display:none}
[data-testid="stSidebar"]{background:#111c27;border-right:1px solid #263441}
[data-testid="stMainBlockContainer"]{padding:2rem 2.5rem 3rem;max-width:1900px}
h1,h2,h3{font-weight:600!important;letter-spacing:-.035em}h1{font-size:2.6rem!important}
[data-testid="stMetric"]{padding:14px 16px;border-top:1px solid #355063;background:#121e29;border-radius:4px}
[data-testid="stMetricLabel"]{color:#9bafbd}[data-testid="stMetricValue"]{font-size:1.65rem}
.eyebrow{font:600 11px Segoe UI,sans-serif;letter-spacing:3px;color:#6fbdd0;margin-bottom:12px}
.hero{padding:20px 0 16px}.hero h1{font-size:3.2rem!important;max-width:780px;line-height:1.1}
.hero p{color:#9dafbe;font-size:18px;max-width:640px}.badge{color:#70c9cf;font-size:12px;letter-spacing:1px}
.stButton>button{border-radius:5px;border-color:#344957}.stButton>button[kind="primary"]{background:#247f98;border:0}
[data-testid="stCaptionContainer"]{color:#91a8b8}div[data-testid="stAlert"]{border-radius:5px}
</style>''',unsafe_allow_html=True)

def go(page):st.session_state['nav']=page

def data(root):
    summary=read_json(root/'output/reconstruction/latest.json');selection=read_json(root/'results/image_intelligence/latest.json')
    try:meta=pd.read_csv(root/'metadata/image_metadata.csv')
    except (OSError,ValueError):meta=pd.DataFrame(columns=['filename','latitude','longitude','altitude_raw_m'])
    for name in ('filename','latitude','longitude','altitude_raw_m'):
        if name not in meta:meta[name]=pd.NA
    return summary,selection,meta

def mission_library(items):
    st.subheader('Mission library')
    category=st.segmented_control('Category',['ALL','URBAN','INFRASTRUCTURE','DISASTER','HISTORICAL'],default='ALL')
    visible=[m for m in items if category in ('ALL',m['category'])]
    if not visible:st.info('No missions in this category. Add real observations through Mission setup.')
    for item in visible:
        with st.container(border=True):
            a,b=st.columns([4,1]);summary,selection,meta=data(item['root'])
            a.markdown('**'+item['name']+'**');gps=meta.dropna(subset=['latitude','longitude'])
            location=f'{gps.latitude.mean():.5f}°, {gps.longitude.mean():.5f}°' if len(gps) else 'Location unavailable'
            alt=int(meta.get('altitude_raw_m',pd.Series(dtype=float)).notna().sum())
            a.caption(f"{item['capture']} · {item['images']} images · GPS {len(gps)} · raw altitude {alt} · {location} · {item['status']}")
            def open_mission(path=item['root']):
                st.session_state['active_root']=str(path);st.session_state['nav']='3D WORLD' if (path/'output/reconstruction/latest.json').exists() else 'FLIGHT'
            b.button('Open mission',key='open_'+str(item['root']),on_click=open_mission)

def setup(root,selection,meta):
    current=profile(root)
    st.subheader('Mission setup')
    a,b=st.columns([2,1])
    with a:
        name=st.text_input('Mission name',value=current['name'])
        mode=st.selectbox('Mission type',list(MODES),index=list(MODES).index(current.get('mode','RECONNAISSANCE')))
        st.caption(MODES[mode][0])
        if st.button('Save mission settings'):
            save_profile(root,name,mode);st.success('Mission settings saved locally.')
    with b:
        st.markdown('#### TELEMETRY')
        st.write('GPS · '+('Available' if meta[['latitude','longitude']].notna().all(axis=1).any() else 'Unavailable'))
        st.write('Raw altitude · '+('Available; datum unverified' if meta.get('altitude_raw_m',pd.Series(dtype=float)).notna().any() else 'Unavailable'))
        st.caption('IMU / RTK / PPK · not supplied')
    st.divider();st.markdown('#### INPUT')
    st.caption('Analysis creates a separate mission and preserves the current reconstruction.')
    with st.form('ingest'):
        source=st.text_input('Video file or image folder',placeholder='Local source path')
        with st.expander('Video sampling'):
            interval=st.number_input('Sample interval (seconds)',min_value=.1,max_value=60.,value=2.)
            cap=st.number_input('Maximum frames',min_value=3,max_value=1000,value=100)
        submit=st.form_submit_button('Analyze flight',type='primary')
    if submit:
        path=Path(source.strip().strip('"'))
        if not source.strip() or not path.exists():st.error('Select an existing image folder or video file.')
        else:
            job=ROOT/'results/jobs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
            job.mkdir(parents=True);save_profile(job,name,mode)
            command=[sys.executable,str(CODE/'scripts/pipeline.py'),'--input',str(path.resolve()),'--job',str(job),'--interval',str(interval),'--max-frames',str(cap)]
            with (job/'worker.log').open('w') as log:subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,cwd=CODE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            st.session_state['active_root']=str(job)
            st.success('Flight analysis started. Open FLIGHT to follow progress.')

def flight(root,summary,selection,meta):
    job=read_json(root/'job.json')
    if job:
        st.caption('PROCESSING STATUS · '+job.get('status','unknown').upper()+' · '+job.get('stage',''))
        if job.get('status')=='failed':st.error('Processing could not finish. Check input overlap, texture and file readability; diagnostics are available below.')
    st.button('Refresh status')
    if not selection:
        st.info('Analyze an image folder or video in Mission setup. This page will show retained frames and selection reasons.')
        st.button('Back to Mission',on_click=go,args=('MISSION',));return
    quality=pd.read_csv(Path(selection['report_directory'])/'image_quality.csv')
    cols=st.columns(4)
    for col,label,value in zip(cols,['Captured frames','Analyzed frames','Retained frames','Registered cameras'],[selection['input_images'],int((quality.status=='ok').sum()),selection['selected_images'],summary.get('registered_images','Not reconstructed')]):col.metric(label,value)
    st.caption('Captured → analyzed → retained → reconstruction. No target rejection percentage.')
    selected=st.selectbox('Source frame',quality.filename.tolist());row=quality[quality.filename==selected].iloc[0]
    a,b=st.columns([2,1])
    with a:
        source=Path(selection['source'])/selected
        if source.exists() and row.status=='ok':st.image(str(source),width='stretch')
        else:st.info('Image unreadable or unavailable; its rejection reason remains recorded.')
    with b:
        st.markdown('#### '+('RETAINED' if str(row.selected).lower()=='true' else 'REJECTED'));st.write(str(row.reason).replace('_',' '))
        fields=['blur_laplacian_variance','brightness_mean','contrast_std','dark_fraction','bright_fraction','orb_keypoints','information_score','warnings']
        st.dataframe(row.reindex(fields).rename('Value').astype(str).replace('nan','Unavailable'))
        st.caption('Information value is a relative heuristic, never a confidence percentage. Camera viewpoint changes are measured after reconstruction.')
    with st.expander('All selection decisions'):st.dataframe(quality,hide_index=True,width='stretch')
    state=read_json(root/'reconstruction_job.json')
    if summary:
        st.success('Reconstruction is cached and ready to inspect.');st.button('Open 3D World',type='primary',on_click=go,args=('3D WORLD',))
    elif state.get('status')=='running':st.info('Reconstruction is running locally. Refresh to update. Sparse geometry is saved before dense processing.')
    else:
        if state.get('status')=='failed':st.error('Reconstruction failed. Try additional overlapping, textured images. Diagnostics show the failing stage.')
        dense=st.checkbox('Build dense cloud and mesh',True);cpu=st.checkbox('CPU feature extraction and matching',False)
        st.caption('Dense stereo requires CUDA. CPU mode applies to feature extraction and matching only.')
        if st.button('Run reconstruction',type='primary',disabled=selection['selected_images']<3):
            command=[sys.executable,str(CODE/'scripts/reconstruct_job.py'),'--project',str(root)]
            if dense:command.append('--dense')
            if cpu:command.append('--cpu')
            with (root/'reconstruction_worker.log').open('w') as log:subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,cwd=CODE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            st.success('Reconstruction started. Refresh to follow the stages.')
    with st.expander('Engineering diagnostics'):
        st.json(job or state)
        for p in (root/'pipeline.log',root/'reconstruction_worker.log'):
            if p.exists():st.code(p.read_text(errors='replace')[-4000:])

def main():
    items=catalog(ROOT)
    st.sidebar.markdown('## ◈ AEROSPHERE');st.sidebar.caption('DEMO V1 / MISSION CONTROL')
    page=st.sidebar.radio('Workspace',PAGES,key='nav',label_visibility='collapsed');st.sidebar.divider()
    active=Path(st.session_state.get('active_root',ROOT))
    if not active.exists():active=ROOT
    options={str(m['root']):m['name'] for m in items}
    if str(active) not in options:options[str(active)]=active.name
    chosen=st.sidebar.selectbox('Active mission',list(options),index=list(options).index(str(active)),format_func=options.get)
    if chosen!=str(active):
        st.session_state['active_root']=chosen;st.session_state.pop('world_point',None);active=Path(chosen)
    if st.session_state.get('world_root')!=str(active):
        for key in ('world_point','world_point_picker','world_scope','world_event','world_source'):
            st.session_state.pop(key,None)
        st.session_state['world_root']=str(active)
    summary,selection,meta=data(active);mission=profile(active)
    st.sidebar.caption(mission.get('mode','RECONNAISSANCE'))
    st.sidebar.markdown('<span class="badge">● LOCAL PROCESSING</span>',unsafe_allow_html=True)
    st.sidebar.caption('No cloud processing. Cached models and geometry stay on this machine.')
    st.sidebar.divider();st.sidebar.markdown('**GITHUB**')
    repo=os.environ.get('AEROSPHERE_REPOSITORY_URL','https://github.com/chandana-ux/AeroSphere')
    if repo.startswith('https://github.com/'):st.sidebar.link_button('Project repository ↗',repo)
    else:st.sidebar.caption('Repository URL is not configured.')
    st.caption('AEROSPHERE / '+page+' / '+mission['name'])
    if page!='HOME':
        a,b=st.columns([1,8]);a.button('← Back',on_click=go,args=(PAGES[max(0,PAGES.index(page)-1)],))
        b.caption('NEXT · '+{'MISSION':'Analyze input','FLIGHT':'Inspect retained evidence, then reconstruct','3D WORLD':'Explore geometry and source observations','EVIDENCE':'Inspect support and gaps','TEMPORAL':'Add a genuine historical observation','INSIGHTS':'Review priorities and uncertainty','EXPORT':'Save the mission package'}[page])
    if page=='HOME':
        st.markdown('<div class="hero"><div class="eyebrow">SINGLE-PASS AERIAL RECONSTRUCTION</div><h1>From One Flight<br>to a Trusted 3D World.</h1><p>Explore what was reconstructed. Inspect the observations behind it. Understand what remains unknown.</p></div>',unsafe_allow_html=True)
        a,b,c=st.columns(3);a.button('Start new mission',type='primary',on_click=go,args=('MISSION',),width='stretch')
        def demo():
            preferred=read_json(ROOT/'demo_mission.json').get('root',str(ROOT))
            st.session_state['active_root']=preferred if Path(preferred).exists() else str(ROOT)
            go('3D WORLD')
        b.button('Open demo mission',on_click=demo,width='stretch',disabled=not (ROOT/'output/reconstruction/latest.json').exists())
        c.button('Mission library',on_click=lambda:st.session_state.update(show_library=True),width='stretch')
        if st.session_state.get('show_library'):
            mission_library(items)
            st.button('Back to overview',on_click=lambda:st.session_state.update(show_library=False))
            return
        if summary:
            cols=st.columns(4)
            for col,label,value in zip(cols,['Registered cameras','Sparse points','Dense points','Mean reprojection error'],[summary['registered_images'],f"{summary['sparse_points']:,}",f"{summary['dense_points']:,}" if 'dense_points' in summary else 'Unavailable',f"{summary['mean_point_reprojection_error_pixels']:.3f} px"]):col.metric(label,value)
            preview=Path(summary['run_directory'])/'dense_view.png'
            if preview.exists():st.image(str(preview),caption='Actual reconstructed cloud · open 3D World to inspect',width='stretch')
            st.caption('Photograph-based demonstration. Reconstruction metrics do not establish field accuracy or validate single-pass video performance.')
        mission_library(items)
    elif page=='MISSION':setup(active,selection,meta)
    elif page=='FLIGHT':flight(active,summary,selection,meta)
    elif not summary or not selection:
        st.info('No completed reconstruction yet. Analyze input in Mission, then run reconstruction from Flight.');st.button('Open Flight',on_click=go,args=('FLIGHT',))
    elif page=='3D WORLD':
        st.title('3D World');section=st.segmented_control('World view',['3D','GEO','MEASURE'],default='3D')
        if section=='3D':render_world(active,summary,selection,meta)
        elif section=='GEO':render_legacy('Geospatial',active,CODE)
        else:
            measurement=st.radio('Measurement tool',['Point distance / GPS','Surface / model-space'],horizontal=True)
            if measurement=='Point distance / GPS':render_legacy('Measurements',active,CODE)
            else:
                from measure import render_model_measure
                render_model_measure(summary)
    elif page=='EVIDENCE':
        choice=st.segmented_control('Evidence workspace',['LINEAGE & REPLAY','QUALITY & COVERAGE'],default='LINEAGE & REPLAY')
        if choice=='LINEAGE & REPLAY':render_lineage(active,summary,selection)
        else:render_extra('Quality & Coverage',active,CODE,meta,selection,summary)
    elif page=='TEMPORAL':render_temporal(active,summary)
    elif page=='INSIGHTS':
        mode=mission.get('mode','RECONNAISSANCE');st.title(mode.title());st.write(MODES[mode][0])
        priorities={'INFRASTRUCTURE':['Inspect structures in the mesh','Check supporting frames around inspection areas','Review road visibility manually'],
                    'DISASTER ASSESSMENT':['Compare genuine historical observations','Inspect access routes in source imagery','Record unobserved regions; damage/debris detection unavailable'],
                    'RECONNAISSANCE':['Inspect camera coverage and unseen regions','Review vehicle/person predictions where available','Check obstacles manually in source imagery'],
                    'URBAN MAPPING':['Inspect building/road context manually','Review GPS positions and model extent','Check coverage before mapping conclusions']}
        for item in priorities[mode]:st.write('• '+item)
        st.caption('Generic COCO detection does not identify buildings, roads, vegetation, damage or debris. Specialized aerial models are planned.')
        st.button('Review mission evidence',on_click=go,args=('TEMPORAL' if mode=='DISASTER ASSESSMENT' else 'EVIDENCE',))
        render_extra('Semantic AI',active,CODE,meta,selection,summary)
    elif page=='EXPORT':
        st.title('Export mission package');st.write('Full-resolution geometry, camera trajectory, GPS metadata, exact sparse tracks, quality reports and mission summary in one ZIP.')
        cameras=pd.read_csv(Path(summary['run_directory'])/'camera_trajectory.csv');geo,_=assess(meta,cameras)
        if st.button('Build mission package',type='primary'):
            with st.spinner('Packaging local artifacts…'):path=package_mission(active,summary,selection,geo)
            st.session_state['package']=(str(active),str(path));st.success('Mission package ready.')
        packaged=st.session_state.get('package')
        if packaged and packaged[0]==str(active) and Path(packaged[1]).exists():
            with open(packaged[1],'rb') as stream:st.download_button('Download mission ZIP',stream,file_name='aerosphere_mission.zip',mime='application/zip')
        st.caption('Native model coordinates. No validated metric surface accuracy. Source images remain local; filenames and recorded observations are included.')
        with st.expander('Individual artifacts and trust report'):render_legacy('Exports & Trust',active,CODE)
    if page not in ('HOME','EXPORT'):
        st.divider();st.button('Next · '+PAGES[PAGES.index(page)+1].title(),on_click=go,args=(PAGES[PAGES.index(page)+1],),key='next_page')

try:main()
except (OSError,ValueError,KeyError) as exc:
    st.error('A mission artifact could not be read. Open another mission or prepare input again.')
    with st.expander('Engineering diagnostics'):st.code(f'{type(exc).__name__}: {exc}')
