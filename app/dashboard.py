"""AeroSphere Demo V1: one local mission workflow, backed by real artifacts."""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

APP=Path(__file__).resolve().parent
sys.path.insert(0,str(APP))
from ingestion import save_uploads, frame_decisions
from mission import MODES,catalog,profile,read_json,save_profile,package_mission
from geo import assess
from legacy import render_legacy
from extras import render_extra
from lineage import render_lineage
from world import render_world
from temporal import render_temporal

ROOT=Path(os.environ.get('AEROSPHERE_DATA_ROOT',APP.parent))
CODE=APP.parent
PAGES=['HOME','MISSION','FLIGHT INTELLIGENCE','RECONSTRUCTION','3D WORLD','INTELLIGENCE','EXPORT']
st.set_page_config(page_title='AeroSphere | 3D Reconstruction & Spatial Intelligence',page_icon='◈',layout='wide',initial_sidebar_state='expanded',menu_items={'Get Help':None,'Report a bug':None,'About':'AeroSphere · From One Flight to a Trusted 3D World'})
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
                st.session_state['active_root']=str(path);st.session_state['nav']='3D WORLD' if (path/'output/reconstruction/latest.json').exists() else 'FLIGHT INTELLIGENCE'
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
    st.divider();st.markdown('#### FLIGHT SOURCE')
    source_type=st.radio('Input method',['UPLOAD DRONE VIDEO','UPLOAD IMAGE SEQUENCE','CONNECT DRONE'],horizontal=True)
    if source_type=='CONNECT DRONE':
        st.info('NO DRONE CONNECTED')
        st.caption('Recorded drone video is ready to use. Live RTSP, SDK and timestamped telemetry require a hardware adapter; none is installed.')
        return
    is_video=source_type=='UPLOAD DRONE VIDEO'
    uploaded=st.file_uploader('Drone video' if is_video else 'Image sequence',
        type=['mp4','mov','avi','mkv'] if is_video else ['jpg','jpeg','png','tif','tiff'],
        accept_multiple_files=not is_video,key='video_upload' if is_video else 'image_upload')
    with st.expander('Use a file or folder already on this computer'):
        source=st.text_input('Local video path' if is_video else 'Local image folder',key='source_path')
    with st.expander('Frame sampling',expanded=is_video):
        interval=st.number_input('Sample interval (seconds)',min_value=.1,max_value=60.,value=.5)
        cap=st.number_input('Maximum frames',min_value=3,max_value=300,value=80)
        st.caption('Samples are analyzed for sharpness, exposure, features and redundancy. A frame cap may shorten the processed flight.')
    if st.button('Analyze flight',type='primary'):
        try:
            if uploaded:
                path=save_uploads([uploaded] if is_video else uploaded,ROOT,video=is_video)
            else:
                path=Path(source.strip().strip('"'))
                if not source.strip() or not path.exists():raise ValueError('Upload a file or select an existing local source.')
                if is_video and not path.is_file():raise ValueError('Select a video file.')
                if not is_video and not path.is_dir():raise ValueError('Select an image folder.')
            job=ROOT/'results/jobs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
            job.mkdir(parents=True);save_profile(job,name,mode)
            (job/'job.json').write_text(json.dumps({'status':'queued','stage':'input','source':str(path)}))
            command=[sys.executable,str(CODE/'scripts/pipeline.py'),'--input',str(path.resolve()),'--job',str(job),'--interval',str(interval),'--max-frames',str(cap)]
            with (job/'worker.log').open('w') as log:subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,cwd=CODE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            st.session_state['active_root']=str(job)
            st.success('Flight analysis started.')
            st.button('View frame analysis',on_click=go,args=('FLIGHT INTELLIGENCE',))
        except (OSError,ValueError) as exc:st.error(str(exc))


def flight(root,summary,selection,meta):
    job=read_json(root/'job.json')
    if job:
        st.caption('PROCESSING STATUS · '+job.get('status','unknown').upper()+' · '+job.get('stage',''))
        if job.get('status')=='failed':st.error('Processing could not finish. Check input overlap, texture and file readability; diagnostics are available below.')
    st.button('Refresh status')
    if not selection:
        st.info('Analyze an image folder or video in Mission setup. This page will show retained frames and selection reasons.')
        st.button('Back to Mission',on_click=go,args=('MISSION',));return
    quality=frame_decisions(root,selection)
    video=read_json(root/'video_ingestion/video_metadata.json')
    if video:
        st.subheader('Input video')
        cols=st.columns(4)
        values=[f"{video.get('reported_duration_s',0):.1f} s" if video.get('reported_duration_s') else 'Unknown',f"{video.get('width')} × {video.get('height')}",video.get('fps') or 'Unknown',video.get('reported_frame_count') or 'Unknown']
        for col,label,value in zip(cols,['Duration','Resolution','FPS','Source frames'],values):col.metric(label,value)
        if video.get('warning'):st.warning(video['warning'])
        with st.expander('Play source video'):
            if Path(video['source']).exists():st.video(video['source'])
    st.subheader('Useful evidence from your flight')
    cols=st.columns(3)
    for col,label,value in zip(cols,['Frames analyzed','Frames selected','Frames rejected'],[len(quality),int(quality.selected.sum()),int((~quality.selected).sum())]):col.metric(label,value)
    timeline=quality.copy();timeline['position']=timeline.timestamp_s if video else range(len(timeline))
    fig=px.scatter(timeline,x='position',y='decision',color='decision',hover_data=['filename','reason'],color_discrete_map={'Selected':'#58d6c3','Rejected':'#ed976a'})
    fig.update_traces(marker=dict(size=11,symbol='square'))
    fig.update_layout(height=180,margin=dict(l=0,r=0,t=5,b=0),xaxis_title='Video time (seconds)' if video else 'Image order',yaxis_title=None,showlegend=False,paper_bgcolor='#0d141c',plot_bgcolor='#111c27')
    st.plotly_chart(fig,width='stretch',config={'displayModeBar':False})
    st.caption('Selected frames retain useful overlap. Warnings are shown; no target rejection percentage is imposed.')
    selected_rows=quality[quality.selected]
    if len(selected_rows):
        pages=max(1,(len(selected_rows)+11)//12)
        page=int(st.number_input('Frame gallery page',min_value=1,max_value=pages,value=1,key='gallery_'+str(root)))
        cols=st.columns(4)
        for i,(_,row) in enumerate(selected_rows.iloc[(page-1)*12:page*12].iterrows()):
            path=Path(selection['source'])/row.filename
            if path.exists():
                stamp=f'{row.timestamp_s:.2f}s · ' if pd.notna(row.timestamp_s) else ''
                cols[i%4].image(str(path),caption=stamp+row.filename,width='stretch')
    with st.expander('Inspect frame quality and selection reasons'):
        selected=st.selectbox('Source frame',quality.filename.tolist());row=quality[quality.filename==selected].iloc[0]
        a,b=st.columns([2,1]);source=Path(selection['source'])/selected
        if source.exists() and row.status=='ok':a.image(str(source),width='stretch')
        b.markdown('#### '+row.decision.upper());b.write(str(row.reason).replace('_',' '))
        fields=['blur_laplacian_variance','brightness_mean','contrast_std','dark_fraction','bright_fraction','orb_keypoints','information_score','warnings']
        b.dataframe(row.reindex(fields).rename('Value').astype(str).replace('nan','Unavailable'))
        st.dataframe(quality,hide_index=True,width='stretch')
    st.button('Continue to reconstruction',type='primary',on_click=go,args=('RECONSTRUCTION',))

def reconstruction(root,summary,selection):
    st.title('Reconstruct your flight')
    st.write('Selected frames → Camera estimation → Sparse structure → Dense cloud → Mesh')
    st.button('Refresh reconstruction status')
    if not selection:
        st.info('Analyze a video or image sequence first.');return
    st.caption(f"{selection['selected_images']} selected source frames are ready. Processing stays on this computer.")
    state=read_json(root/'reconstruction_job.json')
    if state.get('status')=='running':st.info('Reconstruction is running locally. Refresh to update. Sparse geometry is saved before dense processing.')
    elif summary:
        st.success('Available geometry is ready to inspect.');st.button('Open 3D World',type='primary',on_click=go,args=('3D WORLD',))
        if summary.get('dense_status') not in (None,'success'):st.warning('Dense processing did not complete; sparse output is available.')
        with st.expander('Technical details'):st.json(summary)
    else:
        if state.get('status')=='failed':st.error('Reconstruction failed. Try additional overlapping, textured images. Diagnostics show the failing stage.')
        dense=st.checkbox('Build dense cloud and mesh',True);cpu=st.checkbox('CPU feature extraction and matching',False)
        st.caption('Dense stereo requires CUDA. CPU mode applies to feature extraction and matching only.')
        if st.button('Start 3D reconstruction',type='primary',disabled=selection['selected_images']<3):
            (root/'reconstruction_job.json').write_text(json.dumps({'status':'running','stage':'queued'}))
            command=[sys.executable,str(CODE/'scripts/reconstruct_job.py'),'--project',str(root)]
            if dense:command.append('--dense')
            if cpu:command.append('--cpu')
            with (root/'reconstruction_worker.log').open('w') as log:subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,cwd=CODE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            st.success('Reconstruction started. Refresh to follow the stages.')
    with st.expander('Engineering diagnostics'):
        st.json(state)
        for p in (root/'pipeline.log',root/'reconstruction_worker.log'):
            if p.exists():st.code(p.read_text(errors='replace')[-4000:])

def main():
    items=catalog(ROOT)
    st.sidebar.markdown('## ◈ AEROSPHERE');st.sidebar.caption('FLIGHT OPERATIONS')
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
        b.caption('VIDEO → FRAME INTELLIGENCE → RECONSTRUCTION → 3D WORLD')
    if page=='HOME':
        st.markdown('<div class="hero"><div class="eyebrow">SINGLE-PASS AERIAL RECONSTRUCTION</div><h1>From One Flight<br>to a Trusted 3D World.</h1><p>One drone video. Useful source frames. A real 3D world you can inspect.</p></div>',unsafe_allow_html=True)
        a,b,c=st.columns(3);a.button('New mission',type='primary',on_click=go,args=('MISSION',),width='stretch')
        def demo():
            preferred=read_json(ROOT/'demo_mission.json').get('root',str(next((m['root'] for m in items if m['status']=='3D ready'),ROOT)))
            st.session_state['active_root']=preferred if Path(preferred).exists() else str(ROOT)
            go('3D WORLD')
        b.button('Open demo mission',on_click=demo,width='stretch',disabled=not any(m['status']=='3D ready' for m in items))
        c.button('Mission library',on_click=lambda:st.session_state.update(show_library=True),width='stretch')
        if st.session_state.get('show_library'):
            mission_library(items)
            st.button('Back to overview',on_click=lambda:st.session_state.update(show_library=False))
            return
        st.markdown('**DRONE VIDEO**　→　**SELECTED FRAMES**　→　**RECONSTRUCTION**　→　**SPATIAL INTELLIGENCE**')
    elif page=='MISSION':setup(active,selection,meta)
    elif page=='FLIGHT INTELLIGENCE':flight(active,summary,selection,meta)
    elif page=='RECONSTRUCTION':reconstruction(active,summary,selection)
    elif not summary or not selection:
        st.info('No completed reconstruction yet. Analyze input in Mission, then run reconstruction from Flight.');st.button('Open Flight',on_click=go,args=('FLIGHT INTELLIGENCE',))
    elif page=='3D WORLD':
        st.title('3D World');section=st.segmented_control('World view',['3D','GEO','MEASURE','HISTORICAL'],default='3D')
        if section=='3D':render_world(active,summary,selection,meta)
        elif section=='GEO':render_legacy('Geospatial',active,CODE)
        elif section=='HISTORICAL':
            st.caption('CURRENT FLIGHT ONLY · historical data remains separate')
            with st.expander('Add historical context'):render_temporal(active,summary)
        else:
            measurement=st.radio('Measurement tool',['Point distance / GPS','Surface / model-space'],horizontal=True)
            if measurement=='Point distance / GPS':render_legacy('Measurements',active,CODE)
            else:
                from measure import render_model_measure
                render_model_measure(summary)
    elif page=='INTELLIGENCE':
        choice=st.segmented_control('Intelligence workspace',['EVIDENCE','QUALITY & COVERAGE','MISSION INSIGHTS'],default='EVIDENCE')
        if choice=='EVIDENCE':
            render_lineage(active,summary,selection);return
        if choice=='QUALITY & COVERAGE':
            render_extra('Quality & Coverage',active,CODE,meta,selection,summary);return
        mode=mission.get('mode','RECONNAISSANCE');st.title(mode.title());st.write(MODES[mode][0])
        priorities={'INFRASTRUCTURE':['Inspect structures in the mesh','Check supporting frames around inspection areas','Review road visibility manually'],
                    'DISASTER ASSESSMENT':['Compare genuine historical observations','Inspect access routes in source imagery','Record unobserved regions; damage/debris detection unavailable'],
                    'RECONNAISSANCE':['Inspect camera coverage and unseen regions','Review vehicle/person predictions where available','Check obstacles manually in source imagery'],
                    'URBAN MAPPING':['Inspect building/road context manually','Review GPS positions and model extent','Check coverage before mapping conclusions']}
        for item in priorities[mode]:st.write('• '+item)
        st.caption('Generic COCO detection does not identify buildings, roads, vegetation, damage or debris. Specialized aerial models are planned.')
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
